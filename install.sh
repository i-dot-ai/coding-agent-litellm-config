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

# If generated file doesn't exist on disk (e.g. on a feature branch),
# extract it from origin/main
if [ ! -f "$GENERATED_FILE" ]; then
  git -C "$REPO_DIR" fetch origin main --quiet 2>/dev/null || true
  BASENAME="$(basename "$GENERATED_FILE")"
  if git -C "$REPO_DIR" show "origin/main:$BASENAME" >/dev/null 2>&1; then
    git -C "$REPO_DIR" show "origin/main:$BASENAME" > "$GENERATED_FILE.from-main"
    GENERATED_FILE="$GENERATED_FILE.from-main"
    echo "Note: using $BASENAME from origin/main (not on current branch)." >&2
  else
    echo "Error: $GENERATED_FILE not found and not available on origin/main." >&2
    echo "Run generate.py first." >&2
    exit 1
  fi
fi

mkdir -p "$(dirname "$SETTINGS_FILE")"
mkdir -p "$STATE_DIR"

python3 "$MERGE_SCRIPT" "$GENERATED_FILE" "$SETTINGS_FILE"

# Clean up temp file if we extracted from origin/main
[ "${GENERATED_FILE%.from-main}" != "$GENERATED_FILE" ] && rm -f "$GENERATED_FILE"
python3 "$MERGE_SCRIPT" --install-hook "$UPDATE_SCRIPT" "$SETTINGS_FILE"

# Check if API key is already configured
HAS_KEY=$(python3 -c "
import json, os, sys
path = sys.argv[1]
if os.path.exists(path):
    s = json.load(open(path))
    if s.get('env', {}).get('ANTHROPIC_AUTH_TOKEN'):
        print('yes')
" "$SETTINGS_FILE" 2>/dev/null)

if [ "$HAS_KEY" = "yes" ]; then
  echo "API key (ANTHROPIC_AUTH_TOKEN) is already configured."
else
  API_KEY=""
  if [ -t 0 ]; then
    printf "Enter your LiteLLM API key (ANTHROPIC_AUTH_TOKEN), or press Enter to skip: "
    read -r API_KEY
  else
    read -r API_KEY 2>/dev/null || true
  fi

  if [ -n "$API_KEY" ]; then
    TMPGEN=$(mktemp)
    printf '{"env":{"ANTHROPIC_AUTH_TOKEN":"%s"}}' "$API_KEY" > "$TMPGEN"
    python3 "$MERGE_SCRIPT" "$TMPGEN" "$SETTINGS_FILE"
    rm -f "$TMPGEN"
    echo "API key saved to $SETTINGS_FILE."
  else
    echo ""
    echo "API key (ANTHROPIC_AUTH_TOKEN) not found. To add it later:"
    echo "  Add to ~/.claude/settings.json under env:"
    echo "    \"ANTHROPIC_AUTH_TOKEN\": \"sk-your-key\""
  fi
fi

echo ""
echo "Installed. Claude Code will auto-sync settings on session start."
echo "  Hook: $UPDATE_SCRIPT"
echo "  To uninstall: $REPO_DIR/uninstall.sh"
