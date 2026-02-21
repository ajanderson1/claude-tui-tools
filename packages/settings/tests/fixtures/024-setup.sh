#!/bin/bash
# Setup fixture for 024-settings-panel-effective tests.
# Seeds user-scope and project-scope settings/resources, backing up originals.
set -euo pipefail

TEST_AREA="/tmp/test_area"
BACKUP_SUFFIX=".test-024-bak"

# ── Guard: check for stale backups ──────────────────────────────────
if [ -f "$HOME/.claude/settings.json${BACKUP_SUFFIX}" ]; then
  echo "WARNING: Stale backup found at ~/.claude/settings.json${BACKUP_SUFFIX}"
  echo "A previous test run may not have cleaned up. Restoring first..."
  mv "$HOME/.claude/settings.json${BACKUP_SUFFIX}" "$HOME/.claude/settings.json"
fi

# ── Back up existing user settings ──────────────────────────────────
[ -f "$HOME/.claude/settings.json" ] && \
  cp "$HOME/.claude/settings.json" "$HOME/.claude/settings.json${BACKUP_SUFFIX}"

# ── Seed user-scope settings ────────────────────────────────────────
cat > "$HOME/.claude/settings.json" << 'EOF'
{
  "respectGitignore": false,
  "effortLevel": "low"
}
EOF

# ── Seed user-scope resources ───────────────────────────────────────
mkdir -p "$HOME/.claude/commands" "$HOME/.claude/skills/test-user-skill"

cat > "$HOME/.claude/commands/test-user-cmd.md" << 'EOF'
# Test User Command

A test command seeded for TUI integration testing (024).
EOF

cat > "$HOME/.claude/skills/test-user-skill/SKILL.md" << 'EOF'
# Test User Skill

A test skill seeded for TUI integration testing (024).
EOF

# ── Seed project-scope settings ─────────────────────────────────────
mkdir -p "$TEST_AREA/.claude/commands"

cat > "$TEST_AREA/.claude/settings.json" << 'EOF'
{
  "permissions": {
    "allow": [],
    "deny": [],
    "ask": []
  },
  "effortLevel": "high",
  "outputStyle": "concise"
}
EOF

cat > "$TEST_AREA/.claude/commands/test-project-cmd.md" << 'EOF'
# Test Project Command

A test command seeded for TUI integration testing (024).
EOF

echo "✓ Setup complete."
echo "  User scope:    ~/.claude/settings.json  (respectGitignore=false, effortLevel=low)"
echo "  Project scope: $TEST_AREA/.claude/settings.json  (effortLevel=high, outputStyle=concise)"
echo "  User commands: ~/.claude/commands/test-user-cmd.md"
echo "  User skills:   ~/.claude/skills/test-user-skill/SKILL.md"
echo "  Proj commands: $TEST_AREA/.claude/commands/test-project-cmd.md"
