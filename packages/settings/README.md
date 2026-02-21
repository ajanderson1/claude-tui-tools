# claude-tui-settings

TUI dashboard for managing Claude Code's multi-scope project settings.

Claude Code reads settings from 5 different scopes (enterprise, user, project, `.claude/settings.json`, `CLAUDE.md`) with complex precedence rules. This tool shows you what's active, where it came from, and lets you change it — all from one place.

## Install

```bash
pip install git+https://github.com/ajanderson1/claude-tui-tools.git#subdirectory=packages/settings
```

Requires Python >= 3.10 and the `$CLAUDE_REPO` environment variable:

```bash
export CLAUDE_REPO=/path/to/your/claude-repo
```

## Usage

```bash
claude-tui-settings              # Launch interactive TUI dashboard
claude-tui-settings --summary    # Condensed text output (effective config)
claude-tui-settings --report     # Full scope audit report
claude-tui-settings --effective  # Detailed resolved configuration
claude-tui-settings --version    # Show version
claude-tui-settings --help       # Show help
```

### Interactive TUI

The dashboard provides tabbed navigation across:

- **Overview** — profile selection and quick status
- **Commands / Agents / Skills** — browse and toggle resources from your `$CLAUDE_REPO`
- **Plugins / MCPs / Hooks** — manage integrations
- **Settings** — view and edit individual settings with scope indicators (PROJECT / USER / UNSET)
- **Effective** — see the final resolved config after all scope merging
- **Audit** — warnings about duplicate resources, missing files, and scope conflicts

Changes are staged and previewed before writing to `.claude/settings.json`.

### CLI Reports

**`--summary`** prints a compact overview of the effective configuration — useful for quick checks or piping to other tools.

**`--report`** generates a full audit showing every scope, what each contributes, and any warnings.

**`--effective`** shows the detailed resolved value for each setting with its source scope.

## Configuration Scopes

Claude Code reads settings from these scopes (highest priority first):

1. **Enterprise** — organization-wide policies
2. **Project** — `.claude/settings.json` in the project directory
3. **User** — `~/.claude/settings.json`
4. **CLAUDE.md** — instruction files at project and user levels
5. **Defaults** — built-in Claude Code defaults

The TUI shows which scope each setting is coming from and lets you override at the project level.

## License

MIT
