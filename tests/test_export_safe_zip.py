"""Tests for scripts/export_safe_zip.py — exclusion logic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.export_safe_zip import _is_excluded, _is_secret, verify_exclusions


# ---------------------------------------------------------------------------
# Secret detection
# ---------------------------------------------------------------------------

class TestSecretDetection:
    def test_config_py_is_secret(self):
        assert _is_secret("world_models/config.py")

    def test_env_file_is_secret(self):
        assert _is_secret(".env")

    def test_env_variant_is_secret(self):
        assert _is_secret(".env.local")

    def test_id_rsa_is_secret(self):
        assert _is_secret("id_rsa")

    def test_id_ed25519_is_secret(self):
        assert _is_secret("id_ed25519")

    def test_credentials_json_is_secret(self):
        assert _is_secret("credentials.json")

    def test_pem_file_is_secret(self):
        assert _is_secret("cert.pem")

    def test_normal_python_file_is_not_secret(self):
        assert not _is_secret("coordinators/reason.py")

    def test_config_example_is_not_secret(self):
        assert not _is_secret("world_models/config.example.py")


# ---------------------------------------------------------------------------
# Directory exclusions
# ---------------------------------------------------------------------------

class TestDirectoryExclusions:
    def test_git_dir_excluded(self):
        excluded, _ = _is_excluded(".git/config")
        assert excluded

    def test_godot_cache_excluded(self):
        excluded, _ = _is_excluded("avatar/.godot/editor/filesystem_cache10")
        assert excluded

    def test_pycache_excluded(self):
        excluded, _ = _is_excluded("coordinators/__pycache__/reason.cpython-311.pyc")
        assert excluded

    def test_dream_logs_excluded(self):
        excluded, _ = _is_excluded("logs/dream/2026-05-21_202550.json")
        assert excluded

    def test_archivist_logs_excluded(self):
        excluded, _ = _is_excluded("logs/archivist/research.jsonl")
        assert excluded

    def test_venv_excluded(self):
        excluded, _ = _is_excluded(".venv/lib/python3.11/site-packages/anthropic/__init__.py")
        assert excluded


# ---------------------------------------------------------------------------
# Filename pattern exclusions
# ---------------------------------------------------------------------------

class TestFilenameExclusions:
    def test_exe_excluded(self):
        excluded, _ = _is_excluded("avatar/export/gopher-bot-avatar.exe")
        assert excluded

    def test_pck_excluded(self):
        excluded, _ = _is_excluded("avatar/export/gopher-bot-avatar.pck")
        assert excluded

    def test_pyc_excluded(self):
        excluded, _ = _is_excluded("coordinators/reason.pyc")
        assert excluded

    def test_index_lock_excluded(self):
        excluded, _ = _is_excluded(".git/index.lock")
        assert excluded

    def test_vulkan_cache_excluded(self):
        excluded, _ = _is_excluded("avatar/.godot/shader_cache/CanvasShaderRD/abc123.vulkan.cache")
        assert excluded


# ---------------------------------------------------------------------------
# Files that SHOULD be included
# ---------------------------------------------------------------------------

class TestInclusions:
    def test_source_file_included(self):
        excluded, _ = _is_excluded("coordinators/reason.py")
        assert not excluded

    def test_charter_included(self):
        excluded, _ = _is_excluded("AGENT_CHARTER.md")
        assert not excluded

    def test_development_charter_included(self):
        excluded, _ = _is_excluded("DEVELOPMENT_CHARTER.md")
        assert not excluded

    def test_agents_md_included(self):
        excluded, _ = _is_excluded("AGENTS.md")
        assert not excluded

    def test_config_example_included(self):
        excluded, _ = _is_excluded("world_models/config.example.py")
        assert not excluded

    def test_test_files_included(self):
        excluded, _ = _is_excluded("tests/test_reason.py")
        assert not excluded

    def test_requirements_included(self):
        excluded, _ = _is_excluded("requirements.txt")
        assert not excluded

    def test_action_logs_included(self):
        excluded, _ = _is_excluded("logs/actions/20260519.md")
        assert not excluded


# ---------------------------------------------------------------------------
# Verify exclusions integration check
# ---------------------------------------------------------------------------

class TestVerifyExclusions:
    def test_verify_all_pass(self):
        """verify_exclusions() must return True — all known secrets are excluded."""
        assert verify_exclusions() is True
