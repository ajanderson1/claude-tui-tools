"""Tests for detection module."""

import json
import os
from pathlib import Path

import pytest

from claude_tui_settings.models.detection import (
    detect_existing_settings,
    detect_hooks,
    detect_mcps,
    detect_plugins,
    detect_profile,
    detect_resources,
    detect_user_resources,
)


@pytest.fixture
def project_dir(tmp_path):
    """Create a minimal project directory with .claude/ state."""
    project = tmp_path / "myproject"
    project.mkdir()

    claude_dir = project / ".claude"
    claude_dir.mkdir()

    return project


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
    }))
    (profiles_dir / "permissive.json").write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "permissions": {"allow": ["Bash(rm:*)"]},
    }))

    # Commands
    cmd_dir = repo / "commands" / "test"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "hello.md").write_text("# Hello")

    # Hooks
    hook_dir = repo / "hooks" / "available" / "auto-format"
    hook_dir.mkdir(parents=True)
    (hook_dir / "auto-format.sh").write_text("#!/bin/bash")
    (hook_dir / "hook.json").write_text(json.dumps({
        "event": "PostToolUse",
        "matcher": "Edit|Write",
    }))

    return repo


def test_detect_profile_standard(project_dir, claude_repo):
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "effortLevel": "high",
    }))
    profile = detect_profile(settings_path, claude_repo / "profiles")
    assert profile == "standard"


def test_detect_profile_custom(project_dir, claude_repo):
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "permissions": {"deny": ["Bash(shutdown:*)"]},
    }))
    profile = detect_profile(settings_path, claude_repo / "profiles")
    assert profile == "custom"


def test_detect_profile_no_settings(project_dir, claude_repo):
    profile = detect_profile(
        project_dir / ".claude" / "settings.json",
        claude_repo / "profiles",
    )
    assert profile is None


def test_detect_resources_with_symlink(project_dir, claude_repo):
    cmd_dir = project_dir / ".claude" / "commands" / "test"
    cmd_dir.mkdir(parents=True)
    source = claude_repo / "commands" / "test" / "hello.md"
    (cmd_dir / "hello.md").symlink_to(source)

    existing, local = detect_resources(
        project_dir / ".claude" / "commands", claude_repo, "commands",
    )
    assert "test/hello" in existing
    assert len(local) == 0


def test_detect_resources_with_local_file(project_dir, claude_repo):
    cmd_dir = project_dir / ".claude" / "commands"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "custom.md").write_text("# Custom command")

    existing, local = detect_resources(
        project_dir / ".claude" / "commands", claude_repo, "commands",
    )
    assert "custom" in existing
    assert len(local) == 1
    assert local[0].is_local


def test_detect_plugins(project_dir):
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.write_text(json.dumps({
        "enabledPlugins": {
            "test-plugin": True,
            "disabled-plugin": False,
        }
    }))
    plugins = detect_plugins(settings_path)
    assert plugins == {"test-plugin"}


def test_detect_hooks(project_dir, claude_repo):
    settings_path = project_dir / ".claude" / "settings.json"
    hooks_dir = project_dir / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)

    settings_path.write_text(json.dumps({
        "hooks": {
            "PostToolUse": [{
                "matcher": "Edit|Write",
                "hooks": [{
                    "type": "command",
                    "command": str(hooks_dir / "auto-format.sh"),
                }],
            }],
        },
    }))

    existing = detect_hooks(settings_path, claude_repo)
    assert "auto-format" in existing


def test_detect_existing_settings(project_dir):
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "permissions": {"allow": []},
        "effortLevel": "high",
        "model": "opus-4-6",
    }))
    settings = detect_existing_settings(settings_path)
    assert settings == {"effortLevel": "high", "model": "opus-4-6"}
    assert "$schema" not in settings
    assert "permissions" not in settings


def test_detect_mcps(project_dir):
    mcp_path = project_dir / ".mcp.json"
    mcp_path.write_text(json.dumps({
        "mcpServers": {
            "postgres": {"type": "stdio", "command": "pg-mcp"},
            "redis": {"type": "stdio", "command": "redis-mcp"},
        }
    }))
    mcps = detect_mcps(mcp_path)
    assert mcps == {"postgres", "redis"}


# --- detect_user_resources tests ---


def test_detect_user_resources_commands(tmp_path):
    """Detect user-scope commands from .md files."""
    user_dir = tmp_path / ".claude"
    cmd_dir = user_dir / "commands" / "custom"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "hello.md").write_text("# Hello")
    (user_dir / "commands" / "top-level.md").write_text("# Top")

    result = detect_user_resources(user_dir, "commands")
    assert result == {"custom/hello", "top-level"}


def test_detect_user_resources_commands_excludes_readme(tmp_path):
    """CLAUDE.md and README.md are excluded from detection."""
    user_dir = tmp_path / ".claude"
    cmd_dir = user_dir / "commands"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "CLAUDE.md").write_text("# Instructions")
    (cmd_dir / "README.md").write_text("# Readme")
    (cmd_dir / "real.md").write_text("# Real command")

    result = detect_user_resources(user_dir, "commands")
    assert result == {"real"}


def test_detect_user_resources_skills(tmp_path):
    """Detect user-scope skills from directories containing SKILL.md."""
    user_dir = tmp_path / ".claude"
    skills_dir = user_dir / "skills"
    skills_dir.mkdir(parents=True)

    # Valid skill directory
    (skills_dir / "youtube-downloader").mkdir()
    (skills_dir / "youtube-downloader" / "SKILL.md").write_text("# Skill")

    # Another valid skill
    (skills_dir / "code-review").mkdir()
    (skills_dir / "code-review" / "SKILL.md").write_text("# Skill")

    # Directory without SKILL.md (not a skill)
    (skills_dir / "not-a-skill").mkdir()

    # Regular file (not a skill)
    (skills_dir / "random.txt").write_text("not a skill")

    result = detect_user_resources(user_dir, "skills")
    assert result == {"youtube-downloader", "code-review"}


def test_detect_user_resources_empty_dir(tmp_path):
    """Empty resource directory returns empty set."""
    user_dir = tmp_path / ".claude"
    (user_dir / "commands").mkdir(parents=True)

    result = detect_user_resources(user_dir, "commands")
    assert result == set()


def test_detect_user_resources_missing_dir(tmp_path):
    """Missing resource directory returns empty set."""
    user_dir = tmp_path / ".claude"
    user_dir.mkdir()

    result = detect_user_resources(user_dir, "skills")
    assert result == set()


