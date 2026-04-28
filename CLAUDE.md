# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Does

Generates configuration files for [OpenCode](https://opencode.ai) and [Claude Code](https://docs.anthropic.com/en/docs/build-with-claude/claude-code) from a [LiteLLM](https://github.com/BerriAI/litellm) proxy config. The core problem: coding tools can't look up model capabilities (vision, costs, context limits) when model names are custom LiteLLM aliases. This script bridges that gap by fetching metadata from models.dev and mapping it to the aliases.

## Architecture

**Generation** (`generate.py`) with two output paths:

1. **OpenCode path**: Reads LiteLLM `config.yml` → fetches models.dev metadata → maps provider prefixes to models.dev providers → writes `opencode.json` with full model capabilities
2. **Claude Code path**: Scans LiteLLM config for bedrock Claude models → auto-detects latest opus/sonnet/haiku by version number → writes `claude-settings.json` with Bedrock pass-through env vars

Provider prefix mapping (e.g. `bedrock/` → `amazon-bedrock`, `vertex_ai/` → `google-vertex`) is in `LITELLM_TO_MODELSDEV_PROVIDER`. Model lookup falls back through: direct match → strip region prefix (for bedrock `eu.`/`us.` etc.) → longest prefix match with version delimiter.

**Auto-update** (client-side, Claude Code only):
- `install.sh` — one-time setup: deep-merges `claude-settings.json` into `~/.claude/settings.json` and registers a `SessionStart` hook
- `update-claude-settings.sh` — hook target: background `git pull` + conditional merge (throttled to 1/hour)
- `uninstall.sh` — removes the hook and state
- `merge-settings.py` — shared merge logic: updates `env` keys and `model` from generated file while preserving user's hooks, plugins, and extra env vars

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Generate configs (requires access to a litellm config.yml)
python generate.py \
  --litellm-config /path/to/config.yml \
  --base-url "https://llm-gateway.i.ai.gov.uk/v1" \
  --output opencode.json \
  --claude-output claude-settings.json
```

```bash
# Run tests
python3 -m unittest discover -s tests

# Install auto-update for Claude Code
./install.sh

# Uninstall
./uninstall.sh
```

## CI

GitHub Action (`.github/workflows/update-config.yml`) runs daily and on `repository_dispatch` from `core-llm-gateway`. It fetches the litellm config via GitHub App token, regenerates both JSON files, and auto-commits changes.
