#!/usr/bin/env bash
set -euo pipefail
echo "=== Running bandit ==="
bandit -r packages/settings/src/ packages/usage/src/ -ll
echo "=== Running semgrep ==="
semgrep --config auto packages/settings/src/ packages/usage/src/
echo "=== Checking for secrets ==="
grep -rn "api_key\|token\|secret\|password\|credential\|API_KEY" packages/ || echo "No secrets found"
echo "=== Checking for personal paths ==="
grep -rn "/Users/\|/home/.*/" packages/ || echo "No personal paths found"
echo "=== Audit complete ==="
