"""Instructions section -- CLAUDE.md, rules, MEMORY.md across scopes (read-only)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Static

from claude_tui_settings.models.config import ConfigState


class InstructionsSection(VerticalScroll, can_focus=False):
    """Instructions tab showing all instruction files Claude Code will load."""

    def __init__(self, config: ConfigState) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Static("Instructions", classes="section-title")
        yield Static(
            "[dim]Read-only: These are all instruction files Claude Code "
            "will load for this project. All files are additive.[/dim]\n"
        )

        # Group by scope
        scope_order = ["managed", "user", "user-project", "project", "local"]
        scope_labels = {
            "managed": "Managed",
            "user": "User (global)",
            "user-project": "User (per-project)",
            "project": "Project",
            "local": "Local",
        }

        grouped: dict[str, list] = {s: [] for s in scope_order}
        for f in self.config.instruction_files:
            if f.scope in grouped:
                grouped[f.scope].append(f)

        for scope in scope_order:
            files = grouped[scope]
            if not files:
                continue

            label = scope_labels.get(scope, scope)
            file_count = len(files)
            title = f"{label} scope ({file_count} file{'s' if file_count != 1 else ''})"

            with Collapsible(title=title, collapsed=False):
                for f in files:
                    if f.exists:
                        type_badge = self._type_badge(f.file_type)
                        yield Static(f"  {type_badge} {f.path}")
                        if f.preview:
                            for line in f.preview.splitlines()[:2]:
                                yield Static(f"    [dim]{line}[/dim]")
                    else:
                        yield Static(f"  [dim](not found) {f.path}[/dim]")

    @staticmethod
    def _type_badge(file_type: str) -> str:
        match file_type:
            case "claude_md":
                return "[green]CLAUDE.md[/green]"
            case "rules":
                return "[yellow]rules[/yellow]"
            case "memory":
                return "[magenta]MEMORY[/magenta]"
            case "local_md":
                return "[blue]local[/blue]"
            case _:
                return file_type
