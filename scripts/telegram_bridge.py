#!/usr/bin/env python3
"""
telegram_bridge.py — Cầu nối 2 chiều Telegram <-> Antigravity IDE chat.

Chạy như một thread nền bên trong dashboard_server.py:
  - Long-poll Telegram getUpdates để nhận tin nhắn của bố.
  - Đẩy nội dung vào Antigravity IDE qua CDP (inject_prompt_via_cdp).
  - Theo dõi transcript IDE; khi Antigravity trả lời xong -> gửi ngược về Telegram.

Cấu hình: file telegram_bridge.json cạnh file này:
  {
    "enabled": true,
    "token": "123456789:ABC...",      # token từ @BotFather
    "allowed_chat_ids": [7873118569], # chỉ bố mới điều khiển được (để [] = cho mọi người)
    "poll_interval": 2.0,
    "reply_timeout": 240
  }
"""

import os
import json
import time
import threading
import urllib.parse
import urllib.request

_BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_BRIDGE_DIR, "telegram_bridge.json")

# These are injected from dashboard_server (set via init()).
_inject_prompt = None        # fn(ws_url, prompt) -> str
_discover_ws = None          # fn() -> ws_url | None
_get_history = None          # fn(limit) -> [ {role, content, images}, ... ]
_read_options = None         # fn() -> {has_options, options:[...]}  (optional)

_thread = None
_stop = threading.Event()


def init(inject_prompt, discover_ws, get_history, read_options=None):
    """Wire in the server's CDP helpers so we don't duplicate logic."""
    global _inject_prompt, _discover_ws, _get_history, _read_options
    _inject_prompt = inject_prompt
    _discover_ws = discover_ws
    _get_history = get_history
    _read_options = read_options


def _load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------- Telegram API helpers ----------------
def _tg_api(token, method, params=None, timeout=35):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    if params is not None:
        data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _send_message(token, chat_id, text):
    # Telegram caps a message at 4096 chars; chunk long replies.
    MAXLEN = 4000
    text = text or ""
    chunks = [text[i:i + MAXLEN] for i in range(0, len(text), MAXLEN)] or [""]
    for ch in chunks:
        sent = False
        # Try Markdown first, then plain text; each with 2 retries for flaky network.
        for parse_mode in ("Markdown", None):
            params = {"chat_id": chat_id, "text": ch, "disable_web_page_preview": "true"}
            if parse_mode:
                params["parse_mode"] = parse_mode
            for attempt in range(2):
                try:
                    r = _tg_api(token, "sendMessage", params, timeout=25)
                    if r.get("ok"):
                        sent = True
                        break
                    # API rejected (e.g. bad markdown) -> fall through to next parse_mode
                    print(f"[tg-bridge] sendMessage rejected ({parse_mode}): {r.get('description')}")
                    break
                except Exception as e:
                    print(f"[tg-bridge] sendMessage net error ({parse_mode}, try {attempt+1}): {e}")
                    time.sleep(1.5)
            if sent:
                break
        if not sent:
            print("[tg-bridge] ⚠️ FAILED to deliver a chunk after all retries.")


def _send_app_button(token, chat_id):
    """Send an inline button that opens the Mini App web interface."""
    cfg = _load_config()
    url = cfg.get("miniapp_url") or "https://ag.thangterter.online/scripts/miniapp.html"
    # Attach the API auth token so the Mini App can reach the protected API.
    api_token = os.environ.get("SYNAPZ_API_TOKEN", "").strip()
    if api_token and "token=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}token={api_token}"
    try:
        _tg_api(token, "sendMessage", {
            "chat_id": chat_id,
            "text": "🚀 Mở giao diện Antigravity:",
            "reply_markup": json.dumps({
                "inline_keyboard": [[{"text": "📱 Mở Antigravity App", "web_app": {"url": url}}]]
            }),
        }, timeout=20)
    except Exception as e:
        print(f"[tg-bridge] send_app_button failed: {e}")


def _last_assistant_text():
    """Most recent Antigravity prose message, or '' if none."""
    try:
        msgs = _get_history(limit=40) or []
    except Exception:
        return ""
    for m in reversed(msgs):
        if m.get("role") == "assistant":
            return (m.get("content") or "").strip()
    return ""


def _wait_for_reply(prev_reply, timeout, poll=2.0):
    """Block until a NEW assistant message appears (different from prev), or timeout."""
    deadline = time.time() + timeout
    last_seen = prev_reply
    stable_since = None
    while time.time() < deadline and not _stop.is_set():
        time.sleep(poll)
        cur = _last_assistant_text()
        if cur and cur != prev_reply:
            # Wait for the text to stop growing (Antigravity streams) before sending.
            if cur == last_seen:
                if stable_since and (time.time() - stable_since) >= 3.0:
                    return cur
            else:
                last_seen = cur
                stable_since = time.time()
    # Timed out: return whatever differs, if anything.
    cur = _last_assistant_text()
    return cur if cur and cur != prev_reply else None


def _handle_message(cfg, token, chat_id, text):
    allowed = cfg.get("allowed_chat_ids") or []
    if allowed and chat_id not in allowed:
        _send_message(token, chat_id, "⛔ Chat này không được phép điều khiển Antigravity.")
        return

    text = (text or "").strip()
    if not text:
        return

    # Simple commands
    low = text.lower()
    if low in ("/start", "/help"):
        _send_message(token, chat_id,
                      "🔵 *Antigravity Bridge*\n"
                      "Nhắn bất kỳ nội dung nào, con sẽ đẩy vào Antigravity IDE và "
                      "gửi lại câu trả lời.\n\n"
                      "Lệnh:\n"
                      "/app — mở giao diện app\n"
                      "/launch — khởi động Antigravity IDE\n"
                      "/status — kiểm tra IDE\n"
                      "/last — xem câu trả lời gần nhất")
        _send_app_button(token, chat_id)
        return
    if low == "/app":
        _send_app_button(token, chat_id)
        return
    if low == "/launch":
        _send_message(token, chat_id, "⏳ Đang khởi động Antigravity IDE… (~30s)")
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8899/api/ide/launch",
                data=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=90) as resp:
                d = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            d = {"ok": False, "reason": str(e)}
        if d.get("ok"):
            _send_message(token, chat_id, "✅ Antigravity IDE đã mở (CDP 9333). Bố nhắn tiếp được rồi.")
        else:
            _send_message(token, chat_id, f"❌ Không mở được IDE: {d.get('reason','?')}")
        return
    if low == "/status":
        ws = _discover_ws()
        _send_message(token, chat_id,
                      "✅ IDE online (CDP 9333)" if ws else "❌ Không thấy IDE (CDP 9333). Gõ /launch để mở.")
        return
    if low == "/last":
        _send_message(token, chat_id, _last_assistant_text() or "(chưa có câu trả lời)")
        return

    ws = _discover_ws()
    if not ws:
        _send_message(token, chat_id, "❌ Antigravity IDE không phản hồi (CDP 9333). Gõ /launch để con mở IDE.")
        return

    prev = _last_assistant_text()
    print(f"[tg-bridge] 📨 msg from {chat_id}: {text[:60]!r} | prev_reply_len={len(prev)}")
    _send_message(token, chat_id, "⏳ Đã gửi cho Antigravity, đang chờ trả lời...")

    res = _inject_prompt(ws, text)
    print(f"[tg-bridge] inject result: {res!r}")
    if res and res != "injected":
        _send_message(token, chat_id, f"⚠️ Không tìm thấy ô chat trong IDE (CDP trả: {res}).")
        return

    reply = _wait_for_reply(prev, timeout=cfg.get("reply_timeout", 240),
                            poll=cfg.get("poll_interval", 2.0))
    if reply:
        print(f"[tg-bridge] ✅ got reply ({len(reply)} chars), sending back.")
        _send_message(token, chat_id, reply)
    else:
        print("[tg-bridge] ⌛ no new reply within timeout.")
        _send_message(token, chat_id,
                      "⌛ Antigravity chưa trả lời xong (hết thời gian chờ). "
                      "Bố gõ /last lát nữa để xem kết quả.")


def _run():
    cfg = _load_config()
    token = (cfg.get("token") or "").strip()
    if not cfg.get("enabled") or not token:
        print("[tg-bridge] disabled (no token / enabled=false). Skipping.")
        return

    # Verify token
    try:
        me = _tg_api(token, "getMe", timeout=15)
        if not me.get("ok"):
            print(f"[tg-bridge] invalid token: {me}")
            return
        bot_name = me["result"].get("username")
        print(f"[tg-bridge] 🤖 connected as @{bot_name}")
    except Exception as e:
        print(f"[tg-bridge] getMe failed: {e}")
        return

    offset = None
    # Drop backlog so we don't replay old messages on restart.
    try:
        upd = _tg_api(token, "getUpdates", {"offset": -1, "timeout": 0}, timeout=15)
        if upd.get("ok") and upd["result"]:
            offset = upd["result"][-1]["update_id"] + 1
    except Exception:
        pass

    while not _stop.is_set():
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset
            upd = _tg_api(token, "getUpdates", params, timeout=40)
            if not upd.get("ok"):
                time.sleep(3)
                continue
            for item in upd["result"]:
                offset = item["update_id"] + 1
                msg = item.get("message") or item.get("edited_message")
                if not msg:
                    continue
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")
                if text:
                    try:
                        _handle_message(cfg, token, chat_id, text)
                    except Exception as e:
                        print(f"[tg-bridge] handle error: {e}")
                        try:
                            _send_message(token, chat_id, f"❌ Lỗi bridge: {e}")
                        except Exception:
                            pass
        except Exception as e:
            print(f"[tg-bridge] poll error: {e}")
            time.sleep(3)


def start():
    """Spawn the bridge thread (no-op if config disabled)."""
    global _thread
    cfg = _load_config()
    if not cfg.get("enabled") or not (cfg.get("token") or "").strip():
        print("[tg-bridge] not started (telegram_bridge.json missing/disabled).")
        return False
    _stop.clear()
    _thread = threading.Thread(target=_run, name="telegram-bridge", daemon=True)
    _thread.start()
    return True


def stop():
    _stop.set()
