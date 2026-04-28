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
        return [
            {
                "model_name": name,
                "litellm_params": {"model": f"bedrock/{bedrock_id}"},
            }
            for name, bedrock_id in entries
        ]

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


if __name__ == "__main__":
    unittest.main()
