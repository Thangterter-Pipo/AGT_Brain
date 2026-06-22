#!/usr/bin/env python3
"""
folder_watcher.py — Watcher for Antigravity memory folders.
Monitors local decisions and incidents. Triggers SQLite Graph Sync and Causality Linker automatically.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Paths configuration
BASE_DIR = os.environ.get("AGT_BRAIN_ROOT", "E:\\AGT_Brain")
DECISIONS_DIR = os.path.join(BASE_DIR, "memory", "decisions")
INCIDENTS_DIR = os.path.join(BASE_DIR, "memory", "incidents")
ENGINE_SCRIPT = os.path.join(BASE_DIR, "scripts", "agt_brain_memory.py")

def get_folder_state():
    """Scans decisions and incidents directories and returns a dictionary of {file_path: mtime}."""
    state = {}
    
    # Decisions (.json)
    if os.path.exists(DECISIONS_DIR):
        for fpath in Path(DECISIONS_DIR).glob("*.json"):
            try:
                state[str(fpath)] = os.path.getmtime(fpath)
            except OSError:
                pass
                
    # Incidents (.md)
    if os.path.exists(INCIDENTS_DIR):
        for fpath in Path(INCIDENTS_DIR).glob("*.md"):
            try:
                state[str(fpath)] = os.path.getmtime(fpath)
            except OSError:
                pass
                
    return state

def trigger_sync():
    """Calls agt_brain_memory.py --sync-graph to update the SQLite graph database."""
    print(f"🔄 [{time.strftime('%Y-%m-%d %H:%M:%S')}] 🧠 Changes detected! Triggering SQLite Graph Sync and Causality Linker...")
    try:
        # Run sync-graph command using the same python executable
        result = subprocess.run(
            [sys.executable, ENGINE_SCRIPT, "--sync-graph"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        print("✅ Graph sync succeeded!")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"❌ Graph sync failed with error: {e}")
        if e.stdout:
            print(f"Stdout:\n{e.stdout}")
        if e.stderr:
            print(f"Stderr:\n{e.stderr}")
    except Exception as e:
        print(f"⚠️ Unexpected error while executing sync: {e}")

def main():
    print("🚀 Antigravity Local Memory Watcher started...")
    print(f"📂 Watching decisions: {DECISIONS_DIR}")
    print(f"📂 Watching incidents: {INCIDENTS_DIR}")
    print("⏰ Checking for modifications every 3 seconds. Press Ctrl+C to stop.\n")
    
    # Initial sync on startup to make sure everything is updated
    trigger_sync()
    
    last_state = get_folder_state()
    
    try:
        while True:
            time.sleep(3.0)
            current_state = get_folder_state()
            
            # Detect changes (added, removed, or modified files)
            if current_state != last_state:
                # Log details about what changed
                added = [f for f in current_state if f not in last_state]
                removed = [f for f in last_state if f not in current_state]
                modified = [f for f in current_state if f in last_state and current_state[f] != last_state[f]]
                
                if added:
                    print(f"➕ File(s) added: {[os.path.basename(f) for f in added]}")
                if removed:
                    print(f"➖ File(s) removed: {[os.path.basename(f) for f in removed]}")
                if modified:
                    print(f"📝 File(s) modified: {[os.path.basename(f) for f in modified]}")
                
                # Run the syncer
                trigger_sync()
                last_state = current_state
                
    except KeyboardInterrupt:
        print("\n👋 Watcher stopped. Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()
