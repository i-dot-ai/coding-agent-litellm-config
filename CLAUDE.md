# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Does

Generates `claude-settings.json` for [Claude Code](https://docs.anthropic.com/en/docs/build-with-claude/claude-code) from a [LiteLLM](https://github.com/BerriAI/litellm) proxy config, so it routes through LiteLLM's Bedrock pass-through with the right opus/sonnet/haiku model aliases pinned.

This repo doesn't generate config for [OpenCode](https://opencode.ai) - see the README's "OpenCode" section, which points at the [opencode-litellm](https://github.com/yuseferi/opencode-litellm) plugin instead (it discovers models live from the gateway, no generated file needed).

## Architecture

**Generation** (`generate.py`):

Reads LiteLLM `config.yml` → picks the one model per tier tagged `model_info.claude_tier: opus|sonnet|haiku` → writes `claude-settings.json` with Bedrock pass-through env vars. `detect_claude_models()` does the tag lookup; it deliberately does *not* guess a model's tier from its name.

**Auto-update** (client-side, Claude Code only):
- `install.sh` — one-time setup: deep-merges `claude-settings.json` into `~/.claude/settings.json` and registers a `SessionStart` hook
- `update-claude-settings.sh` — hook target: background `git pull` + conditional merge (throttled to 1/hour)
- `uninstall.sh` — removes the hook and state
- `merge-settings.py` — shared merge logic: updates `env` keys and `model` from generated file while preserving user's hooks, plugins, and extra env vars

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Generate claude-settings.json (requires access to a litellm config.yml)
python generate.py \
  --litellm-config /path/to/config.yml \
  --base-url "https://llm-gateway.i.ai.gov.uk/v1" \
  --output claude-settings.json
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

GitHub Action (`.github/workflows/update-config.yml`) runs daily and on `repository_dispatch` from `core-llm-gateway`. It fetches the litellm config via GitHub App token, regenerates `claude-settings.json`, and auto-commits changes.
