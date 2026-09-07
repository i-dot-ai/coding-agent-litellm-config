# coding-agent-litellm-config

Auto-generated [Claude Code](https://docs.anthropic.com/en/docs/build-with-claude/claude-code) configuration for our [LiteLLM](https://github.com/BerriAI/litellm) proxy.

## Problem

Claude Code needs configuration to route through LiteLLM's Bedrock pass-through endpoint, with the correct model names pinned. Model names are custom LiteLLM aliases, so which alias is "the current opus/sonnet/haiku model" has to come from somewhere - this repo reads it from the gateway's own config rather than guessing from the name.

## Solution

The `generate.py` script:
1. Reads the LiteLLM `config.yml`
2. Picks the one model per tier (opus/sonnet/haiku) flagged with `model_info.claude_tier` in that file
3. Generates a `claude-settings.json` for Claude Code with Bedrock pass-through configuration

## Usage

### Claude Code

The generated `claude-settings.json` configures Claude Code to use LiteLLM's Bedrock pass-through, pinned to whichever models the gateway's `config.yml` has tagged with `claude_tier: opus|sonnet|haiku`.

#### Install (works before or after installing Claude Code)

```bash
git clone git@github.com:i-dot-ai/coding-agent-litellm-config.git
cd coding-agent-litellm-config
./install.sh
```

The install script will:
1. Deep-merge `claude-settings.json` into `~/.claude/settings.json` (creating it if it doesn't exist, preserving your existing hooks, plugins, and extra env vars if it does)
2. Prompt for your LiteLLM API key (`ANTHROPIC_AUTH_TOKEN`) and save it to settings — you can also skip and add it later
3. Register a `SessionStart` hook so Claude Code auto-pulls updates when a new session starts (throttled to once per hour, runs in background)

The install works from any branch — if `claude-settings.json` doesn't exist locally, it reads it from `origin/main`.

The API key is per-user and not included in the generated config, but the merge preserves it across updates.

Now install and run Claude Code:

```bash
npm install -g @anthropic-ai/claude-code
claude
```

#### Rollback and pause

A backup of your settings is saved before each auto-update to `~/.config/coding-agent-litellm-config/settings.json.backup`.

To restore and pause auto-updates:
```bash
cp ~/.config/coding-agent-litellm-config/settings.json.backup ~/.claude/settings.json
touch ~/.config/coding-agent-litellm-config/paused
```

To resume auto-updates:
```bash
rm ~/.config/coding-agent-litellm-config/paused
```

#### Uninstall

```bash
./uninstall.sh
```

Removes the auto-update hook. Your other settings (hooks, plugins, env vars) are preserved.

#### What the generated settings contain

```json
{
  "model": "bedrock-claude-4.6-opus",
  "env": {
    "ANTHROPIC_BEDROCK_BASE_URL": "https://llm-gateway.i.ai.gov.uk/bedrock",
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "CLAUDE_CODE_SKIP_BEDROCK_AUTH": "1",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "bedrock-claude-4.6-opus",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "bedrock-claude-4.6-sonnet",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "bedrock-claude-4.5-haiku"
  }
}
```

- `CLAUDE_CODE_USE_BEDROCK` tells Claude Code to use the Bedrock API format
- `CLAUDE_CODE_SKIP_BEDROCK_AUTH` skips local AWS auth since LiteLLM handles authentication with AWS
- `ANTHROPIC_BEDROCK_BASE_URL` points to LiteLLM's Bedrock pass-through endpoint
- `ANTHROPIC_DEFAULT_*_MODEL` pins Claude Code to specific model aliases from the LiteLLM config

The model names come from whichever Bedrock Claude model in `config.yml` has `model_info.claude_tier` set to that tier - see the comments in `core-llm-gateway`'s `backend/config/config.yml` for how to move the tag to a newer model.

### Regenerate manually

```bash
pip install -r requirements.txt

python generate.py \
  --litellm-config /path/to/core-llm-gateway/backend/config/config.yml \
  --base-url "https://llm-gateway.i.ai.gov.uk/v1" \
  --output claude-settings.json
```

### Automatic updates

**Server-side:** A GitHub Action runs daily and whenever the litellm config changes, regenerating `claude-settings.json` and committing any updates.

**Client-side:** If you ran `./install.sh`, Claude Code will fetch `origin/main` on new session start (background, throttled to once/hour) and merge any changes into `~/.claude/settings.json`. This works regardless of which branch is checked out locally.

To trigger from `core-llm-gateway` when the config changes, add a dispatch step to the gateway's CI:

```yaml
- name: Trigger claude-settings config update
  if: contains(github.event.commits.*.modified, 'backend/config/config.yml')
  uses: peter-evans/repository-dispatch@v3
  with:
    token: ${{ secrets.GH_PAT }}
    repository: i-dot-ai/coding-agent-litellm-config
    event-type: litellm-config-updated
```

## OpenCode

This repo doesn't generate config for [OpenCode](https://opencode.ai). Use the [opencode-litellm](https://github.com/yuseferi/opencode-litellm) plugin instead - it discovers the gateway's models directly from its `/v1/models` endpoint at startup, so there's no file to generate or keep in sync:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["opencode-plugin-litellm@latest"],
  "provider": {
    "litellm": {
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "https://llm-gateway.i.ai.gov.uk/v1"
      }
    }
  }
}
```

See that plugin's README for full setup and authentication details.
