"""Tests for discovery module."""

import json
import os
from pathlib import Path

import pytest

from claude_tui_settings.models.discovery import (
    discover_agents,
    discover_commands,
    discover_hooks,
    discover_mcps,
    discover_plugins,
    discover_profiles,
    discover_skills,
)


@pytest.fixture
def claude_repo(tmp_path):
    """Create a minimal $CLAUDE_REPO structure for testing."""
    repo = tmp_path / "claude"
    repo.mkdir()

    # Profiles
    profiles_dir = repo / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "standard.json").write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "description": "Standard profile",
    }))
    (profiles_dir / "strict.json").write_text(json.dumps({
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "description": "Strict profile",
        "permissions": {"ask": ["Bash(rm:*)"]},
    }))

    # Commands
    cmd_dir = repo / "commands" / "test"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "hello.md").write_text("# Hello command")
    (cmd_dir / "world.md").write_text("# World command")
    # Add README.md that should be skipped
    (repo / "commands" / "README.md").write_text("# Commands")

    # Agents
    agent_dir = repo / "agents"
    agent_dir.mkdir()
    (agent_dir / "researcher.md").write_text("# Researcher agent")

    # Skills
    skill_dir = repo / "skills" / "textual-tui"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Textual TUI skill")

    # Plugins
    plugin_dir = repo / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "registry.json").write_text(json.dumps({
        "plugins": [
            {"id": "test-plugin", "name": "Test", "description": "A test plugin"},
        ]
    }))

    # MCPs
    mcp_dir = repo / "mcps" / "test-mcp"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "config.json").write_text(json.dumps({
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "test-mcp"],
    }))
    (mcp_dir / "README.md").write_text(
        "---\nname: Test MCP\ndescription: A test MCP\ncommand: npx\n---\n# Test"
    )

    # Hooks
    hook_dir = repo / "hooks" / "available" / "test-hook"
    hook_dir.mkdir(parents=True)
    (hook_dir / "hook.json").write_text(json.dumps({
        "event": "PostToolUse",
        "matcher": "Edit",
        "description": "Test hook",
        "command_template": "{HOOKS_DIR}/test.sh",
    }))
    (hook_dir / "test.sh").write_text("#!/bin/bash\necho test")
    os.chmod(hook_dir / "test.sh", 0o755)

    return repo


def test_discover_profiles(claude_repo):
    profiles = discover_profiles(claude_repo)
    assert len(profiles) == 2
    names = {p.name for p in profiles}
    assert "standard" in names
    assert "strict" in names
    standard = next(p for p in profiles if p.name == "standard")
    assert standard.description == "Standard profile"


def test_discover_commands(claude_repo):
    commands = discover_commands(claude_repo)
    assert len(commands) == 2
    names = {c.name for c in commands}
    assert "test/hello" in names
    assert "test/world" in names
    # Check folder grouping
    assert all(c.folder == "test" for c in commands)


def test_discover_agents(claude_repo):
    agents = discover_agents(claude_repo)
    assert len(agents) == 1
    assert agents[0].name == "researcher"


def test_discover_skills(claude_repo):
    skills = discover_skills(claude_repo)
    assert len(skills) == 1
    assert skills[0].name == "textual-tui"


def test_discover_plugins(claude_repo):
    plugins = discover_plugins(claude_repo)
    assert len(plugins) == 1
    assert plugins[0].id == "test-plugin"
    assert plugins[0].name == "Test"
    assert plugins[0].description == "A test plugin"


def test_discover_mcps(claude_repo):
    mcps = discover_mcps(claude_repo)
    assert len(mcps) == 1
    assert mcps[0].name == "test-mcp"
    assert mcps[0].description == "A test MCP"
    assert mcps[0].config["type"] == "stdio"


def test_discover_hooks(claude_repo):
    hooks = discover_hooks(claude_repo)
    assert len(hooks) == 1
    assert hooks[0].name == "test-hook"
    assert hooks[0].event == "PostToolUse"
    assert hooks[0].matcher == "Edit"
    assert "test.sh" in hooks[0].script_files


def test_discover_missing_dir():
    """Discovery with non-existent repo returns empty lists."""
    missing = Path("/nonexistent/repo")
    assert discover_profiles(missing) == []
    assert discover_commands(missing) == []
    assert discover_agents(missing) == []
    assert discover_skills(missing) == []
    assert discover_plugins(missing) == []
    assert discover_mcps(missing) == []
    assert discover_hooks(missing) == []
