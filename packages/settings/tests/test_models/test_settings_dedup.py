"""Tests for settings scope helpers and persistence dedup (issue #8)."""

import json
from pathlib import Path

import pytest

from claude_tui_settings.models.config import (
    _NO_VALUE,
    ConfigState,
    EffectiveConfig,
    Profile,
    ResolvedValue,
)
from claude_tui_settings.models.persistence import apply_config


def _make_config(**kwargs) -> ConfigState:
    defaults = dict(claude_repo=Path("/tmp/claude"))
    defaults.update(kwargs)
    return ConfigState(**defaults)


# --- get_user_scope_value ---


class TestGetUserScopeValue:
    def test_returns_user_value_when_user_is_winner(self):
        """When User scope is the effective winner, return its value."""
        config = _make_config(effective=EffectiveConfig(settings=[
            ResolvedValue(key="effortLevel", value="high", source_scope="User"),
        ]))
        assert config.get_user_scope_value("effortLevel") == "high"

    def test_returns_user_value_when_overridden_by_project(self):
        """When Project overrides User, extract user value from overridden_scopes."""
        config = _make_config(effective=EffectiveConfig(settings=[
            ResolvedValue(
                key="effortLevel", value="low", source_scope="Project",
                overridden_scopes=[("User", "high")],
            ),
        ]))
        assert config.get_user_scope_value("effortLevel") == "high"

    def test_returns_user_project_value(self):
        """User-Project scope is also treated as user scope."""
        config = _make_config(effective=EffectiveConfig(settings=[
            ResolvedValue(key="effortLevel", value="medium", source_scope="User-Project"),
        ]))
        assert config.get_user_scope_value("effortLevel") == "medium"

    def test_returns_no_value_when_only_project_scope(self):
        """When only Project scope exists, no user-scope value."""
        config = _make_config(effective=EffectiveConfig(settings=[
            ResolvedValue(key="effortLevel", value="low", source_scope="Project"),
        ]))
        assert config.get_user_scope_value("effortLevel") is _NO_VALUE

    def test_returns_no_value_for_unknown_key(self):
        config = _make_config(effective=EffectiveConfig(settings=[]))
        assert config.get_user_scope_value("nonexistent") is _NO_VALUE

    def test_returns_no_value_when_managed_only(self):
        config = _make_config(effective=EffectiveConfig(settings=[
            ResolvedValue(key="effortLevel", value="high", source_scope="Managed"),
        ]))
        assert config.get_user_scope_value("effortLevel") is _NO_VALUE

    def test_returns_user_value_from_deep_overridden_scopes(self):
        """User value extracted even when multiple scopes override."""
        config = _make_config(effective=EffectiveConfig(settings=[
            ResolvedValue(
                key="effortLevel", value="max", source_scope="Managed",
                overridden_scopes=[("Project", "low"), ("User", "medium")],
            ),
        ]))
        assert config.get_user_scope_value("effortLevel") == "medium"

    def test_boolean_value_preserved(self):
        """Boolean user-scope values are returned as-is."""
        config = _make_config(effective=EffectiveConfig(settings=[
            ResolvedValue(key="verbose", value=True, source_scope="User"),
        ]))
        assert config.get_user_scope_value("verbose") is True


# --- get_effective_value ---


class TestGetEffectiveValue:
    def test_returns_effective_value(self):
        config = _make_config(effective=EffectiveConfig(settings=[
            ResolvedValue(key="effortLevel", value="high", source_scope="User"),
        ]))
        assert config.get_effective_value("effortLevel") == "high"

    def test_returns_default_for_unknown_key(self):
        config = _make_config(effective=EffectiveConfig(settings=[]))
        assert config.get_effective_value("nonexistent", "fallback") == "fallback"

    def test_returns_none_default(self):
        config = _make_config(effective=EffectiveConfig(settings=[]))
        assert config.get_effective_value("nonexistent") is None


# --- Persistence dedup ---


@pytest.fixture
def claude_repo(tmp_path):
    repo = tmp_path / "claude"
    repo.mkdir()
    profiles_dir = repo / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "standard.json").write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "description": "Standard profile",
    }))
    return repo


@pytest.fixture
def project_dir(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    return project


class TestPersistenceDedup:
    def test_skips_setting_matching_user_scope(self, claude_repo, project_dir):
        """Settings matching user-scope value should not be written."""
        config = ConfigState(
            claude_repo=claude_repo,
            available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
            selected_profile="standard",
            selected_settings={"effortLevel": "high"},
            effective=EffectiveConfig(settings=[
                ResolvedValue(key="effortLevel", value="high", source_scope="User"),
            ]),
        )
        apply_config(config, project_dir)

        data = json.loads((project_dir / ".claude" / "settings.json").read_text())
        assert "effortLevel" not in data

    def test_keeps_setting_differing_from_user_scope(self, claude_repo, project_dir):
        """Settings differing from user-scope value should be written."""
        config = ConfigState(
            claude_repo=claude_repo,
            available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
            selected_profile="standard",
            selected_settings={"effortLevel": "low"},
            effective=EffectiveConfig(settings=[
                ResolvedValue(key="effortLevel", value="high", source_scope="User"),
            ]),
        )
        apply_config(config, project_dir)

        data = json.loads((project_dir / ".claude" / "settings.json").read_text())
        assert data["effortLevel"] == "low"

    def test_keeps_setting_with_no_user_scope(self, claude_repo, project_dir):
        """Settings with no user-scope counterpart should be written normally."""
        config = ConfigState(
            claude_repo=claude_repo,
            available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
            selected_profile="standard",
            selected_settings={"customSetting": "value"},
            effective=EffectiveConfig(settings=[]),
        )
        apply_config(config, project_dir)

        data = json.loads((project_dir / ".claude" / "settings.json").read_text())
        assert data["customSetting"] == "value"

    def test_dedup_with_overridden_user_scope(self, claude_repo, project_dir):
        """Dedup works when user scope is in overridden_scopes (project wins)."""
        config = ConfigState(
            claude_repo=claude_repo,
            available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
            selected_profile="standard",
            selected_settings={"effortLevel": "medium"},
            effective=EffectiveConfig(settings=[
                ResolvedValue(
                    key="effortLevel", value="low", source_scope="Project",
                    overridden_scopes=[("User", "medium")],
                ),
            ]),
        )
        apply_config(config, project_dir)

        data = json.loads((project_dir / ".claude" / "settings.json").read_text())
        # selected value "medium" matches user-scope "medium", so it's deduped
        assert "effortLevel" not in data
