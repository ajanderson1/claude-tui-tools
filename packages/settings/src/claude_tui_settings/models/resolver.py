"""Effective config resolution — merge all scopes, track provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_tui_settings.models.audit import _encode_project_path, _get_managed_dir, _read_json_safe
from claude_tui_settings.models.config import (
    EffectiveConfig,
    ResolvedHook,
    ResolvedMCPServer,
    ResolvedPermissionRule,
    ResolvedPlugin,
    ResolvedValue,
    SettingDef,
)


def resolve_effective_config(
    project_dir: Path,
    setting_defs: list[SettingDef] | None = None,
) -> EffectiveConfig:
    """Resolve the effective final configuration from all scopes.

    Precedence (highest to lowest):
    1. Managed
    2. Local (.claude/settings.local.json)
    3. Project (.claude/settings.json)
    4. User per-project (~/.claude/projects/<encoded>/settings.json)
    5. User global (~/.claude/settings.json)
    """
    user_claude_dir = Path.home() / ".claude"
    managed_dir = _get_managed_dir()
    encoded = _encode_project_path(project_dir)

    # Load all scope settings in precedence order
    scope_settings: list[tuple[str, dict[str, Any]]] = []

    managed = _read_json_safe(managed_dir / "managed-settings.json")
    if managed:
        scope_settings.append(("Managed", managed))

    local = _read_json_safe(project_dir / ".claude" / "settings.local.json")
    if local:
        scope_settings.append(("Local", local))

    project = _read_json_safe(project_dir / ".claude" / "settings.json")
    if project:
        scope_settings.append(("Project", project))

    user_proj = _read_json_safe(
        user_claude_dir / "projects" / encoded / "settings.json"
    )
    if user_proj:
        scope_settings.append(("User-Project", user_proj))

    user_global = _read_json_safe(user_claude_dir / "settings.json")
    if user_global:
        scope_settings.append(("User", user_global))

    # Note: ~/.claude.json is only used for MCP server resolution
    # (handled in _resolve_mcp_servers), not for scalar settings

    effective = EffectiveConfig()

    # Resolve scalar settings
    effective.settings = _resolve_scalars(scope_settings, setting_defs)

    # Resolve permission rules
    effective.permission_rules = _resolve_permissions(scope_settings)

    # Resolve plugins
    effective.plugins = _resolve_plugins(scope_settings)

    # Resolve hooks
    effective.hooks = _resolve_hooks(scope_settings)

    # Resolve MCP servers
    effective.mcp_servers = _resolve_mcp_servers(project_dir)

    # Count resources
    _count_resources(project_dir, user_claude_dir, effective)

    return effective


def _resolve_scalars(
    scope_settings: list[tuple[str, dict[str, Any]]],
    setting_defs: list[SettingDef] | None,
) -> list[ResolvedValue]:
    """Resolve scalar settings across all scopes."""
    excluded_keys = {
        "$schema", "permissions", "hooks", "enabledPlugins",
        "defaultMode", "mcpServers", "description",
    }

    # Collect all keys from settings files
    all_keys: set[str] = set()
    for _, data in scope_settings:
        for k in data:
            if k not in excluded_keys:
                all_keys.add(k)

    # Add known keys from schema
    if setting_defs:
        for sd in setting_defs:
            all_keys.add(sd.key)

    result = []
    for key in sorted(all_keys):
        if key in excluded_keys:
            continue

        winner_scope = None
        winner_value = None
        overrides = []

        for scope_name, data in scope_settings:
            if key in data:
                if winner_scope is None:
                    winner_scope = scope_name
                    winner_value = data[key]
                else:
                    overrides.append((scope_name, data[key]))

        if winner_scope is not None:
            result.append(ResolvedValue(
                key=key,
                value=winner_value,
                source_scope=winner_scope,
                overridden_scopes=overrides,
            ))
        elif setting_defs:
            # Use schema default
            for sd in setting_defs:
                if sd.key == key and sd.default is not None:
                    result.append(ResolvedValue(
                        key=key,
                        value=sd.default,
                        source_scope="Default",
                    ))
                    break

    return result


def _resolve_permissions(
    scope_settings: list[tuple[str, dict[str, Any]]],
) -> list[ResolvedPermissionRule]:
    """Resolve permission rules — first-match wins per pattern, track overrides."""
    # Collect all (pattern -> list of (scope, rule_type)) in precedence order
    pattern_hits: dict[str, list[tuple[str, str]]] = {}
    for scope_name, data in scope_settings:
        perms = data.get("permissions", {})
        for rule_type in ("deny", "ask", "allow"):
            rules = perms.get(rule_type, [])
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, str):
                        pattern_hits.setdefault(rule, []).append(
                            (scope_name, rule_type.upper())
                        )

    result = []
    for pattern, hits in pattern_hits.items():
        winner_scope, winner_type = hits[0]
        overrides = [(scope, rtype) for scope, rtype in hits[1:]]
        result.append(ResolvedPermissionRule(
            rule_type=winner_type,
            pattern=pattern,
            source_scope=winner_scope,
            overridden_scopes=overrides,
        ))
    return result


def _resolve_plugins(
    scope_settings: list[tuple[str, dict[str, Any]]],
) -> list[ResolvedPlugin]:
    """Resolve enabledPlugins across all scopes — first-match wins per plugin."""
    # Collect all plugin IDs across scopes
    all_ids: set[str] = set()
    for _, data in scope_settings:
        enabled_plugins = data.get("enabledPlugins", {})
        if isinstance(enabled_plugins, dict):
            all_ids.update(enabled_plugins.keys())

    result = []
    for plugin_id in sorted(all_ids):
        winner_scope = None
        winner_value = None
        overrides = []

        for scope_name, data in scope_settings:
            enabled_plugins = data.get("enabledPlugins", {})
            if isinstance(enabled_plugins, dict) and plugin_id in enabled_plugins:
                val = bool(enabled_plugins[plugin_id])
                if winner_scope is None:
                    winner_scope = scope_name
                    winner_value = val
                else:
                    overrides.append((scope_name, val))

        if winner_scope is not None:
            result.append(ResolvedPlugin(
                plugin_id=plugin_id,
                enabled=winner_value,
                source_scope=winner_scope,
                overridden_scopes=overrides,
            ))

    return result


def _resolve_hooks(
    scope_settings: list[tuple[str, dict[str, Any]]],
) -> list[ResolvedHook]:
    """Resolve hooks — merge additively with scope provenance."""
    result = []
    for scope_name, data in scope_settings:
        hooks_obj = data.get("hooks", {})
        if not isinstance(hooks_obj, dict):
            continue
        for event, matchers in hooks_obj.items():
            if not isinstance(matchers, list):
                continue
            for matcher_entry in matchers:
                if not isinstance(matcher_entry, dict):
                    continue
                matcher = matcher_entry.get("matcher", "*")
                hook_list = matcher_entry.get("hooks", [])
                if not isinstance(hook_list, list):
                    continue
                for hook_def in hook_list:
                    command = hook_def.get("command", "")
                    if command:
                        result.append(ResolvedHook(
                            event=event,
                            matcher=matcher,
                            command=command,
                            source_scope=scope_name,
                        ))
    return result


def _resolve_mcp_servers(project_dir: Path) -> list[ResolvedMCPServer]:
    """Resolve MCP servers from all scopes."""
    result = []
    seen: set[str] = set()

    user_claude_dir = Path.home() / ".claude"
    managed_dir = _get_managed_dir()

    # Precedence order for MCP configs
    mcp_sources: list[tuple[str, Path]] = [
        ("Managed", managed_dir / "managed-mcp.json"),
        ("Local", project_dir / ".claude" / "settings.local.json"),
        ("Project", project_dir / ".mcp.json"),
        ("User", Path.home() / ".claude.json"),
    ]

    for scope_name, path in mcp_sources:
        data = _read_json_safe(path)
        servers = data.get("mcpServers", {})
        for name, config in servers.items():
            if name not in seen:
                seen.add(name)
                result.append(ResolvedMCPServer(
                    name=name,
                    config=config if isinstance(config, dict) else {},
                    source_scope=scope_name,
                ))

    return result


def _count_resources(
    project_dir: Path,
    user_claude_dir: Path,
    effective: EffectiveConfig,
) -> None:
    """Count resources from project and user scopes."""
    for resource_type, proj_attr, user_attr in [
        ("commands", "project_commands", "user_commands"),
        ("agents", "project_agents", "user_agents"),
        ("skills", "project_skills", "user_skills"),
    ]:
        proj_dir = project_dir / ".claude" / resource_type
        if proj_dir.is_dir():
            count = sum(
                1 for f in proj_dir.rglob("*.md")
                if f.name not in ("CLAUDE.md", "README.md")
            ) if resource_type != "skills" else sum(
                1 for d in proj_dir.iterdir()
                if d.is_dir() and (d / "SKILL.md").exists()
            )
            setattr(effective, proj_attr, count)

        if user_attr:
            user_dir = user_claude_dir / resource_type
            if user_dir.is_dir():
                count = sum(
                    1 for f in user_dir.rglob("*.md")
                    if f.name not in ("CLAUDE.md", "README.md")
                ) if resource_type != "skills" else sum(
                    1 for d in user_dir.iterdir()
                    if d.is_dir() and (d / "SKILL.md").exists()
                )
                setattr(effective, user_attr, count)
