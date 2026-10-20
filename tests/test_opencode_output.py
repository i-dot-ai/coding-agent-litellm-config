#!/usr/bin/env python3
"""Quick tests for generated opencode.json output shape.

These assert the generator now emits the OpenCode V2 provider shape and
does not include the legacy allowed_openai_params field that allowed
forwarding unsupported OpenAI params (like "store").
"""
from __future__ import annotations

import json
import os
import unittest

import pathlib

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent


class TestOpencodeOutput(unittest.TestCase):
    def test_generated_file_has_providers_and_no_allowed_openai_params(self):
        opencode_path = ROOT / "opencode.json"
        assert opencode_path.exists(), f"{opencode_path} missing"

        data = json.loads(opencode_path.read_text())

        # Must use 'providers' (plural)
        self.assertIn("providers", data)

        # No top-level legacy 'provider' key
        self.assertNotIn("provider", data)

        # Ensure none of the providers include allowed_openai_params anywhere
        providers = data.get("providers", {})
        serialized = json.dumps(providers)
        self.assertNotIn("allowed_openai_params", serialized)


if __name__ == "__main__":
    unittest.main()
