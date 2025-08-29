
HELLO WORLD

## Setup

### Creating Symlinks for Claude Hooks

The Claude hook files should be symlinked from the project root to the `.claude/hooks/` directory. To set up the symlinks:

```bash
# Remove existing files if present
rm -f .claude/hooks/claude-git.py
rm -f .claude/hooks/claude-saga.py

# Create symlinks
ln -s ../../claude-git.py .claude/hooks/claude-git.py
ln -s ../../claude-saga.py .claude/hooks/claude-saga.py
```

This ensures that the hook files in `.claude/hooks/` always reflect the latest versions from the project root.

TODO:
install script should update settings.json and should chmod+x the hooks.

Debug:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "DEBUG_PYCHARM=1 uv run /Users/iain/Desktop/Projects/sporran/.claude/hooks/init.py"
          }
        ]
      }
    ]
  }
}

```
