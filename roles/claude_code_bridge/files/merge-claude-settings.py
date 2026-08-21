#!/usr/bin/env python3
"""Idempotently register the Noesis bridge hook in ~/.claude/settings.json.

Adds a UserPromptSubmit and a Stop hook entry pointing at the bridge-check
hook, unless already present. Preserves all existing settings and hooks.

Usage:
    merge-claude-settings.py <settings_path> <hook_command> [timeout_s]

Prints "updated" when settings.json changed, "unchanged" otherwise.
"""
import json
import sys
from pathlib import Path


def ensure_hook(hooks, event, command, timeout):
    entries = hooks.setdefault(event, [])
    for group in entries:
        for h in group.get("hooks", []):
            if h.get("command") == command:
                return False  # already registered
    entries.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": command, "timeout": timeout}],
    })
    return True


def main():
    if len(sys.argv) < 3:
        print("usage: merge-claude-settings.py <settings_path> <hook_command> [timeout_s]", file=sys.stderr)
        sys.exit(2)

    settings_path = Path(sys.argv[1])
    hook_command = sys.argv[2]
    timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    if settings_path.exists():
        data = json.loads(settings_path.read_text())
    else:
        data = {}

    hooks = data.setdefault("hooks", {})
    changed = ensure_hook(hooks, "UserPromptSubmit", hook_command, timeout)
    changed |= ensure_hook(hooks, "Stop", hook_command, timeout)

    if changed:
        settings_path.write_text(json.dumps(data, indent=2) + "\n")
        print("updated")
    else:
        print("unchanged")


if __name__ == "__main__":
    main()
