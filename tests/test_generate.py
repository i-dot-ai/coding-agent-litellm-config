#!/usr/bin/env python3
"""Tests for generate.py — model name normalization for Claude Code."""
from __future__ import annotations

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from generate import normalize_claude_model_name, detect_claude_models, generate_claude_settings


class TestNormalizeClaudeModelName(unittest.TestCase):
    """Old-style names (bedrock-claude-4.7-opus) are rewritten to tier-first format."""

    def test_old_style_opus(self):
        self.assertEqual(
            normalize_claude_model_name("bedrock-claude-4.7-opus"),
            "bedrock-claude-opus-4-7",
        )

    def test_old_style_sonnet(self):
        self.assertEqual(
            normalize_claude_model_name("bedrock-claude-4.6-sonnet"),
            "bedrock-claude-sonnet-4-6",
        )

    def test_old_style_haiku(self):
        self.assertEqual(
            normalize_claude_model_name("bedrock-claude-4.5-haiku"),
            "bedrock-claude-haiku-4-5",
        )

    def test_new_style_strips_region(self):
        """New-style names with region suffix are stripped to bare form."""
        self.assertEqual(
            normalize_claude_model_name("bedrock-claude-opus-4-7-eu"),
            "bedrock-claude-opus-4-7",
        )

    def test_new_style_strips_different_region(self):
        self.assertEqual(
            normalize_claude_model_name("bedrock-claude-sonnet-4-6-us"),
            "bedrock-claude-sonnet-4-6",
        )

    def test_new_style_haiku_strips_region(self):
        self.assertEqual(
            normalize_claude_model_name("bedrock-claude-haiku-4-5-eu"),
            "bedrock-claude-haiku-4-5",
        )

    def test_already_correct_passthrough(self):
        self.assertEqual(
            normalize_claude_model_name("bedrock-claude-opus-4-7"),
            "bedrock-claude-opus-4-7",
        )

    def test_non_bedrock_passthrough(self):
        self.assertEqual(
            normalize_claude_model_name("claude-opus-4-7"),
            "claude-opus-4-7",
        )

    def test_unknown_format_passthrough(self):
        self.assertEqual(
            normalize_claude_model_name("some-random-model"),
            "some-random-model",
        )

    def test_old_style_contains_expected_pattern(self):
        """Normalized name must contain 'claude-opus-4-7' for Claude Code."""
        result = normalize_claude_model_name("bedrock-claude-4.7-opus")
        self.assertIn("claude-opus-4-7", result)

    def test_new_style_contains_expected_pattern(self):
        result = normalize_claude_model_name("bedrock-claude-opus-4-7-eu")
        self.assertIn("claude-opus-4-7", result)


class TestGenerateClaudeSettingsOldNames(unittest.TestCase):
    """Settings generation with old-style LiteLLM aliases."""

    def _make_models(self, entries):
        return [
            {
                "model_name": name,
                "litellm_params": {"model": f"bedrock/{bedrock_id}"},
            }
            for name, bedrock_id in entries
        ]

    def test_output_model_names_are_normalized(self):
        models = self._make_models([
            ("bedrock-claude-4.7-opus", "eu.anthropic.claude-opus-4-7"),
            ("bedrock-claude-4.6-sonnet", "eu.anthropic.claude-sonnet-4-6-v1"),
            ("bedrock-claude-4.5-haiku", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["model"], "bedrock-claude-opus-4-7")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"], "bedrock-claude-opus-4-7")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"], "bedrock-claude-sonnet-4-6")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "bedrock-claude-haiku-4-5")


class TestGenerateClaudeSettingsNewNames(unittest.TestCase):
    """Settings generation with new-style LiteLLM aliases (tier-first, region suffix)."""

    def _make_models(self, entries):
        return [
            {
                "model_name": name,
                "litellm_params": {"model": f"bedrock/{bedrock_id}"},
            }
            for name, bedrock_id in entries
        ]

    def test_region_suffix_stripped(self):
        models = self._make_models([
            ("bedrock-claude-opus-4-7-eu", "eu.anthropic.claude-opus-4-7"),
            ("bedrock-claude-sonnet-4-6-eu", "eu.anthropic.claude-sonnet-4-6"),
            ("bedrock-claude-haiku-4-5-eu", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"),
        ])
        settings = generate_claude_settings(
            base_url="https://example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["model"], "bedrock-claude-opus-4-7")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"], "bedrock-claude-opus-4-7")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"], "bedrock-claude-sonnet-4-6")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "bedrock-claude-haiku-4-5")

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


if __name__ == "__main__":
    unittest.main()
