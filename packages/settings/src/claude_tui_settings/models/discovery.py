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


# Directory names recognised as grouping directories (not part of resource names).
_GROUP_DIRS = frozenset({"first_party", "third_party"})


def _discover_md_resources(base_dir: Path) -> list[Resource]:
    """Discover .md resources recursively, building folder hierarchy.

    Supports both flat layouts (``commands/test/hello.md``) and grouped
    layouts (``commands/first_party/test/hello.md``).  When a top-level
    subdirectory matches a known group name the group is recorded on the
    resource but stripped from ``name`` and ``folder`` so that downstream
    references (symlinks, presets) remain stable.
    """
    if not base_dir.is_dir():
        return []
    result = []
    skip_names = {"CLAUDE.md", "README.md", ".gitignore", ".DS_Store"}
    for md_file in sorted(base_dir.rglob("*.md")):
        if md_file.name in skip_names:
            continue
        rel = md_file.relative_to(base_dir)
        parts = rel.parts

        # Detect group prefix
        group = ""
        if len(parts) >= 2 and parts[0] in _GROUP_DIRS:
            group = parts[0]
            parts = parts[1:]  # strip group from the logical path

        logical_rel = Path(*parts) if parts else rel
        folder = str(logical_rel.parent) if logical_rel.parent != Path(".") else ""
        name = str(logical_rel.with_suffix(""))

        result.append(Resource(
            name=name,
            path=md_file,
            folder=folder,
            group=group,
        ))
    return result


def discover_skills(claude_repo: Path) -> list[Resource]:
    """Discover skills from ``$CLAUDE_REPO/skills/*/SKILL.md`` sentinel files.

    Also scans one level deeper to support grouped layouts such as
    ``skills/first_party/journal/SKILL.md``.  The group directory is
    recorded on the resource but stripped from the skill name so that
    downstream references remain stable.
    """
    skills_dir = claude_repo / "skills"
    if not skills_dir.is_dir():
        return []
    seen: set[str] = set()
    result = []

    # Flat: skills/*/SKILL.md
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        if skill_md.parent.name in _GROUP_DIRS:
            continue  # skip the group dir itself
        skill_name = skill_md.parent.name
        if skill_name not in seen:
            seen.add(skill_name)
            result.append(Resource(
                name=skill_name,
                path=skill_md.parent,
            ))

    # Grouped: skills/{first_party,third_party}/*/SKILL.md
    for group_name in _GROUP_DIRS:
        group_dir = skills_dir / group_name
        if not group_dir.is_dir():
            continue
        for skill_md in sorted(group_dir.glob("*/SKILL.md")):
            skill_name = skill_md.parent.name
            if skill_name not in seen:
                seen.add(skill_name)
                result.append(Resource(
                    name=skill_name,
                    path=skill_md.parent,
                    group=group_name,
                ))

    result.sort(key=lambda r: r.name)
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
    """Discover MCP servers from ``$CLAUDE_REPO/mcps/*/config.json``.

    Also scans one level deeper to support grouped layouts such as
    ``mcps/third_party/context7/config.json``.  The group directory is
    recorded on the MCP but stripped from the name.
    """
    mcps_dir = claude_repo / "mcps"
    if not mcps_dir.is_dir():
        return []

    seen: set[str] = set()
    result: list[MCP] = []

    def _add_mcp(config_file: Path, group: str = "") -> None:
        mcp_name = config_file.parent.name
        if mcp_name in seen:
            return
        seen.add(mcp_name)
        try:
            config = json.loads(config_file.read_text())
        except (json.JSONDecodeError, OSError):
            return

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
            group=group,
        ))

    # Flat: mcps/*/config.json
    for config_file in sorted(mcps_dir.glob("*/config.json")):
        if config_file.parent.name in _GROUP_DIRS:
            continue
        _add_mcp(config_file)

    # Grouped: mcps/{first_party,third_party}/*/config.json
    for group_name in _GROUP_DIRS:
        group_dir = mcps_dir / group_name
        if not group_dir.is_dir():
            continue
        for config_file in sorted(group_dir.glob("*/config.json")):
            _add_mcp(config_file, group=group_name)

    result.sort(key=lambda r: r.name)
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
