#!/bin/bash
# Teardown fixture for 024-settings-panel-effective tests.
# Restores user-scope settings from backup and removes test resources.
set -euo pipefail

TEST_AREA="/tmp/test_area"
BACKUP_SUFFIX=".test-024-bak"

# ── Restore user settings ───────────────────────────────────────────
if [ -f "$HOME/.claude/settings.json${BACKUP_SUFFIX}" ]; then
  mv "$HOME/.claude/settings.json${BACKUP_SUFFIX}" "$HOME/.claude/settings.json"
  echo "✓ Restored ~/.claude/settings.json from backup"
else
  rm -f "$HOME/.claude/settings.json"
  echo "✓ Removed ~/.claude/settings.json (no backup existed)"
fi

# ── Remove test user-scope resources ────────────────────────────────
rm -f "$HOME/.claude/commands/test-user-cmd.md"
rm -rf "$HOME/.claude/skills/test-user-skill"
echo "✓ Removed test user-scope resources"

# ── Clean test_area project-scope fixtures ──────────────────────────
rm -f "$TEST_AREA/.claude/commands/test-project-cmd.md"
# Don't remove settings.json — may have been modified by test; leave for inspection
echo "✓ Removed test project-scope command"

echo "Teardown complete."
