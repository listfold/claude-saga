# /// script
# requires-python = ">=3.12"
# dependencies = [
# "pydevd-pycharm==251.23774.444"
# ]
# ///

"""
Init hook saga - Initializes shadow worktrees for Claude sessions
Uses the claude-saga framework for saga-based effect handling.
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

# Import the saga framework
import importlib.util
spec = importlib.util.spec_from_file_location("claude_saga", Path(__file__).parent / "claude-saga.py")
claude_saga = importlib.util.module_from_spec(spec)
sys.modules["claude_saga"] = claude_saga
spec.loader.exec_module(claude_saga)

from claude_saga import (
    BaseSagaState, SagaRuntime,
    Call, Put, Select, Log, Stop, Complete,
    run_command_effect, write_file_effect, 
    change_directory_effect, create_directory_effect,
    log_debug, connect_pycharm_debugger_effect,
    validate_input_saga, parse_json_saga
)

@dataclass
class InitSagaState(BaseSagaState):
    """State object specific to init hook"""
    # Git-related state (session_id is already in BaseSagaState)
    git_root: Optional[str] = None
    claude_git_dir: Optional[Path] = None
    shadow_dir: Optional[Path] = None

def pycharm_debug_saga():
    """Connect to PyCharm debugger if DEBUG_PYCHARM env var is set"""
    if os.environ.get("DEBUG_PYCHARM") != "1":
        return
    connected = yield Call(connect_pycharm_debugger_effect)
    if not connected:
        yield Stop("Failed to connect to PyCharm debugger")

def setup_and_validate_saga():
    state = yield Select()
    
    # Check git repository and get root
    result = yield Call(run_command_effect, "git rev-parse --show-toplevel")
    if not result or result.returncode != 0:
        yield Stop("Not a git repository, run git init in project root to use this tool.")
    
    git_root = result.stdout.strip()
    
    # Ensure CC is running from the repo root
    if git_root != state.cwd:
        yield Stop("Claude Code is not running from the repo's root, run claude code from the repo root to use this tool.")
    
    # Change hook's execution context to repo root.
    yield Call(change_directory_effect, git_root)

    # Setup paths, store them in state
    claude_git_dir = Path(git_root) / ".claude" / "git"
    shadow_dir = claude_git_dir / "shadow-worktree"  # Persistent shadow worktree

    # Create required directories
    yield Call(create_directory_effect, claude_git_dir)
    yield Call(create_directory_effect, shadow_dir)

    # Ensure claude_git_dir is in .gitignore, add it if not
    check_result = yield Call(run_command_effect, f"grep -q '{claude_git_dir.relative_to(git_root)}' .gitignore", cwd=git_root)
    if check_result.returncode != 0:
        yield Call(run_command_effect, f"echo '{claude_git_dir.relative_to(git_root)}/' >> .gitignore", cwd=git_root)
        yield Log("info", f"Added {claude_git_dir.relative_to(git_root)}/ to .gitignore")
    
    # Update state with all collected info
    yield Put({
        "git_root": git_root,
        "claude_git_dir": claude_git_dir,
        "shadow_dir": shadow_dir,
    })

def ensure_shadow_worktree_saga():
    """Ensure the shadow worktree exists"""
    state = yield Select()
    worktree_list = yield Call(run_command_effect, "git worktree list")
    if worktree_list and str(state.shadow_dir) in worktree_list.stdout:
        yield Log("info", "Shadow worktree already exists")
        return
    # Create shadow worktree if it doesn't exist
    yield Log("info", "Creating shadow worktree")

    # Create new worktree at current HEAD (later any uncommitted changes in the main repo will be added to the shadow)
    worktree_result = yield Call(run_command_effect, f'git worktree add -d "{state.shadow_dir}" HEAD')
    if not worktree_result or worktree_result.returncode != 0:
        yield Stop("Failed to create shadow worktree")
    
    yield Log("info", f"Created shadow worktree at {state.shadow_dir}")


def synchronize_main_to_shadow_saga():
    """ensure shadow worktree matches main repo state using git archive diff"""
    state = yield Select()
    
    # Use .claude/git directory for archive (already in .gitignore)
    archive_dir = state.claude_git_dir / "main-archive"
    
    try:
        # Create clean archive of main repo (we create a temp git archive because it respects .gitignore, useful snapshot of the main repo)
        yield Call(change_directory_effect, state.git_root)
        
        # Clean up any previous archive
        yield Call(run_command_effect, f'rm -rf "{archive_dir}"', capture_output=False)
        
        # Create archive directory
        yield Call(create_directory_effect, archive_dir)
        
        # Extract git archive to archive directory
        archive_result = yield Call(run_command_effect, 
            f'git archive HEAD | tar -x -C "{archive_dir}"')
        
        if archive_result and archive_result.returncode != 0:
            yield Stop("Failed to create git archive")
        
        # Generate diff between clean archive and shadow worktree
        cross_diff_result = yield Call(run_command_effect, 
            f'git diff --no-index "{archive_dir}" "{state.shadow_dir}"')
        
        cross_diff = ""
        
        # git diff --no-index returns exit code 1 when differences exist, 0 when identical
        if cross_diff_result and cross_diff_result.returncode == 0:
            yield Log("info", "Main repo and shadow worktree are already synchronized")
            return
        elif cross_diff_result and cross_diff_result.returncode == 1:
            # Differences found - need to synchronize
            cross_diff = cross_diff_result.stdout.strip()
            yield Log("info", "Differences found, synchronizing shadow worktree with main repo")
        else:
            # Error occurred
            yield Stop("Failed to generate cross-repo diff")
        
        # Change to shadow worktree directory
        yield Call(change_directory_effect, str(state.shadow_dir))
        
        # Reset shadow worktree to clean state
        yield Call(run_command_effect, "git reset --hard HEAD", capture_output=False)
        yield Call(run_command_effect, "git clean -fd", capture_output=False)
        
        # Apply cross-repo changes if differences exist
        if cross_diff:
            # Write cross-repo diff to temporary file
            diff_file = state.shadow_dir / "temp_cross_repo_sync.patch"
            yield Call(write_file_effect, diff_file, cross_diff)
            
            # Apply the cross-repo patch
            apply_result = yield Call(run_command_effect, 
                f'git apply --reject --ignore-whitespace "{diff_file}"', capture_output=False)
            
            # Clean up temp file
            if diff_file.exists():
                diff_file.unlink()
            
            if apply_result and apply_result.returncode != 0:
                yield Log("warning", "Some patch chunks may have failed - manual review may be needed")
        
        # Stage all changes in shadow worktree
        yield Call(run_command_effect, "git add -A", capture_output=False)
        
        # Commit the synchronization
        commit_msg = f"Sync with main repo state (session {state.session_id})"
        yield Call(run_command_effect, f'git commit --allow-empty -m "{commit_msg}"', capture_output=False)
        yield Log("info", "Shadow worktree synchronized with main repo")
        
    finally:
        # Clean up archive directory
        yield Call(run_command_effect, f'rm -rf "{archive_dir}"', capture_output=False)
        # Return to original directory
        yield Call(change_directory_effect, state.git_root)
        yield Complete("Shadow worktree is ready for this session")

def main_saga():
    """Main saga that handles complete shadow worktree initialization"""
    # Input validation and parsing
    yield from validate_input_saga()
    # Initialize state with hook input json.
    yield from parse_json_saga()
    # Initialize state with fields required by our sagas
    yield Put({
        "git_root": None,
        "claude_git_dir": None,
        "shadow_dir": None,
        "initial_state_file": None
    })
    
    # Complete shadow worktree setup - consolidated 4-step process
    yield from pycharm_debug_saga()               # Debug setup if needed
    yield from setup_and_validate_saga()          # Step 1: Setup & validation
    yield from ensure_shadow_worktree_saga()      # Step 2: Ensure shadow worktree exists
    yield from synchronize_main_to_shadow_saga()  # Step 3: Sync main → shadow  

def main():
    """Main entry point - pure orchestration"""
    # Create runtime with empty initial state object
    runtime = SagaRuntime(InitSagaState())
    # Run the saga
    final_state = runtime.run(main_saga())
    # Output the final state as JSON, CC uses hook stdout to decide its next step.
    print(json.dumps(final_state.to_json()))
    # Exit with appropriate code
    if final_state.continue_:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()