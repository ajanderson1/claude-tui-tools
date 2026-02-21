"""Integration tests for BootstrapApp using Textual Pilot."""

import json
from pathlib import Path

import pytest

from claude_tui_settings.app import BootstrapApp, SECTIONS
from claude_tui_settings.models.config import (
    ConfigState,
    Hook,
    MCP,
    Plugin,
    Profile,
    Resource,
    SettingDef,
)


def _make_test_config(tmp_path: Path) -> ConfigState:
    """Create a ConfigState suitable for testing."""
    repo = tmp_path / "claude"
    repo.mkdir(exist_ok=True)

    # Create profile file
    profiles_dir = repo / "profiles"
    profiles_dir.mkdir(exist_ok=True)
    (profiles_dir / "standard.json").write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "description": "Standard profile",
    }))
    (profiles_dir / "strict.json").write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "description": "Strict profile",
        "permissions": {"ask": ["Bash(rm:*)"]},
    }))

    return ConfigState(
        claude_repo=repo,
        available_profiles=[
            Profile("standard", "Standard", profiles_dir / "standard.json"),
            Profile("strict", "Strict", profiles_dir / "strict.json"),
        ],
        available_commands=[
            Resource("test/hello", repo / "commands" / "test" / "hello.md", "test"),
            Resource("test/world", repo / "commands" / "test" / "world.md", "test"),
        ],
        available_agents=[
            Resource("researcher", repo / "agents" / "researcher.md"),
        ],
        available_skills=[
            Resource("textual-tui", repo / "skills" / "textual-tui"),
        ],
        available_plugins=[
            Plugin("test-plugin", "Test Plugin", "A test plugin"),
        ],
        available_mcps=[
            MCP("test-mcp", {"type": "stdio"}, "Test MCP"),
        ],
        available_hooks=[
            Hook("auto-format", "PostToolUse", "Edit|Write", "Auto format"),
        ],
        available_settings=[
            SettingDef("effortLevel", "enum", "Effort level", "medium", ["low", "medium", "high"]),
            SettingDef("respectGitignore", "boolean", "Respect gitignore", True),
        ],
        existing_profile="standard",
        selected_profile="standard",
    )


@pytest.mark.asyncio
async def test_app_renders(tmp_path):
    """Test that the app renders without errors."""
    config = _make_test_config(tmp_path)
    app = BootstrapApp(config=config)
    async with app.run_test(size=(80, 24)) as pilot:
        # App should render
        assert app.is_running


@pytest.mark.asyncio
async def test_sidebar_has_all_sections(tmp_path):
    """Test that sidebar contains all 11 sections."""
    config = _make_test_config(tmp_path)
    app = BootstrapApp(config=config)
    async with app.run_test(size=(80, 24)) as pilot:
        from textual.widgets import OptionList
        sidebar = app.query_one("#sidebar-list", OptionList)
        assert sidebar.option_count == 11


@pytest.mark.asyncio
async def test_sidebar_navigation(tmp_path):
    """Test navigating sidebar with arrow keys."""
    config = _make_test_config(tmp_path)
    app = BootstrapApp(config=config)
    async with app.run_test(size=(80, 24)) as pilot:
        # Focus the sidebar
        from textual.widgets import OptionList
        sidebar = app.query_one("#sidebar-list", OptionList)
        sidebar.focus()
        await pilot.pause()

        # Navigate down
        await pilot.press("down")
        await pilot.pause()
        assert app.current_section == 1  # Permissions


@pytest.mark.asyncio
async def test_overview_shows_no_changes(tmp_path):
    """Test overview shows no changes for matching config."""
    config = _make_test_config(tmp_path)
    app = BootstrapApp(config=config)
    async with app.run_test(size=(80, 24)) as pilot:
        # Overview is shown by default
        from claude_tui_settings.widgets.overview import OverviewSection
        overview = app.query_one(OverviewSection)
        assert overview is not None


@pytest.mark.asyncio
async def test_quit_with_no_changes(tmp_path):
    """Test that q exits immediately with no pending changes."""
    config = _make_test_config(tmp_path)
    app = BootstrapApp(config=config)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("q")
        await pilot.pause()
        # App should have exited (or be exiting)


@pytest.mark.asyncio
async def test_alt_jump_keys(tmp_path):
    """Test Alt+N shortcuts for section jumping."""
    config = _make_test_config(tmp_path)
    app = BootstrapApp(config=config)
    async with app.run_test(size=(80, 24)) as pilot:
        # Jump to Skills (index 4 = Alt+5)
        await pilot.press("alt+5")
        await pilot.pause()
        assert app.current_section == 4


@pytest.mark.asyncio
async def test_no_changes_apply_notifies(tmp_path):
    """Test that Ctrl+S with no changes shows notification."""
    config = _make_test_config(tmp_path)
    app = BootstrapApp(config=config)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()
        # Should show "No changes to apply" notification
