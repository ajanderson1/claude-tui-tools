#!/bin/bash
# Diagnostic: capture screen content at key positions in the Settings panel
set -euo pipefail

SESSION="tui-024-dump"
APP="cd /tmp/test_area && python -m claude_tui_settings"

# Clean up any existing session
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create session and launch app
tmux new-session -d -s "$SESSION" -x 80 -y 24
tmux send-keys -t "$SESSION" "$APP" Enter
echo "Waiting 8s for app startup..."
sleep 8

# Navigate to Settings (8 Downs in sidebar)
for i in $(seq 1 8); do tmux send-keys -t "$SESSION" Down; done
sleep 0.5

echo "=== AFTER SIDEBAR NAV TO SETTINGS ==="
tmux capture-pane -t "$SESSION" -p
echo "=== END ==="
echo ""

# Tab to content
tmux send-keys -t "$SESSION" Tab
sleep 5

echo "=== AFTER TAB TO CONTENT (initial view) ==="
tmux capture-pane -t "$SESSION" -p
echo "=== END ==="
echo ""

# Navigate down in 5-step increments, capturing each
for batch in 1 2 3 4 5 6 7 8; do
  for i in $(seq 1 5); do tmux send-keys -t "$SESSION" Down; done
  sleep 0.3
  echo "=== AFTER ${batch}x5 = $((batch * 5)) Downs from initial ==="
  tmux capture-pane -t "$SESSION" -p
  echo "=== END ==="
  echo ""
done

# Quit
tmux send-keys -t "$SESSION" q
sleep 1
tmux kill-session -t "$SESSION" 2>/dev/null || true
echo "Done."
