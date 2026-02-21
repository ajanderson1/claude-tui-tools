"""Permissions section — profile RadioSet + rules display."""

from __future__ import annotations

import json

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import RadioButton, RadioSet, Static

from claude_tui_settings.models.config import ConfigState


class PermissionsSection(VerticalScroll, can_focus=False):
    """Permissions tab with profile selection and rules display."""

    def __init__(self, config: ConfigState) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Static("Permissions", classes="section-title")
        yield Static("[dim]Select a permission profile:[/dim]")

        with RadioSet(id="profile-radio"):
            for profile in self.config.available_profiles:
                btn = RadioButton(
                    f"{profile.name} - {profile.description}",
                    value=(profile.name == self.config.selected_profile),
                    name=profile.name,
                )
                yield btn

        yield Static("", id="perm-rules-display")

    def on_mount(self) -> None:
        self._refresh_rules()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle profile selection change."""
        radio = event.pressed
        profile_name = radio.name
        if profile_name:
            self.config.selected_profile = profile_name
            self._refresh_rules()
            self.app.mutate_reactive(type(self.app).config)

    def _refresh_rules(self) -> None:
        """Update the permissions rules display for the selected profile."""
        display = self.query_one("#perm-rules-display", Static)

        profile = None
        for p in self.config.available_profiles:
            if p.name == self.config.selected_profile:
                profile = p
                break

        if not profile:
            display.update("[dim]No profile selected[/dim]")
            return

        try:
            data = json.loads(profile.json_path.read_text())
        except (json.JSONDecodeError, OSError):
            display.update("[dim]Could not read profile[/dim]")
            return

        lines = [f"\n[bold]Profile: {profile.name}[/bold]"]
        if profile.description:
            lines.append(f"[dim]{profile.description}[/dim]\n")

        perms = data.get("permissions", {})
        if not perms:
            lines.append("[dim]No explicit permission rules (default behavior)[/dim]")
        else:
            for rule_type in ("deny", "ask", "allow"):
                rules = perms.get(rule_type, [])
                if rules:
                    match rule_type:
                        case "deny":
                            color = "red"
                        case "ask":
                            color = "yellow"
                        case "allow":
                            color = "green"
                        case _:
                            color = "white"
                    lines.append(f"\n  [{color}]{rule_type.upper()}:[/{color}]")
                    for rule in rules:
                        lines.append(f"    [{color}]{rule}[/{color}]")

        display.update("\n".join(lines))
