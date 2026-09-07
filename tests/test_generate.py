#!/usr/bin/env python3
"""Tests for generate.py — Claude Code settings generation."""

from __future__ import annotations

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from generate import detect_claude_models, generate_claude_settings


class TestDetectClaudeModels(unittest.TestCase):
    def _make_models(self, entries):
        """entries: list of (model_name, claude_tier_or_None)."""
        return [
            {
                "model_name": name,
                "model_info": {"claude_tier": tier} if tier else {},
            }
            for name, tier in entries
        ]

    def test_picks_tagged_models(self):
        models = self._make_models(
            [
                ("bedrock-claude-opus-5-eu", "opus"),
                ("bedrock-claude-opus-4-8-eu", None),
                ("bedrock-claude-sonnet-5-0-eu", "sonnet"),
                ("gpt-4o-mini-sweden", None),
            ]
        )
        result = detect_claude_models(models)
        self.assertEqual(result["opus"], "bedrock-claude-opus-5-eu")
        self.assertEqual(result["sonnet"], "bedrock-claude-sonnet-5-0-eu")
        self.assertIsNone(result["haiku"])

    def test_first_tagged_model_wins_per_tier(self):
        models = self._make_models(
            [
                ("bedrock-claude-opus-5-eu", "opus"),
                ("bedrock-claude-opus-4-8-eu", "opus"),
            ]
        )
        result = detect_claude_models(models)
        self.assertEqual(result["opus"], "bedrock-claude-opus-5-eu")

    def test_no_tags_returns_all_none(self):
        models = self._make_models(
            [
                ("gpt-4o-mini-sweden", None),
            ]
        )
        result = detect_claude_models(models)
        self.assertIsNone(result["opus"])
        self.assertIsNone(result["sonnet"])
        self.assertIsNone(result["haiku"])

    def test_missing_model_info_is_ignored(self):
        models = [{"model_name": "some-model"}]
        result = detect_claude_models(models)
        self.assertIsNone(result["opus"])


class TestGenerateClaudeSettings(unittest.TestCase):
    def _make_models(self, entries):
        return [
            {
                "model_name": name,
                "model_info": {"claude_tier": tier} if tier else {},
            }
            for name, tier in entries
        ]

    def test_pins_opus_sonnet_haiku_and_derives_bedrock_url(self):
        models = self._make_models(
            [
                ("bedrock-claude-opus-5-eu", "opus"),
                ("bedrock-claude-opus-4-8-eu", None),
                ("bedrock-claude-sonnet-5-0-eu", "sonnet"),
                ("gpt-4o-mini-sweden", None),
            ]
        )
        settings = generate_claude_settings(
            base_url="https://gateway.example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["env"]["ANTHROPIC_BEDROCK_BASE_URL"], "https://gateway.example.com/bedrock")
        self.assertEqual(settings["env"]["CLAUDE_CODE_USE_BEDROCK"], "1")
        self.assertEqual(settings["env"]["CLAUDE_CODE_SKIP_BEDROCK_AUTH"], "1")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"], "bedrock-claude-opus-5-eu")
        self.assertEqual(settings["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"], "bedrock-claude-sonnet-5-0-eu")
        self.assertNotIn("ANTHROPIC_DEFAULT_HAIKU_MODEL", settings["env"])
        self.assertEqual(settings["model"], "bedrock-claude-opus-5-eu")

    def test_falls_back_to_sonnet_as_default_when_no_opus_pinned(self):
        models = self._make_models(
            [
                ("bedrock-claude-sonnet-5-0-eu", "sonnet"),
            ]
        )
        settings = generate_claude_settings(
            base_url="https://gateway.example.com/v1",
            litellm_models=models,
        )
        self.assertEqual(settings["model"], "bedrock-claude-sonnet-5-0-eu")

    def test_no_pinned_models_when_nothing_tagged(self):
        models = self._make_models(
            [
                ("gpt-4o-mini-sweden", None),
            ]
        )
        settings = generate_claude_settings(
            base_url="https://gateway.example.com/v1",
            litellm_models=models,
        )
        self.assertNotIn("model", settings)
        self.assertNotIn("ANTHROPIC_DEFAULT_OPUS_MODEL", settings["env"])
        self.assertNotIn("ANTHROPIC_DEFAULT_SONNET_MODEL", settings["env"])
        self.assertNotIn("ANTHROPIC_DEFAULT_HAIKU_MODEL", settings["env"])


if __name__ == "__main__":
    unittest.main()
