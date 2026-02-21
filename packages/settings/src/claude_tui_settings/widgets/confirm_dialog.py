"""Modal dialogs for removal confirmation and exit with unsaved changes."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from claude_tui_settings.models.config import DiffEntry


class ConfirmDialog(ModalScreen[bool]):
    """Modal dialog for confirming removals on Ctrl+S."""

    def __init__(self, removals: list[DiffEntry]) -> None:
        super().__init__()
        self.removals = removals

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-container"):
            yield Label("Confirm Removals", id="confirm-title")
            yield Static("The following items will be removed:")
            with VerticalScroll(id="confirm-items"):
                for entry in self.removals:
                    label = f"  - [{entry.domain}] {entry.key}"
                    if entry.reason:
                        label += f" [dim]({entry.reason})[/dim]"
                    yield Static(label, classes="diff-remove")
            with Horizontal(id="confirm-buttons"):
                yield Button("Confirm", variant="error", id="confirm-yes")
                yield Button("Cancel", variant="primary", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class RevertDialog(ModalScreen[bool]):
    """Modal dialog for confirming revert to filesystem state."""

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-container"):
            yield Label("Revert Changes", id="confirm-title")
            yield Static("Revert to filesystem state and lose all unsaved changes?")
            with Horizontal(id="confirm-buttons"):
                yield Button("Revert", variant="error", id="confirm-yes")
                yield Button("Cancel", variant="primary", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class ExitDialog(ModalScreen[str]):
    """Modal dialog for exit with unsaved changes."""

    def compose(self) -> ComposeResult:
        with Vertical(id="exit-container"):
            yield Label("Unsaved Changes", id="exit-title")
            yield Static("You have unsaved changes. What would you like to do?")
            with Horizontal(id="exit-buttons"):
                yield Button("Save & Exit", variant="success", id="exit-save")
                yield Button("Discard & Exit", variant="error", id="exit-discard")
                yield Button("Cancel", variant="primary", id="exit-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "exit-save":
                self.dismiss("save")
            case "exit-discard":
                self.dismiss("discard")
            case "exit-cancel":
                self.dismiss("cancel")
