"""Settings section — scope-aware form with badges and revert/unset."""

from __future__ import annotations

import json
from typing import Literal

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Select, Static, Switch

from claude_tui_settings.models.config import _NO_VALUE, ConfigState, SettingDef


class SettingChanged(Message):
    """Fired when a setting value changes in project scope."""

    def __init__(self, key: str, value: object) -> None:
        super().__init__()
        self.key = key
        self.value = value


class SettingReverted(Message):
    """Fired when a setting is reverted to user scope or unset entirely."""

    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key


Scope = Literal["USER", "PROJECT", "UNSET"]


class SettingRow(Widget):
    """A single setting with scope badge, action link, and control widget."""

    def __init__(self, setting_def: SettingDef, config: ConfigState) -> None:
        super().__init__()
        self.setting_def = setting_def
        self.config = config
        self._ready = False
        self._badge: Static | None = None
        self._action_link: Static | None = None
        self._control: Switch | Select | Input | None = None
        self._unset_hint: Static | None = None

    # ── Scope helpers ──────────────────────────────────────────────

    def _determine_scope(self) -> Scope:
        if self.setting_def.key in self.config.selected_settings:
            return "PROJECT"
        if self.config.get_user_scope_value(self.setting_def.key) is not _NO_VALUE:
            return "USER"
        return "UNSET"

    def _get_display_value(self) -> object:
        key = self.setting_def.key
        scope = self._determine_scope()
        if scope == "PROJECT":
            return self.config.selected_settings[key]
        if scope == "USER":
            return self.config.get_user_scope_value(key)
        return None

    def _get_user_value(self) -> object:
        return self.config.get_user_scope_value(self.setting_def.key)

    # ── Compose ────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        scope = self._determine_scope()
        value = self._get_display_value()
        user_val = self._get_user_value()
        key = self.setting_def.key

        # Header: key + badge + spacer + action link
        with Horizontal(classes="setting-header"):
            yield Static(f"[bold]{key}[/bold]", classes="setting-key")
            self._badge = Static(
                self._badge_text(scope),
                classes=f"scope-badge {self._badge_css(scope)}",
            )
            yield self._badge
            yield Static("", classes="setting-spacer")
            action_markup = self._action_markup(scope, user_val)
            self._action_link = Static(
                action_markup,
                id=f"action-{key}",
                classes="setting-action-link",
            )
            if scope != "PROJECT":
                self._action_link.display = False
            yield self._action_link

        # Description
        if self.setting_def.description:
            yield Static(
                f"[dim]{self.setting_def.description}[/dim]",
                classes="setting-description",
            )

        # Control widget
        yield from self._compose_control(value, scope)

    def _badge_text(self, scope: Scope) -> str:
        match scope:
            case "USER":
                return "(USER)"
            case "PROJECT":
                return "(PROJECT)"
            case _:
                return "(NOT SET)"

    def _badge_css(self, scope: Scope) -> str:
        match scope:
            case "USER":
                return "scope-user"
            case "PROJECT":
                return "scope-project"
            case _:
                return "scope-unset"

    def _action_markup(self, scope: Scope, user_val: object) -> str:
        if scope != "PROJECT":
            return ""
        label = "revert" if user_val is not _NO_VALUE else "unset"
        return f"[underline]{label}[/underline]"

    def _compose_control(self, value: object, scope: Scope) -> ComposeResult:
        key = self.setting_def.key
        setting = self.setting_def
        is_unset = scope == "UNSET"

        match setting.type:
            case "boolean":
                switch = Switch(
                    value=bool(value) if value is not None else False,
                    name=key,
                )
                if is_unset:
                    switch.add_class("setting-unset-switch")
                self._control = switch
                yield switch
                if is_unset:
                    self._unset_hint = Static(
                        "[dim](not set — toggle to set)[/dim]",
                        classes="setting-unset-hint",
                    )
                    yield self._unset_hint
            case "enum":
                valid_values = set(setting.enum_values or [])
                options = [(str(v), v) for v in (setting.enum_values or [])]
                kwargs: dict = {"name": key, "allow_blank": True}
                if value in valid_values:
                    kwargs["value"] = value
                sel = Select(options, **kwargs)
                self._control = sel
                yield sel
            case "number" | "integer":
                placeholder = ""
                if is_unset and setting.default is not None:
                    placeholder = f"Default: {setting.default}"
                inp = Input(
                    value=str(value) if value is not None else "",
                    placeholder=placeholder,
                    name=key,
                    type="number",
                    valid_empty=True,
                )
                self._control = inp
                yield inp
            case _:
                display = ""
                if value is not None and value != {}:
                    if isinstance(value, (dict, list)):
                        display = json.dumps(value)
                    else:
                        display = str(value)
                placeholder = ""
                if is_unset and setting.default:
                    placeholder = f"Default: {setting.default}"
                inp = Input(value=display, placeholder=placeholder, name=key)
                self._control = inp
                yield inp

    # ── Lifecycle ──────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.call_later(self._mark_ready)

    def _mark_ready(self) -> None:
        self._ready = True

    # ── Badge / action updates ─────────────────────────────────────

    def _update_scope_display(self, scope: Scope) -> None:
        """Update badge text, CSS class, and action button visibility."""
        if self._badge:
            self._badge.update(self._badge_text(scope))
            self._badge.remove_class("scope-user", "scope-project", "scope-unset")
            self._badge.add_class(self._badge_css(scope))

        if self._action_link:
            if scope == "PROJECT":
                user_val = self._get_user_value()
                self._action_link.update(
                    self._action_markup(scope, user_val)
                )
                self._action_link.display = True
            else:
                self._action_link.display = False

        # Boolean UNSET visual state
        if self.setting_def.type == "boolean":
            if scope == "UNSET":
                if self._control:
                    self._control.add_class("setting-unset-switch")
                if self._unset_hint:
                    self._unset_hint.display = True
            else:
                if self._control:
                    self._control.remove_class("setting-unset-switch")
                if self._unset_hint:
                    self._unset_hint.display = False

    # ── Value change logic ─────────────────────────────────────────

    def _handle_value_change(self, new_value: object) -> None:
        """Process a control value change with scope semantics."""
        if not self._ready:
            return

        key = self.setting_def.key
        user_val = self._get_user_value()

        # Clear / empty → remove from project scope
        if new_value is None:
            if key in self.config.selected_settings:
                self.config.selected_settings.pop(key)
                new_scope: Scope = "USER" if user_val is not _NO_VALUE else "UNSET"
                self._update_scope_display(new_scope)
                self.post_message(SettingChanged(key=key, value=None))
            return

        # Value matches user scope → auto-demote (or no-op if already USER)
        if user_val is not _NO_VALUE and new_value == user_val:
            if key in self.config.selected_settings:
                self.config.selected_settings.pop(key)
                self._update_scope_display("USER")
                self.post_message(SettingChanged(key=key, value=None))
            return

        # Actual change → promote to PROJECT
        self.config.selected_settings[key] = new_value
        self._update_scope_display("PROJECT")
        self.post_message(SettingChanged(key=key, value=new_value))

    def _do_revert_or_unset(self) -> None:
        """Handle revert (→ USER) or unset (→ UNSET) action."""
        key = self.setting_def.key
        user_val = self._get_user_value()

        self.config.selected_settings.pop(key, None)

        if user_val is not _NO_VALUE:
            new_scope: Scope = "USER"
            self._set_control_value(user_val)
        else:
            new_scope = "UNSET"
            self._set_control_value(None)

        self._update_scope_display(new_scope)
        self.post_message(SettingReverted(key=key))

    def _set_control_value(self, value: object) -> None:
        """Set the control widget value, suppressing the triggered event.

        Uses Textual's ``prevent`` context manager to block Changed messages
        from being posted, avoiding any timing issues with call_later.
        """
        if isinstance(self._control, Switch):
            with self._control.prevent(Switch.Changed):
                self._control.value = bool(value) if value is not None else False
        elif isinstance(self._control, Select):
            with self._control.prevent(Select.Changed):
                if value is None:
                    self._control.clear()
                else:
                    self._control.value = value
        elif isinstance(self._control, Input):
            with self._control.prevent(Input.Changed):
                if value is None:
                    self._control.value = ""
                elif isinstance(value, (dict, list)):
                    self._control.value = json.dumps(value)
                else:
                    self._control.value = str(value)

    # ── Event handlers ─────────────────────────────────────────────

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.name == self.setting_def.key:
            self._handle_value_change(event.value)
            event.stop()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.name == self.setting_def.key:
            if event.value is Select.BLANK or event.value is Select.NULL:
                self._handle_value_change(None)
            else:
                self._handle_value_change(event.value)
            event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.name == self.setting_def.key:
            if event.value == "":
                self._handle_value_change(None)
            else:
                value: object = event.value
                # Parse JSON for complex types (dict/list)
                try:
                    parsed = json.loads(event.value)
                    if isinstance(parsed, (dict, list)):
                        value = parsed
                except (json.JSONDecodeError, ValueError):
                    pass
                # Number coercion (only if still a string)
                if isinstance(value, str):
                    try:
                        value = int(value)
                    except ValueError:
                        try:
                            value = float(value)
                        except ValueError:
                            pass
                self._handle_value_change(value)
            event.stop()

    def on_click(self, event) -> None:
        """Handle click on the action link Static."""
        if self._action_link is None or not self._action_link.display:
            return
        # Check if the clicked widget is the action link or inside it
        widget = event.widget
        while widget is not None and widget is not self:
            if widget is self._action_link:
                self._do_revert_or_unset()
                event.stop()
                return
            widget = widget.parent


class SettingsSection(VerticalScroll):
    """Settings tab with scope-aware dynamic form."""

    def __init__(self, config: ConfigState) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Static("Settings", classes="section-title")

        if not self.config.available_settings:
            yield Static("[dim]Schema unavailable - settings editor disabled[/dim]")
            return

        for setting in self.config.available_settings:
            yield SettingRow(setting, self.config)

        yield Static(
            "\n[dim]Sandbox settings are not yet supported and may be "
            "implemented in a future release.[/dim]",
            classes="setting-sandbox-note",
        )
