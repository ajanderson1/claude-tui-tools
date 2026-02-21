"""--summary output: condensed text output with effective values and scope provenance."""

from __future__ import annotations

from pathlib import Path

from claude_tui_settings.cli import resolve_claude_repo
from claude_tui_settings.models.resolver import resolve_effective_config
from claude_tui_settings.models.instruction_files import discover_instruction_files
from claude_tui_settings.models.detection import (
    detect_profile,
    detect_resources,
    detect_mcps,
    detect_plugins,
    detect_hooks,
    detect_existing_settings,
)


def run_summary() -> None:
    """Print condensed summary of effective configuration."""
    project_dir = Path.cwd()

    try:
        claude_repo = resolve_claude_repo()
    except SystemExit:
        claude_repo = None

    effective = resolve_effective_config(project_dir)

    # Profile
    if claude_repo:
        settings_path = project_dir / ".claude" / "settings.json"
        profile = detect_profile(settings_path, claude_repo / "profiles")
        if profile:
            print(f"profile: {profile} [project]")

    # Resources
    if effective.project_commands or effective.user_commands:
        parts = []
        if effective.project_commands:
            parts.append(f"{effective.project_commands} project")
        if effective.user_commands:
            parts.append(f"{effective.user_commands} user")
        total = effective.project_commands + effective.user_commands
        print(f"commands: {' + '.join(parts)} = {total} total")

    if effective.project_agents or effective.user_agents:
        parts = []
        if effective.project_agents:
            parts.append(f"{effective.project_agents} project")
        if effective.user_agents:
            parts.append(f"{effective.user_agents} user")
        total = effective.project_agents + effective.user_agents
        print(f"agents: {' + '.join(parts)} = {total} total")

    if effective.project_skills:
        print(f"skills: {effective.project_skills} project")

    # MCP servers
    if effective.mcp_servers:
        parts = []
        for s in effective.mcp_servers:
            parts.append(f"{s.name} [{s.source_scope.lower()}]")
        print(f"mcps: {', '.join(parts)}")

    # Hooks
    if effective.hooks:
        parts = []
        for h in effective.hooks:
            label = Path(h.command).stem
            parts.append(f"{label} [{h.source_scope.lower()}]")
        print(f"hooks: {', '.join(parts)}")

    # Settings
    if effective.settings:
        parts = []
        for s in effective.settings:
            scope_str = f"[{s.source_scope.lower()}]"
            override_str = ""
            if s.overridden_scopes:
                overridden = s.overridden_scopes[0]
                override_str = f", overrides {overridden[0].lower()} \"{overridden[1]}\""
            parts.append(f"{s.key}={s.value} {scope_str}{override_str}")
        print(f"settings: {', '.join(parts)}")

    # Instruction files
    inst_files = discover_instruction_files(project_dir)
    existing_files = [f for f in inst_files if f.exists]
    if existing_files:
        parts = []
        for f in existing_files:
            parts.append(f"{f.path.name} [{f.scope}]")
        print(f"instructions: {', '.join(parts)}")

