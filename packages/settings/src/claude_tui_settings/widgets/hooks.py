"""Hooks section — resource_list with global hook dimming."""

from __future__ import annotations

from claude_tui_settings.models.config import ConfigState
from claude_tui_settings.widgets.resource_list import ResourceList


def make_hooks_section(config: ConfigState) -> ResourceList:
    """Create the hooks section widget."""
    items = []
    for h in config.available_hooks:
        desc = f"{h.event} on {h.matcher}"
        if h.description:
            desc += f" - {h.description}"
        items.append({
            "name": h.name,
            "description": desc,
            "is_local": h.is_global,  # Global hooks are non-selectable
        })
    return ResourceList(
        title="Hooks",
        domain="hooks",
        items=items,
        selected=config.selected_hooks,
    )
