#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "GitPython>=3.1.0",
# ]
# ///

import json
import sys
import os
from pathlib import Path
from git import Repo

# Configuration
PROJECT_DIR = Path.cwd()
PROJECT_NAME = PROJECT_DIR.name
WORKTREE_DIR = PROJECT_DIR.parent / f"{PROJECT_NAME}-claude"
SESSION_FILE = PROJECT_DIR / ".claude" / "session-active"
CLAUDE_DIR = PROJECT_DIR / ".claude"

def main():
    # Read JSON input from Claude
    input_data = json.loads(sys.stdin.read())
    
    # Check if this is a stop event with Claude already continuing
    # (to prevent infinite loops)
    stop_active = input_data.get('stop_hook_active', False)
    if stop_active:
        print(json.dumps({"continue": True}))
        return
    
    # Check if we have an active session
    if not SESSION_FILE.exists():
        # No active session, let Claude stop normally
        print(json.dumps({"continue": True}))
        return
    
    # We have an active session - check the worktree status
    if not WORKTREE_DIR.exists():
        # Worktree missing but session file exists - clean up
        SESSION_FILE.unlink()
        print(json.dumps({"continue": True}))
        return
    
    # Get the branch name and check for uncommitted changes
    git_branch = SESSION_FILE.read_text().strip()
    
    try:
        # Open the worktree repository
        repo = Repo(WORKTREE_DIR)
        
        # Check if we have any commits in this session
        try:
            commits = list(repo.iter_commits(f'main..HEAD'))
            commit_count = len(commits)
        except:
            commit_count = 0
        
        if commit_count == 0:
            # No commits yet, safe to stop
            print(json.dumps({"continue": True}))
        else:
            # We have commits - ask Claude to continue
            response = {
                "decision": "block",
                "reason": f"You have {commit_count} uncommitted changes in the worktree (branch: {git_branch}). Would you like me to continue working on them, or would you prefer to stop and review them first?"
            }
            print(json.dumps(response))
            
    except Exception as e:
        # If something goes wrong, log but allow stop
        print(json.dumps({
            "continue": True,
            "message": f"Error checking worktree: {str(e)}"
        }), file=sys.stderr)

if __name__ == "__main__":
    main()
