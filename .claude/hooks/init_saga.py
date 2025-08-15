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
from typing import Any, Generator, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum, auto

# Debug using pycharm
if os.environ.get("DEBUG_PYCHARM") == "1":
    import pydevd_pycharm
    pydevd_pycharm.settrace('localhost', port=12345, stdoutToServer=True, stderrToServer=True)


# ============================================================================
# Redux Saga-like Effect System
# ============================================================================

class EffectType(Enum):
    """Types of effects that can be yielded from sagas"""
    CALL = auto()      # Call a function with side effects
    PUT = auto()       # Update state
    SELECT = auto()    # Select from state
    FORK = auto()      # Fork a new saga
    ALL = auto()       # Run multiple effects in parallel
    TAKE = auto()      # Wait for an action
    LOG = auto()       # Log a message
    CANCEL = auto()    # Cancel the saga


@dataclass
class Effect:
    """Base class for all effects"""
    type: EffectType
    payload: Any = None


@dataclass
class Call(Effect):
    """Effect for calling functions with side effects"""
    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__(EffectType.CALL)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs


@dataclass
class Put(Effect):
    """Effect for updating state"""
    def __init__(self, update: dict | Callable):
        super().__init__(EffectType.PUT, update)


@dataclass
class Select(Effect):
    """Effect for selecting from state"""
    def __init__(self, selector: Optional[Callable] = None):
        super().__init__(EffectType.SELECT, selector)


@dataclass
class Fork(Effect):
    """Effect for forking a new saga"""
    def __init__(self, saga: Generator, *args, **kwargs):
        super().__init__(EffectType.FORK)
        self.saga = saga
        self.args = args
        self.kwargs = kwargs


@dataclass
class All(Effect):
    """Effect for running multiple effects in parallel"""
    def __init__(self, effects: list[Effect]):
        super().__init__(EffectType.ALL, effects)


@dataclass
class Log(Effect):
    """Effect for logging"""
    def __init__(self, level: str, message: str):
        super().__init__(EffectType.LOG)
        self.level = level
        self.message = message


@dataclass
class Cancel(Effect):
    """Effect for canceling the saga with an error"""
    def __init__(self, error: str):
        super().__init__(EffectType.CANCEL, error)


# ============================================================================
# State Management
# ============================================================================

@dataclass
class SagaState:
    """State object that flows through sagas"""
    # Input data
    input_data: dict
    
    # Git-related state
    session_id: Optional[str] = None
    git_root: Optional[str] = None
    claude_git_dir: Optional[Path] = None
    shadow_dir: Optional[Path] = None
    initial_state_file: Optional[Path] = None
    
    # Control flow
    success: bool = True
    error_message: Optional[str] = None
    
    # Response
    response: dict = field(default_factory=dict)
    
    # Additional metadata
    metadata: dict = field(default_factory=dict)


# ============================================================================
# Side Effect Functions (Impure)
# ============================================================================

def run_command_effect(cmd: str, cwd: Optional[str] = None, capture_output: bool = True) -> Optional[subprocess.CompletedProcess]:
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=capture_output, text=True)
        return result
    except Exception as e:
        return None


def write_file_effect(path: Path, content: str) -> bool:
    """Write content to a file"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        return True
    except Exception as e:
        return False


def change_directory_effect(path: str) -> bool:
    """Change the current working directory"""
    try:
        os.chdir(path)
        return True
    except Exception as e:
        return False


def create_directory_effect(path: Path) -> bool:
    """Create a directory"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        return False


# ============================================================================
# Logging Effects
# ============================================================================

def log_debug(message: str):
    if os.environ.get("DEBUG", "0") == "1":
        print(f'[DEBUG] {message}', file=sys.stderr)


def log_info(message: str):
    print(f'[INFO] {message}', file=sys.stderr)


def log_error(message: str):
    print(f'[ERROR] {message}', file=sys.stderr)


# ============================================================================
# Sagas (Generators that yield effects)
# ============================================================================

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
    check_result = yield Call(run_command_effect, "grep -q '^\.claude/git' .gitignore", cwd=state.git_root)
    
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


def root_saga():
    """Root saga that composes all sub-sagas"""
    yield validate_session_saga()
    yield check_git_repository_saga()
    yield validate_working_directory_saga()
    yield setup_paths_saga()
    yield check_existing_worktree_saga()
    yield update_gitignore_saga()
    yield initialize_git_saga()
    yield create_directories_saga()
    yield capture_initial_state_saga()
    yield create_worktree_saga()
    yield apply_initial_state_saga()
    yield prepare_success_response_saga()


# ============================================================================
# Saga Runtime
# ============================================================================

class SagaRuntime:
    """Runtime for executing sagas"""
    
    def __init__(self, initial_state: SagaState):
        self.state = initial_state
        self.cancelled = False
        self.cancel_reason = None
    
    def run(self, saga: Generator) -> SagaState:
        """Run a saga to completion"""
        try:
            effect = None
            while not self.cancelled:
                try:
                    yielded = saga.send(effect)
                    effect = self._handle_effect(yielded)
                except StopIteration:
                    break
        except Exception as e:
            log_error(f"Saga runtime error: {e}")
            self.state.success = False
            self.state.error_message = str(e)
        
        return self.state
    
    def _handle_effect(self, effect: Effect) -> Any:
        """Handle an effect and return its result"""
        if not isinstance(effect, Effect):
            return None
        
        match effect.type:
            case EffectType.CALL:
                return self._handle_call(effect)
            case EffectType.PUT:
                return self._handle_put(effect)
            case EffectType.SELECT:
                return self._handle_select(effect)
            case EffectType.FORK:
                return self._handle_fork(effect)
            case EffectType.ALL:
                return self._handle_all(effect)
            case EffectType.LOG:
                return self._handle_log(effect)
            case EffectType.CANCEL:
                return self._handle_cancel(effect)
            case _:
                return None
    
    def _handle_call(self, effect: Call) -> Any:
        """Handle a CALL effect"""
        try:
            return effect.fn(*effect.args, **effect.kwargs)
        except Exception as e:
            log_error(f"Call effect failed: {e}")
            return None
    
    def _handle_put(self, effect: Put) -> None:
        """Handle a PUT effect to update state"""
        if isinstance(effect.payload, dict):
            for key, value in effect.payload.items():
                setattr(self.state, key, value)
        elif callable(effect.payload):
            self.state = effect.payload(self.state)
    
    def _handle_select(self, effect: Select) -> SagaState:
        """Handle a SELECT effect to get state"""
        if effect.payload and callable(effect.payload):
            return effect.payload(self.state)
        return self.state
    
    def _handle_fork(self, effect: Fork) -> None:
        """Handle a FORK effect (simplified - runs synchronously)"""
        forked_runtime = SagaRuntime(self.state)
        self.state = forked_runtime.run(effect.saga(*effect.args, **effect.kwargs))
    
    def _handle_all(self, effect: All) -> list:
        """Handle an ALL effect (simplified - runs sequentially)"""
        results = []
        for sub_effect in effect.payload:
            results.append(self._handle_effect(sub_effect))
        return results
    
    def _handle_log(self, effect: Log) -> None:
        """Handle a LOG effect"""
        match effect.level:
            case "debug":
                log_debug(effect.message)
            case "info":
                log_info(effect.message)
            case "error":
                log_error(effect.message)
    
    def _handle_cancel(self, effect: Cancel) -> None:
        """Handle a CANCEL effect"""
        self.cancelled = True
        self.cancel_reason = effect.payload


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point"""
    # Check if stdin is a terminal (not piped)
    if sys.stdin.isatty():
        print("Error: No input provided. This script expects JSON input via stdin.", file=sys.stderr)
        print("Usage: echo '{\"session_id\": \"test\", \"cwd\": \"/path\"}' | uv run init_saga.py", file=sys.stderr)
        sys.exit(1)
    
    # Parse input
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)
    
    log_debug(json.dumps(input_data))
    
    # Create initial state
    initial_state = SagaState(input_data=input_data)
    
    # Create runtime and run the root saga
    runtime = SagaRuntime(initial_state)
    final_state = runtime.run(root_saga())
    
    # Output the result
    print(json.dumps(final_state.response))
    
    # Exit with appropriate code
    if final_state.response.get("continue", False):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()