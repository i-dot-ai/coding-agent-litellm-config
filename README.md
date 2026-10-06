# coding-agent-litellm-config

Auto-generated [OpenCode](https://opencode.ai) and [Claude Code](https://docs.anthropic.com/en/docs/build-with-claude/claude-code) configuration for our [LiteLLM](https://github.com/BerriAI/litellm) proxy.

## Problem

When using OpenCode with a LiteLLM proxy via `@ai-sdk/openai-compatible`, OpenCode cannot look up model capabilities (vision, PDF support, reasoning, costs, context limits) from [models.dev](https://models.dev) because the model names are custom aliases that don't match any known provider/model entries.

This means features like image input silently fail — OpenCode strips the image before it ever reaches the proxy.

Claude Code also needs configuration to route through LiteLLM's Bedrock pass-through endpoint, with the correct model names pinned.

## Solution

The `generate.py` script:
1. Reads the LiteLLM `config.yml` to get model aliases and their underlying provider models
2. Fetches the full model metadata from models.dev
3. Maps litellm provider prefixes (`azure/`, `bedrock/`, `vertex_ai/`) to models.dev providers
4. Generates an `opencode.json` with full metadata (modalities, costs, limits, capabilities)
5. Generates a `claude-settings.json` for Claude Code with Bedrock pass-through configuration

## Usage

### OpenCode

Copy or symlink `opencode.json` to your global opencode config:

```bash
cp opencode.json ~/.config/opencode/opencode.json
```

Or symlink it:
```bash
ln -sf $(pwd)/opencode.json ~/.config/opencode/opencode.json
```

### Claude Code

The generated `claude-settings.json` configures Claude Code to use LiteLLM's Bedrock pass-through. It auto-detects the latest fable, opus, sonnet, and haiku models from the LiteLLM config.

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

#### Keeping your API key in 1Password

Rather than saving your key in plaintext, store it in 1Password and press Enter to skip the key prompt during install. Copy the key's reference (right-click the field in 1Password → **Copy Secret Reference**) and add to your shell profile (`~/.zshrc`):

```bash
export ANTHROPIC_AUTH_TOKEN="op://<vault>/<item>/<field>"
alias claude='op run -- claude'
```

Open a new terminal to pick it up. `op run` ([1Password CLI](https://developer.1password.com/docs/cli/get-started/)) resolves the key only for the `claude` process, so this works when launching from a terminal, not from IDE extensions or desktop apps. A key already under `env` in `~/.claude/settings.json` takes precedence, so remove it.

For OpenCode, add `"apiKey": "{env:LITELLM_API_KEY}"` to the `litellm` provider's `options`, set `LITELLM_API_KEY` and alias `opencode` the same way, then run `opencode auth logout` to remove any stored key.

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
  "model": "bedrock-claude-fable-5-1-global",
  "env": {
    "ANTHROPIC_BEDROCK_BASE_URL": "https://llm-gateway.i.ai.gov.uk/bedrock",
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "CLAUDE_CODE_SKIP_BEDROCK_AUTH": "1",
    "ANTHROPIC_DEFAULT_FABLE_MODEL": "bedrock-claude-fable-5-1-global",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "bedrock-claude-opus-5-5-eu",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "bedrock-claude-sonnet-5-5-eu",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "bedrock-claude-haiku-4-5-eu"
  }
}
```

- `CLAUDE_CODE_USE_BEDROCK` tells Claude Code to use the Bedrock API format
- `CLAUDE_CODE_SKIP_BEDROCK_AUTH` skips local AWS auth since LiteLLM handles authentication with AWS
- `ANTHROPIC_BEDROCK_BASE_URL` points to LiteLLM's Bedrock pass-through endpoint
- `ANTHROPIC_DEFAULT_*_MODEL` pins Claude Code to specific model aliases from the LiteLLM config
- `model` is the default, chosen in preference order fable > opus > sonnet

The model names are auto-detected from the LiteLLM config by finding bedrock Claude models and picking the latest version of each tier (fable, opus, sonnet, haiku). A tier is only emitted if a matching model exists in the config. Where the upstream config sets `model_info.claude_tier`, that marker is authoritative; otherwise the tier is inferred from the model name.

Note: selecting a model from Claude Code's built-in `/model` picker writes the raw Bedrock model ID (e.g. `eu.anthropic.claude-fable-5-1`) to your settings, which the gateway will reject. Use the LiteLLM alias instead (e.g. `/model bedrock-claude-fable-5-1-global`), or rely on the generated default.

### Regenerate manually

```bash
pip install -r requirements.txt

python generate.py \
  --litellm-config /path/to/core-llm-gateway/backend/config/config.yml \
  --base-url "https://llm-gateway.i.ai.gov.uk/v1" \
  --output opencode.json \
  --claude-output claude-settings.json
```

### Automatic updates

**Server-side:** A GitHub Action runs daily and whenever the litellm config changes, regenerating both `opencode.json` and `claude-settings.json` and committing any updates.

**Client-side:** If you ran `./install.sh`, Claude Code will fetch `origin/main` on new session start (background, throttled to once/hour) and merge any changes into `~/.claude/settings.json`. This works regardless of which branch is checked out locally.

To trigger from `core-llm-gateway` when the config changes, add a dispatch step to the gateway's CI:

```yaml
- name: Trigger opencode config update
  if: contains(github.event.commits.*.modified, 'backend/config/config.yml')
  uses: peter-evans/repository-dispatch@v3
  with:
    token: ${{ secrets.GH_PAT }}
    repository: i-dot-ai/coding-agent-litellm-config
    event-type: litellm-config-updated
```

## Provider mapping

| LiteLLM prefix | models.dev provider |
|---|---|
| `azure/` | `azure` |
| `bedrock/` | `amazon-bedrock` |
| `vertex_ai/` | `google-vertex` |
| `openai/` | `openai` |
| `anthropic/` | `anthropic` |
| `gemini/` | `google` |
| `mistral/` | `mistral` |

## What gets mapped

For each model, the script copies from models.dev:
- `modalities` (input: text/image/pdf/audio/video, output: text)
- `limit` (context window, max output tokens)
- `cost` (input/output per million tokens, cache read/write)
- `reasoning`, `temperature`, `tool_call`, `attachment` capability flags
