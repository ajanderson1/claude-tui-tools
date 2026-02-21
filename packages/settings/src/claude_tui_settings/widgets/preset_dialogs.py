"""Modal dialogs for saving and loading presets."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets._option_list import Option

from claude_tui_settings.models.config import ConfigState, Preset
from claude_tui_settings.models.presets import slugify, validate_preset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_option_prompt(preset: Preset) -> Text:
    text = Text()
    text.append(escape(preset.name), style="bold")
    text.append("\n")
    if preset.description:
        desc = preset.description[:50] + "..." if len(preset.description) > 50 else preset.description
        text.append(escape(desc), style="dim")
    if preset.created_at:
        text.append(f"  {preset.created_at[:10]}", style="italic dim")
    return text


# ---------------------------------------------------------------------------
# SavePresetDialog
# ---------------------------------------------------------------------------

class SavePresetDialog(ModalScreen[tuple[str, str] | None]):
    """Modal dialog for saving the current configuration as a preset."""

    def __init__(self, existing_slugs: set[str]) -> None:
        super().__init__()
        self._existing_slugs = existing_slugs
        self._confirmed_overwrite = False
        self._last_conflict_slug: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="save-preset-container"):
            yield Label("Save Preset", id="save-preset-title")
            yield Input(placeholder="Preset name (required)", id="save-preset-name")
            yield Input(placeholder="Description (optional)", id="save-preset-desc")
            yield Static("", id="save-preset-error")
            with Horizontal(id="save-preset-buttons"):
                yield Button("Save", variant="success", id="save-preset-save")
                yield Button("Cancel", variant="primary", id="save-preset-cancel")

    def on_mount(self) -> None:
        self.query_one("#save-preset-name", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "save-preset-name":
            self._confirmed_overwrite = False
            self._last_conflict_slug = None
            error = self.query_one("#save-preset-error", Static)
            if not event.value.strip():
                error.update("Name is required.")
            else:
                error.update("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-preset-cancel":
            self.dismiss(None)
            return

        if event.button.id == "save-preset-save":
            name_input = self.query_one("#save-preset-name", Input)
            desc_input = self.query_one("#save-preset-desc", Input)
            error = self.query_one("#save-preset-error", Static)

            name = name_input.value.strip()
            if not name:
                error.update("Name is required.")
                return

            try:
                slug = slugify(name)
            except ValueError:
                error.update("Name produces an invalid slug. Use alphanumeric characters.")
                return

            if slug in self._existing_slugs:
                if self._confirmed_overwrite and self._last_conflict_slug == slug:
                    # Second press — allow overwrite
                    self.dismiss((name, desc_input.value.strip()))
                    return
                self._confirmed_overwrite = True
                self._last_conflict_slug = slug
                error.update(
                    f"Preset '{escape(slug)}' already exists. Save again to overwrite."
                )
                return

            self.dismiss((name, desc_input.value.strip()))


# ---------------------------------------------------------------------------
# LoadPresetDialog
# ---------------------------------------------------------------------------

class LoadPresetDialog(ModalScreen[tuple[Preset, set[tuple[str, str]]] | None]):
    """Modal dialog for selecting and loading a preset."""

    def __init__(self, presets: list[Preset], state: ConfigState) -> None:
        super().__init__()
        self._presets = presets
        self._state = state
        self._current_issues: list[tuple[str, str, str]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="load-preset-container"):
            yield Label("Load Preset", id="load-preset-title")
            if not self._presets:
                yield Static(
                    "No saved presets found. Use Ctrl+E to save a preset first."
                )
                with Horizontal(id="load-preset-buttons"):
                    yield Button("OK", variant="primary", id="load-preset-ok")
            else:
                options = [
                    Option(_make_option_prompt(p), id=p.slug)
                    for p in self._presets
                ]
                yield OptionList(*options, id="preset-list")
                yield Static("", id="validation-warnings")
                with Horizontal(id="load-preset-buttons"):
                    yield Button("Load", variant="success", id="load-preset-load")
                    yield Button("Cancel", variant="primary", id="load-preset-cancel")

    def on_mount(self) -> None:
        if self._presets:
            option_list = self.query_one("#preset-list", OptionList)
            option_list.focus()
            # Trigger initial validation for first item
            self._validate_highlighted(0)

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted,
    ) -> None:
        self._validate_highlighted(event.option_index)

    def _validate_highlighted(self, index: int) -> None:
        if index < 0 or index >= len(self._presets):
            return
        preset = self._presets[index]
        self._current_issues = validate_preset(preset, self._state)

        warnings = self.query_one("#validation-warnings", Static)
        load_btn = self.query_one("#load-preset-load", Button)

        if not self._current_issues:
            warnings.update("")
            load_btn.label = "Load"
        else:
            # Group by domain
            by_domain: dict[str, list[str]] = {}
            for domain, _key, msg in self._current_issues:
                by_domain.setdefault(domain, []).append(escape(msg))

            lines: list[str] = []
            for domain, msgs in by_domain.items():
                lines.append(f"[bold]{escape(domain)}:[/bold]")
                for m in msgs:
                    lines.append(f"  - {m}")

            warnings.update("\n".join(lines))
            n = len(self._current_issues)
            load_btn.label = f"Load (skip {n})"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("load-preset-cancel", "load-preset-ok"):
            self.dismiss(None)
            return

        if event.button.id == "load-preset-load":
            option_list = self.query_one("#preset-list", OptionList)
            idx = option_list.highlighted
            if idx is None or idx < 0 or idx >= len(self._presets):
                return
            preset = self._presets[idx]
            skip_set = {(domain, key) for domain, key, _msg in self._current_issues}
            self.dismiss((preset, skip_set))


# ---------------------------------------------------------------------------
# ConfirmLoadDialog
# ---------------------------------------------------------------------------

class ConfirmLoadDialog(ModalScreen[bool]):
    """Modal dialog confirming preset load when there are unsaved changes."""

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-load-container"):
            yield Label("Unsaved Changes", id="confirm-load-title")
            yield Static(
                "You have unsaved changes. Loading a preset will overwrite "
                "your current selections. Continue?"
            )
            with Horizontal(id="confirm-load-buttons"):
                yield Button("Yes", variant="error", id="confirm-load-yes")
                yield Button("No", variant="primary", id="confirm-load-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-load-yes")
