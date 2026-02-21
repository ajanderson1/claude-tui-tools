# claude-tui-usage

Visual pace-aware usage monitor for Claude Code rate limits.

Raw usage percentages don't tell you if you're burning too fast. This tool compares your consumption pace against elapsed time in the billing window, so you know whether to ease off or keep going.

## Install

```bash
pip install git+https://github.com/ajanderson1/claude-tui-tools.git#subdirectory=packages/usage
```

Requires Python >= 3.9 and the `expect` binary:

```bash
# macOS
brew install expect

# Linux
apt-get install expect
```

## Usage

```bash
claude-tui-usage              # Single check
claude-tui-usage --loop       # Continuous monitoring (default: 5 min interval)
claude-tui-usage --interval 60 --loop   # Custom interval (seconds)
claude-tui-usage --raw        # Show raw captured output from Claude CLI
claude-tui-usage --quiet      # Suppress output, exit code only
claude-tui-usage --debug      # Show raw reset time strings
claude-tui-usage --version    # Show version
```

### Output

```
Usage Analysis - Friday February 21 at 14:30 (took 3.21s)

  Weekly Usage (168h)
  Time:   ████████████████░░░░░░░░░░░░░░░░░░░░░░░░  40% time
  Usage:  ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  23% used
  Status: Below pace (17pp) | Resets in 4d 2h

  ---

  Session Usage (5h)
  Time:   ██████████████████████████████░░░░░░░░░░░░  72% time
  Usage:  ██████████████████████████████████████████  42% used
  Status: Below pace (30pp) | Resets in 1h 24m
```

- **Green** = below pace (you have headroom)
- **Red** = above pace (consider slowing down)
- **pp** = percentage points difference between usage and elapsed time

### Loop Mode

`--loop` refreshes automatically. Press `Ctrl+C` to exit. Only one instance can run at a time (enforced via lock file at `~/.cache/claude-tui-usage/usage.lock`).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Parse or validation failure |
| 2 | Lock acquisition failed (another instance running) |
| 3 | Capture failure (Claude CLI not responding) |

## Known Behaviors

- Uses `pkill -f` to clean up spawned `claude /usage` processes after each capture. This prevents orphaned processes from accumulating.
- Requires `expect` for terminal automation — the Claude CLI's `/usage` command outputs to a TTY, which can't be captured with simple subprocess pipes.

## License

MIT
