# Claude Saga

A Redux Saga-like effect system for Python, designed for building maintainable Claude Code hooks and other applications that need clean separation of side effects.

## Features

- **Effect-based programming**: Separate pure logic from side effects
- **Generator-based sagas**: Use Python generators to orchestrate complex workflows
- **Type-safe effects**: Strongly typed effect system with dataclasses
- **Built for Claude Code hooks**: Designed specifically for Claude Code hook development
- **Testable**: Pure functions and effects make testing straightforward
- **Composable**: Build complex sagas from simple, reusable pieces

## Installation

```bash
pip install claude-saga
```

Or with UV:

```bash
uv add claude-saga
```

## Quick Start

```python
from claude_saga import (
    BaseSagaState, SagaRuntime,
    Call, Put, Select, Log, Stop, Complete,
    run_command_effect
)

# Define your state
class MyState(BaseSagaState):
    counter: int = 0
    result: str = ""

# Define a saga
def my_saga():
    # Log a message
    yield Log("info", "Starting saga")
    
    # Get current state
    state = yield Select()
    
    # Call a side effect
    result = yield Call(run_command_effect, "echo 'Hello World'")
    
    # Update state
    yield Put({"result": result.stdout, "counter": state.counter + 1})
    
    # Complete with success
    yield Complete("Saga completed successfully")

# Run the saga
runtime = SagaRuntime(MyState())
final_state = runtime.run(my_saga())
print(final_state.to_json())
```

## Effect Types

### Call
Execute functions with side effects:
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
Stop execution with an error:
```python
yield Stop("Error message")
```

### Complete
Complete execution successfully:
```python
yield Complete("Success message")
```

## Common Effects

The library includes common side-effect functions:

- `run_command_effect(cmd, cwd=None, capture_output=True)` - Run shell commands
- `write_file_effect(path, content)` - Write files
- `change_directory_effect(path)` - Change working directory
- `create_directory_effect(path)` - Create directories
- `connect_pycharm_debugger_effect()` - Connect to PyCharm debugger

## Common Sagas

Pre-built sagas for common tasks:

- `validate_input_saga()` - Validate stdin input is provided
- `parse_json_saga()` - Parse JSON from stdin (for Claude Code hooks)

## Building Claude Code Hooks

Claude Saga is designed to make Claude Code hooks maintainable and testable:

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
    yield from validate_input_saga()
    yield from parse_json_saga()
    
    # Your hook logic here
    
    # Complete
    yield Complete("Hook executed successfully")

def main():
    runtime = SagaRuntime(HookState())
    final_state = runtime.run(main_saga())
    print(json.dumps(final_state.to_json()))
    sys.exit(0 if final_state.continue_ else 1)

if __name__ == "__main__":
    main()
```

## Development

### Running Tests

```bash
uv run pytest
```

### Building

```bash
uv build
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.