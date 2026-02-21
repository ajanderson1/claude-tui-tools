"""Preset I/O — list, parse, validate, save, and load saved configurations."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_tui_settings.models.config import ConfigState, Preset


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Turn a human-readable preset name into a filesystem-safe slug.

    Raises ``ValueError`` if the result is empty after sanitisation.
    """
    # Normalise unicode → ASCII approximation
    normalised = unicodedata.normalize("NFKD", name)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    if not slug:
        raise ValueError(f"Cannot slugify name: {name!r}")
    return slug


# ---------------------------------------------------------------------------
# Listing / parsing
# ---------------------------------------------------------------------------

_RESOURCE_FIELDS = ("commands", "agents", "skills", "plugins", "mcps", "hooks")
_SCALAR_TYPES = (str, int, float, bool, type(None))


def list_presets(
    claude_repo: Path,
    *,
    max_files: int = 100,
    max_size: int = 256 * 1024,
) -> list[Preset]:
    """Return all valid presets found under ``claude_repo/configs/``."""
    configs_dir = claude_repo / "configs"
    if not configs_dir.is_dir():
        return []

    presets: list[Preset] = []
    count = 0
    for path in sorted(configs_dir.glob("*.json")):
        if count >= max_files:
            break
        if path.is_symlink():
            continue
        try:
            if path.stat().st_size > max_size:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        slug = path.stem
        preset = _parse_preset(slug, data)
        if preset is not None:
            presets.append(preset)
        count += 1

    presets.sort(key=lambda p: p.name)
    return presets


def _parse_preset(slug: str, data: dict[str, Any]) -> Preset | None:
    """Strictly validate *data* and return a ``Preset`` or ``None``."""
    if not isinstance(data, dict):
        return None

    profile = data.get("profile")
    if not isinstance(profile, str):
        return None

    # Validate resource lists
    resource_values: dict[str, list[str]] = {}
    for field_name in _RESOURCE_FIELDS:
        raw = data.get(field_name, [])
        if not isinstance(raw, list):
            return None
        if not all(isinstance(item, str) for item in raw):
            return None
        resource_values[field_name] = raw

    # Validate settings
    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        return None
    for val in settings.values():
        if not isinstance(val, _SCALAR_TYPES):
            return None

    # Meta
    meta = data.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}

    name = meta.get("name", slug)
    description = meta.get("description", "")
    created_at = meta.get("created_at", "")

    return Preset(
        name=name if isinstance(name, str) else slug,
        slug=slug,
        description=description if isinstance(description, str) else "",
        created_at=created_at if isinstance(created_at, str) else "",
        profile=profile,
        settings=settings,
        **resource_values,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_preset(
    preset: Preset,
    state: ConfigState,
) -> list[tuple[str, str, str]]:
    """Check *preset* against *state* and return a list of issues.

    Each issue is a ``(domain, key, message)`` tuple.
    """
    issues: list[tuple[str, str, str]] = []

    # Profile
    known_profiles = frozenset(p.name for p in state.available_profiles)
    if preset.profile not in known_profiles:
        issues.append(("profile", preset.profile, f"Unknown profile: {preset.profile}"))

    # Resources
    _domain_pairs: list[tuple[str, list[str], frozenset[str]]] = [
        ("commands", preset.commands, frozenset(r.name for r in state.available_commands)),
        ("agents", preset.agents, frozenset(r.name for r in state.available_agents)),
        ("skills", preset.skills, frozenset(r.name for r in state.available_skills)),
        ("plugins", preset.plugins, frozenset(p.id for p in state.available_plugins)),
        ("mcps", preset.mcps, frozenset(m.name for m in state.available_mcps)),
        ("hooks", preset.hooks, frozenset(h.name for h in state.available_hooks)),
    ]
    for domain, items, available in _domain_pairs:
        for item in items:
            if item not in available:
                issues.append((domain, item, f"Not available: {item}"))

    # Settings
    known_settings = frozenset(s.key for s in state.available_settings)
    for key in preset.settings:
        if key not in known_settings:
            issues.append(("settings", key, f"Unknown setting: {key}"))

    return issues


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_preset(name: str, description: str, config: ConfigState) -> Path:
    """Persist the current selections in *config* as a named preset.

    Returns the path to the written JSON file.
    """
    slug = slugify(name)
    configs_dir = config.claude_repo / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)

    target = configs_dir / f"{slug}.json"
    if target.is_symlink():
        raise ValueError(f"Refusing to overwrite symlink: {target}")

    now = datetime.now(timezone.utc).isoformat()

    data: dict[str, Any] = {
        "meta": {
            "name": name,
            "description": description,
            "created_at": now,
        },
        "profile": config.selected_profile,
        "commands": sorted(config.selected_commands),
        "agents": sorted(config.selected_agents),
        "skills": sorted(config.selected_skills),
        "plugins": sorted(config.selected_plugins),
        "mcps": sorted(config.selected_mcps),
        "hooks": sorted(config.selected_hooks),
        "settings": dict(sorted(config.selected_settings.items())),
    }

    # Atomic write
    fd, tmp_path = tempfile.mkstemp(dir=configs_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return target


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_preset_into_state(
    preset: Preset,
    state: ConfigState,
    skip: set[tuple[str, str]] | None = None,
) -> None:
    """Apply *preset* selections onto *state*, skipping items in *skip*.

    *skip* is a set of ``(domain, key)`` tuples that should not be applied.
    """
    if skip is None:
        skip = set()

    # Profile
    if ("profile", preset.profile) not in skip:
        state.selected_profile = preset.profile

    # Resources
    _mappings: list[tuple[str, list[str], set[str]]] = [
        ("commands", preset.commands, state.selected_commands),
        ("agents", preset.agents, state.selected_agents),
        ("skills", preset.skills, state.selected_skills),
        ("plugins", preset.plugins, state.selected_plugins),
        ("mcps", preset.mcps, state.selected_mcps),
        ("hooks", preset.hooks, state.selected_hooks),
    ]
    for domain, items, target in _mappings:
        target.clear()
        for item in items:
            if (domain, item) not in skip:
                target.add(item)

    # Settings
    state.selected_settings.clear()
    for key, value in preset.settings.items():
        if ("settings", key) not in skip:
            state.selected_settings[key] = value
