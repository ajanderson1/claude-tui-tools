"""Write settings.json, .mcp.json, symlinks, CLAUDE.md with staging/atomic-rename."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from claude_tui_settings.models.config import _NO_VALUE, ConfigState, Hook, MCP, SettingDef


def apply_config(config: ConfigState, project_dir: Path) -> list[str]:
    """Apply the current ConfigState to disk atomically.

    1. Write to .claude/.tmp/ staging directory
    2. Validate staged files
    3. Atomic rename into place
    4. Update CLAUDE.md sentinel sections
    5. Update .gitignore

    Returns a list of validation warnings for settings that failed
    type coercion and were reverted (excluded from output).
    """
    claude_dir = project_dir / ".claude"
    staging_dir = claude_dir / ".tmp"

    # Clean up any leftover staging directory
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    try:
        staging_dir.mkdir(parents=True, exist_ok=True)

        # 1. Build and stage settings.json (with validation)
        settings_data, validation_warnings = _build_settings_json(config)
        staged_settings = staging_dir / "settings.json"
        staged_settings.write_text(json.dumps(settings_data, indent=2) + "\n")

        # 2. Build and stage .mcp.json
        mcp_data = _build_mcp_json(config)
        staged_mcp = staging_dir / ".mcp.json"
        staged_mcp.write_text(json.dumps(mcp_data, indent=2) + "\n")

        # 3. Stage symlinks for commands, agents, skills
        _stage_symlinks(config, staging_dir, "commands")
        _stage_symlinks(config, staging_dir, "agents")
        _stage_skill_symlinks(config, staging_dir)

        # 4. Stage hook scripts
        _stage_hooks(config, staging_dir)

        # Validate staged files
        _validate_staged(staging_dir)

        # Atomic rename into place
        _atomic_install(staging_dir, claude_dir, project_dir)

        # Update CLAUDE.md
        _update_claude_md(config, project_dir)

        # Update .gitignore
        _update_gitignore(project_dir)

        return validation_warnings

    except Exception:
        # Clean up staging on failure
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise


def _build_settings_json(config: ConfigState) -> tuple[dict[str, Any], list[str]]:
    """Build the settings.json content from ConfigState.

    Merge order: profile base -> plugins -> hooks -> scalar overrides.

    Returns (settings_dict, validation_warnings).  Settings that fail
    type coercion are excluded and a warning string is appended.
    """
    warnings: list[str] = []

    # 1. Start with profile base
    profile_path = None
    for p in config.available_profiles:
        if p.name == config.selected_profile:
            profile_path = p.json_path
            break

    if profile_path and profile_path.is_file():
        result = json.loads(profile_path.read_text())
    else:
        result = {"$schema": "https://json.schemastore.org/claude-code-settings.json"}

    # Remove description (metadata only)
    result.pop("description", None)

    # Hoist profile base for comparison (read once, not per-key)
    profile_base = dict(result)

    # 2. Plugins merge
    if config.selected_plugins:
        result["enabledPlugins"] = {
            plugin_id: True for plugin_id in sorted(config.selected_plugins)
        }

    # 3. Hooks merge
    hooks_structure = _build_hooks_structure(config)
    if hooks_structure:
        result["hooks"] = hooks_structure

    # Build schema type lookup for coercion
    schema_types = {s.key: s.type for s in config.available_settings}

    # 4. Scalar overrides (with user-scope dedup + validation)
    # Iterate a snapshot — we may pop invalid entries during the loop
    for key, value in sorted(list(config.selected_settings.items())):
        # Skip if value matches the profile base value
        if key in profile_base and profile_base[key] == value:
            continue
        # Skip if value matches user-scope (dedup — issue #8)
        user_val = config.get_user_scope_value(key)
        if user_val is not _NO_VALUE and value == user_val:
            continue
        try:
            result[key] = _coerce_setting_value(value, schema_types.get(key, "string"))
        except SettingValidationError as exc:
            warnings.append(f"{key}: {exc}")
            # Revert: remove from selected_settings so UI reflects the revert
            config.selected_settings.pop(key, None)

    return result, warnings


class SettingValidationError(ValueError):
    """Raised when a setting value cannot be coerced to its schema type."""


def _coerce_setting_value(value: Any, schema_type: str) -> Any:
    """Coerce a setting value to match its JSON schema type.

    UI inputs arrive as strings; this ensures they're written as the
    correct JSON type (array, object, number, boolean, etc.).

    Raises SettingValidationError if the value cannot be coerced.
    """
    if value is None:
        return value

    # Already the right type — no coercion needed
    if schema_type == "array" and isinstance(value, list):
        return value
    if schema_type == "object" and isinstance(value, dict):
        return value
    if schema_type == "boolean" and isinstance(value, bool):
        return value
    if schema_type in ("number", "integer") and isinstance(value, (int, float)):
        return value
    if schema_type == "string":
        return str(value) if not isinstance(value, str) else value

    # Coerce from string
    if isinstance(value, str):
        if schema_type in ("array", "object"):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                expected = "JSON array" if schema_type == "array" else "JSON object"
                raise SettingValidationError(
                    f"Expected {expected}, got invalid JSON string"
                )
            if schema_type == "array" and not isinstance(parsed, list):
                raise SettingValidationError(
                    f"Expected array, but parsed JSON is {type(parsed).__name__}"
                )
            if schema_type == "object" and not isinstance(parsed, dict):
                raise SettingValidationError(
                    f"Expected object, but parsed JSON is {type(parsed).__name__}"
                )
            return parsed
        if schema_type == "boolean":
            return value.lower() in ("true", "1", "yes")
        if schema_type == "integer":
            try:
                return int(value)
            except ValueError:
                raise SettingValidationError(
                    f"Expected integer, got '{value}'"
                )
        if schema_type == "number":
            try:
                return float(value)
            except ValueError:
                raise SettingValidationError(
                    f"Expected number, got '{value}'"
                )

    # Wrong native type (e.g. list where string expected)
    raise SettingValidationError(
        f"Expected {schema_type}, got {type(value).__name__}"
    )


def _build_hooks_structure(config: ConfigState) -> dict[str, list]:
    """Build the hooks JSON structure from selected hooks."""
    if not config.selected_hooks:
        return {}

    hooks_dir = config.claude_repo / "hooks" / "available"
    result: dict[str, list] = {}

    for hook_name in sorted(config.selected_hooks):
        # Find the hook definition
        hook_def: Hook | None = None
        for h in config.available_hooks:
            if h.name == hook_name:
                hook_def = h
                break
        if not hook_def:
            continue

        hook_json_path = hooks_dir / hook_name / "hook.json"
        if not hook_json_path.is_file():
            continue

        try:
            data = json.loads(hook_json_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        event = data.get("event", "")
        matcher = data.get("matcher", "")
        command_template = data.get("command_template", "")

        # Substitute {HOOKS_DIR} with absolute path
        hooks_install_dir = Path(os.getcwd()) / ".claude" / "hooks"
        command = command_template.replace("{HOOKS_DIR}", str(hooks_install_dir))

        entry = {"matcher": matcher, "hooks": [{"type": "command", "command": command}]}

        if event not in result:
            result[event] = []
        result[event].append(entry)

    return result


def _build_mcp_json(config: ConfigState) -> dict[str, Any]:
    """Build the .mcp.json content from selected MCPs."""
    servers: dict[str, Any] = {}
    for mcp_name in sorted(config.selected_mcps):
        for mcp in config.available_mcps:
            if mcp.name == mcp_name:
                servers[mcp_name] = mcp.config
                break
    return {"mcpServers": servers}


def _stage_symlinks(
    config: ConfigState, staging_dir: Path, resource_type: str,
) -> None:
    """Stage symlinks for commands/agents."""
    match resource_type:
        case "commands":
            selected = config.selected_commands
            available = config.available_commands
        case "agents":
            selected = config.selected_agents
            available = config.available_agents
        case _:
            return

    resource_staging = staging_dir / resource_type
    resource_staging.mkdir(parents=True, exist_ok=True)

    # Determine user-scope set for dedup
    match resource_type:
        case "commands":
            user_set = config.user_commands
        case "agents":
            user_set = config.user_agents
        case _:
            user_set = set()

    for name in sorted(selected):
        # Skip items already provided at user scope (dedup)
        if name in user_set:
            continue

        # Find the available resource
        resource = None
        for r in available:
            if r.name == name:
                resource = r
                break
        if not resource or resource.is_local:
            continue

        # Create symlink in staging dir preserving folder structure
        link_path = resource_staging / (name + ".md")
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(resource.path)


def _stage_skill_symlinks(config: ConfigState, staging_dir: Path) -> None:
    """Stage symlinks for skills (directory symlinks)."""
    skills_staging = staging_dir / "skills"
    skills_staging.mkdir(parents=True, exist_ok=True)

    for name in sorted(config.selected_skills):
        # Skip items already provided at user scope (dedup)
        if name in config.user_skills:
            continue

        resource = None
        for r in config.available_skills:
            if r.name == name:
                resource = r
                break
        if not resource or resource.is_local:
            continue

        link_path = skills_staging / name
        link_path.symlink_to(resource.path)


def _stage_hooks(config: ConfigState, staging_dir: Path) -> None:
    """Copy hook script files to staging hooks directory."""
    hooks_staging = staging_dir / "hooks"
    hooks_staging.mkdir(parents=True, exist_ok=True)

    hooks_dir = config.claude_repo / "hooks" / "available"

    for hook_name in sorted(config.selected_hooks):
        hook_src_dir = hooks_dir / hook_name
        if not hook_src_dir.is_dir():
            continue
        for script in hook_src_dir.iterdir():
            if script.suffix in (".sh", ".js"):
                dest = hooks_staging / script.name
                shutil.copy2(script, dest)
                dest.chmod(0o755)


def _validate_staged(staging_dir: Path) -> None:
    """Validate all staged files."""
    # Validate JSON files
    for json_file in staging_dir.glob("*.json"):
        json.loads(json_file.read_text())

    # Validate symlinks
    for symlink in staging_dir.rglob("*"):
        if symlink.is_symlink() and not symlink.resolve().exists():
            raise ValueError(f"Broken symlink in staging: {symlink}")


def _atomic_install(
    staging_dir: Path, claude_dir: Path, project_dir: Path,
) -> None:
    """Atomically move staged files into place."""
    claude_dir.mkdir(parents=True, exist_ok=True)

    # Move settings.json
    staged_settings = staging_dir / "settings.json"
    if staged_settings.exists():
        os.replace(staged_settings, claude_dir / "settings.json")

    # Move .mcp.json to project root
    staged_mcp = staging_dir / ".mcp.json"
    if staged_mcp.exists():
        os.replace(staged_mcp, project_dir / ".mcp.json")

    # Move resource directories (commands, agents, skills, hooks)
    for resource_type in ("commands", "agents", "skills", "hooks"):
        staged_resource = staging_dir / resource_type
        if not staged_resource.is_dir():
            continue

        target_dir = claude_dir / resource_type

        # Remove existing repo-sourced symlinks but keep local files
        if target_dir.is_dir():
            for entry in list(target_dir.rglob("*")):
                if entry.is_symlink():
                    entry.unlink()
            # Remove empty directories
            for dirpath in sorted(target_dir.rglob("*"), reverse=True):
                if dirpath.is_dir() and not any(dirpath.iterdir()):
                    dirpath.rmdir()

        # Move staged items
        target_dir.mkdir(parents=True, exist_ok=True)
        for entry in staged_resource.iterdir():
            dest = target_dir / entry.name
            if entry.is_symlink():
                # Recreate symlink
                link_target = os.readlink(entry)
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                dest.symlink_to(link_target)
            elif entry.is_dir():
                if entry.is_symlink():
                    link_target = os.readlink(entry)
                    if dest.exists() or dest.is_symlink():
                        dest.unlink()
                    dest.symlink_to(link_target)
                else:
                    # Copy directory tree for nested structures
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(entry, dest, symlinks=True)
            else:
                shutil.copy2(entry, dest)
                if entry.suffix in (".sh", ".js"):
                    dest.chmod(0o755)

    # Clean up staging
    shutil.rmtree(staging_dir)


def _update_claude_md(config: ConfigState, project_dir: Path) -> None:
    """Update CLAUDE.md sentinel-bounded sections atomically."""
    claude_md = project_dir / "CLAUDE.md"

    if claude_md.is_file():
        content = claude_md.read_text()
    else:
        content = "# CLAUDE.md\n"

    # Update BOOTSTRAPPED_TOOLS section
    content = _update_sentinel_section(
        content,
        "BOOTSTRAPPED_TOOLS",
        _build_bootstrapped_tools_section(config),
    )

    # Write atomically: temp file in same directory, then os.replace()
    fd, tmp_path = tempfile.mkstemp(dir=project_dir, prefix=".CLAUDE.md.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, claude_md)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _update_sentinel_section(
    content: str, sentinel: str, new_section: str,
) -> str:
    """Replace content between sentinel markers, or append if not found."""
    begin = f"<!-- BEGIN:{sentinel} -->"
    end = f"<!-- END:{sentinel} -->"
    pattern = re.compile(
        rf"{re.escape(begin)}.*?{re.escape(end)}",
        re.DOTALL,
    )
    replacement = f"{begin}\n{new_section}\n{end}"

    if pattern.search(content):
        return pattern.sub(replacement, content)
    else:
        return content.rstrip() + "\n\n" + replacement + "\n"


def _build_bootstrapped_tools_section(config: ConfigState) -> str:
    """Build the BOOTSTRAPPED_TOOLS sentinel content."""
    lines = ["## Bootstrapped Tools", ""]
    lines.append(f"**Permission profile:** {config.selected_profile}")
    lines.append("")

    # Commands
    if config.selected_commands:
        lines.append("**Commands:**")
        for name in sorted(config.selected_commands):
            lines.append(f"  - {name}")
    else:
        lines.append("**Commands:**")

    # Agents
    if config.selected_agents:
        lines.append("**Agents:**")
        for name in sorted(config.selected_agents):
            lines.append(f"  - {name}")
    else:
        lines.append("**Agents:**")

    # Skills
    if config.selected_skills:
        lines.append("**Skills:**")
        for name in sorted(config.selected_skills):
            lines.append(f"  - {name}")
    else:
        lines.append("**Skills:**")

    # MCPs
    if config.selected_mcps:
        lines.append("**MCPs:**")
        for name in sorted(config.selected_mcps):
            lines.append(f"  - {name}")
    else:
        lines.append("**MCPs:**")

    # Hooks
    if config.selected_hooks:
        lines.append("**Hooks:**")
        for name in sorted(config.selected_hooks):
            lines.append(f"  - {name}")
    else:
        lines.append("**Hooks:**")

    lines.append("")
    lines.append("Run `claude-tui-settings` to reconfigure.")

    return "\n".join(lines)


def _update_gitignore(project_dir: Path) -> None:
    """Ensure .gitignore has .claude/ entry, written atomically."""
    gitignore = project_dir / ".gitignore"

    if gitignore.is_file():
        content = gitignore.read_text()
        lines = content.splitlines()
    else:
        lines = []
        content = ""

    needed = [".claude/", ".mcp.json"]
    for entry in needed:
        if entry not in lines:
            lines.append(entry)

    new_content = "\n".join(lines)
    if not new_content.endswith("\n"):
        new_content += "\n"

    if new_content != content:
        # Write atomically: temp file in same directory, then os.replace()
        fd, tmp_path = tempfile.mkstemp(dir=project_dir, prefix=".gitignore.tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(new_content)
            os.replace(tmp_path, gitignore)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
