#!/usr/bin/env python3
"""
graph_memory.py — Graph-based Memory & Spreading Activation Engine.
Builds a local SQLite knowledge graph of Decisions & Incidents and retrieves them via associative recall.
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

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables for nodes, edges, and FTS search."""
    conn = get_db_connection()
    with conn:
        # 1. Nodes table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT NOT NULL, -- 'decision', 'incident', 'preference', 'file', 'concept'
                created_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)
        # 2. Edges table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                type TEXT NOT NULL, -- 'cause_of', 'depends_on', 'resolved_by', 'related_to'
                created_at TEXT NOT NULL,
                PRIMARY KEY (source, target, type),
                FOREIGN KEY (source) REFERENCES nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (target) REFERENCES nodes(id) ON DELETE CASCADE
            )
        """)
        
        # 3. FTS5 Virtual table for text search
        # We catch operational error in case FTS5 isn't enabled (unlikely on modern Python)
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                    content,
                    content_id UNINDEXED
                )
            """)
        except sqlite3.OperationalError as e:
            print(f"⚠️ FTS5 not supported: {e}. Falling back to standard LIKE queries for search.")
            
    conn.close()
    print("✅ Graph database initialized successfully.")

def add_node(node_id, content, node_type, created_at=None, metadata=None):
    """Insert or update a memory node."""
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
        
        # Update FTS
        try:
            # Delete old FTS entry if exists
            conn.execute("DELETE FROM nodes_fts WHERE content_id = ?", (node_id,))
            # Insert new
            conn.execute("INSERT INTO nodes_fts (content, content_id) VALUES (?, ?)", (content, node_id))
        except sqlite3.OperationalError:
            pass
            
    conn.close()

def add_link(source, target, weight=1.0, link_type="related_to"):
    """Insert or update a directed edge between nodes."""
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
    """Find initial nodes using FTS5 search (fallback to LIKE if FTS fails)."""
    conn = get_db_connection()
    results = []
    
    # Try FTS5 search first
    try:
        rows = conn.execute("""
            SELECT content_id, rank 
            FROM nodes_fts 
            WHERE nodes_fts MATCH ? 
            ORDER BY rank 
            LIMIT ?
        """, (query_text, limit)).fetchall()
        
        # Normalize FTS ranks (smaller rank is better in FTS5)
        # Convert to score between 0.1 and 1.0
        for r in rows:
            raw_rank = r["rank"]
            score = max(0.1, min(1.0, 1.0 / (1.0 + abs(raw_rank))))
            results.append((r["content_id"], score))
            
    except sqlite3.OperationalError:
        # Fallback to standard LIKE search
        rows = conn.execute("""
            SELECT id, content FROM nodes 
            WHERE content LIKE ? 
            LIMIT ?
        """, (f"%{query_text}%", limit)).fetchall()
        for r in rows:
            results.append((r["id"], 0.8)) # Default high activation score for LIKE match
            
    conn.close()
    return results

def spreading_activation(query_text, decay=0.5, threshold=0.1, max_steps=2):
    """
    Spreading Activation retrieval algorithm.
    Spreads energy from initial matched nodes along graph edges.
    """
    initial_nodes = query_initial_nodes(query_text)
    if not initial_nodes:
        print(f"🔍 No direct matches found for query: '{query_text}'")
        return []

    # Map node_id -> current energy level
    activations = {node_id: score for node_id, score in initial_nodes}
    
    conn = get_db_connection()
    
    for step in range(max_steps):
        next_activations = {}
        # Iterate over currently active nodes
        for node_id, energy in list(activations.items()):
            if energy < threshold:
                continue
                
            # Find neighbors (directed out AND in edges for associative search)
            # Fetch target neighbors (outgoing)
            out_rows = conn.execute("SELECT target, weight, type FROM edges WHERE source = ?", (node_id,)).fetchall()
            for r in out_rows:
                target_id = r["target"]
                edge_weight = r["weight"]
                # Causal edges ('cause_of', 'resolved_by') transfer more energy
                edge_multiplier = 1.2 if r["type"] in ("cause_of", "resolved_by") else 1.0
                
                transfer = energy * edge_weight * decay * edge_multiplier
                next_activations[target_id] = next_activations.get(target_id, 0.0) + transfer
                
            # Fetch source neighbors (incoming - bi-directional association)
            in_rows = conn.execute("SELECT source, weight, type FROM edges WHERE target = ?", (node_id,)).fetchall()
            for r in in_rows:
                source_id = r["source"]
                edge_weight = r["weight"]
                # Reversing link transfers slightly less energy to enforce direction priority
                transfer = energy * edge_weight * decay * 0.8 
                next_activations[source_id] = next_activations.get(source_id, 0.0) + transfer

        # Merge next activations into current activations
        for nid, energy in next_activations.items():
            # Keep max activation or accumulate
            activations[nid] = max(activations.get(nid, 0.0), energy)
            
        # Prune activations below threshold
        activations = {nid: eng for nid, eng in activations.items() if eng >= threshold}

    # Fetch full node details and sort by final energy rank
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
    """Scan memory/decisions/ and memory/incidents/ to populate graph nodes."""
    print("📂 Scanning local Decisions & Incidents directories...")
    
    # Process decisions (.json)
    decisions_count = 0
    if os.path.exists(DECISIONS_DIR):
        for fpath in Path(DECISIONS_DIR).glob("*.json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                node_id = fpath.stem
                content = f"Decision: {data.get('decision')}\nContext: {data.get('context')}\nActions: {', '.join(data.get('actions_taken', []))}"
                add_node(
                    node_id=node_id,
                    content=content,
                    node_type="decision",
                    created_at=data.get("timestamp"),
                    metadata=data
                )
                decisions_count += 1
            except Exception as e:
                print(f"⚠️ Error loading decision {fpath.name}: {e}")
                
    # Process incidents (.md or .json, assuming decisions are json, incidents are json/md)
    incidents_count = 0
    if os.path.exists(INCIDENTS_DIR):
        # We search md files first as reflection.rs writes md
        for fpath in Path(INCIDENTS_DIR).glob("*.md"):
            try:
                content = fpath.read_text(encoding="utf-8")
                node_id = fpath.stem
                add_node(
                    node_id=node_id,
                    content=content,
                    node_type="incident",
                    metadata={"filename": fpath.name}
                )
                incidents_count += 1
            except Exception as e:
                print(f"⚠️ Error loading incident {fpath.name}: {e}")
                
    print(f"✅ Loaded {decisions_count} decisions and {incidents_count} incidents into graph nodes.")

def get_9router_summary_client():
    env_url = os.environ.get("SUPABASE_URL")
    env_key = os.environ.get("SUPABASE_KEY")
    if env_url and env_key:
        return env_url, env_key
    config_path = os.path.join(BASE_DIR, "data", "supabase_config.json")
    if not os.path.exists(config_path):
        return None, None
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return (env_url or config.get("supabase_url")), (env_key or config.get("supabase_key"))

async def build_causality_links_with_llm():
    """
    Calls 9Router (LLM) to analyze Decisions & Incidents text, 
    detecting cause-and-effect relationships to build directed edges automatically.
    """
    conn = get_db_connection()
    nodes = conn.execute("SELECT id, type, content FROM nodes WHERE type IN ('decision', 'incident')").fetchall()
    conn.close()
    
    if len(nodes) < 2:
        print("⚠️ Not enough nodes to build links.")
        return
        
    print(f"🤖 Analyzing causality between {len(nodes)} nodes using LLM...")
    
    # Build list of node summaries for prompt
    node_list = []
    for n in nodes:
        snippet = n["content"][:200].replace("\n", " ")
        node_list.append({
            "id": n["id"],
            "type": n["type"],
            "summary": snippet
        })
        
    system_prompt = (
        "You are SynapzCore Causality Engine. Your task is to analyze the provided list of AI Agent decisions and incidents, "
        "and detect logical relationships between them.\n\n"
        "Specifically, detect:\n"
        "1. 'cause_of': A decision (or incident) that directly caused or triggered an incident.\n"
        "2. 'resolved_by': An incident that was resolved or fixed by a subsequent decision.\n"
        "3. 'related_to': Two decisions or incidents that are highly relevant to each other (e.g., share the same API, library, or feature area).\n\n"
        "Respond ONLY with a valid JSON array of objects with the exact schema:\n"
        "[\n"
        "  { \"source\": \"node_id_1\", \"target\": \"node_id_2\", \"type\": \"cause_of|resolved_by|related_to\", \"weight\": 0.1-1.0 }\n"
        "]\n"
        "Do not include any markdown styling, conversational text, or explanations. Respond with raw JSON only."
    )
    
    payload = {
        "model": "ag/gemini-3-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Nodes list to analyze:\n\n{json.dumps(node_list, indent=2)}"}
        ],
        "stream": False,
        "response_format": {"type": "json_object"}
    }
    
    # 9Router local call (env-first; không hardcode key)
    _nr_base = os.environ.get("NINEROUTER_URL", "http://127.0.0.1:20128")
    _nr_key = os.environ.get("NINEROUTER_KEY", "")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_nr_base}/v1/chat/completions",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {_nr_key}"
                },
                timeout=90.0
            )
            resp.raise_for_status()
            res_content = resp.json()["choices"][0]["message"]["content"]
            
            # Clean possible markdown block wrapping
            if "```json" in res_content:
                res_content = res_content.split("```json")[1].split("```")[0].strip()
            elif "```" in res_content:
                res_content = res_content.split("```")[1].split("```")[0].strip()
                
            links = json.loads(res_content)
            # If wrap in object, extract array
            if isinstance(links, dict) and "links" in links:
                links = links["links"]
            elif isinstance(links, dict):
                links = list(links.values())[0] # Try first key
                
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
                print(f"✅ Generated and saved {links_count} causality links in database.")
            else:
                print(f"❌ Invalid response format from LLM: {res_content}")
    except Exception as e:
        print(f"❌ LLM Causality Linker failed: {e}")

async def run_testing():
    """Self-test function."""
    init_db()
    populate_from_local_files()
    await build_causality_links_with_llm()
    
    # Test query
    query = "telegram"
    print(f"\n🧠 Testing Spreading Activation query: '{query}'")
    results = spreading_activation(query)
    for i, r in enumerate(results, 1):
        print(f"  #{i} [{r['type'].upper()} - Energy: {r['activation_energy']}] {r['id']}")
        print(f"     Content snippet: {r['content'].replace('\n', ' ')[:100]}...")

if __name__ == "__main__":
    import asyncio
    args = sys.argv[1:]
    
    if "--init" in args:
        init_db()
        sys.exit(0)
        
    if "--scan" in args:
        init_db()
        populate_from_local_files()
        asyncio.run(build_causality_links_with_llm())
        sys.exit(0)
        
    if "--query" in args:
        idx = args.index("--query")
        if idx + 1 < len(args):
            q_text = args[idx + 1]
            results = spreading_activation(q_text)
            print(f"🧠 Retrieved nodes via Spreading Activation for '{q_text}':")
            for r in results:
                print(f"  [{r['type'].upper()} - Energy: {r['activation_energy']}] {r['id']}")
        else:
            print("Missing query text.")
        sys.exit(0)
        
    # Default test run
    asyncio.run(run_testing())
