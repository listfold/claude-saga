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
    Call, Put, Select, Log, Cancel,
    run_command_effect, write_file_effect, 
    change_directory_effect, create_directory_effect,
    log_debug, connect_pycharm_debugger_effect,
    validate_input_saga, parse_json_saga
)

@dataclass
class InitSagaState(BaseSagaState):
    """State object specific to init hook"""
    # Git-related state
    session_id: Optional[str] = None
    git_root: Optional[str] = None
    claude_git_dir: Optional[Path] = None
    shadow_dir: Optional[Path] = None
    initial_state_file: Optional[Path] = None


def pycharm_debug_saga():
    """Connect to PyCharm debugger if DEBUG_PYCHARM env var is set"""
    # Check if debug mode is enabled
    if os.environ.get("DEBUG_PYCHARM") != "1":
        return

    yield Log("info", "PyCharm debug mode enabled, attempting to connect to debugger...")

    # Try to connect to the debugger
    connected = yield Call(connect_pycharm_debugger_effect)

    # If connection failed (returned None due to exception), cancel
    if not connected:
        yield Log("error", "Failed to connect to PyCharm debugger")
        yield Log("error", "Check that pydevd-pycharm is installed and debugger is waiting")
        print("HEEEEEEE")
        yield Cancel("Failed to connect to PyCharm debugger")
    else:
        yield Log("info", "Successfully connected to PyCharm debugger")


def validate_session_saga():
    """Validate that session_id exists in input"""
    state = yield Select()
    session_id = state.input_data.get("session_id")
    
    if not session_id:
        yield Log("error", "No session_id found in JSON input")
        yield Put({
            "success": False,
            "error_message": "ERROR: No session_id found in input",
            "response": {
                "continue": False,
                "suppressOutput": False,
                "systemMessage": "ERROR: No session_id found in input"
            }
        })
        yield Cancel("No session_id found")
    
    yield Put({"session_id": session_id})


def check_git_repository_saga():
    """Check if we're in a git repository and get its root"""
    result = yield Call(run_command_effect, "git rev-parse --show-toplevel")
    
    if not result or result.returncode != 0:
        yield Log("error", "Not a git repo, init git to use this tool")
        yield Put({
            "success": False,
            "error_message": "ERROR: Not a git repository",
            "response": {
                "continue": False,
                "suppressOutput": False,
                "systemMessage": "ERROR: Not a git repository"
            }
        })
        yield Cancel("Not a git repository")
    
    git_root = result.stdout.strip()
    yield Put({"git_root": git_root})


def validate_working_directory_saga():
    """Ensure Claude is running from the repo root"""
    state = yield Select()
    
    if state.git_root != state.input_data.get("cwd"):
        yield Log("error", "ERROR: Run claude from the repo's root")
        yield Put({
            "success": False,
            "error_message": "ERROR: Not running from the repo's root",
            "response": {
                "continue": False,
                "suppressOutput": False,
                "systemMessage": "ERROR: Not running from the repo's root"
            }
        })
        yield Cancel("Not running from repo root")
    
    # Change to repo root
    yield Call(change_directory_effect, state.git_root)


def setup_paths_saga():
    """Set up all required paths"""
    state = yield Select()
    
    claude_git_dir = Path(state.git_root) / ".claude" / "git"
    shadow_dir = claude_git_dir / "sessions" / state.session_id / f"session-{state.session_id}-worktree"
    initial_state_file = claude_git_dir / "sessions" / state.session_id / f"session-{state.session_id}-initial.patch"
    
    yield Put({
        "claude_git_dir": claude_git_dir,
        "shadow_dir": shadow_dir,
        "initial_state_file": initial_state_file
    })


def check_existing_worktree_saga():
    """Check if shadow worktree already exists"""
    state = yield Select()
    worktree_list = yield Call(run_command_effect, "git worktree list")
    
    if worktree_list and str(state.shadow_dir) in worktree_list.stdout:
        yield Log("info", f"Shadow worktree already exists for session {state.session_id}")
        yield Put({
            "response": {
                "continue": True,
                "suppressOutput": False,
                "systemMessage": f"Shadow worktree already exists for session {state.session_id}",
                "session_id": state.session_id,
                "shadow_dir": str(state.shadow_dir)
            }
        })
        yield Cancel("Worktree already exists")


def update_gitignore_saga():
    """Add .claude/git/ to .gitignore if not already present"""
    state = yield Select()
    
    # Check if .claude/git/ already exists in .gitignore
    check_result = yield Call(run_command_effect, r"grep -q '^\\.claude/git' .gitignore", cwd=state.git_root)
    
    if check_result and check_result.returncode == 0:
        yield Log("info", ".claude/git/ already exists in .gitignore")
        return
    
    # Add .claude/git/ to .gitignore
    result = yield Call(run_command_effect, "echo '.claude/git/' >> .gitignore", cwd=state.git_root)
    
    if not result or result.returncode != 0:
        yield Log("error", "Failed to add .claude/git/ to .gitignore")
        yield Put({
            "success": False,
            "error_message": "ERROR: Failed to update .gitignore",
            "response": {
                "continue": False,
                "suppressOutput": False,
                "systemMessage": "ERROR: Failed to update .gitignore"
            }
        })
        yield Cancel("Failed to update .gitignore")
    
    yield Log("info", "Added .claude/git/ to .gitignore")


def initialize_git_saga():
    """Initialize git if needed"""
    state = yield Select()
    yield Call(run_command_effect, "git init")
    yield Log("info", f"Initializing shadow worktree for session {state.session_id}")


def create_directories_saga():
    """Ensure required directories exist"""
    state = yield Select()
    yield Call(create_directory_effect, state.initial_state_file.parent)


def capture_initial_state_saga():
    """Capture current state including uncommitted changes"""
    state = yield Select()
    
    yield Call(run_command_effect, "git add -N .", capture_output=False)
    
    # Create the initial state patch
    diff_result = yield Call(run_command_effect, "git diff HEAD")
    
    if diff_result and diff_result.returncode == 0:
        yield Call(write_file_effect, state.initial_state_file, diff_result.stdout)


def create_worktree_saga():
    """Create detached worktree at current HEAD"""
    state = yield Select()
    
    worktree_result = yield Call(run_command_effect, f'git worktree add -d "{state.shadow_dir}" HEAD')
    
    if not worktree_result or worktree_result.returncode != 0:
        yield Log("error", "Failed to create shadow worktree")
        yield Put({
            "success": False,
            "error_message": "ERROR: Failed to create shadow worktree",
            "response": {
                "continue": False,
                "suppressOutput": False,
                "systemMessage": "ERROR: Failed to create shadow worktree"
            }
        })
        yield Cancel("Failed to create shadow worktree")


def apply_initial_state_saga():
    """Apply initial state to shadow worktree"""
    state = yield Select()
    
    yield Call(change_directory_effect, str(state.shadow_dir))
    
    # Apply the patch (ignore errors if patch is empty)
    yield Call(run_command_effect, f'git apply "{state.initial_state_file}"', capture_output=False)
    
    # Add and commit changes
    yield Call(run_command_effect, "git add -A", capture_output=False)
    yield Call(run_command_effect, f'git commit --allow-empty -m "Initial state: session {state.session_id}"', capture_output=False)
    
    yield Log("info", "Shadow worktree initialized")
    
    # Return to main repo root
    yield Call(change_directory_effect, state.git_root)


def prepare_success_response_saga():
    """Prepare the final success response"""
    state = yield Select()
    
    yield Put({
        "response": {
            "continue": True,
            "suppressOutput": False,
            "systemMessage": f"Shadow worktree initialized for session {state.session_id}",
            "session_id": state.session_id,
            "shadow_dir": str(state.shadow_dir)
        }
    })


def initialize_state_saga():
    """Initialize the saga state from parsed input"""
    state = yield Select()
    
    # Extract session_id from input data
    input_data = state.input_data
    session_id = input_data.get("session_id")
    
    # Initialize the saga state fields
    yield Put({
        "session_id": session_id,
        "git_root": None,
        "claude_git_dir": None,
        "shadow_dir": None,
        "initial_state_file": None
    })


def root_saga():
    """Root saga that composes all sub-sagas"""
    yield from pycharm_debug_saga()
    yield from validate_session_saga()
    yield from check_git_repository_saga()
    yield from validate_working_directory_saga()
    yield from setup_paths_saga()
    yield from check_existing_worktree_saga()
    yield from update_gitignore_saga()
    yield from initialize_git_saga()
    yield from create_directories_saga()
    yield from capture_initial_state_saga()
    yield from create_worktree_saga()
    yield from apply_initial_state_saga()
    yield from prepare_success_response_saga()


def main_saga():
    """Main saga that handles input validation and initialization"""
    yield from validate_input_saga()
    yield from parse_json_saga()
    yield from initialize_state_saga()
    yield from root_saga()


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    print("HEEEERE")
    """Main entry point - pure orchestration"""
    # Create runtime with empty initial state object
    runtime = SagaRuntime(InitSagaState())
    
    # Run the main saga
    final_state = runtime.run(main_saga())
    
    # Handle output based on final state
    if hasattr(final_state, 'error'):
        print(f"Error: {final_state.error}", file=sys.stderr)
        if hasattr(final_state, 'usage'):
            print(final_state.usage, file=sys.stderr)
        sys.exit(1)
    elif hasattr(final_state, 'response'):
        print(json.dumps(final_state.response))
    else:
        print("Error: Unexpected state", file=sys.stderr)
        sys.exit(1)
    
    # Exit with appropriate code
    if final_state.response.get("continue", False):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()