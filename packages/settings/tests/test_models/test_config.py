"""Tests for ConfigState and Diff."""

from pathlib import Path

from claude_tui_settings.models.config import ConfigState, Diff, DiffEntry


def _make_config(**kwargs) -> ConfigState:
    defaults = dict(claude_repo=Path("/tmp/claude"))
    defaults.update(kwargs)
    return ConfigState(**defaults)


def test_empty_config_has_profile_add():
    """A fresh config with no existing profile shows a profile addition."""
    config = _make_config()
    diff = config.pending_diff()
    assert len(diff.entries) == 1
    assert diff.entries[0].domain == "profile"
    assert diff.entries[0].action == "add"


def test_matching_profile_no_diff():
    """When selected matches existing profile, no diff."""
    config = _make_config(
        existing_profile="standard",
        selected_profile="standard",
    )
    diff = config.pending_diff()
    assert diff.is_empty


def test_profile_change_shows_modify():
    config = _make_config(
        existing_profile="standard",
        selected_profile="permissive",
    )
    diff = config.pending_diff()
    entries = [e for e in diff.entries if e.domain == "profile"]
    assert len(entries) == 1
    assert entries[0].action == "modify"
    assert entries[0].old_value == "standard"
    assert entries[0].new_value == "permissive"


def test_command_additions():
    config = _make_config(
        existing_profile="standard",
        selected_profile="standard",
        selected_commands={"cmd1", "cmd2"},
    )
    diff = config.pending_diff()
    adds = diff.additions
    assert len(adds) == 2
    assert {e.key for e in adds} == {"cmd1", "cmd2"}


def test_command_removals():
    config = _make_config(
        existing_profile="standard",
        selected_profile="standard",
        existing_commands={"cmd1", "cmd2"},
        selected_commands={"cmd1"},
    )
    diff = config.pending_diff()
    removals = diff.removals
    assert len(removals) == 1
    assert removals[0].key == "cmd2"


def test_settings_diff():
    config = _make_config(
        existing_profile="standard",
        selected_profile="standard",
        existing_settings={"effortLevel": "medium"},
        selected_settings={"effortLevel": "high"},
    )
    diff = config.pending_diff()
    mods = diff.modifications
    assert len(mods) == 1
    assert mods[0].key == "effortLevel"
    assert mods[0].old_value == "medium"
    assert mods[0].new_value == "high"


def test_settings_addition():
    config = _make_config(
        existing_profile="standard",
        selected_profile="standard",
        selected_settings={"newSetting": True},
    )
    diff = config.pending_diff()
    adds = [e for e in diff.additions if e.domain == "settings"]
    assert len(adds) == 1
    assert adds[0].key == "newSetting"


def test_settings_removal():
    config = _make_config(
        existing_profile="standard",
        selected_profile="standard",
        existing_settings={"oldSetting": "val"},
        selected_settings={},
    )
    diff = config.pending_diff()
    removals = [e for e in diff.removals if e.domain == "settings"]
    assert len(removals) == 1
    assert removals[0].key == "oldSetting"


def test_has_pending_changes():
    config = _make_config(
        existing_profile="standard",
        selected_profile="standard",
    )
    assert not config.has_pending_changes

    config.selected_commands.add("new_cmd")
    assert config.has_pending_changes


def test_diff_count_for_domain():
    diff = Diff(entries=[
        DiffEntry(domain="commands", action="add", key="cmd1"),
        DiffEntry(domain="commands", action="add", key="cmd2"),
        DiffEntry(domain="skills", action="add", key="skill1"),
    ])
    assert diff.count_for_domain("commands") == 2
    assert diff.count_for_domain("skills") == 1
    assert diff.count_for_domain("agents") == 0


def test_multi_domain_diff():
    """Test diff across multiple domains simultaneously."""
    config = _make_config(
        existing_profile="standard",
        selected_profile="permissive",
        existing_commands={"old_cmd"},
        selected_commands={"new_cmd"},
        existing_skills=set(),
        selected_skills={"textual-tui"},
    )
    diff = config.pending_diff()
    assert diff.count_for_domain("profile") == 1
    assert diff.count_for_domain("commands") == 2  # 1 add + 1 remove
    assert diff.count_for_domain("skills") == 1
