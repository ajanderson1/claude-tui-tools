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


# --- Grouped directory tests (first_party / third_party) ---


@pytest.fixture
def grouped_repo(tmp_path):
    """Create a $CLAUDE_REPO with first_party/third_party subdirectories."""
    repo = tmp_path / "claude"
    repo.mkdir()

    # Skills: grouped
    fp_skill = repo / "skills" / "first_party" / "journal"
    fp_skill.mkdir(parents=True)
    (fp_skill / "SKILL.md").write_text("# Journal skill")

    tp_skill = repo / "skills" / "third_party" / "external-tool"
    tp_skill.mkdir(parents=True)
    (tp_skill / "SKILL.md").write_text("# External tool skill")

    # MCPs: grouped
    fp_mcp = repo / "mcps" / "first_party" / "pocketsmith"
    fp_mcp.mkdir(parents=True)
    (fp_mcp / "config.json").write_text(json.dumps({
        "type": "stdio", "command": "uvx", "args": ["pocketsmith-mcp"],
    }))

    tp_mcp = repo / "mcps" / "third_party" / "context7"
    tp_mcp.mkdir(parents=True)
    (tp_mcp / "config.json").write_text(json.dumps({
        "type": "stdio", "command": "npx", "args": ["-y", "@upstash/context7-mcp"],
    }))

    # Commands: grouped
    fp_cmd = repo / "commands" / "first_party" / "aj" / "system"
    fp_cmd.mkdir(parents=True)
    (fp_cmd / "analyze-resources.md").write_text("# Analyze resources")
    tp_cmd = repo / "commands" / "third_party" / "community"
    tp_cmd.mkdir(parents=True)
    (tp_cmd / "helper.md").write_text("# Community helper")
    (repo / "commands" / "README.md").write_text("# Commands")

    # Agents: grouped
    fp_agent = repo / "agents" / "first_party"
    fp_agent.mkdir(parents=True)
    (fp_agent / "researcher.md").write_text("# Researcher")
    tp_agent = repo / "agents" / "third_party"
    tp_agent.mkdir(parents=True)
    (tp_agent / "external.md").write_text("# External agent")

    return repo


def test_grouped_skills(grouped_repo):
    """Skills in first_party/ and third_party/ are discovered with group set."""
    skills = discover_skills(grouped_repo)
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert "journal" in names
    assert "external-tool" in names
    # Group is set correctly
    journal = next(s for s in skills if s.name == "journal")
    assert journal.group == "first_party"
    external = next(s for s in skills if s.name == "external-tool")
    assert external.group == "third_party"


def test_grouped_mcps(grouped_repo):
    """MCPs in first_party/ and third_party/ are discovered with group set."""
    mcps = discover_mcps(grouped_repo)
    assert len(mcps) == 2
    names = {m.name for m in mcps}
    assert "pocketsmith" in names
    assert "context7" in names
    ps = next(m for m in mcps if m.name == "pocketsmith")
    assert ps.group == "first_party"
    c7 = next(m for m in mcps if m.name == "context7")
    assert c7.group == "third_party"


def test_grouped_commands(grouped_repo):
    """Commands in first_party/ have group stripped from name and folder."""
    commands = discover_commands(grouped_repo)
    assert len(commands) == 2
    names = {c.name for c in commands}
    # Names must NOT include the group prefix
    assert "aj/system/analyze-resources" in names
    assert "community/helper" in names
    # Group is set
    aj_cmd = next(c for c in commands if c.name == "aj/system/analyze-resources")
    assert aj_cmd.group == "first_party"
    assert aj_cmd.folder == "aj/system"
    comm_cmd = next(c for c in commands if c.name == "community/helper")
    assert comm_cmd.group == "third_party"


def test_grouped_agents(grouped_repo):
    """Agents in first_party/ have group stripped from name."""
    agents = discover_agents(grouped_repo)
    assert len(agents) == 2
    names = {a.name for a in agents}
    assert "researcher" in names
    assert "external" in names
    researcher = next(a for a in agents if a.name == "researcher")
    assert researcher.group == "first_party"


def test_mixed_flat_and_grouped(tmp_path):
    """Both flat and grouped skills are discovered together."""
    repo = tmp_path / "claude"
    repo.mkdir()

    # Flat skill
    flat_skill = repo / "skills" / "flat-skill"
    flat_skill.mkdir(parents=True)
    (flat_skill / "SKILL.md").write_text("# Flat")

    # Grouped skill
    grouped_skill = repo / "skills" / "first_party" / "grouped-skill"
    grouped_skill.mkdir(parents=True)
    (grouped_skill / "SKILL.md").write_text("# Grouped")

    skills = discover_skills(repo)
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert "flat-skill" in names
    assert "grouped-skill" in names
    flat = next(s for s in skills if s.name == "flat-skill")
    assert flat.group == ""
    grouped = next(s for s in skills if s.name == "grouped-skill")
    assert grouped.group == "first_party"


def test_mixed_flat_and_grouped_mcps(tmp_path):
    """Both flat and grouped MCPs are discovered together."""
    repo = tmp_path / "claude"
    repo.mkdir()

    # Flat MCP
    flat_mcp = repo / "mcps" / "flat-mcp"
    flat_mcp.mkdir(parents=True)
    (flat_mcp / "config.json").write_text(json.dumps({
        "type": "stdio", "command": "npx", "args": ["-y", "flat-mcp"],
    }))

    # Grouped MCP
    grouped_mcp = repo / "mcps" / "third_party" / "grouped-mcp"
    grouped_mcp.mkdir(parents=True)
    (grouped_mcp / "config.json").write_text(json.dumps({
        "type": "stdio", "command": "npx", "args": ["-y", "grouped-mcp"],
    }))

    mcps = discover_mcps(repo)
    assert len(mcps) == 2
    names = {m.name for m in mcps}
    assert "flat-mcp" in names
    assert "grouped-mcp" in names
    flat = next(m for m in mcps if m.name == "flat-mcp")
    assert flat.group == ""
    grouped = next(m for m in mcps if m.name == "grouped-mcp")
    assert grouped.group == "third_party"


def test_duplicate_skill_name_flat_wins(tmp_path):
    """If a skill name exists at both flat and grouped level, flat is kept."""
    repo = tmp_path / "claude"
    repo.mkdir()

    flat = repo / "skills" / "dupe-skill"
    flat.mkdir(parents=True)
    (flat / "SKILL.md").write_text("# Flat version")

    grouped = repo / "skills" / "first_party" / "dupe-skill"
    grouped.mkdir(parents=True)
    (grouped / "SKILL.md").write_text("# Grouped version")

    skills = discover_skills(repo)
    assert len(skills) == 1
    assert skills[0].name == "dupe-skill"
    assert skills[0].group == ""  # flat wins
