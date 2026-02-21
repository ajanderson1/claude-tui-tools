"""Tests for preset I/O — slugify, list, parse, validate, save, load."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from claude_tui_settings.models.config import (
    ConfigState,
    Hook,
    MCP,
    Plugin,
    Preset,
    Profile,
    Resource,
    SettingDef,
)
from claude_tui_settings.models.presets import (
    _parse_preset,
    list_presets,
    load_preset_into_state,
    save_preset,
    slugify,
    validate_preset,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(tmp_path: Path, **kwargs) -> ConfigState:
    defaults = dict(
        claude_repo=tmp_path,
        available_profiles=[
            Profile("standard", "Standard profile", tmp_path / "profiles" / "standard.json"),
        ],
        available_commands=[Resource("cmd/a", tmp_path / "commands" / "cmd" / "a")],
        available_agents=[Resource("agent/a", tmp_path / "agents" / "agent" / "a")],
        available_skills=[Resource("skill-a", tmp_path / "skills" / "skill-a")],
        available_plugins=[Plugin("plugin-a", "Plugin A", "")],
        available_mcps=[MCP("mcp-a", {})],
        available_hooks=[Hook("hook-a", "pre_tool_use", "")],
        available_settings=[SettingDef("theme", "string")],
    )
    defaults.update(kwargs)
    return ConfigState(**defaults)


def _write_preset(configs_dir: Path, slug: str, data: dict) -> Path:
    configs_dir.mkdir(parents=True, exist_ok=True)
    path = configs_dir / f"{slug}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _valid_preset_data(*, name: str = "My Preset") -> dict:
    return {
        "meta": {"name": name, "description": "desc", "created_at": "2025-01-01T00:00:00+00:00"},
        "profile": "standard",
        "commands": ["cmd/a"],
        "agents": [],
        "skills": ["skill-a"],
        "plugins": [],
        "mcps": [],
        "hooks": [],
        "settings": {"theme": "dark"},
    }


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        assert slugify("My Preset") == "my-preset"

    def test_unicode(self):
        assert slugify("cafe\u0301") == "cafe"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            slugify("!!!")

    def test_special_chars(self):
        assert slugify("a@b#c$d") == "a-b-c-d"

    def test_multiple_dashes_collapsed(self):
        assert slugify("a---b") == "a-b"

    def test_leading_trailing_stripped(self):
        assert slugify("--hello--") == "hello"


# ---------------------------------------------------------------------------
# list_presets
# ---------------------------------------------------------------------------

class TestListPresets:
    def test_empty_dir(self, tmp_path: Path):
        assert list_presets(tmp_path) == []

    def test_with_files(self, tmp_path: Path):
        configs_dir = tmp_path / "configs"
        _write_preset(configs_dir, "alpha", _valid_preset_data(name="Alpha"))
        _write_preset(configs_dir, "beta", _valid_preset_data(name="Beta"))

        result = list_presets(tmp_path)
        assert len(result) == 2
        assert result[0].name == "Alpha"
        assert result[1].name == "Beta"

    def test_skips_symlinks(self, tmp_path: Path):
        configs_dir = tmp_path / "configs"
        real = _write_preset(configs_dir, "real", _valid_preset_data(name="Real"))
        link = configs_dir / "link.json"
        link.symlink_to(real)

        result = list_presets(tmp_path)
        assert len(result) == 1
        assert result[0].slug == "real"

    def test_skips_large_files(self, tmp_path: Path):
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir(parents=True)
        big = configs_dir / "big.json"
        big.write_text("x" * 1024, encoding="utf-8")

        result = list_presets(tmp_path, max_size=512)
        assert result == []

    def test_skips_invalid_json(self, tmp_path: Path):
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir(parents=True)
        bad = configs_dir / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")

        result = list_presets(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# _parse_preset
# ---------------------------------------------------------------------------

class TestParsePreset:
    def test_valid(self):
        preset = _parse_preset("my-preset", _valid_preset_data())
        assert preset is not None
        assert preset.slug == "my-preset"
        assert preset.name == "My Preset"
        assert preset.profile == "standard"
        assert preset.commands == ["cmd/a"]
        assert preset.settings == {"theme": "dark"}

    def test_invalid_profile(self):
        data = _valid_preset_data()
        data["profile"] = 123
        assert _parse_preset("x", data) is None

    def test_invalid_resource_list(self):
        data = _valid_preset_data()
        data["commands"] = "not-a-list"
        assert _parse_preset("x", data) is None

    def test_invalid_resource_item(self):
        data = _valid_preset_data()
        data["commands"] = [123]
        assert _parse_preset("x", data) is None

    def test_invalid_settings_value(self):
        data = _valid_preset_data()
        data["settings"] = {"key": [1, 2, 3]}
        assert _parse_preset("x", data) is None


# ---------------------------------------------------------------------------
# validate_preset
# ---------------------------------------------------------------------------

class TestValidatePreset:
    def test_all_valid(self, tmp_path: Path):
        state = _make_state(tmp_path)
        preset = Preset(
            name="test", slug="test", profile="standard",
            commands=["cmd/a"], skills=["skill-a"],
            settings={"theme": "dark"},
        )
        issues = validate_preset(preset, state)
        assert issues == []

    def test_missing_items(self, tmp_path: Path):
        state = _make_state(tmp_path)
        preset = Preset(
            name="test", slug="test", profile="unknown",
            commands=["cmd/missing"], agents=["agent/missing"],
            settings={"nonexistent": "val"},
        )
        issues = validate_preset(preset, state)
        domains = {i[0] for i in issues}
        assert "profile" in domains
        assert "commands" in domains
        assert "agents" in domains
        assert "settings" in domains
        assert len(issues) == 4


# ---------------------------------------------------------------------------
# save_preset
# ---------------------------------------------------------------------------

class TestSavePreset:
    def test_save(self, tmp_path: Path):
        state = _make_state(tmp_path)
        state.selected_profile = "standard"
        state.selected_commands = {"cmd/a"}
        state.selected_skills = {"skill-a"}
        state.selected_settings = {"theme": "dark"}

        path = save_preset("My Preset", "A description", state)
        assert path.exists()
        assert path.name == "my-preset.json"

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["meta"]["name"] == "My Preset"
        assert data["meta"]["description"] == "A description"
        assert data["profile"] == "standard"
        assert data["commands"] == ["cmd/a"]
        assert data["settings"] == {"theme": "dark"}

    def test_refuses_symlink(self, tmp_path: Path):
        state = _make_state(tmp_path)
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir()
        target = configs_dir / "real.json"
        target.write_text("{}", encoding="utf-8")
        link = configs_dir / "my-preset.json"
        link.symlink_to(target)

        with pytest.raises(ValueError, match="symlink"):
            save_preset("My Preset", "", state)


# ---------------------------------------------------------------------------
# load_preset_into_state
# ---------------------------------------------------------------------------

class TestLoadPresetIntoState:
    def test_load(self, tmp_path: Path):
        state = _make_state(tmp_path)
        preset = Preset(
            name="test", slug="test", profile="standard",
            commands=["cmd/a"], skills=["skill-a"],
            settings={"theme": "dark"},
        )
        load_preset_into_state(preset, state)

        assert state.selected_profile == "standard"
        assert state.selected_commands == {"cmd/a"}
        assert state.selected_skills == {"skill-a"}
        assert state.selected_settings == {"theme": "dark"}
        # Other domains should be cleared
        assert state.selected_agents == set()

    def test_load_with_skip(self, tmp_path: Path):
        state = _make_state(tmp_path)
        preset = Preset(
            name="test", slug="test", profile="standard",
            commands=["cmd/a"], skills=["skill-a"],
            settings={"theme": "dark"},
        )
        skip = {("commands", "cmd/a"), ("settings", "theme")}
        load_preset_into_state(preset, state, skip=skip)

        assert state.selected_commands == set()
        assert state.selected_skills == {"skill-a"}
        assert state.selected_settings == {}
        assert state.selected_profile == "standard"
