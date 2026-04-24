#!/usr/bin/env bash
# Called by Claude Code SessionStart hook. Must be fast, silent, non-fatal.
# Forks to background immediately so session startup is never delayed.
set +e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${STATE_DIR:-${HOME}/.config/coding-agent-litellm-config}"
GENERATED_FILE="${REPO_DIR}/claude-settings.json"
SETTINGS_FILE="${SETTINGS_FILE:-${HOME}/.claude/settings.json}"
MERGE_SCRIPT="${REPO_DIR}/merge-settings.py"
THROTTLE_SECONDS=3600
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
  esac
done

[ -d "$REPO_DIR/.git" ] || exit 0

# Everything runs in background — zero latency on session start
(
  THROTTLE_FILE="${STATE_DIR}/.last-update"
  LOCK_DIR="${STATE_DIR}/.update-lock"
  FAIL_FILE="${STATE_DIR}/.consecutive-pull-failures"

  export GIT_TERMINAL_PROMPT=0
  mkdir -p "$STATE_DIR"

  # Pause file: skip updates entirely when present (unless --force)
  if [ "$FORCE" -eq 0 ] && [ -f "${STATE_DIR}/paused" ]; then
    exit 0
  fi

  # Throttle: skip if checked recently (unless --force)
  if [ "$FORCE" -eq 0 ] && [ -f "$THROTTLE_FILE" ]; then
    LAST=$(cat "$THROTTLE_FILE" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    if [ $(( NOW - LAST )) -lt $THROTTLE_SECONDS ]; then
      exit 0
    fi
  fi

  # Acquire lockfile (skip if another instance is running)
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    if [ -f "$LOCK_DIR/pid" ]; then
      LOCK_PID=$(cat "$LOCK_DIR/pid" 2>/dev/null || echo 0)
      if [ "$LOCK_PID" -gt 0 ] 2>/dev/null && ! kill -0 "$LOCK_PID" 2>/dev/null; then
        rm -rf "$LOCK_DIR" 2>/dev/null
        mkdir "$LOCK_DIR" 2>/dev/null || exit 0
      else
        exit 0
      fi
    else
      exit 0
    fi
  fi

  echo $$ > "$LOCK_DIR/pid" 2>/dev/null
  trap 'rm -rf "$LOCK_DIR" 2>/dev/null' EXIT

  BASENAME="$(basename "$GENERATED_FILE")"

  # Get current hash from origin/main (works regardless of checked-out branch)
  OLD_HASH=$(git -C "$REPO_DIR" show "origin/main:$BASENAME" 2>/dev/null | shasum 2>/dev/null | cut -d' ' -f1)

  # Fetch latest main from origin
  if git -C "$REPO_DIR" fetch origin main --quiet 2>/dev/null; then
    rm -f "$FAIL_FILE" 2>/dev/null
  else
    FAILURES=$(cat "$FAIL_FILE" 2>/dev/null || echo 0)
    FAILURES=$(( FAILURES + 1 ))
    echo "$FAILURES" > "$FAIL_FILE" 2>/dev/null
  fi

  date +%s > "$THROTTLE_FILE" 2>/dev/null

  NEW_HASH=$(git -C "$REPO_DIR" show "origin/main:$BASENAME" 2>/dev/null | shasum 2>/dev/null | cut -d' ' -f1)

  if [ "$OLD_HASH" != "$NEW_HASH" ] && [ -n "$NEW_HASH" ]; then
    # Extract the file from origin/main and merge it
    TMPFILE="${STATE_DIR}/.claude-settings-latest.json"
    if git -C "$REPO_DIR" show "origin/main:$BASENAME" > "$TMPFILE" 2>/dev/null; then
      # Backup current settings before merging
      if [ -f "$SETTINGS_FILE" ]; then
        cp "$SETTINGS_FILE" "${STATE_DIR}/settings.json.backup" 2>/dev/null
      fi
      python3 "$MERGE_SCRIPT" "$TMPFILE" "$SETTINGS_FILE" --only-if-changed 2>/dev/null
      rm -f "$TMPFILE" 2>/dev/null
    fi
  fi
) &

exit 0
