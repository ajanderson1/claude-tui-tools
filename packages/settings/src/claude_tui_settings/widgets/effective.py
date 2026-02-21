"""Effective section -- resolved final config from all scopes (read-only)."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Rule, Static

from claude_tui_settings.models.config import ConfigState


class EffectiveSection(VerticalScroll, can_focus=False):
    """Effective tab showing the fully resolved configuration after all scopes merge."""

    def __init__(self, config: ConfigState) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Static("Effective Configuration", classes="section-title")
        yield Static(
            "[dim]Read-only: The resolved configuration after all scopes merge. "
            "This is what Claude Code will actually use.[/dim]\n"
        )

        yield from self._compose_settings()
        yield from self._compose_permissions()
        yield from self._compose_plugins()
        yield from self._compose_mcp_servers()
        yield from self._compose_hooks()
        yield from self._compose_resources()

    def _compose_settings(self) -> ComposeResult:
        eff = self.config.effective
        if not eff.settings:
            return

        yield Static("[bold]Settings[/bold]")
        dt = DataTable(cursor_type="row")
        dt.add_columns("Key", "Value", "Source", "Overrides")
        for s in eff.settings:
            override_str = ""
            if s.overridden_scopes:
                parts = []
                for scope, val in s.overridden_scopes:
                    parts.append(f'{scope} "{val}"')
                override_str = ", ".join(parts)

            value_str = str(s.value)
            if len(value_str) > 30:
                value_str = value_str[:27] + "..."

            dt.add_row(
                Text(s.key, style="bold"),
                Text(value_str, style="green"),
                Text(s.source_scope, style="cyan"),
                Text(override_str, style="dim italic") if override_str else Text(""),
            )
        yield dt
        yield Rule()

    def _compose_permissions(self) -> ComposeResult:
        eff = self.config.effective
        if not eff.permission_rules:
            return

        yield Static("[bold]Permissions[/bold]")
        dt = DataTable(cursor_type="row")
        dt.add_columns("Type", "Pattern", "Source", "Overrides")
        for r in eff.permission_rules:
            match r.rule_type:
                case "ALLOW":
                    color = "green"
                case "DENY":
                    color = "red"
                case "ASK":
                    color = "yellow"
                case _:
                    color = "white"

            override_str = ""
            if r.overridden_scopes:
                parts = []
                for scope, rtype in r.overridden_scopes:
                    parts.append(f"{scope} {rtype}")
                override_str = ", ".join(parts)

            pattern = r.pattern
            if len(pattern) > 40:
                pattern = pattern[:37] + "..."

            dt.add_row(
                Text(r.rule_type, style=color),
                Text(pattern),
                Text(r.source_scope, style="cyan"),
                Text(override_str, style="dim italic") if override_str else Text(""),
            )
        yield dt
        yield Rule()

    def _compose_plugins(self) -> ComposeResult:
        eff = self.config.effective
        if not eff.plugins:
            return

        yield Static("[bold]Plugins[/bold]")
        dt = DataTable(cursor_type="row")
        dt.add_columns("Plugin", "Status", "Source", "Overrides")
        for p in eff.plugins:
            status_text = "enabled" if p.enabled else "disabled"
            status_style = "green" if p.enabled else "red"

            override_str = ""
            if p.overridden_scopes:
                parts = []
                for scope, val in p.overridden_scopes:
                    parts.append(f'{scope} {"enabled" if val else "disabled"}')
                override_str = ", ".join(parts)

            dt.add_row(
                Text(p.plugin_id, style="bold"),
                Text(status_text, style=status_style),
                Text(p.source_scope, style="cyan"),
                Text(override_str, style="dim italic") if override_str else Text(""),
            )
        yield dt
        yield Rule()

    def _compose_mcp_servers(self) -> ComposeResult:
        eff = self.config.effective
        if not eff.mcp_servers:
            return

        yield Static("[bold]MCP Servers[/bold]")
        dt = DataTable(cursor_type="row")
        dt.add_columns("Name", "Source")
        for s in eff.mcp_servers:
            dt.add_row(
                Text(s.name, style="bold"),
                Text(s.source_scope, style="cyan"),
            )
        yield dt
        yield Rule()

    def _compose_hooks(self) -> ComposeResult:
        eff = self.config.effective
        if not eff.hooks:
            return

        yield Static("[bold]Hooks[/bold]")
        dt = DataTable(cursor_type="row")
        dt.add_columns("Event", "Matcher", "Command", "Source")
        for h in eff.hooks:
            label = Path(h.command).stem if h.command else h.command
            dt.add_row(
                Text(h.event),
                Text(h.matcher),
                Text(label),
                Text(h.source_scope, style="cyan"),
            )
        yield dt
        yield Rule()

    def _compose_resources(self) -> ComposeResult:
        eff = self.config.effective
        total_cmds = eff.project_commands + eff.user_commands
        total_agents = eff.project_agents + eff.user_agents

        if not (total_cmds or total_agents or eff.project_skills):
            return

        yield Static("[bold]Resources[/bold]")
        dt = DataTable(cursor_type="row")
        dt.add_columns("Type", "Project", "User")

        if total_cmds:
            dt.add_row(
                Text("Commands", style="bold"),
                Text(str(eff.project_commands)),
                Text(str(eff.user_commands)),
            )
        if total_agents:
            dt.add_row(
                Text("Agents", style="bold"),
                Text(str(eff.project_agents)),
                Text(str(eff.user_agents)),
            )
        if eff.project_skills:
            dt.add_row(
                Text("Skills", style="bold"),
                Text(str(eff.project_skills)),
                Text("0"),
            )
        yield dt
