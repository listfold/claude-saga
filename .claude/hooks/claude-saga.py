# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

"""
Claude Saga Framework - A Redux Saga-like effect system for Python
This module provides reusable saga infrastructure for hooks.
"""

import os
import subprocess
import sys
import json
from pathlib import Path
from typing import Any, Generator, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum, auto


# ============================================================================
# Redux Saga-like Effect System
# ============================================================================

class EffectType(Enum):
    """Types of effects that can be yielded from sagas"""
    CALL = auto()      # Call a function with side effects
    PUT = auto()       # Update state
    SELECT = auto()    # Select from state
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
# Base State Management
# ============================================================================

@dataclass
class BaseSagaState:
    """Base state object that can be extended by specific hooks"""
    # Input data
    input_data: Optional[dict] = None
    
    # Control flow
    success: bool = True
    error_message: Optional[str] = None
    
    # Response
    response: dict = field(default_factory=dict)
    
    # Additional metadata
    metadata: dict = field(default_factory=dict)


# ============================================================================
# Common Side Effect Functions (Impure)
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
        print(f'[DEBUG] {message}')


def log_info(message: str):
    print(f'[INFO] {message}')


def log_error(message: str):
    print(f'[ERROR] {message}', file=sys.stderr)


# ============================================================================
# Custom Effects, generally useful
# ============================================================================

def connect_pycharm_debugger_effect():
    """Effect function to connect to PyCharm debugger"""
    try:
        import pydevd_pycharm
        pydevd_pycharm.settrace(
            'localhost', 
            port=12345, 
            stdoutToServer=True, 
            stderrToServer=True
        )
        return True
    except ImportError:
        raise ImportError("pydevd-pycharm package not installed")
    except Exception as e:
        raise RuntimeError(f"Could not connect to debugger: {e}")



# ============================================================================
# Saga Runtime
# ============================================================================

class SagaRuntime:
    """Runtime for executing sagas"""
    
    def __init__(self, initial_state: BaseSagaState):
        self.state = initial_state
        self.cancelled = False
        self.cancel_reason = None
    
    def run(self, saga: Generator) -> BaseSagaState:
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
    
    def _handle_cancel(self, effect: Cancel) -> None:
        """Handle a CANCEL effect"""
        self.cancelled = True
        self.cancel_reason = effect.payload
        
        # Log the cancellation reason
        log_error(f"Saga cancelled: {effect.payload}")
        
        # Update state to reflect the cancellation
        self.state.success = False
        self.state.error_message = effect.payload
        
        # Exit immediately with non-zero status
        sys.exit(1)


# ============================================================================
# Common Hook Sagas
# ============================================================================

def validate_input_saga():
    """Validate that input is provided via stdin"""
    if sys.stdin.isatty():
        yield Put({
            "error": "No input provided. This script expects JSON input via stdin.",
            "usage": "echo '{\"session_id\": \"test\", \"cwd\": \"/path\"}' | uv run <script>.py"
        })
        yield Cancel("No input provided")


def parse_json_saga():
    """Parse JSON input from stdin"""
    try:
        input_data = json.load(sys.stdin)
        yield Put({"input_data": input_data})
    except json.JSONDecodeError as e:
        yield Put({"error": f"Invalid JSON input: {e}"})
        yield Cancel(f"Invalid JSON input: {e}")