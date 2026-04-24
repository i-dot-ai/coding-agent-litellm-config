#!/usr/bin/env python3
"""Tests for install.sh and uninstall.sh — end-to-end shell script tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_DIR = os.path.join(os.path.dirname(__file__), "..")
INSTALL_SCRIPT = os.path.join(REPO_DIR, "install.sh")
UNINSTALL_SCRIPT = os.path.join(REPO_DIR, "uninstall.sh")

HOOK_MARKER = "update-claude-settings.sh"


def run_install(settings_path: str, state_dir: str, generated_path: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "SETTINGS_FILE": settings_path,
        "STATE_DIR": state_dir,
        "GENERATED_FILE": generated_path,
    }
    return subprocess.run(
        ["bash", INSTALL_SCRIPT],
        capture_output=True, text=True, env=env,
    )


def run_uninstall(settings_path: str, state_dir: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "SETTINGS_FILE": settings_path,
        "STATE_DIR": state_dir,
    }
    return subprocess.run(
        ["bash", UNINSTALL_SCRIPT],
        capture_output=True, text=True, env=env,
    )


def load_settings(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def has_update_hook(settings: dict) -> bool:
    for entry in settings.get("hooks", {}).get("SessionStart", []):
        for hook in entry.get("hooks", []):
            if HOOK_MARKER in hook.get("command", ""):
                return True
    return False


def count_update_hooks(settings: dict) -> int:
    count = 0
    for entry in settings.get("hooks", {}).get("SessionStart", []):
        for hook in entry.get("hooks", []):
            if HOOK_MARKER in hook.get("command", ""):
                count += 1
    return count


def get_hook_entry(settings: dict) -> dict:
    for entry in settings.get("hooks", {}).get("SessionStart", []):
        for hook in entry.get("hooks", []):
            if HOOK_MARKER in hook.get("command", ""):
                return entry
    return {}


def get_hook_command(settings: dict) -> str:
    entry = get_hook_entry(settings)
    for hook in entry.get("hooks", []):
        if HOOK_MARKER in hook.get("command", ""):
            return hook["command"]
    return ""


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.settings_path = os.path.join(self.tmp, "settings.json")
        self.state_dir = os.path.join(self.tmp, "state")
        self.generated_path = os.path.join(self.tmp, "claude-settings.json")
        with open(self.generated_path, "w") as f:
            json.dump({
                "env": {"CLAUDE_CODE_USE_BEDROCK": "1"},
                "model": "bedrock-claude-4.7-opus",
            }, f)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_install_adds_hook_to_empty_settings(self):
        result = run_install(self.settings_path, self.state_dir, self.generated_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = load_settings(self.settings_path)
        self.assertTrue(has_update_hook(settings))

    def test_install_hook_is_absolute_path(self):
        """Hook command must be an absolute path (#8)."""
        result = run_install(self.settings_path, self.state_dir, self.generated_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = load_settings(self.settings_path)
        cmd = get_hook_command(settings)
        self.assertTrue(cmd.startswith("/"), f"Hook command must be absolute, got: {cmd}")

    def test_install_hook_has_startup_matcher(self):
        """Hook should only fire on new sessions, not resume/clear/compact."""
        result = run_install(self.settings_path, self.state_dir, self.generated_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = load_settings(self.settings_path)
        entry = get_hook_entry(settings)
        self.assertEqual(entry.get("matcher"), "startup")

    def test_install_adds_hook_with_existing_other_hooks(self):
        with open(self.settings_path, "w") as f:
            json.dump({
                "hooks": {
                    "Stop": [{"hooks": [{"type": "command", "command": "notify.sh"}]}],
                },
            }, f)
        result = run_install(self.settings_path, self.state_dir, self.generated_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = load_settings(self.settings_path)
        self.assertTrue(has_update_hook(settings))
        self.assertEqual(len(settings["hooks"]["Stop"]), 1)

    def test_install_deduplicates(self):
        run_install(self.settings_path, self.state_dir, self.generated_path)
        run_install(self.settings_path, self.state_dir, self.generated_path)
        settings = load_settings(self.settings_path)
        self.assertEqual(count_update_hooks(settings), 1)

    def test_install_merges_env_and_model(self):
        with open(self.settings_path, "w") as f:
            json.dump({
                "env": {"AIKIDO_API_KEY": "secret"},
                "model": "old-model",
                "alwaysThinkingEnabled": True,
            }, f)
        result = run_install(self.settings_path, self.state_dir, self.generated_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = load_settings(self.settings_path)
        self.assertEqual(settings["env"]["AIKIDO_API_KEY"], "secret")
        self.assertEqual(settings["env"]["CLAUDE_CODE_USE_BEDROCK"], "1")
        self.assertEqual(settings["model"], "bedrock-claude-4.7-opus")
        self.assertTrue(settings["alwaysThinkingEnabled"])

    def test_install_creates_state_dir(self):
        run_install(self.settings_path, self.state_dir, self.generated_path)
        self.assertTrue(os.path.isdir(self.state_dir))


class TestUninstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.settings_path = os.path.join(self.tmp, "settings.json")
        # State dir must be under a .config/ path for the safety guard
        self.config_dir = os.path.join(self.tmp, ".config")
        self.state_dir = os.path.join(self.config_dir, "coding-agent-litellm-config")
        self.generated_path = os.path.join(self.tmp, "claude-settings.json")
        with open(self.generated_path, "w") as f:
            json.dump({"env": {"KEY": "val"}, "model": "m"}, f)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _install_first(self):
        run_install(self.settings_path, self.state_dir, self.generated_path)

    def test_uninstall_removes_hook(self):
        self._install_first()
        settings = load_settings(self.settings_path)
        self.assertTrue(has_update_hook(settings))

        result = run_uninstall(self.settings_path, self.state_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = load_settings(self.settings_path)
        self.assertFalse(has_update_hook(settings))

    def test_uninstall_cleans_empty_hooks(self):
        self._install_first()
        result = run_uninstall(self.settings_path, self.state_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = load_settings(self.settings_path)
        self.assertNotIn("hooks", settings)

    def test_uninstall_preserves_other_hooks(self):
        with open(self.settings_path, "w") as f:
            json.dump({
                "hooks": {
                    "Stop": [{"hooks": [{"type": "command", "command": "notify.sh"}]}],
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "/path/to/update-claude-settings.sh"}]},
                    ],
                },
            }, f)

        result = run_uninstall(self.settings_path, self.state_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = load_settings(self.settings_path)
        self.assertFalse(has_update_hook(settings))
        self.assertEqual(len(settings["hooks"]["Stop"]), 1)

    def test_uninstall_noop_when_no_hook(self):
        with open(self.settings_path, "w") as f:
            json.dump({"model": "test"}, f)

        result = run_uninstall(self.settings_path, self.state_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = load_settings(self.settings_path)
        self.assertEqual(settings["model"], "test")

    def test_uninstall_removes_state_dir(self):
        self._install_first()
        self.assertTrue(os.path.isdir(self.state_dir))
        # Uninstall expects STATE_DIR under ~/.config/ — simulate with HOME override
        env = {
            **os.environ,
            "SETTINGS_FILE": self.settings_path,
            "HOME": self.tmp,
            "STATE_DIR": self.state_dir,
        }
        subprocess.run(["bash", UNINSTALL_SCRIPT], capture_output=True, text=True, env=env)
        self.assertFalse(os.path.exists(self.state_dir))

    def test_uninstall_noop_when_no_settings_file(self):
        result = run_uninstall(self.settings_path, self.state_dir)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_uninstall_refuses_dangerous_state_dir(self):
        """STATE_DIR outside ~/.config/ should NOT be rm -rf'd (#6)."""
        self._install_first()
        # Use a state_dir that's not under $HOME/.config/
        bad_state_dir = os.path.join(self.tmp, "dangerous-dir")
        os.makedirs(bad_state_dir, exist_ok=True)
        sentinel = os.path.join(bad_state_dir, "important-file")
        with open(sentinel, "w") as f:
            f.write("do not delete")

        result = run_uninstall(self.settings_path, bad_state_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(sentinel), "File outside ~/.config/ should not be deleted")


if __name__ == "__main__":
    unittest.main()
