"""Tests for audit module."""

import json
from pathlib import Path

import pytest

from claude_tui_settings.models.audit import run_audit, scan_all_scopes


@pytest.fixture
def project_dir(tmp_path):
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".claude").mkdir()
    return project


def test_scan_scopes_no_project_settings(project_dir):
    scopes = scan_all_scopes(project_dir)
    # No project or local config files, but user-global may exist on real machine
    assert "project" not in scopes
    assert "local" not in scopes


def test_scan_scopes_project_only(project_dir):
    (project_dir / ".claude" / "settings.json").write_text(json.dumps({
        "effortLevel": "high",
    }))
    scopes = scan_all_scopes(project_dir)
    assert "project" in scopes
    assert scopes["project"]["effortLevel"] == "high"


def test_audit_no_conflicts(project_dir):
    (project_dir / ".claude" / "settings.json").write_text(json.dumps({
        "effortLevel": "high",
    }))
    warnings = run_audit(project_dir)
    # Single scope means no conflicts possible
    assert len(warnings) == 0


def test_audit_override_between_scopes(project_dir):
    """Test that conflicting values across scopes are detected."""
    (project_dir / ".claude" / "settings.json").write_text(json.dumps({
        "effortLevel": "high",
    }))
    (project_dir / ".claude" / "settings.local.json").write_text(json.dumps({
        "effortLevel": "low",
    }))
    warnings = run_audit(project_dir)
    override_warnings = [w for w in warnings if w.warning_type == "OVERRIDE"]
    assert len(override_warnings) >= 1
    assert any("effortLevel" in w.key for w in override_warnings)


def test_audit_dupe_same_value(project_dir):
    """Test that same value at multiple scopes is flagged as DUPE."""
    (project_dir / ".claude" / "settings.json").write_text(json.dumps({
        "effortLevel": "high",
    }))
    (project_dir / ".claude" / "settings.local.json").write_text(json.dumps({
        "effortLevel": "high",
    }))
    warnings = run_audit(project_dir)
    dupe_warnings = [w for w in warnings if w.warning_type == "DUPE"]
    assert len(dupe_warnings) >= 1


def test_audit_permission_conflict(project_dir):
    """Test conflicting permission rules across scopes."""
    (project_dir / ".claude" / "settings.json").write_text(json.dumps({
        "permissions": {"allow": ["Bash(rm:*)"]},
    }))
    (project_dir / ".claude" / "settings.local.json").write_text(json.dumps({
        "permissions": {"deny": ["Bash(rm:*)"]},
    }))
    warnings = run_audit(project_dir)
    conflict_warnings = [w for w in warnings if w.warning_type == "CONFLICT"]
    assert len(conflict_warnings) >= 1


def test_audit_orphaned_mcps(project_dir):
    """Test detection of MCPs in settings.local.json."""
    (project_dir / ".claude" / "settings.json").write_text(json.dumps({}))
    (project_dir / ".claude" / "settings.local.json").write_text(json.dumps({
        "mcpServers": {"test-mcp": {"command": "test"}},
    }))
    warnings = run_audit(project_dir)
    orphan_warnings = [w for w in warnings if "mcpServers" in w.key]
    assert len(orphan_warnings) >= 1
