# opencode-litellm-config

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

The generated `claude-settings.json` configures Claude Code to use LiteLLM's Bedrock pass-through. It auto-detects the latest opus, sonnet, and haiku models from the LiteLLM config.

1. Copy the settings file:

   ```bash
   cp claude-settings.json ~/.claude/settings.json
   ```

   Or merge it into your existing `~/.claude/settings.json` if you have other settings.

2. Set your LiteLLM API key in your shell profile (`~/.zshrc` or `~/.bash_profile`):

   ```bash
   export ANTHROPIC_AUTH_TOKEN=sk-your-litellm-key
   ```

   The API key is intentionally **not** included in `claude-settings.json` so it doesn't get overwritten when the config is regenerated.

3. Run Claude Code:

   ```bash
   claude
   ```

   It will use the Bedrock pass-through to route requests through LiteLLM.

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

The model names are auto-detected from the LiteLLM config by finding bedrock Claude models and picking the latest version of each tier (opus, sonnet, haiku).

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

A GitHub Action runs daily and whenever the litellm config changes, regenerating both `opencode.json` and `claude-settings.json` and committing any updates.

To trigger from `core-llm-gateway` when the config changes, add a dispatch step to the gateway's CI:

```yaml
- name: Trigger opencode config update
  if: contains(github.event.commits.*.modified, 'backend/config/config.yml')
  uses: peter-evans/repository-dispatch@v3
  with:
    token: ${{ secrets.GH_PAT }}
    repository: i-dot-ai/opencode-litellm-config
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
