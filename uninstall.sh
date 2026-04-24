#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SETTINGS_FILE="${SETTINGS_FILE:-${HOME}/.claude/settings.json}"
STATE_DIR="${STATE_DIR:-${HOME}/.config/coding-agent-litellm-config}"
MERGE_SCRIPT="${REPO_DIR}/merge-settings.py"

if [ -f "$SETTINGS_FILE" ]; then
  python3 "$MERGE_SCRIPT" --remove-hook "$SETTINGS_FILE"
fi

# Guard: only remove if STATE_DIR is under ~/.config/ and non-empty string
if [ -n "$STATE_DIR" ] && [ -d "$STATE_DIR" ]; then
  case "$STATE_DIR" in
    "$HOME"/.config/*)
      rm -rf "$STATE_DIR"
      ;;
    *)
      echo "Warning: STATE_DIR ($STATE_DIR) is outside ~/.config/, not removing automatically." >&2
      ;;
  esac
fi

echo "Uninstalled. SessionStart hook removed."
echo "Your other settings (hooks, plugins, env vars) are preserved."
