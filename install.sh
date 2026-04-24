#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SETTINGS_FILE="${SETTINGS_FILE:-${HOME}/.claude/settings.json}"
STATE_DIR="${STATE_DIR:-${HOME}/.config/coding-agent-litellm-config}"
GENERATED_FILE="${GENERATED_FILE:-${REPO_DIR}/claude-settings.json}"
MERGE_SCRIPT="${REPO_DIR}/merge-settings.py"
UPDATE_SCRIPT="${REPO_DIR}/update-claude-settings.sh"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but not found." >&2
  exit 1
fi

if [ ! -f "$GENERATED_FILE" ]; then
  echo "Error: $GENERATED_FILE not found. Run generate.py first." >&2
  exit 1
fi

mkdir -p "$(dirname "$SETTINGS_FILE")"
mkdir -p "$STATE_DIR"

# Single atomic operation: merge settings then add hook
python3 "$MERGE_SCRIPT" "$GENERATED_FILE" "$SETTINGS_FILE"
python3 "$MERGE_SCRIPT" --install-hook "$UPDATE_SCRIPT" "$SETTINGS_FILE"

echo "Installed. Claude Code will auto-sync settings on session start."
echo "  Hook: $UPDATE_SCRIPT"
echo "  To uninstall: $REPO_DIR/uninstall.sh"
