"""
poll_coordination.py — Script chạy bởi cronjob Hermes.
Poll coordination state.json, tìm message/task mới chưa đọc cho pipo-hermes,
trả về stdout để Hermes xử lý + báo bố qua Telegram nếu cần.
"""
import json, os, sys, time

STATE = r"E:\AGT_Brain\data\coordination\state.json"
AGENT_ID = "pipo-hermes"
MARKER = r"E:\AGT_Brain\data\coordination\poll_marker.json"

def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[poll_coord] Lỗi đọc state: {e}", file=sys.stderr)
        return {}

def load_marker():
    try:
        with open(MARKER, encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"last_msg_ts": "", "last_task_ts": ""}

def save_marker(m):
    os.makedirs(os.path.dirname(MARKER), exist_ok=True)
    tmp = MARKER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f)
    os.replace(tmp, MARKER)

def main():
    state = load_state()
    marker = load_marker()

    # --- Tin nhắn chưa đọc gửi cho pipo-hermes ---
    msgs = state.get("messages", [])
    unread = [
        m for m in msgs
        if (m.get("to") is None or m.get("to") == AGENT_ID)
        and AGENT_ID not in m.get("read_by", [])
        and m.get("from") != AGENT_ID
        and m.get("created_at", "") > marker["last_msg_ts"]
    ]

    # --- Task pending chưa assign hoặc assign cho pipo-hermes ---
    tasks = state.get("task_queue", [])
    new_tasks = [
        t for t in tasks
        if t.get("status") == "pending"
        and (t.get("assigned_to") in (None, AGENT_ID))
        and t.get("created_at", "") > marker["last_task_ts"]
    ]

    if not unread and not new_tasks:
        # Không có gì mới — im lặng (cronjob no_agent stdout rỗng = không gửi)
        return

    # Có việc mới — in ra để Hermes (LLM) xử lý
    print("## Coordination có việc mới!\n")

    if unread:
        print(f"### {len(unread)} tin nhắn mới:\n")
        for m in unread[-5:]:  # max 5 tin gần nhất
            print(f"- [{m.get('created_at','')}] **{m.get('from','')}**: {m.get('content','')[:200]}")
        print()

    if new_tasks:
        print(f"### {len(new_tasks)} task mới:\n")
        for t in new_tasks:
            print(f"- [{t.get('priority','?')}] **{t.get('title','')}** (assigned={t.get('assigned_to','?')})")
            if t.get("description"):
                print(f"  {t['description'][:150]}")
        print()

    # Cập nhật marker
    all_ts = [m.get("created_at","") for m in msgs if m.get("created_at")]
    all_task_ts = [t.get("created_at","") for t in tasks if t.get("created_at")]
    marker["last_msg_ts"] = max(all_ts) if all_ts else marker["last_msg_ts"]
    marker["last_task_ts"] = max(all_task_ts) if all_task_ts else marker["last_task_ts"]
    save_marker(marker)

if __name__ == "__main__":
    main()
