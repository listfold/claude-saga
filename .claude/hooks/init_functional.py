# /// script
# requires-python = ">=3.12"
# dependencies = [
# "pydevd-pycharm==251.23774.444"
# ]
# ///

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, Callable, Optional, Any
from dataclasses import dataclass, field

# Debug using pycharm
if os.environ.get("DEBUG_PYCHARM") == "1":
    import pydevd_pycharm
    pydevd_pycharm.settrace('localhost', port=12345, stdoutToServer=True, stderrToServer=True)


# Logging functions
def log_debug(message: str) -> None:
    if os.environ.get("DEBUG", "0") == "1":
        print(f'[DEBUG] {message}', file=sys.stderr)


def log_info(message: str) -> None:
    print(f'[INFO] {message}', file=sys.stderr)


def log_error(message: str) -> None:
    print(f'[ERROR] {message}', file=sys.stderr)


# State object that flows through the pipeline
@dataclass
class PipelineState:
    input_data: dict
    session_id: Optional[str] = None
    git_root: Optional[str] = None
    claude_git_dir: Optional[Path] = None
    shadow_dir: Optional[Path] = None
    initial_state_file: Optional[Path] = None
    success: bool = True
    error_message: Optional[str] = None
    response: dict = field(default_factory=dict)
    

# Result type for pipeline steps
@dataclass
class StepResult:
    state: PipelineState
    continue_pipeline: bool = True


# Pipeline function type
PipelineStep = Callable[[PipelineState], StepResult]


def compose_pipeline(*steps: PipelineStep) -> Callable[[PipelineState], PipelineState]:
    """Compose multiple pipeline steps into a single function"""
    def pipeline(initial_state: PipelineState) -> PipelineState:
        state = initial_state
        for step in steps:
            result = step(state)
            state = result.state
            if not result.continue_pipeline:
                break
        return state
    return pipeline


def run_command(cmd: str, cwd: Optional[str] = None, capture_output: bool = True) -> Optional[subprocess.CompletedProcess]:
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=capture_output, text=True)
        return result
    except Exception as e:
        log_error(f"Command failed: {cmd} - {e}")
        return None


# Pipeline steps

def validate_session_id(state: PipelineState) -> StepResult:
    """Validate that session_id exists in input"""
    session_id = state.input_data.get("session_id")
    
    if not session_id:
        log_error("No session_id found in JSON input")
        state.success = False
        state.error_message = "ERROR: No session_id found in input"
        state.response = {
            "continue": False,
            "suppressOutput": False,
            "systemMessage": state.error_message
        }
        return StepResult(state, continue_pipeline=False)
    
    state.session_id = session_id
    return StepResult(state)


def check_git_repository(state: PipelineState) -> StepResult:
    """Check if we're in a git repository and get its root"""
    result = run_command("git rev-parse --show-toplevel")
    
    if not result or result.returncode != 0:
        log_error("Not a git repo, init git to use this tool")
        state.success = False
        state.error_message = "ERROR: Not a git repository"
        state.response = {
            "continue": False,
            "suppressOutput": False,
            "systemMessage": state.error_message
        }
        return StepResult(state, continue_pipeline=False)
    
    state.git_root = result.stdout.strip()
    return StepResult(state)


def validate_working_directory(state: PipelineState) -> StepResult:
    """Ensure Claude is running from the repo root"""
    if state.git_root != state.input_data.get("cwd"):
        log_error("ERROR: Run claude from the repo's root")
        state.success = False
        state.error_message = "ERROR: Not running from the repo's root"
        state.response = {
            "continue": False,
            "suppressOutput": False,
            "systemMessage": state.error_message
        }
        return StepResult(state, continue_pipeline=False)
    
    # Change to repo root
    os.chdir(state.git_root)
    return StepResult(state)


def setup_paths(state: PipelineState) -> StepResult:
    """Set up all required paths"""
    state.claude_git_dir = Path(state.git_root) / ".claude" / "git"
    state.shadow_dir = state.claude_git_dir / "sessions" / state.session_id / f"session-{state.session_id}-worktree"
    state.initial_state_file = state.claude_git_dir / "sessions" / state.session_id / f"session-{state.session_id}-initial.patch"
    return StepResult(state)


def check_existing_worktree(state: PipelineState) -> StepResult:
    """Check if shadow worktree already exists"""
    worktree_list = run_command("git worktree list")
    
    if worktree_list and str(state.shadow_dir) in worktree_list.stdout:
        log_info(f"Shadow worktree already exists for session {state.session_id}")
        state.response = {
            "continue": True,
            "suppressOutput": False,
            "systemMessage": f"Shadow worktree already exists for session {state.session_id}",
            "session_id": state.session_id,
            "shadow_dir": str(state.shadow_dir)
        }
        return StepResult(state, continue_pipeline=False)
    
    return StepResult(state)


def update_gitignore(state: PipelineState) -> StepResult:
    """Add .claude/git/ to .gitignore if not already present"""
    # Check if .claude/git/ already exists in .gitignore
    check_result = run_command("grep -q '^\.claude/git' .gitignore", cwd=state.git_root)
    
    if check_result and check_result.returncode == 0:
        log_info(".claude/git/ already exists in .gitignore")
        return StepResult(state)
    
    # Add .claude/git/ to .gitignore
    result = run_command("echo '.claude/git/' >> .gitignore", cwd=state.git_root)
    
    if not result or result.returncode != 0:
        log_error("Failed to add .claude/git/ to .gitignore")
        state.success = False
        state.error_message = "ERROR: Failed to update .gitignore"
        state.response = {
            "continue": False,
            "suppressOutput": False,
            "systemMessage": state.error_message
        }
        return StepResult(state, continue_pipeline=False)
    
    log_info("Added .claude/git/ to .gitignore")
    return StepResult(state)


def initialize_git_if_needed(state: PipelineState) -> StepResult:
    """Initialize git if needed"""
    run_command("git init")
    log_info(f"Initializing shadow worktree for session {state.session_id}")
    return StepResult(state)


def create_directories(state: PipelineState) -> StepResult:
    """Ensure required directories exist"""
    state.initial_state_file.parent.mkdir(parents=True, exist_ok=True)
    return StepResult(state)


def capture_initial_state(state: PipelineState) -> StepResult:
    """Capture current state including uncommitted changes"""
    run_command("git add -N .", capture_output=False)
    
    # Create the initial state patch
    diff_result = run_command("git diff HEAD")
    if diff_result and diff_result.returncode == 0:
        with open(state.initial_state_file, 'w') as f:
            f.write(diff_result.stdout)
    
    return StepResult(state)


def create_worktree(state: PipelineState) -> StepResult:
    """Create detached worktree at current HEAD"""
    worktree_result = run_command(f'git worktree add -d "{state.shadow_dir}" HEAD')
    
    if not worktree_result or worktree_result.returncode != 0:
        log_error("Failed to create shadow worktree")
        state.success = False
        state.error_message = "ERROR: Failed to create shadow worktree"
        state.response = {
            "continue": False,
            "suppressOutput": False,
            "systemMessage": state.error_message
        }
        return StepResult(state, continue_pipeline=False)
    
    return StepResult(state)


def apply_initial_state_to_shadow(state: PipelineState) -> StepResult:
    """Apply initial state to shadow worktree"""
    os.chdir(state.shadow_dir)
    
    # Apply the patch (ignore errors if patch is empty)
    run_command(f'git apply "{state.initial_state_file}"', capture_output=False)
    
    # Add and commit changes
    run_command("git add -A", capture_output=False)
    run_command(f'git commit --allow-empty -m "Initial state: session {state.session_id}"', capture_output=False)
    
    log_info("Shadow worktree initialized")
    
    # Return to main repo root
    os.chdir(state.git_root)
    
    return StepResult(state)


def prepare_success_response(state: PipelineState) -> StepResult:
    """Prepare the final success response"""
    state.response = {
        "continue": True,
        "suppressOutput": False,
        "systemMessage": f"Shadow worktree initialized for session {state.session_id}",
        "session_id": state.session_id,
        "shadow_dir": str(state.shadow_dir)
    }
    return StepResult(state)


# Main pipeline composition
def create_shadow_worktree_pipeline() -> Callable[[PipelineState], PipelineState]:
    """Create the main pipeline for shadow worktree initialization"""
    return compose_pipeline(
        validate_session_id,
        check_git_repository,
        validate_working_directory,
        setup_paths,
        check_existing_worktree,
        update_gitignore,
        initialize_git_if_needed,
        create_directories,
        capture_initial_state,
        create_worktree,
        apply_initial_state_to_shadow,
        prepare_success_response
    )


def main():
    # Check if stdin is a terminal (not piped)
    if sys.stdin.isatty():
        print("Error: No input provided. This script expects JSON input via stdin.", file=sys.stderr)
        print("Usage: echo '{\"session_id\": \"test\", \"transcript_path\": \"/path\"}' | uv run init_functional.py", file=sys.stderr)
        sys.exit(1)
    
    # Parse input
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)
    
    log_debug(json.dumps(input_data))
    
    # Create initial state
    initial_state = PipelineState(input_data=input_data)
    
    # Run the pipeline
    pipeline = create_shadow_worktree_pipeline()
    final_state = pipeline(initial_state)
    
    # Output the result
    print(json.dumps(final_state.response))
    
    # Exit with appropriate code
    if final_state.response.get("continue", False):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()