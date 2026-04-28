#!/usr/bin/env python3
"""
Generate opencode.json and claude-settings.json from a litellm config.yml and models.dev metadata.

This script:
1. Reads the litellm proxy config.yml to get model aliases and their underlying models
2. Fetches model metadata from models.dev (capabilities, costs, limits, etc.)
3. Maps litellm provider prefixes to models.dev provider IDs
4. Generates an opencode.json with full model metadata
5. Generates a claude-settings.json for Claude Code with Bedrock pass-through config

Usage:
    python generate.py --litellm-config path/to/config.yml --base-url https://llm-gateway.example.com/v1
    python generate.py --litellm-config path/to/config.yml --base-url https://llm-gateway.example.com/v1 --output opencode.json
    python generate.py --litellm-config path/to/config.yml --base-url https://llm-gateway.example.com/v1 --output opencode.json --claude-output claude-settings.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen, Request

import yaml

MODELS_DEV_URL = "https://models.dev/api.json"

# Mapping from litellm provider prefix to models.dev provider ID
LITELLM_TO_MODELSDEV_PROVIDER = {
    "azure": "azure",
    "bedrock": "amazon-bedrock",
    "vertex_ai": "google-vertex",
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "google",
    "cohere": "cohere",
    "mistral": "mistral",
}

# Models that are not chat models and should be excluded from opencode config
EXCLUDED_MODES = {"audio_transcription", "embedding", "image_generation"}


def fetch_models_dev() -> dict:
    """Fetch the full models.dev API data."""
    print("Fetching models.dev metadata...", file=sys.stderr)
    req = Request(MODELS_DEV_URL, headers={"User-Agent": "opencode-litellm-config/1.0"})
    with urlopen(req) as resp:
        return json.loads(resp.read())


def parse_litellm_config(config_path: str) -> list[dict]:
    """Parse a litellm config.yml and return the model list."""
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config.get("model_list", [])


def parse_litellm_model(litellm_model: str) -> tuple[str, str]:
    """
    Parse a litellm model string like 'bedrock/eu.anthropic.claude-opus-4-6-v1'
    into (provider_prefix, model_id).
    """
    if "/" not in litellm_model:
        return ("", litellm_model)
    parts = litellm_model.split("/", 1)
    return (parts[0], parts[1])


def lookup_modelsdev(
    models_dev: dict, provider_prefix: str, model_id: str
) -> Optional[dict]:
    """
    Look up a model in models.dev data.
    Returns the model metadata dict or None if not found.
    """
    modelsdev_provider_id = LITELLM_TO_MODELSDEV_PROVIDER.get(provider_prefix)
    if not modelsdev_provider_id:
        return None

    provider_data = models_dev.get(modelsdev_provider_id, {})
    models = provider_data.get("models", {})

    # Direct lookup
    if model_id in models:
        return models[model_id]

    # For bedrock models with region prefix (e.g., eu.anthropic.claude-opus-4-6-v1)
    # also try without the region prefix
    if "." in model_id:
        parts = model_id.split(".", 1)
        if parts[0] in ("us", "eu", "global", "ap"):
            without_region = parts[1]
            if without_region in models:
                return models[without_region]

    # Try matching the base model name (strip version suffixes like -v1:0, -2024-08-06)
    # Only match if the models.dev entry id is a prefix of our model_id
    # and the next character after the prefix is a version delimiter
    best_match = None
    best_len = 0
    for candidate_id, candidate in models.items():
        if model_id == candidate_id:
            return candidate
        # Check if candidate_id is a proper prefix of model_id
        # (model_id has extra version/date suffix)
        if model_id.startswith(candidate_id) and len(candidate_id) > best_len:
            rest = model_id[len(candidate_id) :]
            # Ensure the remaining part looks like a version suffix
            if rest and rest[0] in ("-", ":", "."):
                best_match = candidate
                best_len = len(candidate_id)

    return best_match


def build_opencode_model(
    model_name: str, litellm_entry: dict, models_dev: dict
) -> Optional[dict]:
    """
    Build an opencode model config entry from a litellm model entry.
    Returns the model config dict or None if the model should be excluded.
    """
    litellm_params = litellm_entry.get("litellm_params", {})
    model_info = litellm_entry.get("model_info", {})

    # Skip non-chat models
    mode = model_info.get("mode")
    if mode in EXCLUDED_MODES:
        return None

    litellm_model = litellm_params.get("model", "")
    provider_prefix, underlying_model_id = parse_litellm_model(litellm_model)

    # Skip embedding and audio models based on litellm model name
    if any(
        x in underlying_model_id.lower()
        for x in ["embedding", "whisper", "tts", "dall-e"]
    ):
        return None

    # Look up in models.dev
    modelsdev_model = lookup_modelsdev(models_dev, provider_prefix, underlying_model_id)

    result = {"name": model_name}

    if modelsdev_model:
        # Copy relevant fields from models.dev
        if "modalities" in modelsdev_model:
            result["modalities"] = modelsdev_model["modalities"]

        if "limit" in modelsdev_model:
            result["limit"] = {}
            if "context" in modelsdev_model["limit"]:
                result["limit"]["context"] = modelsdev_model["limit"]["context"]
            if "output" in modelsdev_model["limit"]:
                result["limit"]["output"] = modelsdev_model["limit"]["output"]

        if "cost" in modelsdev_model:
            cost = modelsdev_model["cost"]
            result["cost"] = {
                "input": cost.get("input", 0),
                "output": cost.get("output", 0),
            }
            if "cache_read" in cost:
                result["cost"]["cache_read"] = cost["cache_read"]
            if "cache_write" in cost:
                result["cost"]["cache_write"] = cost["cache_write"]

        # Boolean capability flags
        for field in ["reasoning", "temperature", "tool_call", "attachment"]:
            if field in modelsdev_model:
                result[field] = modelsdev_model[field]
    else:
        print(
            f"  WARNING: No models.dev match for '{model_name}' "
            f"(litellm model: {litellm_model})",
            file=sys.stderr,
        )

    return result


def generate_opencode_config(
    litellm_config_path: str,
    base_url: str,
    provider_name: str = "LiteLLM",
    provider_id: str = "litellm",
) -> dict:
    """Generate a complete opencode.json config."""
    models_dev = fetch_models_dev()
    litellm_models = parse_litellm_config(litellm_config_path)

    opencode_models = {}
    matched = 0
    unmatched = 0

    for entry in litellm_models:
        model_name = entry.get("model_name", "")
        if not model_name:
            continue

        model_config = build_opencode_model(model_name, entry, models_dev)
        if model_config is None:
            continue

        opencode_models[model_name] = model_config

        if "modalities" in model_config:
            matched += 1
        else:
            unmatched += 1

    print(
        f"\nGenerated config: {matched} models with full metadata, "
        f"{unmatched} models without models.dev match",
        file=sys.stderr,
    )

    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_id: {
                "npm": "@ai-sdk/openai-compatible",
                "name": provider_name,
                "options": {"baseURL": base_url},
                "models": opencode_models,
            }
        },
    }


def detect_claude_models(litellm_models: list[dict]) -> dict[str, Optional[str]]:
    """
    Auto-detect the best opus, sonnet, and haiku models from the litellm config.

    Looks for bedrock Claude models by matching model_name patterns.
    For each tier (opus/sonnet/haiku), picks the model with the highest
    version number.

    Returns a dict with keys 'opus', 'sonnet', 'haiku' mapped to model_name
    strings (or None if not found).
    """
    # Collect candidates: (model_name, version_tuple) for each tier
    candidates: dict[str, list[tuple[str, tuple[float, ...]]]] = {
        "opus": [],
        "sonnet": [],
        "haiku": [],
    }

    for entry in litellm_models:
        model_name = entry.get("model_name", "")
        litellm_params = entry.get("litellm_params", {})
        litellm_model = litellm_params.get("model", "")

        # Only consider bedrock Claude models
        if not litellm_model.startswith("bedrock/"):
            continue
        underlying = litellm_model.split("/", 1)[1].lower()
        if "anthropic" not in underlying and "claude" not in underlying:
            continue

        name_lower = model_name.lower()

        # Determine tier
        tier = None
        for t in ("opus", "sonnet", "haiku"):
            if t in name_lower:
                tier = t
                break
        if tier is None:
            continue

        # Extract version numbers from the model name for sorting
        # e.g. "bedrock-claude-4.6-opus" -> (4, 6)
        # e.g. "bedrock-claude-4.5-sonnet" -> (4, 5)
        version_numbers = re.findall(r"(\d+(?:\.\d+)?)", model_name)
        version_tuple = (
            tuple(float(v) for v in version_numbers) if version_numbers else (0,)
        )

        candidates[tier].append((model_name, version_tuple))

    # Pick the highest version for each tier
    result: dict[str, Optional[str]] = {}
    for tier in ("opus", "sonnet", "haiku"):
        if candidates[tier]:
            # Sort by version tuple descending, pick the first
            best = sorted(candidates[tier], key=lambda x: x[1], reverse=True)[0]
            result[tier] = best[0]
            print(f"  Claude Code {tier}: {best[0]}", file=sys.stderr)
        else:
            result[tier] = None
            print(f"  Claude Code {tier}: not found", file=sys.stderr)

    return result



def generate_claude_settings(
    base_url: str,
    litellm_models: list[dict],
) -> dict:
    """
    Generate a claude-settings.json for Claude Code with Bedrock pass-through.

    The settings configure Claude Code to route through LiteLLM's /bedrock
    endpoint, skipping local AWS auth (LiteLLM handles it).

    API key (ANTHROPIC_AUTH_TOKEN) is NOT included -- users should set it
    in their shell profile so it persists across config regenerations.
    """
    # Derive bedrock URL from base URL: strip /v1 suffix and append /bedrock
    bedrock_url = re.sub(r"/v1/?$", "", base_url) + "/bedrock"

    print("\nDetecting Claude models for Claude Code settings...", file=sys.stderr)
    claude_models = detect_claude_models(litellm_models)

    env: dict[str, str] = {
        "ANTHROPIC_BEDROCK_BASE_URL": bedrock_url,
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "CLAUDE_CODE_SKIP_BEDROCK_AUTH": "1",
    }

    # Add model pinning for each tier found
    model_env_map = {
        "opus": "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "sonnet": "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "haiku": "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    }

    for tier, env_var in model_env_map.items():
        model_name = claude_models.get(tier)
        if model_name is not None:
            env[env_var] = model_name

    result: dict = {"env": env}

    # Set the default model to the best opus, falling back to sonnet
    default_model = claude_models.get("opus") or claude_models.get("sonnet")
    if default_model is not None:
        result["model"] = default_model

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate opencode.json and claude-settings.json from litellm config and models.dev"
    )
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
        "--provider-name",
        default="LiteLLM",
        help="Display name for the provider in opencode (default: LiteLLM)",
    )
    parser.add_argument(
        "--provider-id",
        default="litellm",
        help="Provider ID key in opencode config (default: litellm)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path for opencode.json (default: stdout)",
    )
    parser.add_argument(
        "--claude-output",
        default=None,
        help="Output file path for claude-settings.json (default: not generated)",
    )

    args = parser.parse_args()

    config = generate_opencode_config(
        litellm_config_path=args.litellm_config,
        base_url=args.base_url,
        provider_name=args.provider_name,
        provider_id=args.provider_id,
    )

    output = json.dumps(config, indent=2) + "\n"

    if args.output:
        Path(args.output).write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Generate Claude Code settings if requested
    if args.claude_output:
        litellm_models = parse_litellm_config(args.litellm_config)
        claude_settings = generate_claude_settings(
            base_url=args.base_url,
            litellm_models=litellm_models,
        )
        claude_output = json.dumps(claude_settings, indent=2) + "\n"
        Path(args.claude_output).write_text(claude_output)
        print(f"Written Claude Code settings to {args.claude_output}", file=sys.stderr)


if __name__ == "__main__":
    main()
