"""--report and --effective output: full scope audit and resolved configuration."""

from __future__ import annotations

from pathlib import Path

from claude_tui_settings.cli import resolve_claude_repo
from claude_tui_settings.models.audit import run_audit, scan_all_scopes
from claude_tui_settings.models.resolver import resolve_effective_config
from claude_tui_settings.models.instruction_files import discover_instruction_files


def run_report() -> None:
    """Print full scope audit report."""
    project_dir = Path.cwd()

    print("=== Claude Code Scope Audit ===")
    print()

    # Scan all scopes
    scopes = scan_all_scopes(project_dir)
    for scope_name, data in scopes.items():
        print(f"[{scope_name}]")
        for key, value in sorted(data.items()):
            if key in ("$schema", "description"):
                continue
            if isinstance(value, dict):
                print(f"  {key}: ({len(value)} keys)")
            elif isinstance(value, list):
                print(f"  {key}: ({len(value)} items)")
            else:
                print(f"  {key}: {value}")
        print()

    # Warnings
    warnings = run_audit(project_dir)
    if warnings:
        print("=== Warnings ===")
        print()
        for w in warnings:
            print(f"  [{w.warning_type}] {w.message}")
        print()
    else:
        print("No scope conflicts detected.")
        print()

    # Instruction files
    inst_files = discover_instruction_files(project_dir)
    existing = [f for f in inst_files if f.exists]
    if existing:
        print("=== Instruction Files ===")
        print()
        for f in existing:
            print(f"  [{f.scope}] {f.path}")
            if f.preview:
                for line in f.preview.splitlines():
                    print(f"    {line}")
        print()


def run_effective() -> None:
    """Print detailed resolved configuration with full precedence chains."""
    project_dir = Path.cwd()
    effective = resolve_effective_config(project_dir)

    # Settings
    if effective.settings:
        print("[Settings]")
        for s in effective.settings:
            override_str = ""
            if s.overridden_scopes:
                overrides = ", ".join(
                    f'{scope} "{val}"' for scope, val in s.overridden_scopes
                )
                override_str = f" overrides {overrides}"
            value_str = str(s.value)
            print(f"  {s.key:<30} = {value_str:<25} [{s.source_scope}]{override_str}")
        print()

    # Permissions
    if effective.permission_rules:
        print("[Permissions]")
        for r in effective.permission_rules:
            print(f"  {r.rule_type:<5} {r.pattern:<35} [{r.source_scope}]")
        print()

    # MCP Servers
    if effective.mcp_servers:
        print("[MCP Servers]")
        for s in effective.mcp_servers:
            print(f"  {s.name:<30} [{s.source_scope}]")
        print()

    # Hooks
    if effective.hooks:
        print("[Hooks]")
        for h in effective.hooks:
            label = Path(h.command).stem if h.command else h.command
            print(f"  {h.event} {h.matcher:<20} {label:<20} [{h.source_scope}]")
        print()

    # Resources
    total_cmds = effective.project_commands + effective.user_commands
    if total_cmds:
        parts = []
        if effective.project_commands:
            parts.append(f"{effective.project_commands} project")
        if effective.user_commands:
            parts.append(f"{effective.user_commands} user")
        print(f"[Commands] {' + '.join(parts)} = {total_cmds} total")
        print()

    total_agents = effective.project_agents + effective.user_agents
    if total_agents:
        parts = []
        if effective.project_agents:
            parts.append(f"{effective.project_agents} project")
        if effective.user_agents:
            parts.append(f"{effective.user_agents} user")
        print(f"[Agents] {' + '.join(parts)} = {total_agents} total")
        print()

    # Instructions
    inst_files = discover_instruction_files(project_dir)
    existing = [f for f in inst_files if f.exists]
    if existing:
        print(f"[Instructions] {len(existing)} files")
        for f in existing:
            scope_label = f.scope.capitalize()
            print(f"  {f.path:<50} [{scope_label}]")
        print()
