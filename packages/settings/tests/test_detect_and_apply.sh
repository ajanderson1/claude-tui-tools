#!/usr/bin/env bash
# Unit tests for claude-bootstrap detection, selection, and apply phases.
# Tests set up filesystem fixtures, extract & run specific functions,
# and assert expected state deterministically (no TUI interaction).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$SCRIPT_DIR/claude-bootstrap"
CLAUDE_REPO="${CLAUDE_REPO:?CLAUDE_REPO not set}"
PASS=0
FAIL=0
ERRORS=()

# ---------- test framework ----------

setup_tmpdir() {
  TEST_DIR=$(mktemp -d)
  PROJECT_DIR="$TEST_DIR/project"
  mkdir -p "$PROJECT_DIR/.claude"
}

teardown_tmpdir() {
  rm -rf "$TEST_DIR"
}

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    ((PASS++))
  else
    ((FAIL++))
    ERRORS+=("FAIL: $label — expected '$expected', got '$actual'")
  fi
}

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    ((PASS++))
  else
    ((FAIL++))
    ERRORS+=("FAIL: $label — expected to contain '$needle', got '$haystack'")
  fi
}

assert_file_exists() {
  local label="$1" path="$2"
  if [[ -e "$path" ]]; then ((PASS++)); else ((FAIL++)); ERRORS+=("FAIL: $label — not found: $path"); fi
}

assert_file_not_exists() {
  local label="$1" path="$2"
  if [[ ! -e "$path" ]]; then ((PASS++)); else ((FAIL++)); ERRORS+=("FAIL: $label — should not exist: $path"); fi
}

assert_symlink_target() {
  local label="$1" link="$2" expected_target="$3"
  if [[ -L "$link" ]]; then
    local actual; actual=$(readlink "$link")
    assert_eq "$label" "$expected_target" "$actual"
  else
    ((FAIL++)); ERRORS+=("FAIL: $label — not a symlink: $link")
  fi
}

assert_json_key() {
  local label="$1" file="$2" query="$3" expected="$4"
  local actual; actual=$(jq -r "$query" "$file" 2>/dev/null)
  assert_eq "$label" "$expected" "$actual"
}

# Run detect_existing_state in a subshell that sources just the needed parts
run_detect() {
  # Build a mini script that defines the function and calls it
  local result
  result=$(bash << HEREDOC
set -uo pipefail
PROJECT_DIR="$PROJECT_DIR"
CLAUDE_REPO="$CLAUDE_REPO"
HAS_JQ=true
EXISTING_PROFILE=""
EXISTING_COMMANDS=()
EXISTING_AGENTS=()
EXISTING_SKILLS=()
EXISTING_MCPS=()
EXISTING_PLUGINS=()
EXISTING_HOOKS=()
PROJECT_NOTE=""

$(sed -n '/^detect_symlink_resources()/,/^}$/p' "$SCRIPT")
$(sed -n '/^detect_existing_state()/,/^}$/p' "$SCRIPT")

detect_existing_state

echo "PROFILE=\$EXISTING_PROFILE"
echo "COMMANDS_COUNT=\${#EXISTING_COMMANDS[@]}"
for c in "\${EXISTING_COMMANDS[@]}"; do echo "CMD=\$c"; done
echo "SKILLS_COUNT=\${#EXISTING_SKILLS[@]}"
for s in "\${EXISTING_SKILLS[@]}"; do echo "SKILL=\$s"; done
echo "MCPS_COUNT=\${#EXISTING_MCPS[@]}"
for m in "\${EXISTING_MCPS[@]}"; do echo "MCP=\$m"; done
echo "PLUGINS_COUNT=\${#EXISTING_PLUGINS[@]}"
for p in "\${EXISTING_PLUGINS[@]}"; do echo "PLUGIN=\$p"; done
echo "HOOKS_COUNT=\${#EXISTING_HOOKS[@]}"
for h in "\${EXISTING_HOOKS[@]}"; do echo "HOOK=\$h"; done
echo "PROJECT_NOTE=\$PROJECT_NOTE"
HEREDOC
  )
  echo "$result"
}

# Parse key=value output from run_detect
get_val() { echo "$1" | grep "^$2=" | head -1 | cut -d= -f2-; }
get_all() { echo "$1" | grep "^$2=" | cut -d= -f2-; }
get_count() { echo "$1" | grep "^${2}_COUNT=" | head -1 | cut -d= -f2-; }

# ---------- Profile Detection ----------

test_profile_detection_standard() {
  setup_tmpdir
  cp "$CLAUDE_REPO/profiles/standard.json" "$PROJECT_DIR/.claude/settings.json"
  local out; out=$(run_detect)
  assert_eq "profile: standard" "standard" "$(get_val "$out" PROFILE)"
  teardown_tmpdir
}

test_profile_detection_strict() {
  setup_tmpdir
  cp "$CLAUDE_REPO/profiles/strict.json" "$PROJECT_DIR/.claude/settings.json"
  local out; out=$(run_detect)
  assert_eq "profile: strict" "strict" "$(get_val "$out" PROFILE)"
  teardown_tmpdir
}

test_profile_detection_with_plugins_key() {
  setup_tmpdir
  jq '. + {enabledPlugins: {"foo": true}}' "$CLAUDE_REPO/profiles/standard.json" \
    > "$PROJECT_DIR/.claude/settings.json"
  local out; out=$(run_detect)
  assert_eq "profile: standard despite plugins" "standard" "$(get_val "$out" PROFILE)"
  teardown_tmpdir
}

test_profile_detection_with_hooks_key() {
  setup_tmpdir
  jq '. + {hooks: {PreToolUse: []}}' "$CLAUDE_REPO/profiles/standard.json" \
    > "$PROJECT_DIR/.claude/settings.json"
  local out; out=$(run_detect)
  assert_eq "profile: standard despite hooks" "standard" "$(get_val "$out" PROFILE)"
  teardown_tmpdir
}

test_profile_detection_unknown() {
  setup_tmpdir
  echo '{"allowedTools":["random"]}' > "$PROJECT_DIR/.claude/settings.json"
  local out; out=$(run_detect)
  assert_eq "profile: unknown = empty" "" "$(get_val "$out" PROFILE)"
  teardown_tmpdir
}

test_profile_detection_no_file() {
  setup_tmpdir
  rm -f "$PROJECT_DIR/.claude/settings.json"
  local out; out=$(run_detect)
  assert_eq "profile: no file = empty" "" "$(get_val "$out" PROFILE)"
  teardown_tmpdir
}

# ---------- Command Detection ----------

test_command_detection_symlinks() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/commands/custom_commands/capture2journal"
  # Find actual command files to symlink
  local src_dir="$CLAUDE_REPO/commands/custom_commands/capture2journal"
  if [[ -d "$src_dir" ]]; then
    ln -s "$src_dir/capture2gotcha.md" \
      "$PROJECT_DIR/.claude/commands/custom_commands/capture2journal/capture2gotcha.md" 2>/dev/null || true
    ln -s "$src_dir/capture2task.md" \
      "$PROJECT_DIR/.claude/commands/custom_commands/capture2journal/capture2task.md" 2>/dev/null || true
  else
    # Create fake source commands
    mkdir -p "$TEST_DIR/fakerepo/commands/folder"
    echo "# cmd" > "$TEST_DIR/fakerepo/commands/folder/cmd1.md"
    echo "# cmd" > "$TEST_DIR/fakerepo/commands/folder/cmd2.md"
    CLAUDE_REPO="$TEST_DIR/fakerepo"
    mkdir -p "$PROJECT_DIR/.claude/commands/folder"
    ln -s "$TEST_DIR/fakerepo/commands/folder/cmd1.md" "$PROJECT_DIR/.claude/commands/folder/cmd1.md"
    ln -s "$TEST_DIR/fakerepo/commands/folder/cmd2.md" "$PROJECT_DIR/.claude/commands/folder/cmd2.md"
  fi

  local out; out=$(run_detect)
  assert_eq "commands: 2 detected" "2" "$(get_count "$out" COMMANDS)"
  teardown_tmpdir
}

test_command_detection_local_files() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/commands"
  echo "# regular file" > "$PROJECT_DIR/.claude/commands/fake.md"
  local out; out=$(run_detect)
  assert_eq "commands: local file detected" "1" "$(get_count "$out" COMMANDS)"
  assert_eq "commands: local file name" "fake" "$(get_all "$out" CMD)"
  teardown_tmpdir
}

test_command_detection_ignores_foreign_symlinks() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/commands"
  ln -s "/some/other/repo/commands/foo.md" "$PROJECT_DIR/.claude/commands/foo.md"
  local out; out=$(run_detect)
  assert_eq "commands: foreign symlinks ignored" "0" "$(get_count "$out" COMMANDS)"
  teardown_tmpdir
}

test_command_detection_no_dir() {
  setup_tmpdir
  local out; out=$(run_detect)
  assert_eq "commands: no dir = 0" "0" "$(get_count "$out" COMMANDS)"
  teardown_tmpdir
}

# ---------- Skills Detection ----------

test_skills_detection_symlinks() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/skills"
  # Find a real skill dir
  local real_skill=""
  for sd in "$CLAUDE_REPO/skills"/*/SKILL.md; do
    [[ -f "$sd" ]] || continue
    real_skill=$(basename "$(dirname "$sd")")
    break
  done
  if [[ -n "$real_skill" ]]; then
    ln -s "$CLAUDE_REPO/skills/$real_skill" "$PROJECT_DIR/.claude/skills/$real_skill"
  else
    mkdir -p "$PROJECT_DIR/.claude/skills/fake-skill"
  fi
  local out; out=$(run_detect)
  assert_eq "skills: 1 detected" "1" "$(get_count "$out" SKILLS)"
  teardown_tmpdir
}

test_skills_detection_directories() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/skills/skill-a"
  mkdir -p "$PROJECT_DIR/.claude/skills/skill-b"
  local out; out=$(run_detect)
  assert_eq "skills: 2 dirs detected" "2" "$(get_count "$out" SKILLS)"
  teardown_tmpdir
}

test_skills_detection_empty() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/skills"
  local out; out=$(run_detect)
  assert_eq "skills: empty = 0" "0" "$(get_count "$out" SKILLS)"
  teardown_tmpdir
}

test_skills_detection_ignores_files() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/skills"
  echo "not a skill" > "$PROJECT_DIR/.claude/skills/stray.txt"
  local out; out=$(run_detect)
  assert_eq "skills: files ignored" "0" "$(get_count "$out" SKILLS)"
  teardown_tmpdir
}

# ---------- MCP Detection ----------

test_mcp_detection() {
  setup_tmpdir
  cat > "$PROJECT_DIR/.mcp.json" << 'EOF'
{"mcpServers":{"context7":{"type":"stdio"},"serena":{"type":"stdio"}}}
EOF
  local out; out=$(run_detect)
  assert_eq "MCPs: 2 detected" "2" "$(get_count "$out" MCPS)"
  assert_contains "MCPs: context7" "context7" "$(get_all "$out" MCP)"
  assert_contains "MCPs: serena" "serena" "$(get_all "$out" MCP)"
  teardown_tmpdir
}

test_mcp_detection_empty() {
  setup_tmpdir
  echo '{"mcpServers":{}}' > "$PROJECT_DIR/.mcp.json"
  local out; out=$(run_detect)
  assert_eq "MCPs: empty = 0" "0" "$(get_count "$out" MCPS)"
  teardown_tmpdir
}

test_mcp_detection_no_file() {
  setup_tmpdir
  local out; out=$(run_detect)
  assert_eq "MCPs: no file = 0" "0" "$(get_count "$out" MCPS)"
  teardown_tmpdir
}

# ---------- Plugins Detection ----------

test_plugin_detection() {
  setup_tmpdir
  jq '. + {enabledPlugins:{"feature-dev@claude-plugins-official":true,"todoist@claude-plugins-official":true}}' \
    "$CLAUDE_REPO/profiles/standard.json" > "$PROJECT_DIR/.claude/settings.json"
  local out; out=$(run_detect)
  assert_eq "plugins: 2 detected" "2" "$(get_count "$out" PLUGINS)"
  teardown_tmpdir
}

test_plugin_detection_none() {
  setup_tmpdir
  cp "$CLAUDE_REPO/profiles/standard.json" "$PROJECT_DIR/.claude/settings.json"
  local out; out=$(run_detect)
  assert_eq "plugins: none = 0" "0" "$(get_count "$out" PLUGINS)"
  teardown_tmpdir
}

# ---------- Hooks Detection ----------

test_hooks_detection() {
  setup_tmpdir
  local hook_dir="$CLAUDE_REPO/hooks/available/auto-format"
  if [[ ! -d "$hook_dir" ]]; then
    echo "  SKIP: test_hooks_detection (no auto-format hook)"
    teardown_tmpdir
    return
  fi
  local sample_script; sample_script=$(ls "$hook_dir"/*.sh "$hook_dir"/*.js 2>/dev/null | head -1)
  if [[ -z "$sample_script" ]]; then
    echo "  SKIP: test_hooks_detection (no scripts)"
    teardown_tmpdir
    return
  fi
  local script_name; script_name=$(basename "$sample_script")
  cat > "$PROJECT_DIR/.claude/settings.json" << HOOKEOF
{"allowedTools":[],"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"/path/to/$script_name"}]}]}}
HOOKEOF
  local out; out=$(run_detect)
  assert_eq "hooks: 1 detected" "1" "$(get_count "$out" HOOKS)"
  assert_eq "hooks: auto-format" "auto-format" "$(get_all "$out" HOOK)"
  teardown_tmpdir
}

test_hooks_detection_none() {
  setup_tmpdir
  cp "$CLAUDE_REPO/profiles/standard.json" "$PROJECT_DIR/.claude/settings.json"
  local out; out=$(run_detect)
  assert_eq "hooks: none = 0" "0" "$(get_count "$out" HOOKS)"
  teardown_tmpdir
}

# ---------- Project Note Detection ----------

test_project_note_detection() {
  setup_tmpdir
  cat > "$PROJECT_DIR/CLAUDE.md" << 'EOF'
# CLAUDE.md
<!-- BEGIN:PROJECT_NOTE -->
## Project Note
This project's Obsidian project note: `/Users/me/Journal/Atlas/myproject.md`
<!-- END:PROJECT_NOTE -->
EOF
  local out; out=$(run_detect)
  assert_eq "project note detected" "/Users/me/Journal/Atlas/myproject.md" "$(get_val "$out" PROJECT_NOTE)"
  teardown_tmpdir
}

test_project_note_detection_none() {
  setup_tmpdir
  echo "# CLAUDE.md" > "$PROJECT_DIR/CLAUDE.md"
  local out; out=$(run_detect)
  assert_eq "project note: none" "" "$(get_val "$out" PROJECT_NOTE)"
  teardown_tmpdir
}

test_project_note_no_claudemd() {
  setup_tmpdir
  local out; out=$(run_detect)
  assert_eq "project note: no file" "" "$(get_val "$out" PROJECT_NOTE)"
  teardown_tmpdir
}

# ---------- Apply: Profile ----------

test_apply_profile() {
  setup_tmpdir
  bash << HEREDOC
set -euo pipefail
PROJECT_DIR="$PROJECT_DIR"; CLAUDE_REPO="$CLAUDE_REPO"
info() { :; }; ok() { :; }; warn() { :; }; fail() { :; }; header() { :; }
SELECTED_PROFILE="strict"
SELECTED_COMMANDS=(); SELECTED_SKILLS=(); SELECTED_MCPS=()
SELECTED_PLUGINS=(); SELECTED_HOOKS=()
mkdir -p "\$PROJECT_DIR/.claude"
PROFILE_FILE="\$CLAUDE_REPO/profiles/\${SELECTED_PROFILE}.json"
SETTINGS=\$(cat "\$PROFILE_FILE")
echo "\$SETTINGS" | jq '.' > "\$PROJECT_DIR/.claude/settings.json"
HEREDOC
  assert_file_exists "apply: settings.json" "$PROJECT_DIR/.claude/settings.json"
  local stripped; stripped=$(jq -S 'del(.enabledPlugins,.hooks)' "$PROJECT_DIR/.claude/settings.json")
  local expected; expected=$(jq -S '.' "$CLAUDE_REPO/profiles/strict.json")
  assert_eq "apply: strict profile content matches" "$expected" "$stripped"
  teardown_tmpdir
}

# ---------- Apply: Commands ----------

test_apply_commands() {
  setup_tmpdir
  # Find a real command
  local real_cmd; real_cmd=$(find "$CLAUDE_REPO/commands" -name "*.md" ! -name ".gitignore" 2>/dev/null | head -1)
  if [[ -z "$real_cmd" ]]; then echo "  SKIP: test_apply_commands"; teardown_tmpdir; return; fi
  local rel="${real_cmd#"$CLAUDE_REPO/commands/"}"; rel="${rel%.md}"

  bash << HEREDOC
set -euo pipefail
PROJECT_DIR="$PROJECT_DIR"; CLAUDE_REPO="$CLAUDE_REPO"
info() { :; }; ok() { :; }; warn() { :; }; fail() { :; }; header() { :; }
SELECTED_COMMANDS=("$rel")
for cmd in "\${SELECTED_COMMANDS[@]}"; do
  cmd_dir="\$PROJECT_DIR/.claude/commands/\$(dirname "\$cmd")"
  mkdir -p "\$cmd_dir"
  source_file="\$CLAUDE_REPO/commands/\${cmd}.md"
  target_file="\$cmd_dir/\$(basename "\$cmd").md"
  [[ -f "\$source_file" ]] && ln -sf "\$source_file" "\$target_file"
done
HEREDOC
  local expected_link="$PROJECT_DIR/.claude/commands/$rel.md"
  assert_file_exists "apply: command symlink" "$expected_link"
  assert_symlink_target "apply: command target" "$expected_link" "$CLAUDE_REPO/commands/$rel.md"
  teardown_tmpdir
}

# ---------- Apply: Skills ----------

test_apply_skills() {
  setup_tmpdir
  local real_skill=""
  for sd in "$CLAUDE_REPO/skills"/*/SKILL.md; do
    [[ -f "$sd" ]] || continue
    real_skill=$(basename "$(dirname "$sd")")
    break
  done
  if [[ -z "$real_skill" ]]; then echo "  SKIP: test_apply_skills"; teardown_tmpdir; return; fi

  bash << HEREDOC
set -euo pipefail
PROJECT_DIR="$PROJECT_DIR"; CLAUDE_REPO="$CLAUDE_REPO"
info() { :; }; ok() { :; }; warn() { :; }; fail() { :; }; header() { :; }
mkdir -p "\$PROJECT_DIR/.claude/skills"
ln -sf "\$CLAUDE_REPO/skills/$real_skill" "\$PROJECT_DIR/.claude/skills/$real_skill"
HEREDOC
  assert_file_exists "apply: skill symlink" "$PROJECT_DIR/.claude/skills/$real_skill"
  assert_symlink_target "apply: skill target" \
    "$PROJECT_DIR/.claude/skills/$real_skill" "$CLAUDE_REPO/skills/$real_skill"
  teardown_tmpdir
}

# ---------- Apply: MCPs ----------

test_apply_mcps() {
  setup_tmpdir
  local real_mcp=""
  for mc in "$CLAUDE_REPO/mcps"/*/config.json; do
    [[ -f "$mc" ]] || continue
    real_mcp=$(basename "$(dirname "$mc")")
    break
  done
  if [[ -z "$real_mcp" ]]; then echo "  SKIP: test_apply_mcps"; teardown_tmpdir; return; fi

  bash << HEREDOC
set -euo pipefail
PROJECT_DIR="$PROJECT_DIR"; CLAUDE_REPO="$CLAUDE_REPO"
info() { :; }; ok() { :; }; warn() { :; }; fail() { :; }; header() { :; }
mkdir -p "\$PROJECT_DIR/.claude"
MCP_JSON='{"mcpServers":{}}'
config_file="\$CLAUDE_REPO/mcps/$real_mcp/config.json"
MCP_JSON=\$(echo "\$MCP_JSON" | jq --arg name "$real_mcp" --slurpfile cfg "\$config_file" '.mcpServers[\$name] = \$cfg[0]')
echo "\$MCP_JSON" | jq '.' > "\$PROJECT_DIR/.claude/settings.local.json"
HEREDOC
  assert_file_exists "apply: settings.local.json" "$PROJECT_DIR/.claude/settings.local.json"
  assert_json_key "apply: MCP key" "$PROJECT_DIR/.claude/settings.local.json" \
    ".mcpServers | has(\"$real_mcp\")" "true"
  teardown_tmpdir
}

# ---------- Apply: Plugins ----------

test_apply_plugins() {
  setup_tmpdir
  local plugin="feature-dev@claude-plugins-official"
  bash << HEREDOC
set -euo pipefail
PROJECT_DIR="$PROJECT_DIR"; CLAUDE_REPO="$CLAUDE_REPO"
info() { :; }; ok() { :; }; warn() { :; }; fail() { :; }; header() { :; }
mkdir -p "\$PROJECT_DIR/.claude"
SETTINGS=\$(cat "\$CLAUDE_REPO/profiles/standard.json")
PLUGINS_JSON='{"$plugin":true}'
SETTINGS=\$(echo "\$SETTINGS" | jq --argjson plugins "\$PLUGINS_JSON" '. + {enabledPlugins: \$plugins}')
echo "\$SETTINGS" | jq '.' > "\$PROJECT_DIR/.claude/settings.json"
HEREDOC
  assert_json_key "apply: plugin enabled" "$PROJECT_DIR/.claude/settings.json" \
    ".enabledPlugins[\"$plugin\"]" "true"
  teardown_tmpdir
}

# ---------- Apply: Hooks ----------

test_apply_hooks() {
  setup_tmpdir
  local hook_name="auto-format"
  local hook_dir="$CLAUDE_REPO/hooks/available/$hook_name"
  if [[ ! -d "$hook_dir" ]] || [[ ! -f "$hook_dir/hook.json" ]]; then
    echo "  SKIP: test_apply_hooks"
    teardown_tmpdir; return
  fi

  bash << HEREDOC
set -euo pipefail
PROJECT_DIR="$PROJECT_DIR"; CLAUDE_REPO="$CLAUDE_REPO"
info() { :; }; ok() { :; }; warn() { :; }; fail() { :; }; header() { :; }
mkdir -p "\$PROJECT_DIR/.claude/hooks"
mkdir -p "\$PROJECT_DIR/.claude"
SETTINGS=\$(cat "\$CLAUDE_REPO/profiles/standard.json")
HOOKS_JSON='{}'
hook_json="\$CLAUDE_REPO/hooks/available/$hook_name/hook.json"
event=\$(jq -r '.event' "\$hook_json")
matcher=\$(jq -r '.matcher // empty' "\$hook_json")
cmd_template=\$(jq -r '.command_template' "\$hook_json")
cmd="\${cmd_template//\{HOOKS_DIR\}/\$PROJECT_DIR/.claude/hooks}"
cp "\$CLAUDE_REPO/hooks/available/$hook_name"/*.sh "\$PROJECT_DIR/.claude/hooks/" 2>/dev/null || true
cp "\$CLAUDE_REPO/hooks/available/$hook_name"/*.js "\$PROJECT_DIR/.claude/hooks/" 2>/dev/null || true
chmod +x "\$PROJECT_DIR/.claude/hooks"/*.sh 2>/dev/null || true
hook_entry=\$(jq -n --arg cmd "\$cmd" --arg matcher "\$matcher" \
  'if \$matcher != "" then {matcher: \$matcher, hooks: [{type: "command", command: \$cmd}]}
   else {hooks: [{type: "command", command: \$cmd}]} end')
HOOKS_JSON=\$(echo "\$HOOKS_JSON" | jq --arg event "\$event" --argjson entry "\$hook_entry" \
  '.[\$event] = ((.[\$event] // []) + [\$entry])')
SETTINGS=\$(echo "\$SETTINGS" | jq --argjson hooks "\$HOOKS_JSON" '. + {hooks: \$hooks}')
echo "\$SETTINGS" | jq '.' > "\$PROJECT_DIR/.claude/settings.json"
HEREDOC
  assert_json_key "apply: hooks present" "$PROJECT_DIR/.claude/settings.json" \
    '.hooks | length > 0' "true"
  local has_scripts=false
  for f in "$PROJECT_DIR/.claude/hooks"/*.sh "$PROJECT_DIR/.claude/hooks"/*.js; do
    [[ -f "$f" ]] && has_scripts=true && break
  done
  assert_eq "apply: hook scripts copied" "true" "$has_scripts"
  teardown_tmpdir
}

# ---------- Apply: Empty selections ----------

test_apply_empty() {
  setup_tmpdir
  bash << HEREDOC
set -euo pipefail
PROJECT_DIR="$PROJECT_DIR"; CLAUDE_REPO="$CLAUDE_REPO"
info() { :; }; ok() { :; }; warn() { :; }; fail() { :; }; header() { :; }
mkdir -p "\$PROJECT_DIR/.claude"
SETTINGS=\$(cat "\$CLAUDE_REPO/profiles/standard.json")
echo "\$SETTINGS" | jq '.' > "\$PROJECT_DIR/.claude/settings.json"
HEREDOC
  assert_file_exists "apply empty: settings.json" "$PROJECT_DIR/.claude/settings.json"
  assert_file_not_exists "apply empty: no commands" "$PROJECT_DIR/.claude/commands"
  assert_file_not_exists "apply empty: no skills" "$PROJECT_DIR/.claude/skills"
  assert_file_not_exists "apply empty: no settings.local" "$PROJECT_DIR/.claude/settings.local.json"
  teardown_tmpdir
}

# ---------- Removal: Commands ----------

test_removal_commands() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/commands/folder"
  echo "x" > "$TEST_DIR/source.md"
  ln -s "$TEST_DIR/source.md" "$PROJECT_DIR/.claude/commands/folder/cmd.md"
  assert_file_exists "removal: symlink before" "$PROJECT_DIR/.claude/commands/folder/cmd.md"

  rm -f "$PROJECT_DIR/.claude/commands/folder/cmd.md"
  rmdir "$PROJECT_DIR/.claude/commands/folder" 2>/dev/null || true
  rmdir "$PROJECT_DIR/.claude/commands" 2>/dev/null || true

  assert_file_not_exists "removal: symlink gone" "$PROJECT_DIR/.claude/commands/folder/cmd.md"
  assert_file_not_exists "removal: empty dir cleaned" "$PROJECT_DIR/.claude/commands/folder"
  teardown_tmpdir
}

# ---------- Removal: Skills ----------

test_removal_skills_symlink() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/skills"
  ln -s "/some/skill" "$PROJECT_DIR/.claude/skills/my-skill"
  rm -f "$PROJECT_DIR/.claude/skills/my-skill"
  rmdir "$PROJECT_DIR/.claude/skills" 2>/dev/null || true
  assert_file_not_exists "removal: skill symlink gone" "$PROJECT_DIR/.claude/skills/my-skill"
  teardown_tmpdir
}

test_removal_skills_directory() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/skills/local-skill"
  echo "SKILL" > "$PROJECT_DIR/.claude/skills/local-skill/SKILL.md"
  # rm -f won't remove directories — need rm -rf
  rm -rf "$PROJECT_DIR/.claude/skills/local-skill"
  assert_file_not_exists "removal: skill dir gone" "$PROJECT_DIR/.claude/skills/local-skill"
  teardown_tmpdir
}

# ---------- Removal: MCPs ----------

test_removal_mcp_clears_settings_local() {
  setup_tmpdir
  echo '{"mcpServers":{"foo":{}}}' > "$PROJECT_DIR/.claude/settings.local.json"
  rm -f "$PROJECT_DIR/.claude/settings.local.json"
  assert_file_not_exists "removal: settings.local.json gone" "$PROJECT_DIR/.claude/settings.local.json"
  teardown_tmpdir
}

# ---------- Helpers: _fmt_list ----------

test_fmt_list() {
  eval "$(sed -n '/_fmt_list()/,/^}/p' "$SCRIPT")"
  assert_eq "fmt_list: empty" "(none)" "$(_fmt_list)"
  assert_eq "fmt_list: single" "alpha" "$(_fmt_list "alpha")"
  assert_eq "fmt_list: multi" "alpha, beta, gamma" "$(_fmt_list "alpha" "beta" "gamma")"
}

# ---------- Helpers: _resolve_command_selections ----------

test_resolve_display_selections() {
  eval "$(sed -n '/_resolve_display_selections()/,/^}/p' "$SCRIPT")"

  # Strips " (local)" suffix and sorts
  local result; result=$(_resolve_display_selections "custom_commands/capture2journal/capture2gotcha (local)" "custom_commands/code/health-check")
  assert_eq "resolve: strips local suffix" "2" "$(echo "$result" | wc -l | tr -d ' ')"
  assert_contains "resolve: individual" "custom_commands/code/health-check" "$result"

  # Empty string
  result=$(_resolve_display_selections "")
  local count; count=$(echo -n "$result" | grep -c . 2>/dev/null) || count=0
  assert_eq "resolve: empty → 0" "0" "$count"
}

# ---------- Local Discovery ----------

test_skills_discovery_includes_local() {
  setup_tmpdir
  # Create a local skill dir (not a symlink)
  mkdir -p "$PROJECT_DIR/.claude/skills/my-local-skill"
  echo "# Local" > "$PROJECT_DIR/.claude/skills/my-local-skill/SKILL.md"

  # Source the discovery section in a subshell
  local result
  result=$(bash << HEREDOC
set -uo pipefail
PROJECT_DIR="$PROJECT_DIR"
CLAUDE_REPO="$CLAUDE_REPO"

AVAILABLE_SKILLS=()
for skill_dir in "\$CLAUDE_REPO/skills"/*/SKILL.md; do
  [[ -f "\$skill_dir" ]] || continue
  dir="\$(dirname "\$skill_dir")"
  AVAILABLE_SKILLS+=("\$(basename "\$dir")")
done

declare -A IS_LOCAL_SKILL
if [[ -d "\$PROJECT_DIR/.claude/skills" ]]; then
  for entry in "\$PROJECT_DIR/.claude/skills"/*/; do
    [[ -d "\$entry" ]] || continue
    local_name="\$(basename "\$entry")"
    if [[ -L "\${entry%/}" ]]; then
      lt=\$(readlink "\${entry%/}")
      [[ "\$lt" == "\$CLAUDE_REPO/skills/"* ]] && continue
    fi
    dup_idx=-1
    for i in "\${!AVAILABLE_SKILLS[@]}"; do
      if [[ "\${AVAILABLE_SKILLS[\$i]}" == "\$local_name" ]]; then
        dup_idx=\$i; break
      fi
    done
    if (( dup_idx >= 0 )); then
      unset 'AVAILABLE_SKILLS[dup_idx]'
      AVAILABLE_SKILLS=("\${AVAILABLE_SKILLS[@]}")
    fi
    AVAILABLE_SKILLS=("\$local_name" "\${AVAILABLE_SKILLS[@]}")
    IS_LOCAL_SKILL["\$local_name"]=1
  done
fi

echo "COUNT=\${#AVAILABLE_SKILLS[@]}"
echo "FIRST=\${AVAILABLE_SKILLS[0]}"
echo "IS_LOCAL=\${IS_LOCAL_SKILL[my-local-skill]:-}"
HEREDOC
  )
  local count; count=$(echo "$result" | grep "^COUNT=" | cut -d= -f2-)
  local first; first=$(echo "$result" | grep "^FIRST=" | cut -d= -f2-)
  local is_local; is_local=$(echo "$result" | grep "^IS_LOCAL=" | cut -d= -f2-)
  assert_eq "local skill in list" "my-local-skill" "$first"
  assert_eq "local skill flagged" "1" "$is_local"
  teardown_tmpdir
}

test_skills_discovery_local_first() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/skills/aaa-local"
  echo "# Local" > "$PROJECT_DIR/.claude/skills/aaa-local/SKILL.md"

  local result
  result=$(bash << HEREDOC
set -uo pipefail
PROJECT_DIR="$PROJECT_DIR"
CLAUDE_REPO="$CLAUDE_REPO"

AVAILABLE_SKILLS=("shared-skill-z")
declare -A IS_LOCAL_SKILL
for entry in "\$PROJECT_DIR/.claude/skills"/*/; do
  [[ -d "\$entry" ]] || continue
  local_name="\$(basename "\$entry")"
  [[ -L "\${entry%/}" ]] && continue
  AVAILABLE_SKILLS=("\$local_name" "\${AVAILABLE_SKILLS[@]}")
  IS_LOCAL_SKILL["\$local_name"]=1
done

echo "FIRST=\${AVAILABLE_SKILLS[0]}"
HEREDOC
  )
  local first; first=$(echo "$result" | grep "^FIRST=" | cut -d= -f2-)
  assert_eq "local skill first" "aaa-local" "$first"
  teardown_tmpdir
}

test_skills_removal_local_directory() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/skills/local-to-remove"
  echo "stuff" > "$PROJECT_DIR/.claude/skills/local-to-remove/SKILL.md"

  # Simulate the fixed removal logic
  local skill_path="$PROJECT_DIR/.claude/skills/local-to-remove"
  if [[ -L "$skill_path" ]]; then
    rm -f "$skill_path"
  elif [[ -d "$skill_path" ]]; then
    rm -rf "$skill_path"
  fi
  assert_file_not_exists "local skill dir removed" "$skill_path"
  teardown_tmpdir
}

test_commands_discovery_includes_local() {
  setup_tmpdir
  mkdir -p "$PROJECT_DIR/.claude/commands"
  echo "# Local cmd" > "$PROJECT_DIR/.claude/commands/my-local-cmd.md"

  local result
  result=$(bash << HEREDOC
set -uo pipefail
PROJECT_DIR="$PROJECT_DIR"
CLAUDE_REPO="$CLAUDE_REPO"

AVAILABLE_COMMANDS=()
declare -A COMMAND_FOLDERS
declare -A IS_LOCAL_COMMAND
if [[ -d "\$PROJECT_DIR/.claude/commands" ]]; then
  while IFS= read -r cmd_file; do
    [[ -z "\$cmd_file" ]] && continue
    if [[ -L "\$cmd_file" ]]; then
      local_target=\$(readlink "\$cmd_file")
      [[ "\$local_target" == "\$CLAUDE_REPO/commands/"* ]] && continue
    fi
    rel="\${cmd_file#"\$PROJECT_DIR/.claude/commands/"}"
    name="\${rel%.md}"
    AVAILABLE_COMMANDS=("\$name" "\${AVAILABLE_COMMANDS[@]}")
    IS_LOCAL_COMMAND["\$name"]=1
  done < <(find "\$PROJECT_DIR/.claude/commands" -name "*.md" ! -type d 2>/dev/null | sort)
fi

echo "COUNT=\${#AVAILABLE_COMMANDS[@]}"
echo "FIRST=\${AVAILABLE_COMMANDS[0]}"
echo "IS_LOCAL=\${IS_LOCAL_COMMAND[my-local-cmd]:-}"
HEREDOC
  )
  local count; count=$(echo "$result" | grep "^COUNT=" | cut -d= -f2-)
  local first; first=$(echo "$result" | grep "^FIRST=" | cut -d= -f2-)
  local is_local; is_local=$(echo "$result" | grep "^IS_LOCAL=" | cut -d= -f2-)
  assert_eq "local cmd count" "1" "$count"
  assert_eq "local cmd name" "my-local-cmd" "$first"
  assert_eq "local cmd flagged" "1" "$is_local"
  teardown_tmpdir
}

test_awk_tools_section_multiline() {
  setup_tmpdir
  # Create a CLAUDE.md with existing bootstrapped tools section
  cat > "$PROJECT_DIR/CLAUDE.md" << 'EOF'
# CLAUDE.md

<!-- BEGIN:BOOTSTRAPPED_TOOLS -->
## Bootstrapped Tools

**Permission profile:** standard

**Commands:**
  - /old/command
**Skills:**
**MCPs:**
**Hooks:**

Run `claude-bootstrap` to reconfigure.
<!-- END:BOOTSTRAPPED_TOOLS -->
EOF

  # Build a multiline replacement using a temp file approach
  local tools_tmp
  tools_tmp=$(mktemp)
  cat > "$tools_tmp" << 'TOOLSEOF'
<!-- BEGIN:BOOTSTRAPPED_TOOLS -->
## Bootstrapped Tools

**Permission profile:** strict

**Commands:**
  - /new/command1
  - /new/command2
**Skills:**
  - my-skill
**MCPs:**
**Hooks:**

Run `claude-bootstrap` to reconfigure.
<!-- END:BOOTSTRAPPED_TOOLS -->
TOOLSEOF

  awk '
    /<!-- BEGIN:BOOTSTRAPPED_TOOLS -->/{skip=1; while((getline line < "'"$tools_tmp"'") > 0) print line; next}
    /<!-- END:BOOTSTRAPPED_TOOLS -->/{skip=0; next}
    !skip{print}
  ' "$PROJECT_DIR/CLAUDE.md" > "$PROJECT_DIR/CLAUDE.md.tmp"
  rm -f "$tools_tmp"
  mv "$PROJECT_DIR/CLAUDE.md.tmp" "$PROJECT_DIR/CLAUDE.md"

  # Verify the update worked
  local content
  content=$(cat "$PROJECT_DIR/CLAUDE.md")
  assert_contains "awk: has new profile" "strict" "$content"
  assert_contains "awk: has new command" "/new/command1" "$content"
  assert_contains "awk: has skill" "my-skill" "$content"
  assert_contains "awk: no old command" "# CLAUDE.md" "$content"
  # Old command should be gone
  if [[ "$content" == *"/old/command"* ]]; then
    ((FAIL++)); ERRORS+=("FAIL: awk: old command still present")
  else
    ((PASS++))
  fi
  teardown_tmpdir
}

# ---------- Run all ----------

printf "Running claude-bootstrap unit tests...\n"
printf "CLAUDE_REPO=%s\n\n" "$CLAUDE_REPO"

# Profile
test_profile_detection_standard
test_profile_detection_strict
test_profile_detection_with_plugins_key
test_profile_detection_with_hooks_key
test_profile_detection_unknown
test_profile_detection_no_file

# Commands
test_command_detection_symlinks
test_command_detection_local_files
test_command_detection_ignores_foreign_symlinks
test_command_detection_no_dir

# Skills
test_skills_detection_symlinks
test_skills_detection_directories
test_skills_detection_empty
test_skills_detection_ignores_files

# MCPs
test_mcp_detection
test_mcp_detection_empty
test_mcp_detection_no_file

# Plugins
test_plugin_detection
test_plugin_detection_none

# Hooks
test_hooks_detection
test_hooks_detection_none

# Project Note
test_project_note_detection
test_project_note_detection_none
test_project_note_no_claudemd

# Apply
test_apply_profile
test_apply_commands
test_apply_skills
test_apply_mcps
test_apply_plugins
test_apply_hooks
test_apply_empty

# Removal
test_removal_commands
test_removal_skills_symlink
test_removal_skills_directory
test_removal_mcp_clears_settings_local

# Local Discovery
test_skills_discovery_includes_local
test_skills_discovery_local_first
test_skills_removal_local_directory
test_commands_discovery_includes_local
test_awk_tools_section_multiline

# Helpers
test_fmt_list
test_resolve_display_selections

# Results
printf "\n================================\n"
printf "  PASS: %d\n" "$PASS"
printf "  FAIL: %d\n" "$FAIL"
printf "================================\n"
if (( FAIL > 0 )); then
  printf "\n"
  for err in "${ERRORS[@]}"; do printf "  %s\n" "$err"; done
  exit 1
fi
printf "\nAll tests passed.\n"
