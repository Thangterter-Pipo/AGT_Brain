#!/usr/bin/env python3
"""
dream_compression.py — Honcho-style memory dreaming and context compression.
Synthesizes raw memories into a structured summary and moves original records to memories_archive.
"""

import os
import sys
import json
import httpx
from datetime import datetime, timezone

def get_config_path():
    base_dir = os.environ.get("AGT_BRAIN_ROOT", "E:\\AGT_Brain")
    return os.path.join(base_dir, "data", "supabase_config.json")

def main():
    config_path = get_config_path()
    if not os.path.exists(config_path):
        print(f"❌ Supabase config not found at {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    supabase_url = config.get("supabase_url")
    supabase_key = config.get("supabase_key")
    if not supabase_url or not supabase_key:
        print("❌ Invalid Supabase config file")
        sys.exit(1)

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    print("💤 [Dreaming] Fetching recent memories for compression...")
    
    # Step 1: Fetch 100 recent memories
    fetch_url = f"{supabase_url}/rest/v1/memories?select=*&order=created_at.desc&limit=100"
    try:
        response = httpx.get(fetch_url, headers=headers, timeout=20.0)
        response.raise_for_status()
        recent_memories = response.json()
    except Exception as e:
        print(f"❌ Failed to fetch memories from Supabase: {e}")
        sys.exit(1)

    # Step 2: Filter memories that need compression
    memories_to_compress = []
    for m in recent_memories:
        importance = m.get("importance", 3)
        category = m.get("category", "general")
        metadata = m.get("metadata") or {}
        
        # Filter rules:
        # - importance < 5 (keep high importance memories intact)
        # - not summary, reflection, decision, incident categories
        # - metadata doesn't have "compressed" == True
        if (importance < 5 
                and category not in ("summary", "reflection", "decision", "incident")
                and not metadata.get("compressed")):
            memories_to_compress.append(m)

    count = len(memories_to_compress)
    if count < 5:
        print(f"💤 [Dreaming] Only found {count} raw memories. Postponing compression (minimum required: 5).")
        sys.exit(0)

    print(f"💤 [Dreaming] Found {count} raw memories to compress. Initiating synthesis...")

    # Step 3: Format raw memories for LLM
    text_to_compress = ""
    for m in memories_to_compress:
        text_to_compress += f"- ID: {m.get('id')}, Agent: {m.get('agent')}, Category: {m.get('category')}, Content: {m.get('content')}\n"

    system_prompt = (
        "You are Antigravity Dreaming Engine — a system process that runs while the AI agent sleeps to synthesize raw episodic memories into a structured semantic summary.\n\n"
        "Your goal is to compress the provided raw memories of recent user interactions, system context, preferences, and issues into a concise, high-value bullet-point list.\n"
        "Requirements:\n"
        "- Group information logically (e.g., User Context & Preferences, Architecture Decisions, Solved Incidents).\n"
        "- Keep the summary extremely concise, clear, and actionable (under 200 words total).\n"
        "- Strip away all conversational fluff, formatting details, and transient debug outputs.\n"
        "- Answer in Vietnamese as the primary user language is Vietnamese."
    )

    # LLM Synthesis: Try 9Router local gateway, then Grok VPS, then Grok localhost
    summary = None
    
    # 1. Try 9Router Local (Fast & Highly Stable)
    print("💤 [Dreaming] Attempting synthesis using 9Router Local...")
    try:
        ninerouter_url = "http://127.0.0.1:20128/v1/chat/completions"
        headers_9r = {
            "Content-Type": "application/json",
            "Authorization": "Bearer sk-f7d8d77f96db61e1-gv5z1w-64ae04b4"
        }
        payload_9r = {
            "model": "ag/gemini-3-flash",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Raw memories to compress:\n\n{text_to_compress}"}
            ],
            "stream": False
        }
        resp = httpx.post(ninerouter_url, json=payload_9r, headers=headers_9r, timeout=60.0)
        resp.raise_for_status()
        summary = resp.json()["choices"][0]["message"]["content"]
        print("✅ Synthesis completed via 9Router (ag/gemini-3-flash)")
    except Exception as e:
        print(f"⚠️ 9Router Local failed: {e}")

    # 2. Try Grok VPS (Fallback 1)
    if not summary:
        print("💤 [Dreaming] Attempting fallback to Grok VPS...")
        grok_base = os.environ.get("GROK_API_BASE", "http://194.163.174.78:8000")
        try:
            payload_grok = {
                "model": "grok-4.20-0309-non-reasoning",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Raw memories to compress:\n\n{text_to_compress}"}
                ],
                "stream": False
            }
            resp = httpx.post(f"{grok_base}/v1/chat/completions", json=payload_grok, headers={"Content-Type": "application/json"}, timeout=120.0)
            resp.raise_for_status()
            summary = resp.json()["choices"][0]["message"]["content"]
            print("✅ Synthesis completed via Grok VPS")
        except Exception as e:
            print(f"⚠️ Grok VPS failed: {e}")

    # 3. Try Grok Localhost (Fallback 2)
    if not summary:
        print("💤 [Dreaming] Attempting fallback to Grok Localhost...")
        try:
            payload_grok = {
                "model": "grok-4.20-0309-non-reasoning",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Raw memories to compress:\n\n{text_to_compress}"}
                ],
                "stream": False
            }
            resp = httpx.post("http://127.0.0.1:8000/v1/chat/completions", json=payload_grok, headers={"Content-Type": "application/json"}, timeout=60.0)
            resp.raise_for_status()
            summary = resp.json()["choices"][0]["message"]["content"]
            print("✅ Synthesis completed via Grok Localhost")
        except Exception as e:
            print(f"❌ All LLM backends failed. Last error: {e}")
            sys.exit(1)

    print(f"💤 [Dreaming] Summary generated:\n{summary}\n")

    # Step 4: Save summary memory to Supabase
    source_ids = [m.get("id") for m in memories_to_compress if m.get("id") is not None]
    summary_metadata = {
        "type": "dream_summary",
        "source_ids": source_ids,
        "compressed_at": datetime.now(timezone.utc).isoformat()
    }
    
    summary_payload = {
        "content": summary,
        "role": "antigravity",
        "agent": "antigravity",
        "category": "summary",
        "importance": 4,
        "confidence": 5,
        "metadata": summary_metadata
    }

    print("💤 [Dreaming] Saving summary memory to Supabase...")
    try:
        save_resp = httpx.post(f"{supabase_url}/rest/v1/memories", json=summary_payload, headers=headers, timeout=20.0)
        save_resp.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to save summary memory to Supabase: {e}")
        sys.exit(1)

    # Step 5: Archive raw memories
    print(f"💤 [Dreaming] Moving {count} raw memories to memories_archive...")
    try:
        # 5.1 Clean payloads (remove embedding field which may cause schema cache issues)
        for m in memories_to_compress:
            m.pop("embedding", None)

        # 5.2 Insert to archive
        archive_resp = httpx.post(f"{supabase_url}/rest/v1/memories_archive", json=memories_to_compress, headers=headers, timeout=20.0)
        if archive_resp.is_error:
            print(f"❌ Archive insert failed body: {archive_resp.text}")
        archive_resp.raise_for_status()
        
        # 5.3 Delete from memories
        id_list = ",".join(str(i) for i in source_ids)
        delete_url = f"{supabase_url}/rest/v1/memories?id=in.({id_list})"
        delete_resp = httpx.delete(delete_url, headers=headers, timeout=20.0)
        delete_resp.raise_for_status()
    except Exception as e:
        print(f"❌ Failed during archive process: {e}")
        sys.exit(1)

    print("✅ [Dreaming] Memory compression cycle completed successfully!")

if __name__ == "__main__":
    main()
