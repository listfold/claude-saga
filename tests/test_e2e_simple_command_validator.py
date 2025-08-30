#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pytest",
# ]
# ///

"""
E2E Test for Simple Command Validator Saga

End-to-end tests that run the validator as a subprocess with JSON input/output.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "tool_name,command,expected_continue,expected_exit_code",
    [
        ("Bash", "grep 'pattern' file.txt", False, 2),
        ("Bash", "find . -name '*.py'", False, 2),
        ("Bash", "rg 'pattern' file.txt", True, 0),
        ("Bash", "ls -la", True, 0),
        ("NotBash", "some command", True, 0),
    ],
)
def test_command_validator(tool_name, command, expected_continue, expected_exit_code):
    """Test validator by piping JSON input and checking response"""
    validator_script = (
        Path(__file__).parent.parent / "examples" / "simple_command_validator.py"
    )

    # Create JSON input
    json_input = json.dumps(
        {"tool_name": tool_name, "tool_input": {"command": command}}
    )

    # Run the validator
    result = subprocess.run(
        [sys.executable, str(validator_script)],
        input=json_input,
        capture_output=True,
        text=True,
    )

    # Parse JSON response
    response = json.loads(result.stdout.strip())

    # Assert response
    assert response["continue"] == expected_continue
    assert result.returncode == expected_exit_code
