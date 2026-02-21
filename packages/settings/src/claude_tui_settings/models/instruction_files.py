"""Discover instruction files across all scopes."""

from __future__ import annotations

from pathlib import Path

from claude_tui_settings.models.audit import _encode_project_path, _get_managed_dir
from claude_tui_settings.models.config import InstructionFile


def discover_instruction_files(project_dir: Path) -> list[InstructionFile]:
    """Discover all CLAUDE.md, rules, MEMORY.md across all scopes."""
    files: list[InstructionFile] = []
    user_claude_dir = Path.home() / ".claude"
    managed_dir = _get_managed_dir()
    encoded = _encode_project_path(project_dir)

    # 1. Managed CLAUDE.md
    _add_if_exists(files, managed_dir / "CLAUDE.md", "managed", "claude_md")

    # 2. User (global) scope
    _add_if_exists(files, user_claude_dir / "CLAUDE.md", "user", "claude_md")
    _add_rules(files, user_claude_dir / "rules", "user")

    # 3. User (per-project) scope
    per_project_dir = user_claude_dir / "projects" / encoded
    _add_if_exists(files, per_project_dir / "CLAUDE.md", "user-project", "claude_md")
    _add_if_exists(
        files, per_project_dir / "memory" / "MEMORY.md", "user-project", "memory",
    )

    # 4. Project scope
    # CLAUDE.md can be at root or .claude/CLAUDE.md
    project_claude_md = project_dir / "CLAUDE.md"
    claude_dir_claude_md = project_dir / ".claude" / "CLAUDE.md"
    if project_claude_md.is_file():
        _add_if_exists(files, project_claude_md, "project", "claude_md")
    elif claude_dir_claude_md.is_file():
        _add_if_exists(files, claude_dir_claude_md, "project", "claude_md")

    _add_rules(files, project_dir / ".claude" / "rules", "project")

    # 5. Local scope
    _add_if_exists(files, project_dir / "CLAUDE.local.md", "local", "local_md")

    return files


def _add_if_exists(
    files: list[InstructionFile],
    path: Path,
    scope: str,
    file_type: str,
) -> None:
    """Add an instruction file entry, checking if it exists."""
    exists = path.is_file()
    preview = ""
    if exists:
        try:
            lines = path.read_text().splitlines()[:3]
            preview = "\n".join(lines)
        except OSError:
            pass
    files.append(InstructionFile(
        path=path,
        scope=scope,
        file_type=file_type,
        preview=preview,
        exists=exists,
    ))


def _add_rules(
    files: list[InstructionFile],
    rules_dir: Path,
    scope: str,
) -> None:
    """Add rule files from a rules directory."""
    if not rules_dir.is_dir():
        return
    for rule_file in sorted(rules_dir.rglob("*.md")):
        _add_if_exists(files, rule_file, scope, "rules")
