# Codebase Map — Issue #1

## Project Structure (Monorepo)
- `packages/settings/` — claude-tui-settings (Textual TUI app)
- `packages/usage/` — claude-tui-usage (CLI monitor, NOT a Textual app)

## Keybinding Locations
- **Primary**: `packages/settings/src/claude_tui_settings/app.py` lines 85-103
- Import: `from textual.binding import Binding` (line 9)
- Current quit bindings: `q` (line 91) and `ctrl+q` (line 92) → `action_quit_app`
- Quit handler: `action_quit_app()` at line 579

## Usage App
- `packages/usage/src/claude_tui_usage/monitor.py` — CLI tool, no Textual/TUI, no Binding system
- Does NOT have keybindings in the Textual sense

## Test Framework
- pytest with Textual Pilot (settings)
- pytest with fixtures (usage)
- Test files: `packages/settings/tests/test_app.py`, `packages/usage/tests/test_parser.py`

## Key Risk
- `ctrl+x` may conflict with Textual's built-in "cut" in Input widgets (e.g., SavePresetDialog)
