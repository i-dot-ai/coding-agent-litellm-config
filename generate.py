#!/usr/bin/env python3
"""
Generate opencode.json from a litellm config.yml and models.dev metadata.

This script:
1. Reads the litellm proxy config.yml to get model aliases and their underlying models
2. Fetches model metadata from models.dev (capabilities, costs, limits, etc.)
3. Maps litellm provider prefixes to models.dev provider IDs
4. Generates an opencode.json with full model metadata

Usage:
    python generate.py --litellm-config path/to/config.yml --base-url https://llm-gateway.example.com/v1
    python generate.py --litellm-config path/to/config.yml --base-url https://llm-gateway.example.com/v1 --output opencode.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
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


def main():
    parser = argparse.ArgumentParser(
        description="Generate opencode.json from litellm config and models.dev"
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
        help="Output file path (default: stdout)",
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


if __name__ == "__main__":
    main()
