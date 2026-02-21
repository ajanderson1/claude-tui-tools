"""ConfigState dataclass — all selections + pending diff."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_NO_VALUE = object()  # sentinel for "no user-scope value exists"


@dataclass
class Profile:
    name: str
    description: str
    json_path: Path


@dataclass
class Resource:
    name: str
    path: Path
    folder: str = ""
    is_local: bool = False
    is_broken_symlink: bool = False


@dataclass
class Plugin:
    id: str
    name: str
    description: str


@dataclass
class MCP:
    name: str
    config: dict[str, Any]
    description: str = ""
    binary: str = ""
    binary_found: bool = True


@dataclass
class Hook:
    name: str
    event: str
    matcher: str
    description: str = ""
    command_template: str = ""
    script_files: list[str] = field(default_factory=list)
    is_global: bool = False


@dataclass
class Preset:
    name: str
    slug: str
    description: str = ""
    created_at: str = ""
    profile: str = "standard"
    commands: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    plugins: list[str] = field(default_factory=list)
    mcps: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class SettingDef:
    key: str
    type: str  # "boolean", "string", "number", "enum"
    description: str = ""
    default: Any = None
    enum_values: list[str] | None = None


@dataclass
class AuditWarning:
    scope: str
    warning_type: str  # DUPE, OVERRIDE, CONFLICT
    key: str
    message: str


@dataclass
class ResolvedValue:
    key: str
    value: Any
    source_scope: str
    overridden_scopes: list[tuple[str, Any]] = field(default_factory=list)


@dataclass
class ResolvedPermissionRule:
    rule_type: str  # allow, deny, ask
    pattern: str
    source_scope: str
    overridden_scopes: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ResolvedMCPServer:
    name: str
    config: dict[str, Any]
    source_scope: str


@dataclass
class ResolvedHook:
    event: str
    matcher: str
    command: str
    source_scope: str


@dataclass
class ResolvedPlugin:
    plugin_id: str
    enabled: bool
    source_scope: str
    overridden_scopes: list[tuple[str, bool]] = field(default_factory=list)


@dataclass
class EffectiveConfig:
    settings: list[ResolvedValue] = field(default_factory=list)
    permission_rules: list[ResolvedPermissionRule] = field(default_factory=list)
    plugins: list[ResolvedPlugin] = field(default_factory=list)
    mcp_servers: list[ResolvedMCPServer] = field(default_factory=list)
    hooks: list[ResolvedHook] = field(default_factory=list)
    project_commands: int = 0
    user_commands: int = 0
    project_agents: int = 0
    user_agents: int = 0
    project_skills: int = 0
    user_skills: int = 0


@dataclass
class InstructionFile:
    path: Path
    scope: str  # "managed", "user", "user-project", "project", "local"
    file_type: str  # "claude_md", "rules", "memory", "local_md"
    preview: str = ""
    exists: bool = True


@dataclass
class DiffEntry:
    domain: str
    action: str  # "add", "remove", "modify"
    key: str
    old_value: Any = None
    new_value: Any = None
    reason: str = ""


@dataclass
class Diff:
    entries: list[DiffEntry] = field(default_factory=list)

    @property
    def additions(self) -> list[DiffEntry]:
        return [e for e in self.entries if e.action == "add"]

    @property
    def removals(self) -> list[DiffEntry]:
        return [e for e in self.entries if e.action == "remove"]

    @property
    def modifications(self) -> list[DiffEntry]:
        return [e for e in self.entries if e.action == "modify"]

    @property
    def is_empty(self) -> bool:
        return len(self.entries) == 0

    def count_for_domain(self, domain: str) -> int:
        return sum(1 for e in self.entries if e.domain == domain)


@dataclass
class ConfigState:
    # Source repo path
    claude_repo: Path

    # Available (immutable after discovery)
    available_profiles: list[Profile] = field(default_factory=list)
    available_commands: list[Resource] = field(default_factory=list)
    available_agents: list[Resource] = field(default_factory=list)
    available_skills: list[Resource] = field(default_factory=list)
    available_plugins: list[Plugin] = field(default_factory=list)
    available_mcps: list[MCP] = field(default_factory=list)
    available_hooks: list[Hook] = field(default_factory=list)
    available_settings: list[SettingDef] = field(default_factory=list)

    # Existing on disk (snapshot at startup, refreshed after apply)
    existing_profile: str | None = None
    existing_commands: set[str] = field(default_factory=set)
    existing_agents: set[str] = field(default_factory=set)
    existing_skills: set[str] = field(default_factory=set)
    existing_plugins: set[str] = field(default_factory=set)
    existing_mcps: set[str] = field(default_factory=set)
    existing_hooks: set[str] = field(default_factory=set)
    existing_settings: dict[str, Any] = field(default_factory=dict)

    # User selections (mutable, drives the UI)
    selected_profile: str = "standard"
    selected_commands: set[str] = field(default_factory=set)
    selected_agents: set[str] = field(default_factory=set)
    selected_skills: set[str] = field(default_factory=set)
    selected_plugins: set[str] = field(default_factory=set)
    selected_mcps: set[str] = field(default_factory=set)
    selected_hooks: set[str] = field(default_factory=set)
    selected_settings: dict[str, Any] = field(default_factory=dict)

    # Scope audit
    audit_warnings: list[AuditWarning] = field(default_factory=list)

    # Effective configuration (resolved from all scopes — read-only)
    effective: EffectiveConfig = field(default_factory=EffectiveConfig)

    # Instruction files (discovered across all scopes — read-only)
    instruction_files: list[InstructionFile] = field(default_factory=list)

    # User-scope resources (read-only, shown for awareness)
    user_commands: set[str] = field(default_factory=set)
    user_agents: set[str] = field(default_factory=set)
    user_skills: set[str] = field(default_factory=set)

    def get_user_scope_value(self, key: str) -> Any:
        """Return the user-scope value for a setting, or _NO_VALUE if none."""
        for rv in self.effective.settings:
            if rv.key == key:
                if rv.source_scope in ("User", "User-Project"):
                    return rv.value
                for scope_name, scope_val in rv.overridden_scopes:
                    if scope_name in ("User", "User-Project"):
                        return scope_val
        return _NO_VALUE

    def get_effective_value(self, key: str, default: Any = None) -> Any:
        """Return the effective resolved value for a setting."""
        for rv in self.effective.settings:
            if rv.key == key:
                return rv.value
        return default

    @property
    def has_pending_changes(self) -> bool:
        return not self.pending_diff().is_empty

    def pending_diff(self) -> Diff:
        entries: list[DiffEntry] = []

        # Profile diff
        if self.existing_profile is not None:
            if self.selected_profile != self.existing_profile:
                entries.append(DiffEntry(
                    domain="profile",
                    action="modify",
                    key="profile",
                    old_value=self.existing_profile,
                    new_value=self.selected_profile,
                ))
        else:
            entries.append(DiffEntry(
                domain="profile",
                action="add",
                key="profile",
                new_value=self.selected_profile,
            ))

        # Resource diffs (commands, agents, skills, plugins, mcps, hooks)
        # For commands/agents/skills, compute effective selected by excluding
        # user-scope items (dedup: user scope already provides them).
        user_sets = {
            "commands": self.user_commands,
            "agents": self.user_agents,
            "skills": self.user_skills,
        }
        for domain, existing, selected in [
            ("commands", self.existing_commands, self.selected_commands),
            ("agents", self.existing_agents, self.selected_agents),
            ("skills", self.existing_skills, self.selected_skills),
            ("plugins", self.existing_plugins, self.selected_plugins),
            ("mcps", self.existing_mcps, self.selected_mcps),
            ("hooks", self.existing_hooks, self.selected_hooks),
        ]:
            user_set = user_sets.get(domain, set())
            effective = selected - user_set if user_set else selected
            for name in sorted(effective - existing):
                entries.append(DiffEntry(domain=domain, action="add", key=name))
            for name in sorted(existing - effective):
                reason = "already at user scope" if name in user_set else ""
                entries.append(DiffEntry(
                    domain=domain, action="remove", key=name, reason=reason,
                ))

        # Settings diff
        all_keys = set(self.existing_settings.keys()) | set(self.selected_settings.keys())
        for key in sorted(all_keys):
            old_val = self.existing_settings.get(key)
            new_val = self.selected_settings.get(key)
            if old_val is None and new_val is not None:
                entries.append(DiffEntry(
                    domain="settings", action="add", key=key, new_value=new_val,
                ))
            elif old_val is not None and new_val is None:
                entries.append(DiffEntry(
                    domain="settings", action="remove", key=key, old_value=old_val,
                ))
            elif old_val != new_val and new_val is not None:
                entries.append(DiffEntry(
                    domain="settings", action="modify", key=key,
                    old_value=old_val, new_value=new_val,
                ))

        return Diff(entries=entries)
