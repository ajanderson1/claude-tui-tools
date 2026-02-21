# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Monorepo containing two independent TUI companion tools for Claude Code, built with Python and managed via Hatch. Both packages live under `packages/` and can be installed independently or together.

- **claude-tui-settings** (Python >=3.10) — Textual TUI dashboard for managing Claude Code's multi-scope project settings. Discovers resources from a central `$CLAUDE_REPO` directory and creates symlinks into project `.claude/` directories.
- **claude-tui-usage** (Python >=3.9) — Visual pace-aware CLI monitor for Claude Code rate limits. Uses `expect` to capture `claude /usage` output and displays progress bars with pace analysis.

## Build & Install

```bash
# Install both packages for local development
pip install -e ".[all]"

# Install individually
pip install -e packages/settings
pip install -e packages/usage
```

## Running Tests

```bash
# Settings tests (from repo root or packages/settings/)
pytest packages/settings/tests/ -v

# Usage tests (golden fixture-based)
pytest packages/usage/tests/ -v

# Single test file
pytest packages/settings/tests/test_models/test_persistence.py -v

# Single test
pytest packages/settings/tests/test_models/test_persistence.py::test_name -v
```

Settings tests use `asyncio_mode = "auto"`. Usage tests use `addopts = "-v --tb=short"`.

## Environment Requirements

- `$CLAUDE_REPO` env var must point to a Claude Code resource repository (profiles, commands, agents, skills, plugins, mcps, hooks directories)
- `expect` binary required for claude-tui-usage (`brew install expect` on macOS)

## Architecture

### claude-tui-settings

Three-phase pipeline: **Discovery → Detection → Persistence**

1. **Discovery** (`models/discovery.py`) — Scans `$CLAUDE_REPO` for available resources (profiles, commands, agents, skills, plugins, MCPs, hooks, settings). Settings definitions come from the JSON schema at schemastore.org, cached locally for 7 days (`models/schema.py`).

2. **Detection** (`models/detection.py`) — Reads the current project's `.claude/settings.json`, `.mcp.json`, and `.claude/{commands,agents,skills}/` symlinks to determine what's already configured.

3. **Persistence** (`models/persistence.py`) — Applies changes via atomic staging: writes to `.claude/.tmp/`, validates, then `os.replace()` into place. Also updates sentinel-bounded sections in `CLAUDE.md` and `.gitignore`.

**Key data flow:** `ConfigState` (`models/config.py`) is the central dataclass holding all state — available resources, existing on-disk state, and user selections. The `pending_diff()` method computes what would change. The TUI (`app.py`) uses Textual reactives on `ConfigState` to drive UI updates.

**Deduplication logic:** Resources present at user scope (`~/.claude/`) are excluded from project-scope writes to avoid duplication. Settings matching user-scope or profile-base values are also skipped.

**TUI structure** (`app.py`): Sidebar navigator layout with 11 sections. All section widgets are pre-mounted and toggled via CSS display. Background worker fetches the JSON schema if not cached, updating the Settings section reactively. Keybindings: Ctrl+S save, Ctrl+R revert, Ctrl+E export preset, Ctrl+L load preset, Alt+N jump to section N.

### claude-tui-usage

Single-file module (`monitor.py`) with layered architecture:

- **Capture** — Uses `expect` scripts to spawn `claude /usage`, capture terminal output, and clean up processes via `pkill -f`
- **Parse** — Cascade of extraction strategies (regex → structural → number-based) with ANSI stripping and fuzzy date parsing via `python-dateutil`
- **Validate** — Ensures percentages are 0-100, reset times are in future and within window bounds
- **Display** — Color-coded progress bars with pace analysis (usage % vs time elapsed %)

Tests use golden fixtures: `.txt` input files paired with `.expected.json` files in `tests/fixtures/golden/`.
