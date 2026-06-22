#!/usr/bin/env python3
"""
synapz_memory.py — Unified SynapzCore Memory Engine.
Integrates:
  1. Honcho-style Dreaming & Context Compression
  2. SQLite Knowledge Graph & Spreading Activation Recall
  3. Mem0-style LLM-assisted Conflict Resolution & Entity Merging
  4. Unified CLI command interface
"""

import os
import sys
import json
import sqlite3
import httpx
from datetime import datetime, timezone
from pathlib import Path

# Paths configuration
BASE_DIR = os.environ.get("SYNAPZ_ROOT", "E:\\AGT_Brain")
DB_PATH = os.path.join(BASE_DIR, "memory", "graph_memory.db")
DECISIONS_DIR = os.path.join(BASE_DIR, "memory", "decisions")
INCIDENTS_DIR = os.path.join(BASE_DIR, "memory", "incidents")

# 9Router configuration
NINEROUTER_URL = "http://127.0.0.1:20128/v1/chat/completions"
NINEROUTER_EMB_URL = "http://127.0.0.1:20128/v1/embeddings"
NINEROUTER_KEY = "sk-f7d8d77f96db61e1-gv5z1w-64ae04b4"
DEFAULT_MODEL = "ag/gemini-3-flash"

# =====================================================================
# Database & Core Helpers
# =====================================================================

def get_config():
    config_path = os.path.join(BASE_DIR, "data", "supabase_config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Supabase config not found at {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_supabase_headers(config):
    return {
        "apikey": config["supabase_key"],
        "Authorization": f"Bearer {config['supabase_key']}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# =====================================================================
# LLM & Embedding Helpers
# =====================================================================

async def ask_llm(system_prompt: str, user_prompt: str, json_format=False) -> str:
    """Helper to query 9Router local LLM gateway."""
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "stream": False
    }
    if json_format:
        payload["response_format"] = {"type": "json_object"}
        
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            NINEROUTER_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {NINEROUTER_KEY}"
            },
            timeout=90.0
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        
        # Clean potential markdown fences
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return content

async def generate_embedding(text: str) -> list:
    """Generate a 384-dimensional vector embedding via 9Router."""
    payload = {
        "model": "text-embedding-3-small",
        "input": text,
        "dimensions": 384
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            NINEROUTER_EMB_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {NINEROUTER_KEY}"
            },
            timeout=30.0
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

# =====================================================================
# Phase 3: Mem0-style Conflict Resolution & Saving
# =====================================================================

async def resolve_conflict_and_save(content: str, agent: str, category: str, importance=3, confidence=5):
    """
    Saves a memory after performing semantic search and LLM-assisted conflict resolution.
    If a conflict is detected, updates or archives the outdated memory.
    """
    config = get_config()
    headers = get_supabase_headers(config)
    supabase_url = config["supabase_url"]
    
    print(f"🧠 [ConflictResolver] Generating embedding for new memory...")
    try:
        new_emb = await generate_embedding(content)
    except Exception as e:
        print(f"⚠️ Failed to generate embedding: {e}. Saving directly without conflict check.")
        # Fallback save direct
        await save_direct(supabase_url, headers, content, agent, category, importance, confidence)
        return

    # Step 1: Semantic search on Supabase (match_memories RPC)
    print("🧠 [ConflictResolver] Searching for semantically similar memories in cloud...")
    rpc_payload = {
        "query_embedding": str(new_emb),
        "match_threshold": 0.6,
        "match_count": 3
    }
    similar_memories = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{supabase_url}/rest/v1/rpc/match_memories", json=rpc_payload, headers=headers, timeout=20.0)
            resp.raise_for_status()
            similar_memories = resp.json()
    except Exception as e:
        print(f"⚠️ Semantic search failed: {e}. Fallback to direct save.")
        await save_direct(supabase_url, headers, content, agent, category, importance, confidence)
        return

    if not similar_memories:
        print("🧠 [ConflictResolver] No similar memories found. Saving as new record.")
        await save_direct(supabase_url, headers, content, agent, category, importance, confidence, new_emb)
        return

    # Step 2: Query LLM to detect conflicts
    print(f"🧠 [ConflictResolver] Found {len(similar_memories)} similar memories. Checking for conflicts...")
    
    context_list = []
    for m in similar_memories:
        context_list.append({
            "id": m.get("id"),
            "agent": m.get("agent"),
            "category": m.get("category"),
            "content": m.get("content")
        })

    system_prompt = (
        "You are SynapzCore Memory Conflict Resolver. Your job is to compare a new memory entry with existing similar memories "
        "and determine if the new entry contradicts, overrides, or obsoletes any old entries (e.g. key updates, changed preferences, updated decisions).\n\n"
        "Analyze the inputs and choose one action:\n"
        "- 'keep': No conflict detected. The new memory is complementary. Keep all old entries and insert the new one.\n"
        "- 'update': The new memory updates or refines an old entry. Specify which old entry ID to update and provide the merged content.\n"
        "- 'delete': The new memory makes an old entry completely obsolete. Specify which old entry ID(s) to delete.\n"
        "Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        "  \"has_conflict\": true|false,\n"
        "  \"conflicting_id\": null|number,\n"
        "  \"action\": \"keep|update|delete\",\n"
        "  \"merged_content\": null|string\n"
        "}"
    )

    user_prompt = f"New Memory: {content}\n\nExisting Similar Memories:\n{json.dumps(context_list, indent=2)}"
    
    try:
        res_text = await ask_llm(system_prompt, user_prompt, json_format=True)
        decision = json.loads(res_text)
    except Exception as e:
        print(f"⚠️ Conflict checking LLM request failed: {e}. Saving as new.")
        await save_direct(supabase_url, headers, content, agent, category, importance, confidence, new_emb)
        return

    has_conflict = decision.get("has_conflict", False)
    action = decision.get("action", "keep")
    conflict_id = decision.get("conflicting_id")
    merged_content = decision.get("merged_content")

    if has_conflict and conflict_id:
        print(f"⚠️ [ConflictResolver] Conflict detected with ID {conflict_id}. Action: {action.upper()}")
        
        # Find the target memory object
        target_memory = next((m for m in similar_memories if m.get("id") == conflict_id), None)
        
        if action == "delete" and target_memory:
            # Move to archive and delete
            await archive_and_delete(supabase_url, headers, target_memory)
            # Save the new memory
            await save_direct(supabase_url, headers, content, agent, category, importance, confidence, new_emb)
            
        elif action == "update" and target_memory and merged_content:
            # Update the old record content & regenerate embedding
            print(f"🔄 [ConflictResolver] Updating memory {conflict_id} with merged content...")
            merged_emb = await generate_embedding(merged_content)
            update_payload = {
                "content": merged_content,
                "embedding": str(merged_emb),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            async with httpx.AsyncClient() as client:
                resp = await client.patch(f"{supabase_url}/rest/v1/memories?id=eq.{conflict_id}", json=update_payload, headers=headers, timeout=20.0)
                resp.raise_for_status()
            print(f"✅ [ConflictResolver] Memory {conflict_id} updated successfully.")
            
        else:
            # Fallback to keep
            await save_direct(supabase_url, headers, content, agent, category, importance, confidence, new_emb)
    else:
        print("✅ [ConflictResolver] No conflict. Saving memory.")
        await save_direct(supabase_url, headers, content, agent, category, importance, confidence, new_emb)

async def save_direct(supabase_url, headers, content, agent, category, importance, confidence, embedding=None):
    payload = {
        "content": content,
        "role": "antigravity",
        "agent": agent,
        "category": category,
        "importance": importance,
        "confidence": confidence,
        "metadata": {"source": "agt_brain_memory_engine"}
    }
    if embedding:
        payload["embedding"] = str(embedding)
        
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{supabase_url}/rest/v1/memories", json=payload, headers=headers, timeout=20.0)
        resp.raise_for_status()
    print("✅ Memory saved to Supabase cloud.")

async def archive_and_delete(supabase_url, headers, memory):
    # Pop embedding to avoid PostgREST schema cache mismatch error
    memory_copy = memory.copy()
    memory_copy.pop("embedding", None)
    
    print(f"📦 [ConflictResolver] Archiving memory ID {memory.get('id')}...")
    async with httpx.AsyncClient() as client:
        # Insert to memories_archive
        arc_resp = await client.post(f"{supabase_url}/rest/v1/memories_archive", json=memory_copy, headers=headers, timeout=20.0)
        arc_resp.raise_for_status()
        
        # Delete from memories
        del_resp = await client.delete(f"{supabase_url}/rest/v1/memories?id=eq.{memory.get('id')}", headers=headers, timeout=20.0)
        del_resp.raise_for_status()
    print(f"🗑️ [ConflictResolver] Deleted memory ID {memory.get('id')} from active memories.")

# =====================================================================
# Phase 1: Honcho-style Dreaming (Memory Compression)
# =====================================================================

async def run_dreaming_compression():
    """
    Scans raw cloud memories, compresses them into semantic summaries, 
    and moves archived records to memories_archive.
    """
    config = get_config()
    headers = get_supabase_headers(config)
    supabase_url = config["supabase_url"]

    print("💤 [Dreaming] Fetching recent memories for compression...")
    
    # Fetch 100 recent memories
    fetch_url = f"{supabase_url}/rest/v1/memories?select=*&order=created_at.desc&limit=100"
    async with httpx.AsyncClient() as client:
        response = await client.get(fetch_url, headers=headers, timeout=20.0)
        response.raise_for_status()
        recent_memories = response.json()

    # Filter memories that need compression
    memories_to_compress = []
    for m in recent_memories:
        importance = m.get("importance", 3)
        category = m.get("category", "general")
        metadata = m.get("metadata") or {}
        
        if (importance < 5 
                and category not in ("summary", "reflection", "decision", "incident")
                and not metadata.get("compressed")):
            memories_to_compress.append(m)

    count = len(memories_to_compress)
    if count < 5:
        print(f"💤 [Dreaming] Only found {count} raw memories. Postponing compression (minimum required: 5).")
        return

    print(f"💤 [Dreaming] Found {count} raw memories to compress. Initiating synthesis...")

    # Format raw memories for LLM
    text_to_compress = ""
    for m in memories_to_compress:
        text_to_compress += f"- ID: {m.get('id')}, Agent: {m.get('agent')}, Category: {m.get('category')}, Content: {m.get('content')}\n"

    system_prompt = (
        "You are SynapzCore Dreaming Engine — a system process that runs while the AI agent sleeps to synthesize raw episodic memories into a structured semantic summary.\n\n"
        "Your goal is to compress the provided raw memories of recent user interactions, system context, preferences, and issues into a concise, high-value bullet-point list.\n"
        "Requirements:\n"
        "- Group information logically (e.g., User Context & Preferences, Architecture Decisions, Solved Incidents).\n"
        "- Keep the summary extremely concise, clear, and actionable (under 200 words total).\n"
        "- Strip away all conversational fluff, formatting details, and transient debug outputs.\n"
        "- Answer in Vietnamese as the primary user language is Vietnamese."
    )

    print("💤 [Dreaming] Generating compression summary from 9Router...")
    try:
        summary = await ask_llm(system_prompt, f"Raw memories to compress:\n\n{text_to_compress}")
    except Exception as e:
        print(f"❌ LLM request failed: {e}")
        return

    print(f"💤 [Dreaming] Summary generated:\n{summary}\n")

    # Save summary memory to Supabase
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
    async with httpx.AsyncClient() as client:
        save_resp = await client.post(f"{supabase_url}/rest/v1/memories", json=summary_payload, headers=headers, timeout=20.0)
        save_resp.raise_for_status()

    # Archive raw memories
    print(f"💤 [Dreaming] Moving {count} raw memories to memories_archive...")
    
    # Remove embedding field to avoid PostgREST schema cache mismatch
    for m in memories_to_compress:
        m.pop("embedding", None)
        
    try:
        async with httpx.AsyncClient() as client:
            # 1. Insert to archive
            archive_resp = await client.post(f"{supabase_url}/rest/v1/memories_archive", json=memories_to_compress, headers=headers, timeout=20.0)
            archive_resp.raise_for_status()
            
            # 2. Delete from memories
            id_list = ",".join(str(i) for i in source_ids)
            delete_url = f"{supabase_url}/rest/v1/memories?id=in.({id_list})"
            delete_resp = await client.delete(delete_url, headers=headers, timeout=20.0)
            delete_resp.raise_for_status()
    except Exception as e:
        print(f"❌ Failed during archive process: {e}")
        return

    print("✅ [Dreaming] Memory compression cycle completed successfully!")

# =====================================================================
# Phase 2: Graph-based Associative Recall (Spreading Activation)
# =====================================================================

def init_db():
    conn = get_db_connection()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (source, target, type),
                FOREIGN KEY (source) REFERENCES nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (target) REFERENCES nodes(id) ON DELETE CASCADE
            )
        """)
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(content, content_id UNINDEXED)")
        except sqlite3.OperationalError:
            pass
    conn.close()

def add_node(node_id, content, node_type, created_at=None, metadata=None):
    conn = get_db_connection()
    if not created_at:
        created_at = datetime.now(timezone.utc).isoformat()
    meta_str = json.dumps(metadata or {})
    with conn:
        conn.execute("""
            INSERT INTO nodes (id, content, type, created_at, metadata)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content=excluded.content,
                type=excluded.type,
                metadata=excluded.metadata
        """, (node_id, content, node_type, created_at, meta_str))
        try:
            conn.execute("DELETE FROM nodes_fts WHERE content_id = ?", (node_id,))
            conn.execute("INSERT INTO nodes_fts (content, content_id) VALUES (?, ?)", (content, node_id))
        except sqlite3.OperationalError:
            pass
    conn.close()

def add_link(source, target, weight=1.0, link_type="related_to"):
    if source == target:
        return
    conn = get_db_connection()
    created_at = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute("""
            INSERT INTO edges (source, target, weight, type, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, target, type) DO UPDATE SET
                weight=excluded.weight
        """, (source, target, weight, link_type, created_at))
    conn.close()

def query_initial_nodes(query_text, limit=5):
    conn = get_db_connection()
    results = []
    try:
        rows = conn.execute("""
            SELECT content_id, rank 
            FROM nodes_fts 
            WHERE nodes_fts MATCH ? 
            ORDER BY rank 
            LIMIT ?
        """, (query_text, limit)).fetchall()
        for r in rows:
            raw_rank = r["rank"]
            score = max(0.1, min(1.0, 1.0 / (1.0 + abs(raw_rank))))
            results.append((r["content_id"], score))
    except sqlite3.OperationalError:
        rows = conn.execute("SELECT id, content FROM nodes WHERE content LIKE ? LIMIT ?", (f"%{query_text}%", limit)).fetchall()
        for r in rows:
            results.append((r["id"], 0.8))
    conn.close()
    return results

def spreading_activation(query_text, decay=0.5, threshold=0.1, max_steps=2):
    initial_nodes = query_initial_nodes(query_text)
    if not initial_nodes:
        return []

    activations = {node_id: score for node_id, score in initial_nodes}
    conn = get_db_connection()
    
    for step in range(max_steps):
        next_activations = {}
        for node_id, energy in list(activations.items()):
            if energy < threshold:
                continue
                
            # Outgoing links
            out_rows = conn.execute("SELECT target, weight, type FROM edges WHERE source = ?", (node_id,)).fetchall()
            for r in out_rows:
                target_id = r["target"]
                edge_weight = r["weight"]
                edge_multiplier = 1.2 if r["type"] in ("cause_of", "resolved_by") else 1.0
                transfer = energy * edge_weight * decay * edge_multiplier
                next_activations[target_id] = next_activations.get(target_id, 0.0) + transfer
                
            # Incoming links (bi-directional association)
            in_rows = conn.execute("SELECT source, weight, type FROM edges WHERE target = ?", (node_id,)).fetchall()
            for r in in_rows:
                source_id = r["source"]
                edge_weight = r["weight"]
                transfer = energy * edge_weight * decay * 0.8 
                next_activations[source_id] = next_activations.get(source_id, 0.0) + transfer

        for nid, energy in next_activations.items():
            activations[nid] = max(activations.get(nid, 0.0), energy)
            
        activations = {nid: eng for nid, eng in activations.items() if eng >= threshold}

    retrieved = []
    for nid, energy in sorted(activations.items(), key=lambda x: x[1], reverse=True):
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (nid,)).fetchone()
        if row:
            retrieved.append({
                "id": row["id"],
                "content": row["content"],
                "type": row["type"],
                "created_at": row["created_at"],
                "metadata": json.loads(row["metadata"]),
                "activation_energy": round(energy, 3)
            })
    conn.close()
    return retrieved

def populate_from_local_files():
    print("📂 Scanning local Decisions & Incidents directories...")
    decisions_count = 0
    if os.path.exists(DECISIONS_DIR):
        for fpath in Path(DECISIONS_DIR).glob("*.json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                node_id = fpath.stem
                content = f"Decision: {data.get('decision')}\nContext: {data.get('context')}\nActions: {', '.join(data.get('actions_taken', []))}"
                add_node(node_id, content, "decision", data.get("timestamp"), data)
                decisions_count += 1
            except Exception as e:
                print(f"⚠️ Error loading decision {fpath.name}: {e}")
                
    incidents_count = 0
    if os.path.exists(INCIDENTS_DIR):
        for fpath in Path(INCIDENTS_DIR).glob("*.md"):
            try:
                content = fpath.read_text(encoding="utf-8")
                node_id = fpath.stem
                add_node(node_id, content, "incident", metadata={"filename": fpath.name})
                incidents_count += 1
            except Exception as e:
                print(f"⚠️ Error loading incident {fpath.name}: {e}")
    print(f"📂 Loaded {decisions_count} decisions and {incidents_count} incidents into graph nodes.")

async def build_causality_links_with_llm():
    conn = get_db_connection()
    nodes = conn.execute("SELECT id, type, content FROM nodes WHERE type IN ('decision', 'incident')").fetchall()
    conn.close()
    
    if len(nodes) < 2:
        return
        
    print(f"🤖 Analyzing causality between {len(nodes)} nodes using LLM...")
    node_list = [{"id": n["id"], "type": n["type"], "summary": n["content"][:200]} for n in nodes]
    
    system_prompt = (
        "You are SynapzCore Causality Engine. Analyze the provided list of AI Agent decisions and incidents and detect logical relationships.\n\n"
        "Detect:\n"
        "1. 'cause_of': A decision/incident that directly triggered an incident.\n"
        "2. 'resolved_by': An incident resolved by a subsequent decision.\n"
        "3. 'related_to': Two nodes that are highly relevant to each other.\n\n"
        "Respond ONLY with a valid JSON array of objects with the exact schema:\n"
        "[\n"
        "  { \"source\": \"node_id_1\", \"target\": \"node_id_2\", \"type\": \"cause_of|resolved_by|related_to\", \"weight\": 0.1-1.0 }\n"
        "]\n"
        "Respond with raw JSON only, no explanations."
    )
    
    try:
        res_content = await ask_llm(system_prompt, f"Nodes list:\n\n{json.dumps(node_list)}")
        links = json.loads(res_content)
        if isinstance(links, dict) and "links" in links:
            links = links["links"]
        elif isinstance(links, dict):
            links = list(links.values())[0]
            
        links_count = 0
        if isinstance(links, list):
            for link in links:
                source = link.get("source")
                target = link.get("target")
                ltype = link.get("type")
                weight = link.get("weight", 1.0)
                if source and target and ltype:
                    add_link(source, target, weight, ltype)
                    links_count += 1
            print(f"✅ Generated {links_count} causality links in database.")
    except Exception as e:
        print(f"❌ LLM Causality Linker failed: {e}")

# =====================================================================
# CLI Entrypoint
# =====================================================================

async def main_async():
    import argparse
    parser = argparse.ArgumentParser(description="🧠 SynapzCore Unified Memory Engine CLI")
    
    parser.add_argument("--save", type=str, help="Save a new memory with conflict resolution check")
    parser.add_argument("--agent", type=str, default="antigravity", help="Agent associated with saved memory")
    parser.add_argument("--category", type=str, default="general", help="Category of saved memory")
    parser.add_argument("--importance", type=int, default=3, help="Importance tier (1-10)")
    
    parser.add_argument("--dream", action="store_true", help="Run Dreaming context compression cycle")
    parser.add_argument("--sync-graph", action="store_true", help="Sync local Decisions/Incidents into SQLite Graph and run Causality Linker")
    parser.add_argument("--query", type=str, help="Perform Spreading Activation search on graph")
    
    args = parser.parse_args()
    
    if args.save:
        print(f"🧠 Initiating save for: '{args.save[:50]}...'")
        await resolve_conflict_and_save(args.save, args.agent, args.category, args.importance)
        
    elif args.dream:
        await run_dreaming_compression()
        
    elif args.sync_graph:
        init_db()
        populate_from_local_files()
        await build_causality_links_with_llm()
        
    elif args.query:
        init_db()
        results = spreading_activation(args.query)
        print(f"\n🧠 Spreading Activation Results for: '{args.query}'")
        for i, r in enumerate(results, 1):
            print(f"  #{i} [{r['type'].upper()} - Energy: {r['activation_energy']}] {r['id']}")
            print(f"     Snippet: {r['content'].replace('\n', ' ')[:120]}...")
            
    else:
        parser.print_help()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main_async())
