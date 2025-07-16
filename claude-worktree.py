#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "GitPython>=3.1.0",
# ]
# ///

import json
import sys
from pathlib import Path
from git import Repo

def main():
    # This script runs on the PreToolUse hook, it checks if there is a worktree for the current claude session.
    # If there is a worktree, do nothing (other script triggered by PostToolUse write event) will commit the change to the worktree.
    # if there is not a worktree, create one for the current claude session git worktree add -d .claude/worktrees/{claude_session_id}-worktree
    # and update .gitignore to exclude .claude/worktrees folder
    #
    # if there is a worktree for the current session do nothing we're good.
    #
    # Later:
    # Script to commit claude's change in the worktree... this will involve running
    #  1. `git add -A` to stage all (new, modified and deleted) files on the main work tree
    #  2. 
    # 
    # Read Claude's input
    input_data = json.loads(sys.stdin.read())
    
    # Get conversation ID to namespace the worktree
    conversation_id = input_data.get('conversation_id', 'default')
    
    # Setup paths
    project_dir = Path.cwd()
    worktree_name = f"claude-{conversation_id}"
    worktree_path = project_dir / f"{project_dir.name}-{worktree_name}"
   
    # Open the main repository
    repo = Repo(project_dir)
    
    # Check if worktree already exists
    worktree_exists = False
    for worktree in repo.git.worktree('list').splitlines():
        if str(worktree_path) in worktree:
            worktree_exists = True
            break
    
    if not worktree_exists:
        # Create new worktree at current commit
        current_commit = repo.head.commit
        branch_name = f"claude/{conversation_id}"
        
        # Create worktree
        repo.git.worktree('add', str(worktree_path), '-b', branch_name, str(current_commit))
        
        # Save session info
        session_file.write_text(json.dumps({
            "worktree_path": str(worktree_path),
            "branch": branch_name,
            "conversation_id": conversation_id
        }))
    
    else:
        # Worktree exists - check for uncommitted changes
        worktree_repo = Repo(worktree_path)
        
        if worktree_repo.is_dirty() or worktree_repo.untracked_files:
            # Commit any uncommitted changes
            worktree_repo.git.add('-A')
            worktree_repo.index.commit("Claude: Auto-commit uncommitted changes from previous session")
    
    # Claude continues working in the main directory
    # Another hook will sync and commit changes to the worktree
    print(json.dumps({"decision": "approve"}))

if __name__ == "__main__":
    main()s
