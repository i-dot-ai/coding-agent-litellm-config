# opencode-litellm-config

Auto-generated [OpenCode](https://opencode.ai) configuration for our [LiteLLM](https://github.com/BerriAI/litellm) proxy.

## Problem

When using OpenCode with a LiteLLM proxy via `@ai-sdk/openai-compatible`, OpenCode cannot look up model capabilities (vision, PDF support, reasoning, costs, context limits) from [models.dev](https://models.dev) because the model names are custom aliases that don't match any known provider/model entries.

This means features like image input silently fail — OpenCode strips the image before it ever reaches the proxy.

## Solution

The `generate.py` script:
1. Reads the LiteLLM `config.yml` to get model aliases and their underlying provider models
2. Fetches the full model metadata from models.dev
3. Maps litellm provider prefixes (`azure/`, `bedrock/`, `vertex_ai/`) to models.dev providers
4. Generates an `opencode.json` with full metadata (modalities, costs, limits, capabilities)

## Usage

### Copy the config

Copy or symlink `opencode.json` to your global opencode config:

```bash
cp opencode.json ~/.config/opencode/opencode.json
```

Or symlink it:
```bash
ln -sf $(pwd)/opencode.json ~/.config/opencode/opencode.json
```

### Regenerate manually

```bash
pip install -r requirements.txt

python generate.py \
  --litellm-config /path/to/core-llm-gateway/backend/config/config.yml \
  --base-url "https://llm-gateway.i.ai.gov.uk/v1" \
  --output opencode.json
```

### Automatic updates

A GitHub Action runs daily and whenever the litellm config changes, regenerating `opencode.json` and committing any updates.

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
