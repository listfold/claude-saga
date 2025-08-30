"""
Claude Saga Framework - A Redux Saga-like effect system for Python
"""

import os
import subprocess
import sys
import json
from pathlib import Path
from typing import Any, Generator, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum, auto


__version__ = "0.1.0"


class EffectType(Enum):
    """Types of effects that can be yielded from sagas"""
    CALL = auto()  # Call a function with or without side effects
    PUT = auto()  # Update state
    SELECT = auto()  # Select from state
    LOG = auto()  # Log a message
    STOP = auto()  # Stop the saga execution with error
    COMPLETE = auto()  # Stop the saga execution with success


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
class Log(Effect):
    """Effect for logging"""

    def __init__(self, level: str, message: str):
        super().__init__(EffectType.LOG)
        self.level = level
        self.message = message


@dataclass
class Stop(Effect):
    """Effect for stopping the saga execution with error"""

    def __init__(self, message: Optional[str] = None):
        super().__init__(EffectType.STOP, message)


@dataclass
class Complete(Effect):
    """Effect for completing the saga execution with success"""

    def __init__(self, message: Optional[str] = None):
        super().__init__(EffectType.COMPLETE, message)


@dataclass
class BaseSagaState:
    """Base state object that can be extended by specific hooks"""
    # Common input fields from hook
    # https://docs.anthropic.com/en/docs/claude-code/hooks#hook-input
    session_id: Optional[str] = None
    transcript_path: Optional[str] = None
    cwd: Optional[str] = None
    hook_event_name: Optional[str] = None

    # Hook response fields (output)
    # https://docs.anthropic.com/en/docs/claude-code/hooks#hook-output
    continue_: bool = True  # Whether Claude should continue after hook execution
    stopReason: Optional[str] = None  # Message shown when continue is false
    suppressOutput: bool = False  # Hide stdout from transcript mode
    systemMessage: Optional[str] = None  # Optional message to display, shown when continue is true

    # Raw input data for additional fields
    input_data: Optional[dict] = None

    # Additional metadata
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        """Convert state to JSON response for hook output"""
        response = {
            "continue": self.continue_,
            "suppressOutput": self.suppressOutput
        }

        if self.stopReason:
            response["stopReason"] = self.stopReason

        if self.systemMessage:
            response["systemMessage"] = self.systemMessage

        # Add any additional fields from metadata
        response.update(self.metadata)

        return response


# ============================================================================
# Common Side Effect Functions (Impure)
# ============================================================================

def run_command_effect(cmd: str, cwd: Optional[str] = None, capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result"""
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=capture_output, text=True)


def write_file_effect(path: Path, content: str) -> bool:
    """Write content to a file"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)
    return True


def change_directory_effect(path: str) -> bool:
    """Change the current working directory"""
    os.chdir(path)
    return True


def create_directory_effect(path: Path) -> bool:
    """Create a directory"""
    path.mkdir(parents=True, exist_ok=True)
    return True


# ============================================================================
# Logging Effects
# ============================================================================

def log_debug(message: str):
    if os.environ.get("DEBUG", "0") == "1":
        print(f'[DEBUG] {message}')


def log_info(message: str):
    print(f'[INFO] {message}')


def log_error(message: str):
    print(f'[ERROR] {message}', file=sys.stderr)


# ============================================================================
# Custom Effects, generally useful
# ============================================================================

def check_stdin_tty_effect() -> bool:
    """Check if stdin is a terminal (no piped input)"""
    return sys.stdin.isatty()


def read_json_stdin_effect() -> dict:
    """Read and parse JSON from stdin"""
    return json.load(sys.stdin)


def connect_pycharm_debugger_effect():
    """Effect function to connect to PyCharm debugger"""
    import pydevd_pycharm
    pydevd_pycharm.settrace(
        'localhost',
        port=12345,
        stdoutToServer=True,
        stderrToServer=True
    )
    return True


# ============================================================================
# Saga Runtime
# ============================================================================

class SagaRuntime:
    """Runtime for executing sagas"""

    def __init__(self, initial_state: BaseSagaState):
        self.state = initial_state
        self.stopped = False

    def run(self, saga: Generator) -> BaseSagaState:
        """Run a saga to completion"""
        saga_name = saga.gi_code.co_name if hasattr(saga, 'gi_code') else 'unknown'
        try:
            effect = None
            while not self.stopped:
                try:
                    yielded = saga.send(effect)
                    effect = self._handle_effect(yielded)
                except StopIteration:
                    break
        except Exception as e:
            log_error(f"Saga runtime error in '{saga_name}': {e}")
            self.state.continue_ = False
            self.state.stopReason = f"Saga runtime error: {e}"

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
            case EffectType.LOG:
                return self._handle_log(effect)
            case EffectType.STOP:
                return self._handle_stop(effect)
            case EffectType.COMPLETE:
                return self._handle_complete(effect)
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

    def _handle_select(self, effect: Select) -> BaseSagaState:
        """Handle a SELECT effect to get state"""
        if effect.payload and callable(effect.payload):
            return effect.payload(self.state)
        return self.state

    def _handle_log(self, effect: Log) -> None:
        """Handle a LOG effect"""
        match effect.level:
            case "debug":
                log_debug(effect.message)
            case "info":
                log_info(effect.message)
            case "error":
                log_error(effect.message)

    def _handle_stop(self, effect: Stop) -> None:
        """Handle a STOP effect - stop saga execution with error"""
        self.stopped = True
        self.state.continue_ = False
        if effect.payload:  # Set stopReason from the Stop message
            self.state.stopReason = effect.payload

    def _handle_complete(self, effect: Complete) -> None:
        """Handle a COMPLETE effect - stop saga execution with success"""
        self.stopped = True
        self.state.continue_ = True
        if effect.payload:  # Set systemMessage from the Complete message
            self.state.systemMessage = effect.payload


# ============================================================================
# Common Hook Sagas
# ============================================================================

def validate_input_saga():
    """Validate that input is provided via stdin"""
    is_tty = yield Call(check_stdin_tty_effect)
    if is_tty:
        yield Stop("No input provided. This script expects JSON input via stdin.")


def parse_json_saga():
    """Parse CC hooks default / standard JSON input from stdin, and store it in the saga state - see CC hooks docs - https://docs.anthropic.com/en/docs/claude-code/hooks """
    input_data = yield Call(read_json_stdin_effect)
    
    # If reading failed (e.g., invalid JSON), Call returns None
    if input_data is None:
        yield Stop("Invalid JSON input from stdin")
        return
    
    # Store raw input
    yield Put({"input_data": input_data})
    
    # Extract common hook fields into state
    update = {}
    if "session_id" in input_data:
        update["session_id"] = input_data["session_id"]
    if "transcript_path" in input_data:
        update["transcript_path"] = input_data["transcript_path"]
    if "cwd" in input_data:
        update["cwd"] = input_data["cwd"]
    if "hook_event_name" in input_data:
        update["hook_event_name"] = input_data["hook_event_name"]
    
    if update:
        yield Put(update)


# Export all public APIs
__all__ = [
    # Version
    "__version__",
    # Effect types
    "EffectType",
    "Effect",
    "Call",
    "Put",
    "Select",
    "Log",
    "Stop",
    "Complete",
    # State
    "BaseSagaState",
    # Runtime
    "SagaRuntime",
    # Common effects
    "run_command_effect",
    "write_file_effect",
    "change_directory_effect",
    "create_directory_effect",
    "log_debug",
    "log_info",
    "log_error",
    "check_stdin_tty_effect",
    "read_json_stdin_effect",
    "connect_pycharm_debugger_effect",
    # Common sagas
    "validate_input_saga",
    "parse_json_saga",
]