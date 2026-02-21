"""Cross-scope conflict detection (all 5 scopes)."""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any


def _escape_value(val: Any) -> str:
    """Escape a config value for safe embedding in Rich markup."""
    return str(val).replace("[", "\\[")

from claude_tui_settings.models.config import AuditWarning


def _get_managed_dir() -> Path:
    """Get the managed settings directory for the current platform."""
    if platform.system() == "Darwin":
        return Path("/Library/Application Support/ClaudeCode")
    return Path("/etc/claude-code")


def _encode_project_path(project_dir: Path) -> str:
    """Encode project path for per-project user scope directory.

    Claude Code uses a dash-separated path encoding.
    """
    # Claude Code encodes as: /Users/aj/myproject -> -Users-aj-myproject
    return str(project_dir).replace("/", "-").lstrip("-")


def _read_json_safe(path: Path) -> dict[str, Any]:
    """Read JSON file, returning empty dict on any error."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def scan_all_scopes(project_dir: Path) -> dict[str, dict[str, Any]]:
    """Scan all 5 configuration scopes and return their settings.

    Returns dict of scope_name -> settings dict.
    """
    scopes: dict[str, dict[str, Any]] = {}
    user_claude_dir = Path.home() / ".claude"

    # 1. Managed scope
    managed_dir = _get_managed_dir()
    managed_settings = _read_json_safe(managed_dir / "managed-settings.json")
    if managed_settings:
        scopes["managed"] = managed_settings

    # 2. User (global) scope
    user_global = _read_json_safe(user_claude_dir / "settings.json")
    if user_global:
        scopes["user-global"] = user_global

    # Also check legacy ~/.claude.json
    legacy = _read_json_safe(Path.home() / ".claude.json")
    if legacy and "user-global" not in scopes:
        scopes["user-global"] = legacy

    # 3. User (per-project) scope
    encoded = _encode_project_path(project_dir)
    per_project = _read_json_safe(
        user_claude_dir / "projects" / encoded / "settings.json"
    )
    if per_project:
        scopes["user-project"] = per_project

    # 4. Project scope
    project_settings = _read_json_safe(project_dir / ".claude" / "settings.json")
    if project_settings:
        scopes["project"] = project_settings

    # 5. Local scope
    local_settings = _read_json_safe(project_dir / ".claude" / "settings.local.json")
    if local_settings:
        scopes["local"] = local_settings

    return scopes


def run_audit(project_dir: Path) -> list[AuditWarning]:
    """Run cross-scope audit and return warnings."""
    warnings: list[AuditWarning] = []
    scopes = scan_all_scopes(project_dir)

    if len(scopes) < 2:
        return warnings

    # Check for scalar setting conflicts across scopes
    _audit_scalar_conflicts(scopes, warnings)

    # Check for permission rule conflicts
    _audit_permission_conflicts(scopes, warnings)

    # Check for orphaned MCPs in settings.local.json
    _audit_orphaned_mcps(project_dir, warnings)

    return warnings


def _audit_scalar_conflicts(
    scopes: dict[str, dict[str, Any]],
    warnings: list[AuditWarning],
) -> None:
    """Check for scalar setting overrides across scopes."""
    excluded_keys = {
        "$schema", "permissions", "hooks", "enabledPlugins",
        "defaultMode", "mcpServers", "description",
    }

    # Collect all scalar keys across all scopes
    all_keys: set[str] = set()
    for scope_data in scopes.values():
        for k in scope_data:
            if k not in excluded_keys:
                all_keys.add(k)

    # Precedence order (highest to lowest)
    precedence = ["managed", "local", "project", "user-project", "user-global"]

    for key in sorted(all_keys):
        defining_scopes = []
        for scope_name in precedence:
            if scope_name in scopes and key in scopes[scope_name]:
                defining_scopes.append((scope_name, scopes[scope_name][key]))

        if len(defining_scopes) >= 2:
            winner = defining_scopes[0]
            for loser in defining_scopes[1:]:
                if winner[1] != loser[1]:
                    warnings.append(AuditWarning(
                        scope=loser[0],
                        warning_type="OVERRIDE",
                        key=key,
                        message=(
                            f"{key}: {winner[0]} [bold]'{_escape_value(winner[1])}'[/bold] "
                            f"[dim]overrides {loser[0]} '{_escape_value(loser[1])}'[/dim]"
                        ),
                    ))
                else:
                    warnings.append(AuditWarning(
                        scope=loser[0],
                        warning_type="DUPE",
                        key=key,
                        message=(
                            f"{key}: same value '{_escape_value(loser[1])}' "
                            f"[dim]in both {winner[0]} and {loser[0]}[/dim]"
                        ),
                    ))


def _audit_permission_conflicts(
    scopes: dict[str, dict[str, Any]],
    warnings: list[AuditWarning],
) -> None:
    """Check for contradictory permission rules across scopes."""
    # Collect all rules by pattern
    rules_by_pattern: dict[str, list[tuple[str, str]]] = {}

    for scope_name, data in scopes.items():
        perms = data.get("permissions", {})
        for rule_type in ("allow", "deny", "ask"):
            rules = perms.get(rule_type, [])
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, str):
                        if rule not in rules_by_pattern:
                            rules_by_pattern[rule] = []
                        rules_by_pattern[rule].append((scope_name, rule_type))

    for pattern, occurrences in sorted(rules_by_pattern.items()):
        rule_types = {rt for _, rt in occurrences}
        if len(rule_types) > 1:
            scopes_str = ", ".join(f"{s}={rt}" for s, rt in occurrences)
            warnings.append(AuditWarning(
                scope="multi",
                warning_type="CONFLICT",
                key=pattern,
                message=f"Permission rule '{_escape_value(pattern)}' has conflicting types: {scopes_str}",
            ))


def _audit_orphaned_mcps(
    project_dir: Path,
    warnings: list[AuditWarning],
) -> None:
    """Check for MCPs in settings.local.json (should be in .mcp.json)."""
    local_settings = _read_json_safe(project_dir / ".claude" / "settings.local.json")
    if "mcpServers" in local_settings:
        server_names = list(local_settings["mcpServers"].keys())
        warnings.append(AuditWarning(
            scope="local",
            warning_type="OVERRIDE",
            key="mcpServers",
            message=(
                f"MCPs found in settings.local.json: {_escape_value(', '.join(server_names))}. "
                "These should be in .mcp.json."
            ),
        ))
