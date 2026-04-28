#!/usr/bin/env python3
"""Tests for merge-settings.py — the core merge logic for Claude Code settings."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from typing import Optional, List

MERGE_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "merge-settings.py")


def run_merge(generated: dict, user: Optional[dict] = None, extra_args: Optional[List[str]] = None) -> subprocess.CompletedProcess:
    """Helper: write generated/user JSON to temp files and run merge-settings.py."""
    with tempfile.TemporaryDirectory() as tmp:
        gen_path = os.path.join(tmp, "generated.json")
        user_path = os.path.join(tmp, "settings.json")

        with open(gen_path, "w") as f:
            json.dump(generated, f)

        if user is not None:
            with open(user_path, "w") as f:
                json.dump(user, f)

        cmd = [sys.executable, MERGE_SCRIPT, gen_path, user_path] + (extra_args or [])
        result = subprocess.run(cmd, capture_output=True, text=True)

        merged = None
        if os.path.exists(user_path) and result.returncode == 0 and "--dry-run" not in (extra_args or []):
            with open(user_path) as f:
                merged = json.load(f)

        result.merged = merged
        result.user_path = user_path
        return result


class TestMergeIntoEmpty(unittest.TestCase):
    def test_merge_into_missing_user_file(self):
        generated = {
            "env": {"CLAUDE_CODE_USE_BEDROCK": "1"},
            "model": "bedrock-claude-4.7-opus",
        }
        result = run_merge(generated, user=None)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.merged["env"]["CLAUDE_CODE_USE_BEDROCK"], "1")
        self.assertEqual(result.merged["model"], "bedrock-claude-4.7-opus")

    def test_merge_into_empty_user_file(self):
        generated = {
            "env": {"CLAUDE_CODE_USE_BEDROCK": "1"},
            "model": "bedrock-claude-4.7-opus",
        }
        result = run_merge(generated, user={})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.merged, generated)


class TestMergePreservesUserData(unittest.TestCase):
    def test_preserves_user_only_env_vars(self):
        generated = {
            "env": {"CLAUDE_CODE_USE_BEDROCK": "1"},
            "model": "bedrock-claude-4.7-opus",
        }
        user = {
            "env": {
                "CLAUDE_CODE_USE_BEDROCK": "1",
                "AIKIDO_API_KEY": "secret-key-123",
            },
            "model": "bedrock-claude-4.6-opus",
        }
        result = run_merge(generated, user)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.merged["env"]["AIKIDO_API_KEY"], "secret-key-123")
        self.assertEqual(result.merged["env"]["CLAUDE_CODE_USE_BEDROCK"], "1")

    def test_updates_generated_env_vars(self):
        generated = {
            "env": {
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "bedrock-claude-4.7-opus",
                "ANTHROPIC_DEFAULT_SONNET_MODEL": "bedrock-claude-4.6-sonnet",
            },
        }
        user = {
            "env": {
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "bedrock-claude-4.6-opus",
                "ANTHROPIC_DEFAULT_SONNET_MODEL": "bedrock-claude-4.5-sonnet",
                "AIKIDO_API_KEY": "kept",
            },
        }
        result = run_merge(generated, user)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.merged["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"], "bedrock-claude-4.7-opus")
        self.assertEqual(result.merged["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"], "bedrock-claude-4.6-sonnet")
        self.assertEqual(result.merged["env"]["AIKIDO_API_KEY"], "kept")

    def test_overwrites_model(self):
        generated = {"model": "bedrock-claude-4.7-opus"}
        user = {"model": "bedrock-claude-4.6-opus"}
        result = run_merge(generated, user)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.merged["model"], "bedrock-claude-4.7-opus")

    def test_preserves_top_level_user_keys(self):
        generated = {
            "env": {"CLAUDE_CODE_USE_BEDROCK": "1"},
            "model": "bedrock-claude-4.7-opus",
        }
        user = {
            "env": {"CLAUDE_CODE_USE_BEDROCK": "0"},
            "model": "bedrock-claude-4.6-opus",
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "notify.sh"}]}],
            },
            "enabledPlugins": {"aikido@claude-plugins-official": True},
            "alwaysThinkingEnabled": True,
        }
        result = run_merge(generated, user)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.merged["hooks"], user["hooks"])
        self.assertEqual(result.merged["enabledPlugins"], user["enabledPlugins"])
        self.assertTrue(result.merged["alwaysThinkingEnabled"])
        self.assertEqual(result.merged["env"]["CLAUDE_CODE_USE_BEDROCK"], "1")
        self.assertEqual(result.merged["model"], "bedrock-claude-4.7-opus")

    def test_adds_new_env_keys(self):
        generated = {
            "env": {
                "EXISTING_KEY": "updated",
                "BRAND_NEW_KEY": "new-value",
            },
        }
        user = {
            "env": {"EXISTING_KEY": "old"},
        }
        result = run_merge(generated, user)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.merged["env"]["EXISTING_KEY"], "updated")
        self.assertEqual(result.merged["env"]["BRAND_NEW_KEY"], "new-value")

    def test_ignores_unknown_generated_keys(self):
        """Generated keys outside the known set (env, model) are NOT merged (#4)."""
        generated = {
            "env": {"KEY": "val"},
            "model": "m",
            "typo_key": "should-not-appear",
            "hooks": {"Overwrite": "bad"},
        }
        user = {
            "hooks": {"Stop": [{"hooks": []}]},
            "customField": "preserved",
        }
        result = run_merge(generated, user)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("typo_key", result.merged)
        self.assertEqual(result.merged["hooks"], {"Stop": [{"hooks": []}]})
        self.assertEqual(result.merged["customField"], "preserved")


class TestMergeDoesNotMutateInput(unittest.TestCase):
    """Verify merge() deep-copies and never mutates the input dicts (#2)."""

    def test_merge_does_not_mutate_user_dict(self):
        # Import the function directly to test in-process
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        try:
            from importlib import import_module
            mod = import_module("merge-settings")
        except ImportError:
            # Hyphenated module name — use importlib workaround
            import importlib.util
            spec = importlib.util.spec_from_file_location("merge_settings", MERGE_SCRIPT)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

        user = {
            "env": {"EXISTING": "original", "USER_ONLY": "keep"},
            "model": "old",
            "hooks": {"Stop": []},
        }
        generated = {
            "env": {"EXISTING": "updated", "NEW_KEY": "added"},
            "model": "new",
        }

        import copy
        user_before = copy.deepcopy(user)
        mod.merge(generated, user)
        self.assertEqual(user, user_before)

    def test_merge_does_not_mutate_generated_dict(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("merge_settings", MERGE_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        user = {"env": {"A": "1"}}
        generated = {"env": {"B": "2"}, "model": "m"}

        import copy
        gen_before = copy.deepcopy(generated)
        mod.merge(generated, user)
        self.assertEqual(generated, gen_before)


class TestDryRun(unittest.TestCase):
    def test_dry_run_prints_merged_without_writing(self):
        generated = {"model": "new-model"}
        user = {"model": "old-model", "hooks": {"Stop": []}}

        with tempfile.TemporaryDirectory() as tmp:
            gen_path = os.path.join(tmp, "generated.json")
            user_path = os.path.join(tmp, "settings.json")

            with open(gen_path, "w") as f:
                json.dump(generated, f)
            with open(user_path, "w") as f:
                json.dump(user, f)

            cmd = [sys.executable, MERGE_SCRIPT, gen_path, user_path, "--dry-run"]
            result = subprocess.run(cmd, capture_output=True, text=True)

            self.assertEqual(result.returncode, 0)
            stdout_parsed = json.loads(result.stdout)
            self.assertEqual(stdout_parsed["model"], "new-model")
            self.assertEqual(stdout_parsed["hooks"], {"Stop": []})

            with open(user_path) as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk["model"], "old-model")


class TestOnlyIfChanged(unittest.TestCase):
    def test_skips_write_when_content_identical(self):
        settings = {
            "env": {"KEY": "value"},
            "model": "some-model",
        }

        with tempfile.TemporaryDirectory() as tmp:
            gen_path = os.path.join(tmp, "generated.json")
            user_path = os.path.join(tmp, "settings.json")

            with open(gen_path, "w") as f:
                json.dump(settings, f)
            canonical = json.dumps(settings, indent=2) + "\n"
            with open(user_path, "w") as f:
                f.write(canonical)

            # Read content before
            with open(user_path) as f:
                content_before = f.read()

            cmd = [sys.executable, MERGE_SCRIPT, gen_path, user_path, "--only-if-changed"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)

            # Verify content is identical (not relying on mtime)
            with open(user_path) as f:
                content_after = f.read()
            self.assertEqual(content_before, content_after)

    def test_writes_when_content_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen_path = os.path.join(tmp, "generated.json")
            user_path = os.path.join(tmp, "settings.json")

            with open(gen_path, "w") as f:
                json.dump({"model": "new"}, f)
            with open(user_path, "w") as f:
                f.write(json.dumps({"model": "old"}, indent=2) + "\n")

            cmd = [sys.executable, MERGE_SCRIPT, gen_path, user_path, "--only-if-changed"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)

            with open(user_path) as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk["model"], "new")


class TestInvalidJSON(unittest.TestCase):
    def test_invalid_generated_json_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen_path = os.path.join(tmp, "generated.json")
            user_path = os.path.join(tmp, "settings.json")

            with open(gen_path, "w") as f:
                f.write("not valid json{{{")
            with open(user_path, "w") as f:
                json.dump({}, f)

            cmd = [sys.executable, MERGE_SCRIPT, gen_path, user_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_invalid_user_json_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen_path = os.path.join(tmp, "generated.json")
            user_path = os.path.join(tmp, "settings.json")

            with open(gen_path, "w") as f:
                json.dump({"model": "x"}, f)
            with open(user_path, "w") as f:
                f.write("corrupted{{{")

            cmd = [sys.executable, MERGE_SCRIPT, gen_path, user_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


class TestAtomicWrite(unittest.TestCase):
    def test_no_tmp_file_left_behind(self):
        generated = {"model": "test"}
        with tempfile.TemporaryDirectory() as tmp:
            gen_path = os.path.join(tmp, "generated.json")
            user_path = os.path.join(tmp, "settings.json")

            with open(gen_path, "w") as f:
                json.dump(generated, f)

            cmd = [sys.executable, MERGE_SCRIPT, gen_path, user_path]
            subprocess.run(cmd, capture_output=True, text=True)

            files = os.listdir(tmp)
            self.assertNotIn("settings.json.tmp", files)
            self.assertIn("settings.json", files)


class TestHookManagement(unittest.TestCase):
    """Tests for --install-hook and --remove-hook modes."""

    def test_install_hook_to_empty_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "settings.json")
            cmd = [sys.executable, MERGE_SCRIPT, "--install-hook", "/abs/path/update-claude-settings.sh", settings_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)

            with open(settings_path) as f:
                settings = json.load(f)
            hooks = settings["hooks"]["SessionStart"]
            self.assertEqual(len(hooks), 1)
            self.assertIn("update-claude-settings.sh", hooks[0]["hooks"][0]["command"])
            self.assertEqual(hooks[0].get("matcher"), "startup")

    def test_install_hook_uses_absolute_path(self):
        """Hook command must contain the exact path passed in (#8)."""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "settings.json")
            abs_path = "/Users/test/repos/coding-agent-litellm-config/update-claude-settings.sh"
            cmd = [sys.executable, MERGE_SCRIPT, "--install-hook", abs_path, settings_path]
            subprocess.run(cmd, capture_output=True, text=True)

            with open(settings_path) as f:
                settings = json.load(f)
            hook_cmd = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
            self.assertTrue(hook_cmd.startswith("/"), f"Hook command must be absolute path, got: {hook_cmd}")
            self.assertEqual(hook_cmd, abs_path)

    def test_install_hook_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "settings.json")
            hook = "/path/to/update-claude-settings.sh"
            for _ in range(3):
                cmd = [sys.executable, MERGE_SCRIPT, "--install-hook", hook, settings_path]
                subprocess.run(cmd, capture_output=True, text=True)

            with open(settings_path) as f:
                settings = json.load(f)
            self.assertEqual(len(settings["hooks"]["SessionStart"]), 1)

    def test_install_hook_preserves_other_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "settings.json")
            with open(settings_path, "w") as f:
                json.dump({
                    "hooks": {
                        "Stop": [{"hooks": [{"type": "command", "command": "notify.sh"}]}],
                    },
                }, f)

            cmd = [sys.executable, MERGE_SCRIPT, "--install-hook", "/path/update-claude-settings.sh", settings_path]
            subprocess.run(cmd, capture_output=True, text=True)

            with open(settings_path) as f:
                settings = json.load(f)
            self.assertEqual(len(settings["hooks"]["Stop"]), 1)
            self.assertEqual(len(settings["hooks"]["SessionStart"]), 1)

    def test_remove_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "settings.json")
            # Install first
            cmd = [sys.executable, MERGE_SCRIPT, "--install-hook", "/path/update-claude-settings.sh", settings_path]
            subprocess.run(cmd, capture_output=True, text=True)
            # Remove
            cmd = [sys.executable, MERGE_SCRIPT, "--remove-hook", settings_path]
            subprocess.run(cmd, capture_output=True, text=True)

            with open(settings_path) as f:
                settings = json.load(f)
            self.assertNotIn("hooks", settings)

    def test_remove_hook_preserves_other_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "settings.json")
            with open(settings_path, "w") as f:
                json.dump({
                    "hooks": {
                        "Stop": [{"hooks": [{"type": "command", "command": "notify.sh"}]}],
                        "SessionStart": [
                            {"hooks": [{"type": "command", "command": "/path/update-claude-settings.sh"}]},
                        ],
                    },
                }, f)

            cmd = [sys.executable, MERGE_SCRIPT, "--remove-hook", settings_path]
            subprocess.run(cmd, capture_output=True, text=True)

            with open(settings_path) as f:
                settings = json.load(f)
            self.assertNotIn("SessionStart", settings.get("hooks", {}))
            self.assertEqual(len(settings["hooks"]["Stop"]), 1)

    def test_remove_hook_noop_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "settings.json")
            with open(settings_path, "w") as f:
                json.dump({"model": "test"}, f)

            cmd = [sys.executable, MERGE_SCRIPT, "--remove-hook", settings_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)

            with open(settings_path) as f:
                settings = json.load(f)
            self.assertEqual(settings["model"], "test")

    def test_remove_hook_noop_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "settings.json")
            cmd = [sys.executable, MERGE_SCRIPT, "--remove-hook", settings_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
