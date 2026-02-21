"""Unit tests for SettingRow widget — scope transitions and control value setting."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from claude_tui_settings.app import BootstrapApp
from claude_tui_settings.models.config import (
    ConfigState,
    EffectiveConfig,
    ResolvedValue,
    SettingDef,
    _NO_VALUE,
)
from claude_tui_settings.widgets.settings_tab import SettingRow, SettingsSection


def _make_config(
    settings: list[SettingDef],
    selected: dict[str, Any] | None = None,
    effective_settings: list[ResolvedValue] | None = None,
) -> ConfigState:
    """Create a minimal ConfigState for testing settings."""
    return ConfigState(
        claude_repo=Path("/tmp/test-claude"),
        available_settings=settings,
        selected_settings=dict(selected or {}),
        effective=EffectiveConfig(settings=list(effective_settings or [])),
    )


def _make_app(config: ConfigState) -> BootstrapApp:
    return BootstrapApp(config=config)


# ── Scope determination ──────────────────────────────────────────────


class TestScopeDetermination:
    """Test _determine_scope returns correct scope for each state."""

    def test_project_scope(self):
        setting = SettingDef("effortLevel", "enum", "Effort", "medium", ["low", "medium", "high"])
        config = _make_config([setting], selected={"effortLevel": "high"})
        row = SettingRow(setting, config)
        assert row._determine_scope() == "PROJECT"

    def test_user_scope(self):
        setting = SettingDef("effortLevel", "enum", "Effort", "medium", ["low", "medium", "high"])
        rv = ResolvedValue(key="effortLevel", value="low", source_scope="User")
        config = _make_config([setting], effective_settings=[rv])
        row = SettingRow(setting, config)
        assert row._determine_scope() == "USER"

    def test_unset_scope(self):
        setting = SettingDef("effortLevel", "enum", "Effort", "medium", ["low", "medium", "high"])
        config = _make_config([setting])
        row = SettingRow(setting, config)
        assert row._determine_scope() == "UNSET"

    def test_project_overrides_user(self):
        """PROJECT takes precedence even when USER value exists."""
        setting = SettingDef("effortLevel", "enum", "Effort", "medium", ["low", "medium", "high"])
        rv = ResolvedValue(
            key="effortLevel", value="high", source_scope="Project",
            overridden_scopes=[("User", "low")],
        )
        config = _make_config(
            [setting],
            selected={"effortLevel": "high"},
            effective_settings=[rv],
        )
        row = SettingRow(setting, config)
        assert row._determine_scope() == "PROJECT"


# ── Badge text ───────────────────────────────────────────────────────


class TestBadgeText:
    """Test badge text uses parentheses (not brackets) to avoid Rich markup."""

    def test_user_badge(self):
        setting = SettingDef("k", "string")
        config = _make_config([setting])
        row = SettingRow(setting, config)
        assert row._badge_text("USER") == "(USER)"

    def test_project_badge(self):
        setting = SettingDef("k", "string")
        config = _make_config([setting])
        row = SettingRow(setting, config)
        assert row._badge_text("PROJECT") == "(PROJECT)"

    def test_unset_badge(self):
        setting = SettingDef("k", "string")
        config = _make_config([setting])
        row = SettingRow(setting, config)
        assert row._badge_text("UNSET") == "(NOT SET)"


# ── Action link markup ───────────────────────────────────────────────


class TestActionMarkup:
    """Test action link shows correct label based on scope and user value."""

    def test_no_action_for_user_scope(self):
        setting = SettingDef("k", "string")
        config = _make_config([setting])
        row = SettingRow(setting, config)
        assert row._action_markup("USER", "some_value") == ""

    def test_no_action_for_unset_scope(self):
        setting = SettingDef("k", "string")
        config = _make_config([setting])
        row = SettingRow(setting, config)
        assert row._action_markup("UNSET", _NO_VALUE) == ""

    def test_revert_when_user_value_exists(self):
        setting = SettingDef("k", "string")
        config = _make_config([setting])
        row = SettingRow(setting, config)
        markup = row._action_markup("PROJECT", "user_val")
        assert "revert" in markup

    def test_unset_when_no_user_value(self):
        setting = SettingDef("k", "string")
        config = _make_config([setting])
        row = SettingRow(setting, config)
        markup = row._action_markup("PROJECT", _NO_VALUE)
        assert "unset" in markup


# ── _set_control_value for each type ─────────────────────────────────


class TestSetControlValue:
    """Test _set_control_value works for all control types without errors."""

    @pytest.mark.asyncio
    async def test_enum_set_to_none(self, tmp_path):
        """Select.clear() must be used, not Select.BLANK assignment."""
        setting = SettingDef("channel", "enum", "Channel", "stable", ["stable", "beta"])
        config = _make_config(
            [setting],
            selected={"channel": "beta"},
        )
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "channel")

            # Should not raise InvalidSelectValueError
            row._set_control_value(None)
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_enum_set_to_value(self, tmp_path):
        """Setting an enum to a valid value works."""
        setting = SettingDef("channel", "enum", "Channel", "stable", ["stable", "beta"])
        config = _make_config([setting], selected={"channel": "beta"})
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "channel")
            row._set_control_value("stable")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_boolean_set_to_none(self, tmp_path):
        """Setting a boolean to None sets switch to False."""
        setting = SettingDef("gitignore", "boolean", "Respect gitignore", True)
        config = _make_config([setting], selected={"gitignore": True})
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "gitignore")
            row._set_control_value(None)
            await pilot.pause()
            assert row._control.value is False

    @pytest.mark.asyncio
    async def test_boolean_set_to_true(self, tmp_path):
        setting = SettingDef("gitignore", "boolean", "Respect gitignore", True)
        config = _make_config([setting])
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "gitignore")
            row._set_control_value(True)
            await pilot.pause()
            assert row._control.value is True

    @pytest.mark.asyncio
    async def test_string_set_to_none(self, tmp_path):
        """Setting a string to None clears the input."""
        setting = SettingDef("apiKey", "string", "API Key")
        config = _make_config([setting], selected={"apiKey": "abc123"})
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "apiKey")
            row._set_control_value(None)
            await pilot.pause()
            assert row._control.value == ""

    @pytest.mark.asyncio
    async def test_string_set_to_value(self, tmp_path):
        setting = SettingDef("apiKey", "string", "API Key")
        config = _make_config([setting])
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "apiKey")
            row._set_control_value("new-key")
            await pilot.pause()
            assert row._control.value == "new-key"

    @pytest.mark.asyncio
    async def test_number_set_to_none(self, tmp_path):
        setting = SettingDef("timeout", "number", "Timeout seconds")
        config = _make_config([setting], selected={"timeout": 30})
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "timeout")
            row._set_control_value(None)
            await pilot.pause()
            assert row._control.value == ""

    @pytest.mark.asyncio
    async def test_object_set_to_dict(self, tmp_path):
        """Dict values are JSON-serialized into the input."""
        setting = SettingDef("env", "object", "Environment vars")
        config = _make_config([setting])
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "env")
            row._set_control_value({"FOO": "bar"})
            await pilot.pause()
            assert json.loads(row._control.value) == {"FOO": "bar"}


# ── Revert/unset flow ────────────────────────────────────────────────


class TestRevertUnset:
    """Test _do_revert_or_unset for each control type."""

    @pytest.mark.asyncio
    async def test_enum_unset(self, tmp_path):
        """Unsetting an enum (no user value) should clear the select."""
        setting = SettingDef("channel", "enum", "Channel", "stable", ["stable", "beta"])
        config = _make_config([setting], selected={"channel": "beta"})
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "channel")
            assert row._determine_scope() == "PROJECT"

            # Unset — should not raise
            row._do_revert_or_unset()
            await pilot.pause()

            assert "channel" not in config.selected_settings
            assert row._determine_scope() == "UNSET"

    @pytest.mark.asyncio
    async def test_enum_revert_to_user(self, tmp_path):
        """Reverting an enum with user value should restore user value."""
        setting = SettingDef("channel", "enum", "Channel", "stable", ["stable", "beta"])
        rv = ResolvedValue(
            key="channel", value="beta", source_scope="Project",
            overridden_scopes=[("User", "stable")],
        )
        config = _make_config(
            [setting],
            selected={"channel": "beta"},
            effective_settings=[rv],
        )
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "channel")
            row._do_revert_or_unset()
            await pilot.pause()

            assert "channel" not in config.selected_settings
            assert row._determine_scope() == "USER"

    @pytest.mark.asyncio
    async def test_boolean_unset(self, tmp_path):
        """Unsetting a boolean should set switch to False and show UNSET."""
        setting = SettingDef("gitignore", "boolean", "Respect gitignore", True)
        config = _make_config([setting], selected={"gitignore": True})
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()

            rows = app.query(SettingRow)
            row = next(r for r in rows if r.setting_def.key == "gitignore")
            row._do_revert_or_unset()
            await pilot.pause()

            assert "gitignore" not in config.selected_settings
            assert row._determine_scope() == "UNSET"
            assert row._control.value is False


# ── Compose-leak prevention ──────────────────────────────────────────


class TestComposeLeak:
    """Test that compose does NOT leak USER values into selected_settings."""

    @pytest.mark.asyncio
    async def test_user_value_not_promoted_on_compose(self, tmp_path):
        """Opening settings tab with USER-scoped values should not add to selected_settings."""
        setting = SettingDef("effortLevel", "enum", "Effort", "medium", ["low", "medium", "high"])
        rv = ResolvedValue(key="effortLevel", value="low", source_scope="User")
        config = _make_config([setting], effective_settings=[rv])
        app = _make_app(config)
        async with app.run_test(size=(80, 30)) as pilot:
            app._show_section("settings")
            await pilot.pause()
            await pilot.pause()  # Extra pause for call_later to fire

            # selected_settings should still be empty
            assert "effortLevel" not in config.selected_settings
