"""Discover available resources from $CLAUDE_REPO."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from claude_tui_settings.models.config import (
    Hook,
    MCP,
    Plugin,
    Profile,
    Resource,
    SettingDef,
)


def discover_profiles(claude_repo: Path) -> list[Profile]:
    """Discover permission profiles from $CLAUDE_REPO/profiles/*.json."""
    profiles_dir = claude_repo / "profiles"
    if not profiles_dir.is_dir():
        return []
    result = []
    for p in sorted(profiles_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            result.append(Profile(
                name=p.stem,
                description=data.get("description", ""),
                json_path=p,
            ))
        except (json.JSONDecodeError, OSError):
            continue
    return result


def discover_commands(claude_repo: Path) -> list[Resource]:
    """Discover commands from $CLAUDE_REPO/commands/**/*.md."""
    return _discover_md_resources(claude_repo / "commands")


def discover_agents(claude_repo: Path) -> list[Resource]:
    """Discover agents from $CLAUDE_REPO/agents/**/*.md."""
    return _discover_md_resources(claude_repo / "agents")


def _discover_md_resources(base_dir: Path) -> list[Resource]:
    """Discover .md resources recursively, building folder hierarchy."""
    if not base_dir.is_dir():
        return []
    result = []
    skip_names = {"CLAUDE.md", "README.md", ".gitignore", ".DS_Store"}
    for md_file in sorted(base_dir.rglob("*.md")):
        if md_file.name in skip_names:
            continue
        rel = md_file.relative_to(base_dir)
        folder = str(rel.parent) if rel.parent != Path(".") else ""
        name = str(rel.with_suffix(""))  # e.g. "aj/capture2journal/capture2gotcha"
        result.append(Resource(
            name=name,
            path=md_file,
            folder=folder,
        ))
    return result


def discover_skills(claude_repo: Path) -> list[Resource]:
    """Discover skills from $CLAUDE_REPO/skills/*/SKILL.md sentinel files."""
    skills_dir = claude_repo / "skills"
    if not skills_dir.is_dir():
        return []
    result = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_name = skill_md.parent.name
        result.append(Resource(
            name=skill_name,
            path=skill_md.parent,
        ))
    return result


def discover_plugins(claude_repo: Path) -> list[Plugin]:
    """Discover plugins from $CLAUDE_REPO/plugins/registry.json."""
    registry = claude_repo / "plugins" / "registry.json"
    if not registry.is_file():
        return []
    try:
        data = json.loads(registry.read_text())
        return [
            Plugin(
                id=p["id"],
                name=p.get("name", p["id"]),
                description=p.get("description", ""),
            )
            for p in data.get("plugins", [])
        ]
    except (json.JSONDecodeError, OSError, KeyError):
        return []


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter from a markdown file as simple key: value pairs."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    result = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                result[key] = value
    return result


def discover_mcps(claude_repo: Path) -> list[MCP]:
    """Discover MCP servers from $CLAUDE_REPO/mcps/*/config.json."""
    mcps_dir = claude_repo / "mcps"
    if not mcps_dir.is_dir():
        return []
    result = []
    for config_file in sorted(mcps_dir.glob("*/config.json")):
        mcp_name = config_file.parent.name
        try:
            config = json.loads(config_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        # Read description and command from README.md frontmatter
        description = ""
        binary = ""
        readme = config_file.parent / "README.md"
        if readme.is_file():
            try:
                fm = _parse_frontmatter(readme.read_text())
                description = fm.get("description", "")
                binary = fm.get("command", "")
            except OSError:
                pass

        binary_found = True
        if binary:
            binary_found = shutil.which(binary) is not None

        result.append(MCP(
            name=mcp_name,
            config=config,
            description=description,
            binary=binary,
            binary_found=binary_found,
        ))
    return result


def discover_hooks(claude_repo: Path) -> list[Hook]:
    """Discover hooks from $CLAUDE_REPO/hooks/available/*/hook.json."""
    hooks_dir = claude_repo / "hooks" / "available"
    if not hooks_dir.is_dir():
        return []
    result = []
    for hook_json in sorted(hooks_dir.glob("*/hook.json")):
        hook_name = hook_json.parent.name
        try:
            data = json.loads(hook_json.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        # Find script files in same directory
        script_files = []
        for ext in ("*.sh", "*.js"):
            for f in hook_json.parent.glob(ext):
                script_files.append(f.name)

        result.append(Hook(
            name=hook_name,
            event=data.get("event", ""),
            matcher=data.get("matcher", ""),
            description=data.get("description", ""),
            command_template=data.get("command_template", ""),
            script_files=script_files,
        ))
    return result


def _discover_output_styles(claude_repo: Path) -> list[str]:
    """Discover output style names from $CLAUDE_REPO/output-styles/*.md."""
    styles_dir = claude_repo / "output-styles"
    if not styles_dir.is_dir():
        return []
    return sorted(f.stem for f in styles_dir.glob("*.md"))


def discover_settings(
    settings_defs: list[dict],
    claude_repo: Path | None = None,
) -> list[SettingDef]:
    """Convert parsed schema properties into SettingDef list."""
    # Excluded settings that should never be shown in project-scope editor
    excluded = {
        "$schema", "apiKeyHelper", "awsCredentialExport", "awsAuthRefresh",
        "otelHeadersHelper", "forceLoginOrgUUID", "forceLoginMethod",
        "permissions", "hooks", "enabledPlugins", "defaultMode",
        "mcpServers", "description",
    }

    # Discover output styles for the outputStyle dropdown
    output_styles = _discover_output_styles(claude_repo) if claude_repo else []

    result = []
    for d in settings_defs:
        key = d.get("key", "")
        if key in excluded:
            continue
        setting_type = d.get("type", "string")
        enum_values = d.get("enum")

        # Override outputStyle to be a dropdown of discovered styles
        if key == "outputStyle" and output_styles:
            setting_type = "enum"
            enum_values = output_styles

        if enum_values:
            setting_type = "enum"
        result.append(SettingDef(
            key=key,
            type=setting_type,
            description=d.get("description", ""),
            default=d.get("default"),
            enum_values=enum_values,
        ))
    return result
