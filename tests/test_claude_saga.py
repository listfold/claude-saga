#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pytest",
# ]
# ///

"""
Unit tests for the claude_saga framework

Tests the core saga effects, runtime, and state management.
"""

# Import the saga framework
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

spec = importlib.util.spec_from_file_location(
    "claude_saga", Path(__file__).parent.parent / "claude_saga" / "__init__.py"
)
claude_saga = importlib.util.module_from_spec(spec)
sys.modules["claude_saga"] = claude_saga
spec.loader.exec_module(claude_saga)

from claude_saga import (  # noqa: E402
    BaseSagaState,
    Call,
    Complete,
    EffectType,
    Log,
    Put,
    SagaRuntime,
    Select,
    Stop,
    create_directory_effect,
    parse_json_saga,
    run_command_effect,
    validate_input_saga,
    write_file_effect,
)


@dataclass
class MockState(BaseSagaState):
    """Mock state for unit tests"""

    counter: int = 0
    items: list = None

    def __post_init__(self):
        super().__init__()
        if self.items is None:
            self.items = []


class TestEffects:
    """Test effect creation and properties"""

    def test_call_effect_creation(self):
        """Test Call effect creation"""

        def test_fn(x, y=10):
            return x + y

        effect = Call(test_fn, 5, y=20)

        assert effect.type == EffectType.CALL
        assert effect.fn == test_fn
        assert effect.args == (5,)
        assert effect.kwargs == {"y": 20}

    def test_put_effect_creation(self):
        """Test Put effect creation"""
        effect = Put({"counter": 42})

        assert effect.type == EffectType.PUT
        assert effect.payload == {"counter": 42}

    def test_select_effect_creation(self):
        """Test Select effect creation"""

        def selector(state):
            return state.counter

        effect = Select(selector)

        assert effect.type == EffectType.SELECT
        assert effect.payload == selector

    def test_log_effect_creation(self):
        """Test Log effect creation"""
        effect = Log("info", "test message")

        assert effect.type == EffectType.LOG
        assert effect.level == "info"
        assert effect.message == "test message"

    def test_stop_effect_creation(self):
        """Test Stop effect creation"""
        effect = Stop("error occurred")

        assert effect.type == EffectType.STOP
        assert effect.payload == "error occurred"

    def test_complete_effect_creation(self):
        """Test Complete effect creation"""
        effect = Complete("success")

        assert effect.type == EffectType.COMPLETE
        assert effect.payload == "success"


class TestBaseSagaState:
    """Test BaseSagaState functionality"""

    def test_default_state_creation(self):
        """Test default state creation"""
        state = BaseSagaState()

        assert state.continue_
        assert state.stopReason is None
        assert not state.suppressOutput
        assert state.systemMessage is None
        assert state.metadata == {}

    def test_state_to_json(self):
        """Test state serialization to JSON"""
        state = BaseSagaState()
        state.stopReason = "test error"
        state.systemMessage = "test message"
        state.metadata = {"extra": "data"}

        json_output = state.to_json()

        expected = {
            "continue": True,
            "suppressOutput": False,
            "stopReason": "test error",
            "systemMessage": "test message",
            "extra": "data",
        }
        assert json_output == expected

    def test_custom_state_extension(self):
        """Test extending BaseSagaState"""
        state = MockState(counter=5, items=[1, 2, 3])

        assert state.counter == 5
        assert state.items == [1, 2, 3]
        assert state.continue_  # Inherited


class TestSagaRuntime:
    """Test SagaRuntime execution"""

    def test_empty_saga(self):
        """Test running empty saga"""

        def empty_saga():
            return
            yield  # Unreachable but makes it a generator

        runtime = SagaRuntime(MockState())
        result = runtime.run(empty_saga())

        assert result.continue_
        assert not runtime.stopped

    def test_call_effect_execution(self):
        """Test CALL effect execution"""

        def add(x, y):
            return x + y

        def test_saga():
            result = yield Call(add, 3, 4)
            yield Put({"counter": result})

        runtime = SagaRuntime(MockState())
        final_state = runtime.run(test_saga())

        assert final_state.counter == 7

    def test_put_effect_with_dict(self):
        """Test PUT effect with dictionary"""

        def test_saga():
            yield Put({"counter": 42, "items": [1, 2, 3]})

        runtime = SagaRuntime(MockState())
        final_state = runtime.run(test_saga())

        assert final_state.counter == 42
        assert final_state.items == [1, 2, 3]

    def test_put_effect_with_function(self):
        """Test PUT effect with state transformer function"""

        def increment_counter(state):
            state.counter += 1
            return state

        def test_saga():
            yield Put(increment_counter)

        initial_state = MockState(counter=5)
        runtime = SagaRuntime(initial_state)
        final_state = runtime.run(test_saga())

        assert final_state.counter == 6

    def test_select_effect(self):
        """Test SELECT effect"""

        def test_saga():
            state = yield Select()
            yield Put({"counter": state.counter + 10})

        runtime = SagaRuntime(MockState(counter=5))
        final_state = runtime.run(test_saga())

        assert final_state.counter == 15

    def test_select_effect_with_selector(self):
        """Test SELECT effect with selector function"""

        def get_counter(state):
            return state.counter

        def test_saga():
            counter_value = yield Select(get_counter)
            yield Put({"items": [counter_value]})

        runtime = SagaRuntime(MockState(counter=42))
        final_state = runtime.run(test_saga())

        assert final_state.items == [42]

    def test_stop_effect(self):
        """Test STOP effect"""

        def test_saga():
            yield Stop("test error")
            yield Put({"counter": 999})  # Should not execute

        runtime = SagaRuntime(MockState())
        final_state = runtime.run(test_saga())

        assert runtime.stopped
        assert not final_state.continue_
        assert final_state.stopReason == "test error"
        assert final_state.counter == 0  # Should not have been updated

    def test_complete_effect(self):
        """Test COMPLETE effect"""

        def test_saga():
            yield Complete("test success")
            yield Put({"counter": 999})  # Should not execute

        runtime = SagaRuntime(MockState())
        final_state = runtime.run(test_saga())

        assert runtime.stopped
        assert final_state.continue_
        assert final_state.systemMessage == "test success"
        assert final_state.counter == 0  # Should not have been updated

    @patch("claude_saga.log_info")
    def test_log_effect_info(self, mock_log):
        """Test LOG effect with info level"""

        def test_saga():
            yield Log("info", "test info message")

        runtime = SagaRuntime(MockState())
        runtime.run(test_saga())

        mock_log.assert_called_once_with("test info message")

    @patch("claude_saga.log_error")
    def test_log_effect_error(self, mock_log):
        """Test LOG effect with error level"""

        def test_saga():
            yield Log("error", "test error message")

        runtime = SagaRuntime(MockState())
        runtime.run(test_saga())

        mock_log.assert_called_once_with("test error message")

    def test_call_effect_exception_handling(self):
        """Test CALL effect exception handling"""

        def failing_function():
            raise ValueError("test error")

        def test_saga():
            result = yield Call(failing_function)
            # result should be None when exception is caught
            yield Put({"counter": result or -1})

        with patch("claude_saga.log_error") as mock_log:
            runtime = SagaRuntime(MockState())
            final_state = runtime.run(test_saga())

            mock_log.assert_called()
            assert final_state.counter == -1  # None from failed call -> -1

    def test_effect_functions_with_call(self):
        """Test that effect functions work properly through Call"""

        def test_saga():
            # Test successful call
            success = yield Call(create_directory_effect, Path("./test"))
            yield Put({"counter": 1 if success else 0})

        with patch("pathlib.Path.mkdir") as mock_mkdir:
            runtime = SagaRuntime(MockState())
            final_state = runtime.run(test_saga())

            assert final_state.counter == 1  # Should succeed
            mock_mkdir.assert_called_once()

    def test_effect_functions_failure_with_call(self):
        """Test that effect function failures are handled by runtime"""

        def test_saga():
            # Test failed call
            success = yield Call(create_directory_effect, Path("/invalid/path"))
            yield Put({"counter": 1 if success else -1})

        with patch("pathlib.Path.mkdir", side_effect=Exception("Permission denied")):
            with patch("claude_saga.log_error") as mock_log:
                runtime = SagaRuntime(MockState())
                final_state = runtime.run(test_saga())

                assert final_state.counter == -1  # Should fail (None -> False -> -1)
                mock_log.assert_called()

    def test_saga_exception_handling(self):
        """Test saga runtime exception handling"""

        def failing_saga():
            raise RuntimeError("saga error")
            yield  # Unreachable

        with patch("claude_saga.log_error") as mock_log:
            runtime = SagaRuntime(MockState())
            final_state = runtime.run(failing_saga())

            assert not final_state.continue_
            assert "Saga runtime error" in final_state.stopReason
            mock_log.assert_called()

    def test_non_effect_yielded(self):
        """Test yielding non-Effect objects"""

        def test_saga():
            yield "not an effect"
            yield Put({"counter": 42})

        runtime = SagaRuntime(MockState())
        final_state = runtime.run(test_saga())

        # Should continue normally, non-effect yields return None
        assert final_state.counter == 42


class TestCommonEffects:
    """Test common effect functions"""

    @patch("subprocess.run")
    def test_run_command_effect_success(self, mock_run):
        """Test run_command_effect success case"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "command output"
        mock_run.return_value = mock_result

        result = run_command_effect("echo hello")

        assert result == mock_result
        mock_run.assert_called_once_with(
            "echo hello", shell=True, cwd=None, capture_output=True, text=True
        )

    @patch("subprocess.run")
    def test_run_command_effect_exception(self, mock_run):
        """Test run_command_effect raises exception (handled by runtime)"""
        mock_run.side_effect = Exception("command failed")

        with pytest.raises(subprocess.CalledProcessError):
            run_command_effect("failing command")

    @patch("builtins.open")
    @patch("pathlib.Path.mkdir")
    def test_write_file_effect_success(self, mock_mkdir, mock_open):
        """Test write_file_effect success case"""
        mock_file = Mock()
        mock_open.return_value.__enter__ = Mock(return_value=mock_file)
        mock_open.return_value.__exit__ = Mock(return_value=None)

        result = write_file_effect(Path("test.txt"), "content")

        assert result
        mock_file.write.assert_called_once_with("content")

    def test_write_file_effect_exception(self):
        """Test write_file_effect raises exception (handled by runtime)"""
        # Use a path that will cause an error
        with pytest.raises(subprocess.CalledProcessError):
            write_file_effect(Path("/invalid/path/test.txt"), "content")


class TestCommonSagas:
    """Test common saga functions"""

    def test_validate_input_saga_with_stdin(self):
        """Test validate_input_saga when stdin is available"""
        with patch("claude_saga.check_stdin_tty_effect", return_value=False):

            def test_saga():
                yield from validate_input_saga()
                yield Put({"counter": 1})

            runtime = SagaRuntime(MockState())
            final_state = runtime.run(test_saga())

            # Should complete successfully
            assert final_state.counter == 1

    def test_validate_input_saga_without_stdin(self):
        """Test validate_input_saga when no stdin is available"""
        with patch("claude_saga.check_stdin_tty_effect", return_value=True):

            def test_saga():
                yield from validate_input_saga()
                yield Put({"counter": 1})  # Should not execute

            runtime = SagaRuntime(MockState())
            final_state = runtime.run(test_saga())

            # Should stop with error
            assert not final_state.continue_
            assert "No input provided" in final_state.stopReason
            assert final_state.counter == 0  # Should not execute

    def test_parse_json_saga_valid_input(self):
        """Test parse_json_saga with valid JSON"""
        test_json = {"session_id": "123", "cwd": "/test", "tool_name": "Bash"}

        with patch("claude_saga.read_json_stdin_effect", return_value=test_json):

            def test_saga():
                yield from parse_json_saga()

            runtime = SagaRuntime(MockState())
            final_state = runtime.run(test_saga())

            assert final_state.input_data == test_json
            assert final_state.session_id == "123"
            assert final_state.cwd == "/test"

    def test_parse_json_saga_invalid_input(self):
        """Test parse_json_saga with invalid JSON (effect returns None on exception)"""
        # When read_json_stdin_effect raises an exception, _handle_call returns None
        with patch(
            "claude_saga.read_json_stdin_effect",
            side_effect=json.JSONDecodeError("Invalid JSON", "", 0),
        ):
            with patch(
                "claude_saga.log_error"
            ):  # Mock log_error to avoid output during test

                def test_saga():
                    yield from parse_json_saga()

                runtime = SagaRuntime(MockState())
                final_state = runtime.run(test_saga())

                assert not final_state.continue_
                assert "Invalid JSON input" in final_state.stopReason


@pytest.mark.parametrize(
    "level,expected_function",
    [
        ("debug", "log_debug"),
        ("info", "log_info"),
        ("error", "log_error"),
    ],
)
def test_logging_functions(level, expected_function):
    """Test logging functions are called correctly"""
    with patch(f"claude_saga.{expected_function}") as mock_log:

        def test_saga():
            yield Log(level, f"test {level} message")

        runtime = SagaRuntime(MockState())
        runtime.run(test_saga())

        mock_log.assert_called_once_with(f"test {level} message")
