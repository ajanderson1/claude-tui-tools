# Implementation Plan — Issue #1

## Root Cause / Design Approach
The `claude-tui-settings` app only has `q` and `ctrl+q` as quit bindings. Users familiar with `nano` expect `ctrl+x` to quit. This is a trivial enhancement — add one more `Binding()` entry.

**Important discovery:** `claude-tui-usage` is NOT a Textual app — it's a pure CLI script using argparse, subprocess, and ANSI output. It has no `Binding()` system. The issue's request to apply to "both apps" is based on a misunderstanding of the architecture. We'll fix what applies: the settings app.

## Ctrl+X Conflict Analysis
`ctrl+x` is the standard "cut" shortcut in Textual `Input` widgets. Textual's widget-focus priority means focused Input widgets consume `ctrl+x` before it reaches app-level bindings. This is identical to how the existing `q` binding behaves — it doesn't quit when you're typing in an Input. No new problem is introduced. `priority=True` exists as a Binding kwarg to override this, but is deliberately not used here — overriding cut in Input fields would be worse than the status quo.

## Design Decisions
- **`show=False`**: `q` is the canonical visible quit binding (`show=True`). Both `ctrl+q` and `ctrl+x` are hidden muscle-memory aliases, matching the existing pattern where primary bindings are shown and alternates are hidden.
- **ExitDialog limitation**: The ExitDialog uses button-based interaction, not keyboard shortcuts. A second `ctrl+x` inside the dialog has no effect. This is not a regression (same for `q` and `ctrl+q`) but means this is not full nano parity (nano uses `ctrl+x` → `y/n` prompt). Worth noting in PR description.

## Files to Modify
1. `packages/settings/src/claude_tui_settings/app.py` — Add binding after the `ctrl+q` binding, before the `alt+1` binding
2. `packages/settings/tests/test_app.py` — Add test with concrete assertion

## Changes (ordered)
1. Add `Binding("ctrl+x", "quit_app", "Quit", show=False)` after the `ctrl+q` quit binding in BINDINGS list
2. Add `test_ctrl_x_quits_with_no_changes` test that asserts `not app.is_running`

## Test Strategy
- Run existing test suite to confirm no regression
- New test: press `ctrl+x` with no pending changes → assert app exits (`not app.is_running`)

## Challenge

### 1. The conflict-risk analysis is incomplete and potentially wrong

The plan states: "Textual's focused widget bindings take priority over app-level bindings, so `ctrl+x` will only trigger quit when no `Input` widget is focused."

This is mostly correct but glosses over a real problem: the `SavePresetDialog` (in `preset_dialogs.py`) contains two `Input` widgets and auto-focuses the name input on mount (`self.query_one("#save-preset-name", Input).focus()`). If a user opens that modal and then presses `ctrl+x` expecting to cut text, nothing happens (the Input handles it). But if the modal is dismissed and focus returns to the main app, `ctrl+x` will quit — which is exactly what nano users expect. This double-personality is not a problem unique to `ctrl+x`; `q` has the same behaviour. The plan should simply note that Textual's widget-focus priority makes this a non-issue in the same way `q` is a non-issue, and leave it at that. The current framing implies a risk that does not meaningfully differ from the pre-existing `q` binding.

`settings_tab.py` also uses `Input` widgets for free-form setting values. The same widget-priority rule applies there. No new problem is introduced.

### 2. The proposed test does not assert anything

The existing `test_quit_with_no_changes` test at line 124–131 of `test_app.py` is structurally identical to what the plan proposes for `ctrl+x`:

```python
async with app.run_test(size=(80, 24)) as pilot:
    await pilot.press("q")
    await pilot.pause()
    # App should have exited (or be exiting)
```

There is no assertion. The comment "App should have exited (or be exiting)" is not a test — it is documentation of intent. The plan copies this pattern without flagging it. A reviewer would push back: the new test should assert something concrete, such as `assert not app.is_running` after the key press and a pause, or use Textual's `app.return_value` / `ExitApp` mechanism to confirm the exit path was taken. If the existing test is already weak and the new test is equally weak, adding the new test adds noise without adding coverage.

### 3. The "simpler approach" question is not addressed

The plan defaults to adding a third `Binding` entry. That is correct and is the right approach. However, the plan does not consider whether Textual's `App.BINDINGS` supports a `priority` kwarg that would be needed if `ctrl+x` ever needed to fire even when a widget is focused. For this issue it does not matter — but since the plan explicitly discusses the widget-focus priority behaviour, it should mention that `priority=True` exists as a mechanism and explain why it is deliberately not used here (because overriding cut behaviour inside Input fields would be worse than the status quo).

### 4. The `show=False` decision is stated without justification

The plan copies `show=False` from the issue body without challenging whether that is the right default. Looking at the existing bindings, all primary visible bindings use `show=True`; hidden alternates use `show=False`. `ctrl+q` is `show=False` because `q` is already shown. The plan should make clear that `ctrl+x` is `show=False` for the same reason: `q` is the canonical shown quit binding and `ctrl+x` is a secondary muscle-memory alias. This is correct — but it should be stated, not assumed.

### 5. Line-number references will rot immediately

The plan says "Add at line 93 (after existing ctrl+q)". Line numbers in plans are a maintenance hazard: any unrelated edit above that point shifts the target line. The instruction should reference the surrounding code context (after the `ctrl+q` binding, before the `alt+1` binding) rather than a raw line number.

### 6. No consideration of the `ExitDialog` keyboard path

The `ExitDialog` modal (`confirm_dialog.py`) has no `BINDINGS` or `on_key` handler. Its only interaction path is clicking one of three `Button` widgets. A user who presses `ctrl+x` to quit, sees the "Unsaved Changes" dialog, and then instinctively presses `ctrl+x` again expecting nano-style "yes discard" will be surprised: the second `ctrl+x` has no effect inside the modal. This is not a regression (the existing `q` and `ctrl+q` bindings have the same gap), but since the issue is motivated by nano muscle memory, it is worth noting that nano's `ctrl+x` flow is interactive (`ctrl+x` → prompt → `y/n`), whereas this app's flow requires mouse or tab-to-button interaction. The plan should acknowledge this limitation rather than implying full nano parity.

### 7. The `_on_exit_result` callback is untested for the `ctrl+x` path

The plan proposes only one new test: `ctrl+x` with no pending changes. The issue analysis mentions testing the dialog flow ("press Ctrl+X → shows exit dialog → test all dialog options") but the plan's "Changes" section omits this. Given the existing `test_quit_with_no_changes` only tests the no-dialog path for `q`, there is already a gap in coverage for `ctrl+q`. Adding `ctrl+x` without a dialog-path test perpetuates that gap. A human reviewer would reasonably ask: "What tests do we have for the ExitDialog save/discard/cancel paths, and do they cover `ctrl+x` as the trigger?"

### Summary of issues requiring action before implementation

| Issue | Severity | Required action |
|-------|----------|-----------------|
| Test adds no assertion | Medium | Strengthen test to assert `not app.is_running` or equivalent |
| Line number reference in plan | Low | Replace with code-context reference |
| ExitDialog keyboard gap not acknowledged | Low | Document as known limitation in PR description |
| `priority=True` not mentioned | Low | Add one sentence explaining it was considered and rejected |
