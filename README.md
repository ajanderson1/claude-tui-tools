
```
#             ██████╗██╗      █████╗ ██╗   ██╗██████╗ ███████╗                #
#            ██╔════╝██║     ██╔══██╗██║   ██║██╔══██╗██╔════╝                #
#            ██║     ██║     ███████║██║   ██║██║  ██║█████╗                  #
#            ██║     ██║     ██╔══██║██║   ██║██║  ██║██╔══╝                  #
#            ╚██████╗███████╗██║  ██║╚██████╔╝██████╔╝███████╗                #
#             ╚═════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝                #
#                                                                             #
#    ████████╗██╗   ██╗██╗    ████████╗ ██████╗  ██████╗ ██╗     ███████╗     #
#    ╚══██╔══╝██║   ██║██║    ╚══██╔══╝██╔═══██╗██╔═══██╗██║     ██╔════╝     #
#       ██║   ██║   ██║██║       ██║   ██║   ██║██║   ██║██║     ███████╗     #
#       ██║   ██║   ██║██║       ██║   ██║   ██║██║   ██║██║     ╚════██║     #
#       ██║   ╚██████╔╝██║       ██║   ╚██████╔╝╚██████╔╝███████╗███████║     #
#       ╚═╝    ╚═════╝ ╚═╝       ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝╚══════╝     #
#                                                                             #
```

[![CI](https://github.com/ajanderson1/claude-tui-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/ajanderson1/claude-tui-tools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/ajanderson1/claude-tui-tools)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](https://www.python.org/)
[![Release](https://img.shields.io/github/v/release/ajanderson1/claude-tui-tools)](https://github.com/ajanderson1/claude-tui-tools/releases)

**TUI companion tool for Claude Code — settings management.**

Addressing small pain points for solo developers/small teams using Claude Code CLI.

---

## Why

Claude Code settings are scattered across 5 scopes with confusing precedence — where is that setting actually coming from? **claude-tui-settings** is a Textual TUI dashboard that gives you clarity and centralized control over Claude Code's multi-scope project settings.

> I run it ahead of initialising a new project to quickly sync custom commands/skills/settings, or run `claude-tui-settings --report && claude` to recap what settings/plugins/MCPs will be available in the resulting Claude instance.

![claude-tui-settings screenshot](assets/settings-screenshot.png)

---

## Requirements

- Python **≥ 3.10**
- [Textual](https://textual.textualize.io/) and `httpx` (installed automatically)
- A local **Claude resource repo** pointed to by the `$CLAUDE_REPO` environment variable

### The `$CLAUDE_REPO` model

The TUI points at a local directory that serves as a central repo for all your Claude resources (commands, skills, agents, plugins, MCPs, settings). Each project then gets **symlinks** into this repo rather than its own copies.

Why? I constantly refine my custom commands/skills, and the round-trip of *update → commit → push → pull back into project → verify it updated* is painful. Symlinking cuts out that lead time while things are still changing fast.

```bash
export CLAUDE_REPO=/path/to/your/claude-repo
```

---

## Quick Start

Install:

```bash
pip install git+https://github.com/ajanderson1/claude-tui-tools.git#subdirectory=packages/settings
```

Or for local development:

```bash
git clone https://github.com/ajanderson1/claude-tui-tools.git
cd claude-tui-tools
pip install -e ".[all]"
```

Then run:

```bash
claude-tui-settings          # Launch the settings TUI
```

---

## Detailed Docs

- [claude-tui-settings](packages/settings/README.md) — all CLI flags, configuration scopes, TUI navigation

## License

MIT — see [LICENSE](LICENSE).
