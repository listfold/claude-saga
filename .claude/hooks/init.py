# /// script
# requires-python = ">=3.12"
# dependencies = [
# "pydevd-pycharm==251.23774.444"
# ]
# ///

# ref: https://github.com/astral-sh/uv/issues/14018#issuecomment-2982483971

import json
import os
import subprocess
import sys
from pathlib import Path

import pydevd_pycharm
pydevd_pycharm.settrace('localhost', port=12345, stdoutToServer=True, stderrToServer=True)

# Debug setup - only when DEBUG_PYCHARM is set
if os.environ.get("DEBUG_PYCHARM") == "1":
    import pydevd_pycharm
    pydevd_pycharm.settrace('localhost', port=12345, stdoutToServer=True, stderrToServer=True)

def log_debug(message):
    if os.environ.get("DEBUG", "0") == "1":
        print(f'[DEBUG] {message}', file=sys.stderr)

def log_info(message):
    print(f'[INFO] {message}', file=sys.stderr)

def log_error(message):
    print(f'[ERROR] {message}', file=sys.stderr)

def run_command(cmd, cwd=None, capture_output=True):
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=capture_output, text=True)
        return result
    except Exception as e:
        log_error(f"Command failed: {cmd} - {e}")
        return None

def get_git_root():
    """Get the git repository root directory"""
    result = run_command("git rev-parse --show-toplevel")
    if result and result.returncode == 0:
        return result.stdout.strip()
    return None

def output_json_response(continue_flag, suppress_output, system_message, **kwargs):
    """Output JSON response in the format expected by Claude Code hooks"""
    response = {
        "continue": continue_flag,
        "suppressOutput": suppress_output,
        "systemMessage": system_message
    }
    response.update(kwargs)
    return response

def init_shadow_worktree(input_data):
    """Initialize git shadow worktree for AI undo tracking"""
    
    # Get session_id and transcript_path from input
    session_id = input_data.get("session_id")
    transcript_path = input_data.get("transcript_path")
    
    if not session_id:
        log_error("No session_id found in JSON input")
        return output_json_response(False, False, "ERROR: No session_id found in input")
    
    if not transcript_path:
        log_error("No transcript_path found in JSON input")
        return output_json_response(False, False, "ERROR: No transcript_path found in input")
    
    log_debug(f"Session ID: {session_id}")
    log_debug(f"Transcript Path: {transcript_path}")
    
    # Get git root
    main_repo_root = get_git_root()
    if not main_repo_root:
        log_error("Not a git repo, init git to use this tool")
        return output_json_response(False, False, "ERROR: Not a git repository")

    # check that claude is running from the gh root.
    if not main_repo_root == input_data.get("cwd"):
        log_error("ERROR: Run claude code from the repo's root")

    # Change to repo root
    os.chdir(main_repo_root)
    
    # Set up paths in .claude directory
    shadow_dir = Path(main_repo_root) / ".claude" / "efficient-undo" / "sessions" / session_id / f"session-{session_id}-worktree"
    initial_state_file = Path(main_repo_root) / ".claude" / "efficient-undo" / "sessions" / session_id / f"session-{session_id}-initial.patch"
    
    # Check if shadow worktree already exists
    worktree_list = run_command("git worktree list")
    if worktree_list and str(shadow_dir) in worktree_list.stdout:
        log_info(f"Shadow worktree already exists for session {session_id}")
        return output_json_response(True, False, f"Shadow worktree already exists for session {session_id}",
                                  session_id=session_id, shadow_dir=str(shadow_dir))
    
    log_info(f"Initializing shadow worktree for session {session_id}")
    
    # Ensure the directory exists for the patch file
    initial_state_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Capture current state including uncommitted changes
    run_command("git add -N .", capture_output=False)
    
    # Create the initial state patch
    diff_result = run_command("git diff HEAD")
    if diff_result and diff_result.returncode == 0:
        with open(initial_state_file, 'w') as f:
            f.write(diff_result.stdout)
    
    # Create detached worktree at current HEAD
    worktree_result = run_command(f'git worktree add -d "{shadow_dir}" HEAD')
    if not worktree_result or worktree_result.returncode != 0:
        log_error("Failed to create shadow worktree")
        return output_json_response(False, False, "ERROR: Failed to create shadow worktree")
    
    # Apply initial state to shadow
    os.chdir(shadow_dir)
    
    # Apply the patch (ignore errors if patch is empty)
    run_command(f'git apply "{initial_state_file}"', capture_output=False)
    
    # Add and commit changes
    run_command("git add -A", capture_output=False)
    run_command(f'git commit --allow-empty -m "Initial state: session {session_id}"', capture_output=False)
    
    log_info("Shadow worktree initialized")
    
    # Return to main repo root
    os.chdir(main_repo_root)
    
    return output_json_response(True, False, f"Shadow worktree initialized for session {session_id}",
                              session_id=session_id, shadow_dir=str(shadow_dir))

def main():
    # Check if stdin is a terminal (not piped)
    if sys.stdin.isatty():
        print("Error: No input provided. This script expects JSON input via stdin.", file=sys.stderr)
        print("Usage: echo '{\"session_id\": \"test\", \"transcript_path\": \"/path\"}' | uv run init.py", file=sys.stderr)
        sys.exit(1)
    
    # Parse input
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    log_debug(json.dumps(input_data))    

    # Initialize shadow worktree
    result = init_shadow_worktree(input_data)
    
    # Output the result
    print(json.dumps(result))
    
    # Exit with appropriate code
    if not result["continue"]:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()



