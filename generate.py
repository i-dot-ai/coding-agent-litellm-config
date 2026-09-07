#!/usr/bin/env python3
"""
Generate claude-settings.json from a litellm config.yml.

Claude Code needs configuration to route through LiteLLM's Bedrock
pass-through endpoint, with the correct model names pinned. This script:

1. Reads the litellm proxy config.yml
2. Picks the one model per tier (opus/sonnet/haiku) flagged with
   `model_info.claude_tier` in that file - not by guessing from the model
   name, so the gateway config is the single source of truth for which
   model each tier should point at.
3. Writes a claude-settings.json with Bedrock pass-through env vars

OpenCode isn't handled by this script any more: the opencode-litellm
plugin (https://github.com/yuseferi/opencode-litellm) discovers this
gateway's models directly from its /v1/models endpoint at startup, so
there's no config file to generate for it.

Usage:
    python generate.py --litellm-config path/to/config.yml --base-url https://llm-gateway.example.com/v1
    python generate.py --litellm-config path/to/config.yml --base-url https://llm-gateway.example.com/v1 --output claude-settings.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

import yaml

CLAUDE_TIERS = ("opus", "sonnet", "haiku")

CLAUDE_TIER_ENV_VAR = {
    "opus": "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "sonnet": "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "haiku": "ANTHROPIC_DEFAULT_HAIKU_MODEL",
}


def parse_litellm_config(config_path: str) -> list[dict]:
    """Parse a litellm config.yml and return the model list."""
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config.get("model_list", [])


def detect_claude_models(litellm_models: list[dict]) -> dict[str, Optional[str]]:
    """
    Picks the opus/sonnet/haiku models to pin Claude Code to, so it uses
    specific model names rather than aliases. Relies entirely on the
    explicit `model_info.claude_tier` field set in config.yml - see that
    file's comments - rather than guessing a model's tier from its name.

    Returns a dict with keys 'opus', 'sonnet', 'haiku' mapped to
    model_name strings (or None if no model in config.yml has that tier
    set).
    """
    result: dict[str, Optional[str]] = {tier: None for tier in CLAUDE_TIERS}
    for entry in litellm_models:
        model_name = entry.get("model_name", "")
        model_info = entry.get("model_info") or {}
        tier = model_info.get("claude_tier")
        if tier in CLAUDE_TIERS and result[tier] is None:
            result[tier] = model_name
    return result


def generate_claude_settings(base_url: str, litellm_models: list[dict]) -> dict:
    """
    Generate a claude-settings.json for Claude Code with Bedrock pass-through.

    The settings configure Claude Code to route through LiteLLM's /bedrock
    endpoint, skipping local AWS auth (LiteLLM handles it).

    API key (ANTHROPIC_AUTH_TOKEN) is NOT included -- install.sh prompts
    for it separately and merge-settings.py preserves it across updates.
    """
    # Derive bedrock URL from base URL: strip trailing /v1 and append /bedrock.
    bedrock_url = re.sub(r"/v1/?$", "", base_url) + "/bedrock"

    claude_models = detect_claude_models(litellm_models)
    if not any(claude_models.values()):
        print(
            "WARNING: No models in config.yml have a claude_tier set - claude-settings.json will have no pinned models",
            file=sys.stderr,
        )
    for tier in CLAUDE_TIERS:
        print(f"  Claude Code {tier}: {claude_models[tier] or 'not found'}", file=sys.stderr)

    env: dict[str, str] = {
        "ANTHROPIC_BEDROCK_BASE_URL": bedrock_url,
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "CLAUDE_CODE_SKIP_BEDROCK_AUTH": "1",
    }
    for tier in CLAUDE_TIERS:
        model_name = claude_models[tier]
        if model_name is not None:
            env[CLAUDE_TIER_ENV_VAR[tier]] = model_name

    result: dict = {"env": env}

    # Default to the best opus model, falling back to sonnet.
    default_model = claude_models["opus"] or claude_models["sonnet"]
    if default_model is not None:
        result["model"] = default_model

    return result


def main():
    parser = argparse.ArgumentParser(description="Generate claude-settings.json from a litellm config.yml")
    parser.add_argument(
        "--litellm-config",
        required=True,
        help="Path to litellm config.yml",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="LiteLLM proxy base URL (e.g., https://llm-gateway.example.com/v1)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path for claude-settings.json (default: stdout)",
    )

    args = parser.parse_args()

    litellm_models = parse_litellm_config(args.litellm_config)
    settings = generate_claude_settings(base_url=args.base_url, litellm_models=litellm_models)
    output = json.dumps(settings, indent=2) + "\n"

    if args.output:
        Path(args.output).write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
