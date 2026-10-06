#!/usr/bin/env python3
"""Tests for generate.py — Claude Code settings generation."""
from __future__ import annotations

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from generate import detect_claude_models, generate_claude_settings


class TestGenerateClaudeSettings(unittest.TestCase):
    """Settings generation uses model names as-is from the config."""

    def _make_models(self, entries):
        models = []
        for entry in entries:
            name, bedrock_id = entry[0], entry[1]
            tier = entry[2] if len(entry) > 2 else None
            model = {
                "model_name": name,
                "litellm_params": {"model": f"bedrock/{bedrock_id}"},
            }
            if tier is not None:
                model["model_info"] = {"claude_tier": tier}
            models.append(model)
        return models

    def test_model_names_preserved_with_region(self):
        models = self._make_models([
            ("bedrock-claude-opus-4-7-eu", "eu.anthropic.claude-opus-4-7"),
            ("bedrock-claude-sonnet-4-6-eu", "eu.anthropic.claude-sonnet-4-6"),
            ("bedrock-claude-haiku-4-5-eu", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["model"], "bedrock-claude-opus-4-7-eu")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"], "bedrock-claude-opus-4-7-eu")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"], "bedrock-claude-sonnet-4-6-eu")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "bedrock-claude-haiku-4-5-eu")

    def test_all_names_contain_claude_code_pattern(self):
        """Every model name in settings must be parseable by Claude Code's normalizer."""
        models = self._make_models([
            ("bedrock-claude-opus-4-7-eu", "eu.anthropic.claude-opus-4-7"),
            ("bedrock-claude-sonnet-4-6-eu", "eu.anthropic.claude-sonnet-4-6"),
            ("bedrock-claude-haiku-4-5-eu", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        for tier in ("opus", "sonnet", "haiku"):
            env_key = f"ANTHROPIC_DEFAULT_{tier.upper()}_MODEL"
            name = settings["env"][env_key]
            self.assertIn(f"claude-{tier}-", name, f"{env_key}={name} missing claude-{{tier}} pattern")

    def test_picks_latest_version(self):
        models = self._make_models([
            ("bedrock-claude-opus-4-5-eu", "eu.anthropic.claude-opus-4-5-20251101-v1:0"),
            ("bedrock-claude-opus-4-7-eu", "eu.anthropic.claude-opus-4-7"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["model"], "bedrock-claude-opus-4-7-eu")

    def test_bedrock_url_derived_from_base(self):
        models = self._make_models([
            ("bedrock-claude-opus-4-7-eu", "eu.anthropic.claude-opus-4-7"),
        ])
        settings = generate_claude_settings(
            base_url="https://llm-gateway.i.ai.gov.uk/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["env"]["ANTHROPIC_BEDROCK_BASE_URL"], "https://llm-gateway.i.ai.gov.uk/bedrock")

    def test_us_region_model_preserved(self):
        models = self._make_models([
            ("bedrock-claude-sonnet-3-7-us", "anthropic.claude-3-7-sonnet-20250219-v1:0"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"], "bedrock-claude-sonnet-3-7-us")

    def test_claude_tier_marker_is_authoritative(self):
        """An explicit claude_tier marker wins over an unmarked higher version."""
        models = self._make_models([
            # Higher version but NOT marked -- must be ignored for the pin.
            ("bedrock-claude-opus-9-9-eu", "eu.anthropic.claude-opus-9-9"),
            # Lower version but explicitly marked as the opus tier.
            ("bedrock-claude-opus-5-5-eu", "eu.anthropic.claude-opus-5-5", "opus"),
            ("bedrock-claude-sonnet-5-5-eu", "eu.anthropic.claude-sonnet-5-5", "sonnet"),
            ("bedrock-claude-haiku-4-5-eu", "eu.anthropic.claude-haiku-4-5", "haiku"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"], "bedrock-claude-opus-5-5-eu")
        self.assertEqual(settings["model"], "bedrock-claude-opus-5-5-eu")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"], "bedrock-claude-sonnet-5-5-eu")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "bedrock-claude-haiku-4-5-eu")

    def test_highest_version_among_marked_candidates(self):
        """When several models share a claude_tier, the highest version wins."""
        models = self._make_models([
            ("bedrock-claude-sonnet-5-eu", "eu.anthropic.claude-sonnet-5", "sonnet"),
            ("bedrock-claude-sonnet-5-5-eu", "eu.anthropic.claude-sonnet-5-5", "sonnet"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"], "bedrock-claude-sonnet-5-5-eu")

    def test_falls_back_to_name_inference_without_markers(self):
        """Configs without claude_tier still work via version-sorted name inference."""
        models = self._make_models([
            ("bedrock-claude-opus-4-5-eu", "eu.anthropic.claude-opus-4-5"),
            ("bedrock-claude-opus-4-8-eu", "eu.anthropic.claude-opus-4-8"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"], "bedrock-claude-opus-4-8-eu")

    def test_fable_tier_detected_and_preferred_as_default(self):
        """A fable model is pinned via ANTHROPIC_DEFAULT_FABLE_MODEL and wins the default."""
        models = self._make_models([
            ("bedrock-claude-opus-5-5-eu", "eu.anthropic.claude-opus-5-5", "opus"),
            ("bedrock-claude-sonnet-5-5-eu", "eu.anthropic.claude-sonnet-5-5", "sonnet"),
            ("bedrock-claude-haiku-4-5-eu", "eu.anthropic.claude-haiku-4-5", "haiku"),
            ("bedrock-claude-fable-5-1-global", "global.anthropic.claude-fable-5-1", "fable"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_FABLE_MODEL"], "bedrock-claude-fable-5-1-global")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"], "bedrock-claude-opus-5-5-eu")
        self.assertEqual(settings["model"], "bedrock-claude-fable-5-1-global")

    def test_fable_inferred_from_name_without_marker(self):
        models = self._make_models([
            ("bedrock-claude-opus-5-5-eu", "eu.anthropic.claude-opus-5-5"),
            ("bedrock-claude-fable-5-1-global", "global.anthropic.claude-fable-5-1"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_FABLE_MODEL"], "bedrock-claude-fable-5-1-global")
        self.assertEqual(settings["model"], "bedrock-claude-fable-5-1-global")

    def test_no_fable_env_or_default_when_absent(self):
        """Without a fable model, nothing fable-related is emitted and opus is the default."""
        models = self._make_models([
            ("bedrock-claude-opus-5-5-eu", "eu.anthropic.claude-opus-5-5", "opus"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertNotIn("ANTHROPIC_DEFAULT_FABLE_MODEL", settings["env"])
        self.assertEqual(settings["model"], "bedrock-claude-opus-5-5-eu")

    def test_haiku_never_default(self):
        models = self._make_models([
            ("bedrock-claude-haiku-4-5-eu", "eu.anthropic.claude-haiku-4-5", "haiku"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertNotIn("model", settings)


if __name__ == "__main__":
    unittest.main()
