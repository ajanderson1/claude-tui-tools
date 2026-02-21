"""Argument parsing and dispatch for claude-tui-settings."""

from __future__ import annotations

import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> dict:
    """Parse command-line arguments.

    Returns dict with keys: summary, report, effective, help.
    """
    if argv is None:
        argv = sys.argv[1:]

    result = {
        "summary": False,
        "report": False,
        "effective": False,
        "help": False,
        "version": False,
    }

    i = 0
    while i < len(argv):
        arg = argv[i]
        match arg:
            case "--summary":
                result["summary"] = True
            case "--report":
                result["report"] = True
            case "--effective":
                result["effective"] = True
            case "--help" | "-h":
                result["help"] = True
            case "--version" | "-V":
                result["version"] = True
            case "--no-gum":
                print("Note: --no-gum is no longer needed. The Textual TUI replaces gum.")
            case _:
                if arg.startswith("-"):
                    print(f"Unknown flag: {arg}", file=sys.stderr)
                    print("Usage: claude-tui-settings [--summary | --report | --effective | --version | --help]", file=sys.stderr)
                    sys.exit(1)
        i += 1

    return result


def resolve_claude_repo() -> Path:
    """Resolve $CLAUDE_REPO from environment."""
    import os
    repo = os.environ.get("CLAUDE_REPO", "")
    if not repo:
        print("Error: CLAUDE_REPO environment variable is not set.", file=sys.stderr)
        print("Set it to the path of your Claude Code resource repository.", file=sys.stderr)
        print("  export CLAUDE_REPO=/path/to/your/claude-repo", file=sys.stderr)
        sys.exit(1)

    path = Path(repo)
    if not path.is_dir():
        print(f"Error: CLAUDE_REPO directory not found at {path}", file=sys.stderr)
        print("Verify the path exists and contains your Claude Code resources.", file=sys.stderr)
        sys.exit(1)

    return path


def print_help() -> None:
    """Print usage help."""
    print("claude-tui-settings - Configure Claude Code project settings")
    print()
    print("Usage:")
    print("  claude-tui-settings           Launch interactive TUI dashboard")
    print("  claude-tui-settings --summary Condensed text output (effective config)")
    print("  claude-tui-settings --report  Full scope audit report")
    print("  claude-tui-settings --effective Detailed resolved configuration")
    print("  claude-tui-settings --version  Show version")
    print("  claude-tui-settings --help    Show this help")


def _check_not_home() -> None:
    """Abort if CWD is the user's home directory.

    Running from home causes ~/.claude/settings.json to serve as both
    project-scope and user-global scope, leaking project settings to
    every project on the machine.
    """
    if Path.cwd() == Path.home():
        print(
            "Error: claude-tui-settings should not be run from your home directory.",
            file=sys.stderr,
        )
        print(
            "Running from ~ causes project settings to be written to "
            "~/.claude/settings.json,",
            file=sys.stderr,
        )
        print(
            "which Claude Code also reads as user-global settings — effectively "
            "applying this project's config to every project.",
            file=sys.stderr,
        )
        print(file=sys.stderr)
        print(
            "cd into a project directory first, then run claude-tui-settings.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    args = parse_args()

    if args["version"]:
        from claude_tui_settings.__about__ import __version__
        print(f"claude-tui-settings {__version__}")
        sys.exit(0)

    if args["help"]:
        print_help()
        sys.exit(0)

    _check_not_home()

    if args["summary"]:
        from claude_tui_settings.summary import run_summary
        run_summary()
        sys.exit(0)

    if args["report"]:
        from claude_tui_settings.report import run_report
        run_report()
        sys.exit(0)

    if args["effective"]:
        from claude_tui_settings.report import run_effective
        run_effective()
        sys.exit(0)

    # Launch interactive TUI
    _run_tui()


def _run_tui() -> None:
    """Launch the interactive Textual TUI."""
    claude_repo = resolve_claude_repo()
    project_dir = Path.cwd()

    # Build ConfigState
    from claude_tui_settings.models.config import ConfigState
    from claude_tui_settings.models.detection import (
        detect_existing_settings,
        detect_hooks,
        detect_mcps,
        detect_plugins,
        detect_profile,
        detect_resources,
        detect_user_resources,
    )
    from claude_tui_settings.models.discovery import (
        discover_agents,
        discover_commands,
        discover_hooks,
        discover_mcps,
        discover_plugins,
        discover_profiles,
        discover_skills,
    )
    from claude_tui_settings.models.audit import run_audit
    from claude_tui_settings.models.instruction_files import discover_instruction_files
    from claude_tui_settings.models.resolver import resolve_effective_config

    # Discovery
    profiles = discover_profiles(claude_repo)
    commands = discover_commands(claude_repo)
    agents = discover_agents(claude_repo)
    skills = discover_skills(claude_repo)
    plugins = discover_plugins(claude_repo)
    mcps = discover_mcps(claude_repo)
    hooks = discover_hooks(claude_repo)

    # Schema (use cache if available; background fetch handled by app after startup)
    from claude_tui_settings.models.schema import (
        get_cached_schema,
        get_stale_cache,
        parse_schema_properties,
    )
    from claude_tui_settings.models.discovery import discover_settings

    schema = get_cached_schema() or get_stale_cache()
    setting_defs = []
    if schema:
        raw_props = parse_schema_properties(schema)
        setting_defs = discover_settings(raw_props, claude_repo)

    # Detection
    settings_path = project_dir / ".claude" / "settings.json"
    existing_profile = detect_profile(settings_path, claude_repo / "profiles")

    existing_commands, local_commands = detect_resources(
        project_dir / ".claude" / "commands", claude_repo, "commands",
    )
    existing_agents, local_agents = detect_resources(
        project_dir / ".claude" / "agents", claude_repo, "agents",
    )
    existing_skills, local_skills = detect_resources(
        project_dir / ".claude" / "skills", claude_repo, "skills",
    )
    existing_plugins = detect_plugins(settings_path)
    existing_mcps = detect_mcps(project_dir / ".mcp.json")
    existing_hooks = detect_hooks(settings_path, claude_repo)
    existing_settings = detect_existing_settings(settings_path)

    user_claude_dir = Path.home() / ".claude"
    user_commands = detect_user_resources(user_claude_dir, "commands")
    user_agents = detect_user_resources(user_claude_dir, "agents")
    user_skills = detect_user_resources(user_claude_dir, "skills")

    # Audit
    audit_warnings = run_audit(project_dir)

    # Resource duplicate detection (items at both project and user scope)
    from claude_tui_settings.models.config import AuditWarning
    for domain, proj_set, user_set in [
        ("commands", existing_commands, user_commands),
        ("agents", existing_agents, user_agents),
        ("skills", existing_skills, user_skills),
    ]:
        for name in sorted(proj_set & user_set):
            audit_warnings.append(AuditWarning(
                scope="project",
                warning_type="DUPE",
                key=f"{domain}/{name}",
                message=(
                    f"{name}: present in both project and user scope "
                    f"[dim]({domain})[/dim]"
                ),
            ))

    # Instruction files
    instruction_files = discover_instruction_files(project_dir)

    # Effective config
    effective = resolve_effective_config(project_dir, setting_defs)

    # Mark local resources in available lists
    local_names = {r.name for r in local_commands}
    for cmd in commands:
        if cmd.name in local_names:
            cmd.is_local = True

    local_agent_names = {r.name for r in local_agents}
    for agent in agents:
        if agent.name in local_agent_names:
            agent.is_local = True

    local_skill_names = {r.name for r in local_skills}
    for skill in skills:
        if skill.name in local_skill_names:
            skill.is_local = True

    config = ConfigState(
        claude_repo=claude_repo,
        available_profiles=profiles,
        available_commands=commands,
        available_agents=agents,
        available_skills=skills,
        available_plugins=plugins,
        available_mcps=mcps,
        available_hooks=hooks,
        available_settings=setting_defs,
        existing_profile=existing_profile,
        existing_commands=existing_commands,
        existing_agents=existing_agents,
        existing_skills=existing_skills,
        existing_plugins=existing_plugins,
        existing_mcps=existing_mcps,
        existing_hooks=existing_hooks,
        existing_settings=existing_settings,
        selected_profile=existing_profile or "standard",
        selected_commands=set(existing_commands),
        selected_agents=set(existing_agents),
        selected_skills=set(existing_skills),
        selected_plugins=set(existing_plugins),
        selected_mcps=set(existing_mcps),
        selected_hooks=set(existing_hooks),
        selected_settings=dict(existing_settings),
        audit_warnings=audit_warnings,
        effective=effective,
        instruction_files=instruction_files,
        user_commands=user_commands,
        user_agents=user_agents,
        user_skills=user_skills,
    )

    from claude_tui_settings.models.presets import list_presets
    presets = list_presets(claude_repo)

    from claude_tui_settings.app import BootstrapApp
    app = BootstrapApp(config=config, presets=presets)
    app.run()
