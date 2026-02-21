"""Fetch, cache, and parse JSON schema for Claude Code settings."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

SCHEMA_URL = "https://json.schemastore.org/claude-code-settings.json"
CACHE_DIR = Path.home() / ".cache" / "claude-tui-settings"
CACHE_FILE = CACHE_DIR / "schema.json"
CACHE_META = CACHE_DIR / "schema-meta.json"
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


def get_cached_schema() -> dict[str, Any] | None:
    """Return cached schema if it exists and is not stale."""
    if not CACHE_FILE.is_file():
        return None
    if not CACHE_META.is_file():
        return None
    try:
        meta = json.loads(CACHE_META.read_text())
        fetched_at = meta.get("fetched_at", 0)
        if time.time() - fetched_at > CACHE_TTL_SECONDS:
            return None  # Stale
        return json.loads(CACHE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def get_stale_cache() -> dict[str, Any] | None:
    """Return cached schema even if stale (offline fallback)."""
    if not CACHE_FILE.is_file():
        return None
    try:
        return json.loads(CACHE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_schema_cache(schema: dict[str, Any]) -> None:
    """Save schema to cache with timestamp."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(schema, indent=2))
    CACHE_META.write_text(json.dumps({"fetched_at": time.time()}))


async def fetch_schema() -> dict[str, Any] | None:
    """Fetch schema from schemastore.org, with cache fallback."""
    # Try fresh cache first
    cached = get_cached_schema()
    if cached is not None:
        return cached

    # Try to fetch
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(SCHEMA_URL)
            resp.raise_for_status()
            schema = resp.json()
            save_schema_cache(schema)
            return schema
    except Exception:
        # Offline fallback: use stale cache
        return get_stale_cache()


def parse_schema_properties(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract setting definitions from JSON schema properties."""
    properties = schema.get("properties", {})
    result = []
    for key, prop in properties.items():
        entry: dict[str, Any] = {"key": key}

        # Type resolution
        prop_type = prop.get("type", "string")
        if isinstance(prop_type, list):
            # Union type like ["string", "null"] -> use first non-null
            prop_type = next((t for t in prop_type if t != "null"), "string")
        entry["type"] = prop_type

        # Description
        entry["description"] = prop.get("description", "")

        # Default value
        if "default" in prop:
            entry["default"] = prop["default"]

        # Enum values
        if "enum" in prop:
            entry["enum"] = prop["enum"]

        # Handle oneOf for enum-like patterns
        if "oneOf" in prop:
            enum_vals = []
            for option in prop["oneOf"]:
                if "const" in option:
                    enum_vals.append(option["const"])
                elif "enum" in option:
                    enum_vals.extend(option["enum"])
            if enum_vals:
                entry["enum"] = enum_vals

        result.append(entry)
    return result
