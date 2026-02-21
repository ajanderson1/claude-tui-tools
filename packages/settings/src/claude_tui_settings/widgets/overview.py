"""Overview section -- diff/preview + scope audit."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Rule, Static

from claude_tui_settings.models.config import ConfigState, Diff


class OverviewSection(VerticalScroll, can_focus=False):
    """Overview tab showing pending changes diff and scope audit warnings."""

    def __init__(self, config: ConfigState) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Static("Overview", classes="section-title")
        yield Static("", id="overview-audit")
        yield Rule()
        yield Static("", id="overview-diff")
        yield Static("", id="overview-status")

    def on_mount(self) -> None:
        self.refresh_content()

    def refresh_content(self) -> None:
        """Refresh the overview display."""
        self._refresh_audit()
        self._refresh_diff()
        self._refresh_status()

    def _refresh_audit(self) -> None:
        audit_widget = self.query_one("#overview-audit", Static)
        if not self.config.audit_warnings:
            audit_widget.update("")
            return

        lines = ["[bold]Scope Audit Warnings:[/bold]"]
        for w in self.config.audit_warnings:
            match w.warning_type:
                case "DUPE":
                    badge = "[yellow]DUPE[/yellow]"
                case "OVERRIDE":
                    badge = "[red]OVERRIDE[/red]"
                case "CONFLICT":
                    badge = "[bold red]CONFLICT[/bold red]"
                case _:
                    badge = w.warning_type
            lines.append(f"  {badge} {w.message}")
        audit_widget.update("\n".join(lines))

    def _refresh_diff(self) -> None:
        diff_widget = self.query_one("#overview-diff", Static)
        diff = self.config.pending_diff()

        if diff.is_empty:
            diff_widget.update("[dim]No pending changes[/dim]")
            return

        lines = ["[bold]Pending Changes:[/bold]"]

        # Group by domain
        domains: dict[str, list] = {}
        for entry in diff.entries:
            if entry.domain not in domains:
                domains[entry.domain] = []
            domains[entry.domain].append(entry)

        for domain, entries in domains.items():
            lines.append(f"\n  [bold]{domain.title()}:[/bold]")
            for entry in entries:
                key = str(entry.key).replace("[", "\\[")
                match entry.action:
                    case "add":
                        lines.append(f"    [green]+ {key}[/green]")
                    case "remove":
                        lines.append(f"    [red]- {key}[/red]")
                    case "modify":
                        old = str(entry.old_value).replace("[", "\\[")
                        new = str(entry.new_value).replace("[", "\\[")
                        lines.append(
                            f"    [yellow]~ {key}: "
                            f"{old} -> {new}[/yellow]"
                        )

        diff_widget.update("\n".join(lines))

    def _refresh_status(self) -> None:
        status_widget = self.query_one("#overview-status", Static)
        diff = self.config.pending_diff()
        if diff.is_empty:
            status_widget.update("")
        else:
            count = len(diff.entries)
            status_widget.update(
                f"\n[bold]{count} pending change{'s' if count != 1 else ''} "
                f"-- Ctrl+S to apply[/bold]"
            )
