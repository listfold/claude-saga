# Claude Saga
A side-effect manager for Python scripts, specifically designed for building maintainable (easy to build, test, debug) [Claude Code hooks](https://docs.anthropic.com/en/docs/claude-code/hooks), inspired by [Redux Saga](https://redux-saga.js.org/).

#### Disclaimer:
Unstable - API subject to change.

## Quick Start
### Conceptual overview
```python
from claude_saga import (
    BaseSagaState, SagaRuntime,
    Call, Put, Select, Log, Stop, Complete,
    run_command_effect
)

def add(x, y):
    return x + y

class State(BaseSagaState):
    math_result: int = 2
    command_result: str = ""

def my_saga():
    yield Log("info", "Starting saga")
    initial_state = yield Select()
    math_result = yield Call(add, initial_state.math_result, 3)
    command_result = yield Call(run_command_effect, "echo 'Hello World'")
    if command_result is None:
        yield Log("error", "unable to run command")
        yield Stop("hook failed, exited early")
    yield Put({"command_result": command_result.stdout, "math_result": math_result})
    yield Complete("Saga completed successfully")

runtime = SagaRuntime(State())
final_state = runtime.run(my_saga())
print(final_state.to_json())
```

## Building Claude Code Hooks

Claude Saga handles input/output conventions of claude code hooks:

```python
#!/usr/bin/env python
import json
import sys
from claude_saga import (
    BaseSagaState, SagaRuntime,
    validate_input_saga, parse_json_saga,
    Complete
)

class HookState(BaseSagaState):
    # Add your custom state fields
    pass

def main_saga():
    # Validate and parse input
    # https://docs.anthropic.com/en/docs/claude-code/hooks#hook-input
    yield from validate_input_saga()
    # Adds input data to state
    yield from parse_json_saga()
    
    # Your hook logic here
    
    # Complete
    yield Complete("Hook executed successfully")

def main():
    runtime = SagaRuntime(HookState())
    # Final state is an object that conforms to common json fields:
    # https://docs.anthropic.com/en/docs/claude-code/hooks#common-json-fields
    final_state = runtime.run(main_saga())
    # Claude Code exit code behavior:
    # https://docs.anthropic.com/en/docs/claude-code/hooks#simple%3A-exit-code
    print(json.dumps(final_state.to_json()))
    sys.exit(0 if final_state.continue_ else 1)

if __name__ == "__main__":
    main()
```


## Effect Types

### Call
Execute functions, including(and especially) those with side-effects:
```python
result = yield Call(function, arg1, arg2, kwarg=value)
```

### Put
Update the state:
```python
yield Put({"field": "value"})
# or with a function
yield Put(lambda state: MyState(counter=state.counter + 1))
```

### Select
Read from the state:
```python
state = yield Select()
# or with a selector
counter = yield Select(lambda state: state.counter)
```

### Log
Log messages at different levels:
```python
yield Log("info", "Information message")
yield Log("error", "Error message")
yield Log("debug", "Debug message")  # Only shown with DEBUG=1
```

### Stop
Stop execution with an error, hook output contains `continue:false`:
```python
yield Stop("Error message")
```

### Complete
Complete saga successfully, hook output contains `continue:true`:
```python
yield Complete("Success message")
```

## Common Effects

The library includes common effects 
- `log_info`, `log_error`, `log_debug`
- `run_command_effect(cmd, cwd=None, capture_output=True)` - Run shell commands
- `write_file_effect(path, content)` - Write files
- `change_directory_effect(path)` - Change working directory
- `create_directory_effect(path)` - Create directories
- `connect_pycharm_debugger_effect()` - Connect to PyCharm debugger

Notes:
  - When you write your own effects - you don't need to implement error handling - the saga runtime handles Call errors (logs them to stdout) and returns `None` on failure. 
    - If you want to terminate the saga on effect failure, check if the Call result is `None` and yield a `Stop`.

## Common Sagas

Pre-built sagas for common tasks:

- `validate_input_saga()` - Validate stdin input is provided
- `parse_json_saga()` - Parse JSON from stdin into hook state (parses specifically for [Claude Code hook input](https://docs.anthropic.com/en/docs/claude-code/hooks#hook-input))

# Development

### Setup

```bash
uv pip install -e .
```
### Examples

The `examples/` directory contains a practical demonstration:

- `simple_command_validator.py` - Claude Code hook for validating bash commands (saga version of the [official example](https://docs.anthropic.com/en/docs/claude-code/hooks#exit-code-example%3A-bash-command-validation))

```bash
# This will fail since the expected input to stdin is not provided
uv run examples/simple_command_validator.py

# Handle claude code stdin conventions, this command passes validation 
echo '{"tool_name": "Bash", "tool_input": {"command": "ls -la"}}' | uv run examples/simple_command_validator.py

# This command fails validation (uses grep instead of rg)
echo '{"tool_name": "Bash", "tool_input": {"command": "grep pattern file.txt"}}' | uv run examples/simple_command_validator.py

```
### Running Tests

#### Unit Tests
Test the core saga framework components:
```bash
uv run pytest tests/test_claude_saga.py -v
```

#### E2E Tests  
Test complete example hook behavior:
```bash
uv run pytest tests/test_e2e_simple_command_validator.py -v
```

#### All Tests
Run the complete test suite:
```bash
uv run pytest tests/ -v
```
### Building

```bash
uv build
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
I'd like to hear what common effects can be added to the core lib. e.g.
- http_request_effect
- mcp_request_effect

Future work must incorporate
- parsing & validation for each hook's unique input/output behaviors, fields etc...
- retry-able effects
- cancel-able effects
- parallel effects (e.g. `All`), see hypothetical async effects like `mcp_request` etc...
- concurrent effects
