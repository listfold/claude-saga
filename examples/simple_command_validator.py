#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = [
# ]
# ///

"""
Simple Command Validator Saga - saga-ized equivalent of the example hook from:
https://docs.anthropic.com/en/docs/claude-code/hooks#exit-code-example%3A-bash-command-validation

This demonstrates how to convert a simple procedural script to saga pattern
while maintaining the same functionality and behavior.
"""

import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple

# Import the saga framework from parent directory
# TODO depend on claude-saga when it's published.
import importlib.util

spec = importlib.util.spec_from_file_location("claude_saga", Path(__file__).parent.parent / "claude_saga" / "__init__.py")
claude_saga = importlib.util.module_from_spec(spec)
sys.modules["claude_saga"] = claude_saga
spec.loader.exec_module(claude_saga)

from claude_saga import (
    BaseSagaState, SagaRuntime,
    Call, Put, Select, Log, Stop, Complete,
    validate_input_saga, parse_json_saga
)


@dataclass
class ValidatorState(BaseSagaState):
    """Simple state for command validation"""
    tool_name: str = ""
    command: str = ""
    validation_rules: List[Tuple[str, str]] = None
    issues: List[str] = None
    
    def __post_init__(self):
        super().__init__()
        if self.validation_rules is None:
            self.validation_rules = []
        if self.issues is None:
            self.issues = []


def validate_command_effect(command: str, rules: List[Tuple[str, str]]) -> List[str]:
    issues = []
    for pattern, message in rules:
        if re.search(pattern, command):
            issues.append(message)
    return issues


def setup_validation_rules_saga():
    """Initialize validation rules - exactly as in original"""
    validation_rules = [
        (
            r"\bgrep\b(?!.*\|)",
            "Use 'rg' (ripgrep) instead of 'grep' for better performance and features",
        ),
        (
            r"\bfind\s+\S+\s+-name\b",
            "Use 'rg --files | rg pattern' or 'rg --files -g pattern' instead of 'find -name' for better performance",
        ),
    ]
    
    yield Put({"validation_rules": validation_rules})


def extract_tool_data_saga():
    """Extract tool data from input - direct translation from original"""
    state = yield Select()
    
    if not state.input_data:
        yield Stop("No input data")
    
    tool_name = state.input_data.get("tool_name", "")
    tool_input = state.input_data.get("tool_input", {})
    command = tool_input.get("command", "")
    
    yield Put({
        "tool_name": tool_name,
        "command": command
    })
    
    # Exit early if not Bash command
    if tool_name != "Bash" or not command:
        yield Complete("Not a Bash command - skipping validation")


def validate_command_saga():
    """Validate the command using rules"""
    state = yield Select()
    
    # Validate command using pure function
    issues = yield Call(validate_command_effect, state.command, state.validation_rules)
    
    yield Put({"issues": issues})


def output_results_saga():
    """Output results and exit - matches original exactly"""
    state = yield Select()
    
    if state.issues:
        # Print issues to stderr (matches original)
        for message in state.issues:
            yield Log("error", f"• {message}")
        
        # Block tool call (exit code 2)
        yield Stop("Validation issues found")
    else:
        # No issues - allow command (exit code 0)
        yield Complete("Command validation passed")


def main_saga():
    yield from validate_input_saga()
    yield from parse_json_saga()
    yield from setup_validation_rules_saga()
    yield from extract_tool_data_saga()
    yield from validate_command_saga()
    yield from output_results_saga()

def main():
    runtime = SagaRuntime(ValidatorState())
    final_state = runtime.run(main_saga())

    # Output the final state as JSON, CC uses hook stdout to decide its next step.
    print(json.dumps(final_state.to_json()))

    if final_state.continue_:
        sys.exit(0)  # Allow command
    else:
        sys.exit(2)  # Block command and show stderr


if __name__ == "__main__":
    main()