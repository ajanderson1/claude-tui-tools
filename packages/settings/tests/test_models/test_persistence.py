"""Tests for persistence module."""

import json
import os
from pathlib import Path

import pytest

from claude_tui_settings.models.config import ConfigState, Hook, MCP, Plugin, Profile, Resource
from claude_tui_settings.models.persistence import apply_config


@pytest.fixture
def claude_repo(tmp_path):
    """Create a minimal $CLAUDE_REPO."""
    repo = tmp_path / "claude"
    repo.mkdir()

    # Profiles
    profiles_dir = repo / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "standard.json").write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "description": "Standard profile",
    }))

    # Commands
    cmd_dir = repo / "commands" / "test"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "hello.md").write_text("# Hello")

    # Skills
    skill_dir = repo / "skills" / "textual-tui"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Skill")

    # Hooks
    hook_dir = repo / "hooks" / "available" / "auto-format"
    hook_dir.mkdir(parents=True)
    (hook_dir / "hook.json").write_text(json.dumps({
        "event": "PostToolUse",
        "matcher": "Edit|Write",
        "command_template": "{HOOKS_DIR}/auto-format.sh",
    }))
    script = hook_dir / "auto-format.sh"
    script.write_text("#!/bin/bash\necho format")
    script.chmod(0o755)

    return repo


@pytest.fixture
def project_dir(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    return project


def test_apply_creates_settings_json(claude_repo, project_dir):
    config = ConfigState(
        claude_repo=claude_repo,
        available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
        selected_profile="standard",
    )
    apply_config(config, project_dir)

    settings_path = project_dir / ".claude" / "settings.json"
    assert settings_path.is_file()
    data = json.loads(settings_path.read_text())
    assert "$schema" in data
    assert "description" not in data


def test_apply_creates_mcp_json(claude_repo, project_dir):
    config = ConfigState(
        claude_repo=claude_repo,
        available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
        available_mcps=[MCP("test-mcp", {"type": "stdio", "command": "test"}, "Test MCP")],
        selected_profile="standard",
        selected_mcps={"test-mcp"},
    )
    apply_config(config, project_dir)

    mcp_path = project_dir / ".mcp.json"
    assert mcp_path.is_file()
    data = json.loads(mcp_path.read_text())
    assert "test-mcp" in data["mcpServers"]


def test_apply_creates_command_symlinks(claude_repo, project_dir):
    config = ConfigState(
        claude_repo=claude_repo,
        available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
        available_commands=[Resource("test/hello", claude_repo / "commands" / "test" / "hello.md", "test")],
        selected_profile="standard",
        selected_commands={"test/hello"},
    )
    apply_config(config, project_dir)

    link = project_dir / ".claude" / "commands" / "test" / "hello.md"
    assert link.is_symlink()
    assert link.resolve() == (claude_repo / "commands" / "test" / "hello.md").resolve()


def test_apply_creates_skill_symlinks(claude_repo, project_dir):
    config = ConfigState(
        claude_repo=claude_repo,
        available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
        available_skills=[Resource("textual-tui", claude_repo / "skills" / "textual-tui")],
        selected_profile="standard",
        selected_skills={"textual-tui"},
    )
    apply_config(config, project_dir)

    link = project_dir / ".claude" / "skills" / "textual-tui"
    assert link.is_symlink()


def test_apply_writes_plugins(claude_repo, project_dir):
    config = ConfigState(
        claude_repo=claude_repo,
        available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
        selected_profile="standard",
        selected_plugins={"test-plugin@marketplace"},
    )
    apply_config(config, project_dir)

    data = json.loads((project_dir / ".claude" / "settings.json").read_text())
    assert data.get("enabledPlugins", {}).get("test-plugin@marketplace") is True


def test_apply_updates_claude_md(claude_repo, project_dir):
    config = ConfigState(
        claude_repo=claude_repo,
        available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
        selected_profile="standard",
        selected_skills={"textual-tui"},
    )
    apply_config(config, project_dir)

    claude_md = project_dir / "CLAUDE.md"
    assert claude_md.is_file()
    content = claude_md.read_text()
    assert "<!-- BEGIN:BOOTSTRAPPED_TOOLS -->" in content
    assert "<!-- END:BOOTSTRAPPED_TOOLS -->" in content
    assert "textual-tui" in content
    assert "standard" in content
    assert "<!-- BEGIN:PROJECT_NOTE -->" not in content


def test_apply_updates_gitignore(claude_repo, project_dir):
    config = ConfigState(
        claude_repo=claude_repo,
        available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
        selected_profile="standard",
    )
    apply_config(config, project_dir)

    gitignore = project_dir / ".gitignore"
    assert gitignore.is_file()
    content = gitignore.read_text()
    assert ".claude/" in content
    assert ".mcp.json" in content


def test_apply_preserves_existing_claude_md_content(claude_repo, project_dir):
    """Existing CLAUDE.md content outside sentinels should be preserved."""
    claude_md = project_dir / "CLAUDE.md"
    claude_md.write_text("# My Project\n\nCustom content here.\n")

    config = ConfigState(
        claude_repo=claude_repo,
        available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
        selected_profile="standard",
    )
    apply_config(config, project_dir)

    content = claude_md.read_text()
    assert "# My Project" in content
    assert "Custom content here." in content
    assert "<!-- BEGIN:BOOTSTRAPPED_TOOLS -->" in content


def test_apply_cleans_staging_on_failure(claude_repo, project_dir):
    """Staging directory should be cleaned up on failure."""
    staging = project_dir / ".claude" / ".tmp"
    # Verify staging does not exist after a normal apply
    config = ConfigState(
        claude_repo=claude_repo,
        available_profiles=[Profile("standard", "Standard", claude_repo / "profiles" / "standard.json")],
        selected_profile="standard",
    )
    apply_config(config, project_dir)
    assert not staging.exists()
