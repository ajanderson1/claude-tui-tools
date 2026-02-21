"""BootstrapApp — Variant B: Sidebar Navigator layout."""

from __future__ import annotations

import json
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets._option_list import Option
from textual.worker import Worker, WorkerState

PREFS_FILE = Path.home() / ".cache" / "claude-tui-settings" / "preferences.json"
DEFAULT_THEME = "gruvbox"


def _load_theme() -> str:
    """Load saved theme preference, or return default."""
    try:
        prefs = json.loads(PREFS_FILE.read_text())
        return prefs.get("theme", DEFAULT_THEME)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_THEME


def _save_theme(theme: str) -> None:
    """Persist theme preference to disk."""
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    prefs: dict = {}
    try:
        prefs = json.loads(PREFS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    prefs["theme"] = theme
    PREFS_FILE.write_text(json.dumps(prefs, indent=2))

from claude_tui_settings.models.config import ConfigState, Preset
from claude_tui_settings.models.persistence import apply_config
from claude_tui_settings.models.presets import list_presets, save_preset, load_preset_into_state
from claude_tui_settings.widgets.agents import make_agents_section
from claude_tui_settings.widgets.commands import make_commands_section
from claude_tui_settings.widgets.confirm_dialog import ConfirmDialog, ExitDialog, RevertDialog
from claude_tui_settings.widgets.preset_dialogs import (
    ConfirmLoadDialog,
    LoadPresetDialog,
    SavePresetDialog,
)
from claude_tui_settings.widgets.effective import EffectiveSection
from claude_tui_settings.widgets.hooks import make_hooks_section
from claude_tui_settings.widgets.instructions import InstructionsSection
from claude_tui_settings.widgets.mcps import make_mcps_section
from claude_tui_settings.widgets.overview import OverviewSection
from claude_tui_settings.widgets.permissions import PermissionsSection
from claude_tui_settings.widgets.plugins import make_plugins_section
from claude_tui_settings.widgets.resource_list import ResourceToggled
from claude_tui_settings.widgets.settings_tab import SettingChanged, SettingReverted, SettingsSection
from claude_tui_settings.widgets.skills import make_skills_section


# Section definitions: (id, label, is_understand_mode)
SECTIONS = [
    ("overview", "Overview", True),
    ("permissions", "Perms", False),
    ("commands", "Commands", False),
    ("agents", "Agents", False),
    ("skills", "Skills", False),
    ("plugins", "Plugins", False),
    ("mcps", "MCPs", False),
    ("hooks", "Hooks", False),
    ("settings", "Settings", False),
    ("instructions", "Instruct.", True),
    ("effective", "Effective", True),
]


class BootstrapApp(App):
    """Textual app for claude-tui-settings with Sidebar Navigator layout."""

    TITLE = "claude-tui-settings"
    CSS_PATH = "css/app.tcss"
    BINDINGS = [
        Binding("ctrl+s", "apply", "Save", show=True),
        Binding("f2", "apply", "Save (F2)", show=False),
        Binding("ctrl+r", "revert", "Revert", show=True),
        Binding("ctrl+e", "save_preset", "Export", show=True),
        Binding("ctrl+l", "load_preset", "Load", show=True),
        Binding("q", "quit_app", "Quit", show=True),
        Binding("ctrl+q", "quit_app", "Quit", show=False),
        Binding("alt+1", "jump(0)", "Overview", show=False),
        Binding("alt+2", "jump(1)", "Perms", show=False),
        Binding("alt+3", "jump(2)", "Commands", show=False),
        Binding("alt+4", "jump(3)", "Agents", show=False),
        Binding("alt+5", "jump(4)", "Skills", show=False),
        Binding("alt+6", "jump(5)", "Plugins", show=False),
        Binding("alt+7", "jump(6)", "MCPs", show=False),
        Binding("alt+8", "jump(7)", "Hooks", show=False),
        Binding("alt+9", "jump(8)", "Settings", show=False),
        Binding("alt+0", "jump(9)", "Instructions", show=False),
    ]

    config: reactive[ConfigState | None] = reactive(None)
    current_section: reactive[int] = reactive(0)

    def __init__(self, config: ConfigState, presets: list[Preset] | None = None) -> None:
        super().__init__()
        self._initial_config = config
        self._section_widgets: list[Widget] = []
        self._presets: list[Preset] = presets or []

    def compose(self) -> ComposeResult:
        project_name = Path.cwd().name
        yield Header()
        self.title = f"claude-tui-settings -- {project_name}"

        with Horizontal(id="main-container"):
            with Vertical(id="sidebar"):
                yield self._build_sidebar()
            with Vertical(id="content-pane"):
                pass  # Sections mounted in on_mount

        yield Footer()

    def _build_sidebar(self) -> OptionList:
        """Build the sidebar OptionList with section labels.

        Uses visual markers to distinguish Manage (tabs 2-9) from
        Understand (tabs 1, 10, 11) sections.
        """
        options: list[Option] = []
        for _i, (section_id, label, is_understand) in enumerate(SECTIONS):
            # Prefix understand sections with a marker for visual distinction
            if is_understand:
                display_label = f"  {label}"
            else:
                display_label = f"  {label}"
            options.append(Option(display_label, id=section_id))

        option_list = OptionList(*options, id="sidebar-list")
        return option_list

    def on_mount(self) -> None:
        self.theme = _load_theme()
        self.config = self._initial_config
        self._mount_all_sections()
        # Highlight first item in sidebar
        sidebar = self.query_one("#sidebar-list", OptionList)
        sidebar.highlighted = 0
        self._show_section(0)
        # If schema settings are empty, fetch in background so the TUI
        # starts immediately without blocking on the network.
        if not self._initial_config.available_settings:
            self._fetch_schema_background()

    def _fetch_schema_background(self) -> None:
        """Start a background worker to fetch and parse the JSON schema."""
        self.run_worker(self._schema_fetch_worker(), name="schema_fetch", exclusive=True)

    async def _schema_fetch_worker(self) -> list:
        """Async worker: fetch schema and return parsed SettingDef list."""
        from claude_tui_settings.models.schema import fetch_schema, parse_schema_properties
        from claude_tui_settings.models.discovery import discover_settings

        schema = await fetch_schema()
        if schema is None:
            return []
        raw_props = parse_schema_properties(schema)
        claude_repo = self._initial_config.claude_repo
        return discover_settings(raw_props, claude_repo)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle background worker completion to update settings reactively."""
        if event.worker.name != "schema_fetch":
            return
        if event.state == WorkerState.SUCCESS:
            setting_defs = event.worker.result
            if setting_defs and self.config is not None:
                self.config.available_settings = setting_defs
                self.mutate_reactive(BootstrapApp.config)
                # If the settings section is currently visible, refresh it
                if self.current_section == next(
                    (i for i, (sid, _, _) in enumerate(SECTIONS) if sid == "settings"),
                    -1,
                ):
                    self._show_section(self.current_section)

    def _build_section_widget(self, section_id: str) -> Widget:
        """Construct the widget for a given section id using current config."""
        assert self.config is not None
        match section_id:
            case "overview":
                return OverviewSection(self.config)
            case "permissions":
                return PermissionsSection(self.config)
            case "commands":
                return make_commands_section(self.config)
            case "agents":
                return make_agents_section(self.config)
            case "skills":
                return make_skills_section(self.config)
            case "plugins":
                return make_plugins_section(self.config)
            case "mcps":
                return make_mcps_section(self.config)
            case "hooks":
                return make_hooks_section(self.config)
            case "settings":
                return SettingsSection(self.config)
            case "instructions":
                return InstructionsSection(self.config)
            case "effective":
                return EffectiveSection(self.config)
            case _:
                return Static(f"Unknown section: {section_id}")

    def _mount_all_sections(self) -> None:
        """Pre-mount all section widgets inside content-pane, all hidden."""
        if self.config is None:
            return
        content_pane = self.query_one("#content-pane", Vertical)
        content_pane.remove_children()
        self._section_widgets = []
        for section_id, _label, _is_understand in SECTIONS:
            widget = self._build_section_widget(section_id)
            widget.display = False
            self._section_widgets.append(widget)
            content_pane.mount(widget)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle sidebar item selection."""
        # Find the section index from the option id
        for i, (section_id, _, _) in enumerate(SECTIONS):
            if event.option.id == section_id:
                self.current_section = i
                self._show_section(i)
                break

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Show section content when sidebar item is highlighted."""
        for i, (section_id, _, _) in enumerate(SECTIONS):
            if event.option.id == section_id:
                self.current_section = i
                self._show_section(i)
                break

    def _show_section(self, index: int) -> None:
        """Display the section at index by toggling CSS display on pre-mounted widgets."""
        if self.config is None:
            return
        if not self._section_widgets:
            return
        for i, widget in enumerate(self._section_widgets):
            widget.display = i == index

    def _update_sidebar_counts(self) -> None:
        """Update sidebar labels with pending change counts."""
        if self.config is None:
            return

        diff = self.config.pending_diff()
        sidebar = self.query_one("#sidebar-list", OptionList)

        domain_map = {
            "overview": None,
            "permissions": "profile",
            "commands": "commands",
            "agents": "agents",
            "skills": "skills",
            "plugins": "plugins",
            "mcps": "mcps",
            "hooks": "hooks",
            "settings": "settings",
            "instructions": None,
            "effective": None,
        }

        option_idx = 0
        for section_id, label, _ in SECTIONS:
            domain = domain_map.get(section_id)
            count = diff.count_for_domain(domain) if domain else 0

            display = label
            if count > 0:
                display = f"{label} ({count})"

            try:
                option = sidebar.get_option_at_index(option_idx)
                sidebar.replace_option_prompt(option.id, display)
            except Exception:
                pass
            option_idx += 1

    def watch_config(self, config: ConfigState | None) -> None:
        """React to config changes."""
        if config is not None:
            self._update_sidebar_counts()
            # Refresh overview if it's currently displayed
            try:
                overview = self.query_one(OverviewSection)
                overview.config = config
                overview.refresh_content()
            except Exception:
                pass

    def on_resource_toggled(self, event: ResourceToggled) -> None:
        """Handle resource checkbox toggle from any resource list."""
        if self.config is None:
            return

        match event.domain:
            case "commands":
                target = self.config.selected_commands
            case "agents":
                target = self.config.selected_agents
            case "skills":
                target = self.config.selected_skills
            case "plugins":
                target = self.config.selected_plugins
            case "mcps":
                target = self.config.selected_mcps
            case "hooks":
                target = self.config.selected_hooks
            case _:
                return

        if event.selected:
            target.add(event.name)
        else:
            target.discard(event.name)

        self.mutate_reactive(BootstrapApp.config)

    def on_setting_changed(self, event: SettingChanged) -> None:
        """Handle setting value change.

        SettingRow manages selected_settings directly and updates its
        own badge/action display.  We only need to trigger the reactive
        so the pending-diff counter refreshes.
        """
        if self.config is None:
            return
        self.mutate_reactive(BootstrapApp.config)

    def on_setting_reverted(self, event: SettingReverted) -> None:
        """Handle setting revert/unset from SettingRow action button."""
        if self.config is None:
            return
        self.mutate_reactive(BootstrapApp.config)

    def action_apply(self) -> None:
        """Apply configuration (Ctrl+S / F2)."""
        if self.config is None:
            return

        diff = self.config.pending_diff()
        if diff.is_empty:
            self.notify("No changes to apply.")
            return

        removals = diff.removals
        if removals:
            self.push_screen(ConfirmDialog(removals), self._on_confirm_result)
        else:
            self._do_apply()

    def action_revert(self) -> None:
        """Revert all changes back to filesystem state (Ctrl+R)."""
        if self.config is None:
            return

        diff = self.config.pending_diff()
        if diff.is_empty:
            self.notify("No changes to revert.")
            return

        self.push_screen(RevertDialog(), self._on_revert_result)

    def _on_revert_result(self, confirmed: bool) -> None:
        """Handle revert confirmation result."""
        if confirmed:
            self._do_revert()

    def _do_revert(self) -> None:
        """Actually revert configuration from disk."""
        if self.config is None:
            return

        try:
            from claude_tui_settings.models.audit import run_audit
            from claude_tui_settings.models.detection import (
                detect_existing_settings,
                detect_hooks,
                detect_mcps,
                detect_plugins,
                detect_profile,
                detect_resources,
            )
            from claude_tui_settings.models.instruction_files import discover_instruction_files
            from claude_tui_settings.models.resolver import resolve_effective_config

            project_dir = Path.cwd()
            settings_path = project_dir / ".claude" / "settings.json"
            claude_repo = self.config.claude_repo

            # Re-detect existing state
            self.config.existing_profile = detect_profile(
                settings_path, claude_repo / "profiles",
            )
            self.config.existing_commands, _ = detect_resources(
                project_dir / ".claude" / "commands", claude_repo, "commands",
            )
            self.config.existing_agents, _ = detect_resources(
                project_dir / ".claude" / "agents", claude_repo, "agents",
            )
            self.config.existing_skills, _ = detect_resources(
                project_dir / ".claude" / "skills", claude_repo, "skills",
            )
            self.config.existing_plugins = detect_plugins(settings_path)
            self.config.existing_mcps = detect_mcps(project_dir / ".mcp.json")
            self.config.existing_hooks = detect_hooks(settings_path, claude_repo)
            self.config.existing_settings = detect_existing_settings(settings_path)

            # Re-run audit, effective config, instruction files
            self.config.audit_warnings = run_audit(project_dir)
            self.config.effective = resolve_effective_config(
                project_dir, self.config.available_settings,
            )
            self.config.instruction_files = discover_instruction_files(project_dir)

            # Reset selections to match disk state
            self.config.selected_profile = (
                self.config.existing_profile or "standard"
            )
            self.config.selected_commands = set(self.config.existing_commands)
            self.config.selected_agents = set(self.config.existing_agents)
            self.config.selected_skills = set(self.config.existing_skills)
            self.config.selected_plugins = set(self.config.existing_plugins)
            self.config.selected_mcps = set(self.config.existing_mcps)
            self.config.selected_hooks = set(self.config.existing_hooks)
            self.config.selected_settings = dict(self.config.existing_settings)

            self.mutate_reactive(BootstrapApp.config)
            self._presets = list_presets(self.config.claude_repo)
            # Re-mount all sections so widgets reflect the refreshed config state
            self._mount_all_sections()
            self._show_section(self.current_section)
            self.notify("Changes reverted")
        except Exception as e:
            self.notify(f"Error reverting config: {e}", severity="error")

    def _on_confirm_result(self, confirmed: bool) -> None:
        """Handle removal confirmation result."""
        if confirmed:
            self._do_apply()

    def _do_apply(self) -> None:
        """Actually apply the configuration to disk."""
        if self.config is None:
            return

        try:
            validation_warnings = apply_config(self.config, Path.cwd())

            # Refresh existing state from disk
            from claude_tui_settings.models.detection import (
                detect_existing_settings,
                detect_hooks,
                detect_mcps,
                detect_plugins,
                detect_profile,
                detect_resources,
            )

            project_dir = Path.cwd()
            settings_path = project_dir / ".claude" / "settings.json"

            self.config.existing_profile = detect_profile(
                settings_path, self.config.claude_repo / "profiles",
            )
            self.config.existing_commands, _ = detect_resources(
                project_dir / ".claude" / "commands",
                self.config.claude_repo, "commands",
            )
            self.config.existing_agents, _ = detect_resources(
                project_dir / ".claude" / "agents",
                self.config.claude_repo, "agents",
            )
            self.config.existing_skills, _ = detect_resources(
                project_dir / ".claude" / "skills",
                self.config.claude_repo, "skills",
            )
            self.config.existing_plugins = detect_plugins(settings_path)
            self.config.existing_mcps = detect_mcps(project_dir / ".mcp.json")
            self.config.existing_hooks = detect_hooks(
                settings_path, self.config.claude_repo,
            )
            self.config.existing_settings = detect_existing_settings(settings_path)

            # Sync selections to match what was actually written (deduped)
            self.config.selected_settings = dict(self.config.existing_settings)

            self.mutate_reactive(BootstrapApp.config)

            # Remount so scope badges refresh after dedup
            self._mount_all_sections()
            self._show_section(self.current_section)

            if validation_warnings:
                for warning in validation_warnings:
                    self.notify(f"Setting reverted: {warning}", severity="warning")
                self.notify(
                    "Applied with warnings — some settings were reverted",
                    severity="warning",
                )
            else:
                self.notify("Configuration applied successfully!", severity="information")
        except Exception as e:
            self.notify(f"Error applying config: {e}", severity="error")

    # ── Preset save / load ──────────────────────────────────────────

    def action_save_preset(self) -> None:
        """Save the current configuration as a named preset (Ctrl+E)."""
        if self.config is None:
            return
        existing_slugs = {p.slug for p in self._presets}
        self.push_screen(SavePresetDialog(existing_slugs), self._on_save_preset_result)

    def _on_save_preset_result(self, result: tuple[str, str] | None) -> None:
        if result is None or self.config is None:
            return
        name, description = result
        try:
            save_preset(name, description, self.config)
            self._presets = list_presets(self.config.claude_repo)
            self.notify(f"Preset saved: {name}")
        except (OSError, ValueError) as e:
            self.notify(f"Error saving preset: {e}", severity="error")

    def action_load_preset(self) -> None:
        """Load a saved preset into the current configuration (Ctrl+L)."""
        if self.config is None:
            return
        if self.config.has_pending_changes:
            self.push_screen(
                ConfirmLoadDialog(),
                self._on_confirm_load_result,
            )
        else:
            self._show_load_dialog()

    def _on_confirm_load_result(self, confirmed: bool) -> None:
        if confirmed:
            self._show_load_dialog()

    def _show_load_dialog(self) -> None:
        if self.config is None:
            return
        self.push_screen(
            LoadPresetDialog(self._presets, self.config),
            self._on_load_preset_result,
        )

    def _on_load_preset_result(self, result: tuple | None) -> None:
        if result is None or self.config is None:
            return
        preset, skip_set = result
        load_preset_into_state(preset, self.config, skip_set)
        self.mutate_reactive(BootstrapApp.config)
        self._mount_all_sections()
        self._show_section(self.current_section)
        self.notify(f"Loaded preset: {preset.name}")

    # ── Quit ─────────────────────────────────────────────────────

    def action_quit_app(self) -> None:
        """Quit with unsaved changes check."""
        if self.config and self.config.has_pending_changes:
            self.push_screen(ExitDialog(), self._on_exit_result)
        else:
            _save_theme(self.theme)
            self.exit()

    def _on_exit_result(self, result: str) -> None:
        """Handle exit dialog result."""
        match result:
            case "save":
                self._do_apply()
                _save_theme(self.theme)
                self.exit()
            case "discard":
                _save_theme(self.theme)
                self.exit()
            case "cancel":
                pass  # Stay in app

    def action_jump(self, index: int) -> None:
        """Jump to a section by index (Alt+N)."""
        if 0 <= index < len(SECTIONS):
            sidebar = self.query_one("#sidebar-list", OptionList)
            sidebar.highlighted = index
            self.current_section = index
            self._show_section(index)
