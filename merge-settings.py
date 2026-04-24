#!/usr/bin/env python3
"""Merge generated claude-settings.json into user's ~/.claude/settings.json.

Deep-merges env vars (preserving user's extra keys) and overwrites model.
All other user settings (hooks, plugins, etc.) are preserved untouched.

Usage:
  python3 merge-settings.py <generated-file> <user-settings-file> [--dry-run] [--only-if-changed]
  python3 merge-settings.py --install-hook <hook-command> <user-settings-file>
  python3 merge-settings.py --remove-hook <user-settings-file>
"""
from __future__ import annotations

import copy
import json
import os
import sys

KNOWN_GENERATED_KEYS = {"env", "model"}
HOOK_MARKER = "update-claude-settings.sh"


def merge(generated: dict, user: dict) -> dict:
    result = copy.deepcopy(user)

    if "env" in generated:
        if "env" not in result:
            result["env"] = {}
        for key, value in generated["env"].items():
            result["env"][key] = value

    if "model" in generated:
        result["model"] = generated["model"]

    return result


def add_hook(settings: dict, hook_cmd: str) -> dict:
    result = copy.deepcopy(settings)

    if "hooks" not in result:
        result["hooks"] = {}
    if "SessionStart" not in result["hooks"]:
        result["hooks"]["SessionStart"] = []

    filtered = [
        entry for entry in result["hooks"]["SessionStart"]
        if not any(HOOK_MARKER in h.get("command", "") for h in entry.get("hooks", []))
    ]
    filtered.append({
        "hooks": [{"type": "command", "command": hook_cmd}]
    })
    result["hooks"]["SessionStart"] = filtered
    return result


def remove_hook(settings: dict) -> dict:
    result = copy.deepcopy(settings)

    if "hooks" not in result or "SessionStart" not in result["hooks"]:
        return result

    result["hooks"]["SessionStart"] = [
        entry for entry in result["hooks"]["SessionStart"]
        if not any(HOOK_MARKER in h.get("command", "") for h in entry.get("hooks", []))
    ]
    if not result["hooks"]["SessionStart"]:
        del result["hooks"]["SessionStart"]
    if not result["hooks"]:
        del result["hooks"]
    return result


def atomic_write(path: str, content: str) -> None:
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            f.write(content)
        os.rename(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_settings(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def main():
    args = sys.argv[1:]

    if "--install-hook" in args:
        idx = args.index("--install-hook")
        if len(args) < idx + 3:
            print("Usage: merge-settings.py --install-hook <hook-command> <settings-file>", file=sys.stderr)
            sys.exit(1)
        hook_cmd = args[idx + 1]
        settings_path = args[idx + 2]
        settings = load_settings(settings_path)
        result = add_hook(settings, hook_cmd)
        atomic_write(settings_path, json.dumps(result, indent=2) + "\n")
        return

    if "--remove-hook" in args:
        idx = args.index("--remove-hook")
        if len(args) < idx + 2:
            print("Usage: merge-settings.py --remove-hook <settings-file>", file=sys.stderr)
            sys.exit(1)
        settings_path = args[idx + 1]
        settings = load_settings(settings_path)
        result = remove_hook(settings)
        atomic_write(settings_path, json.dumps(result, indent=2) + "\n")
        return

    dry_run = "--dry-run" in args
    only_if_changed = "--only-if-changed" in args
    positional = [a for a in args if not a.startswith("--")]

    if len(positional) != 2:
        print("Usage: merge-settings.py <generated> <user-settings> [--dry-run] [--only-if-changed]", file=sys.stderr)
        sys.exit(1)

    generated_path, user_path = positional

    with open(generated_path) as f:
        generated = json.load(f)

    user = load_settings(user_path)
    merged = merge(generated, user)
    output = json.dumps(merged, indent=2) + "\n"

    if dry_run:
        print(output, end="")
        return

    if only_if_changed and os.path.exists(user_path):
        with open(user_path) as f:
            if f.read() == output:
                return

    atomic_write(user_path, output)


if __name__ == "__main__":
    main()
