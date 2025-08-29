
HELLO WORLD


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
