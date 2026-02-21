"""Detect existing state from .claude/ on disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_tui_settings.models.config import Resource


def detect_profile(
    settings_path: Path,
    profiles_dir: Path,
) -> str | None:
    """Detect which profile matches the current settings.json.

    Strips scalars, hooks, enabledPlugins, defaultMode and compares
    the remaining keys against each profile (also stripped of description).
    """
    if not settings_path.is_file():
        return None
    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    # Strip to only $schema and permissions
    stripped = {}
    for k in ("$schema", "permissions"):
        if k in settings:
            stripped[k] = settings[k]

    if not profiles_dir.is_dir():
        return "custom"

    for profile_path in sorted(profiles_dir.glob("*.json")):
        try:
            profile_data = json.loads(profile_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        profile_stripped = {}
        for k in ("$schema", "permissions"):
            if k in profile_data:
                profile_stripped[k] = profile_data[k]
        if stripped == profile_stripped:
            return profile_path.stem

    return "custom"


def detect_resources(
    resource_dir: Path,
    claude_repo: Path,
    resource_type: str,
) -> tuple[set[str], list[Resource]]:
    """Detect existing resources (commands/agents/skills) from .claude/<type>/.

    Returns (set of repo-sourced names, list of local Resources).
    """
    existing_names: set[str] = set()
    local_resources: list[Resource] = []

    if not resource_dir.is_dir():
        return existing_names, local_resources

    repo_base = claude_repo / resource_type

    for entry in sorted(resource_dir.rglob("*")):
        if entry.name.startswith("."):
            continue
        # For commands/agents: only care about .md files
        # For skills: care about directories with SKILL.md
        if resource_type == "skills":
            if not entry.is_dir():
                continue
            if not (entry / "SKILL.md").exists():
                continue
            name = entry.name
        else:
            if not entry.name.endswith(".md"):
                continue
            if entry.name in ("CLAUDE.md", "README.md"):
                continue
            rel = entry.relative_to(resource_dir)
            name = str(rel.with_suffix(""))

        if entry.is_symlink():
            target = entry.resolve()
            if not target.exists():
                # Broken symlink
                existing_names.add(name)
                local_resources.append(Resource(
                    name=name, path=entry, is_broken_symlink=True,
                ))
            else:
                existing_names.add(name)
        else:
            # Local (non-symlinked) file
            existing_names.add(name)
            local_resources.append(Resource(
                name=name, path=entry, is_local=True,
            ))

    return existing_names, local_resources


def detect_plugins(settings_path: Path) -> set[str]:
    """Detect enabled plugins from .claude/settings.json -> .enabledPlugins."""
    if not settings_path.is_file():
        return set()
    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return set()
    enabled = settings.get("enabledPlugins", {})
    return {k for k, v in enabled.items() if v is True}


def detect_hooks(
    settings_path: Path,
    claude_repo: Path,
) -> set[str]:
    """Detect existing hooks by reverse-mapping command basenames.

    Reads .hooks from settings.json, extracts command paths,
    and matches against $CLAUDE_REPO/hooks/available/ scripts.
    """
    if not settings_path.is_file():
        return set()
    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return set()

    hooks_obj = settings.get("hooks", {})
    if not hooks_obj:
        return set()

    # Build map of script basename -> hook name
    available_dir = claude_repo / "hooks" / "available"
    script_to_hook: dict[str, str] = {}
    if available_dir.is_dir():
        for hook_dir in available_dir.iterdir():
            if not hook_dir.is_dir():
                continue
            for script in hook_dir.iterdir():
                if script.suffix in (".sh", ".js"):
                    script_to_hook[script.name] = hook_dir.name

    existing_hooks: set[str] = set()
    for event_key, matchers in hooks_obj.items():
        if not isinstance(matchers, list):
            continue
        for matcher_entry in matchers:
            hook_list = matcher_entry.get("hooks", [])
            if not isinstance(hook_list, list):
                continue
            for hook_def in hook_list:
                command = hook_def.get("command", "")
                if command:
                    basename = Path(command).name
                    if basename in script_to_hook:
                        existing_hooks.add(script_to_hook[basename])

    return existing_hooks


def detect_existing_settings(settings_path: Path) -> dict[str, Any]:
    """Read scalar settings from settings.json, excluding structural keys."""
    if not settings_path.is_file():
        return {}
    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    excluded = {
        "$schema", "permissions", "hooks", "enabledPlugins",
        "defaultMode", "mcpServers", "description",
    }
    return {k: v for k, v in settings.items() if k not in excluded}


def detect_mcps(mcp_json_path: Path) -> set[str]:
    """Detect existing MCPs from .mcp.json -> .mcpServers keys."""
    if not mcp_json_path.is_file():
        return set()
    try:
        data = json.loads(mcp_json_path.read_text())
    except (json.JSONDecodeError, OSError):
        return set()
    servers = data.get("mcpServers", {})
    return set(servers.keys())


def detect_user_resources(
    user_claude_dir: Path,
    resource_type: str,
) -> set[str]:
    """Detect user-scope resources from ~/.claude/{commands,agents,skills}/."""
    resource_dir = user_claude_dir / resource_type
    if not resource_dir.is_dir():
        return set()

    names: set[str] = set()
    if resource_type == "skills":
        for entry in resource_dir.iterdir():
            if entry.is_dir() and (entry / "SKILL.md").exists():
                names.add(entry.name)
    else:
        for entry in resource_dir.rglob("*.md"):
            if entry.name in ("CLAUDE.md", "README.md"):
                continue
            rel = entry.relative_to(resource_dir)
            names.add(str(rel.with_suffix("")))
    return names
