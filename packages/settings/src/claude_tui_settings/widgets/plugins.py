"""Plugins section — checkbox list with descriptions."""

from __future__ import annotations

from claude_tui_settings.models.config import ConfigState
from claude_tui_settings.widgets.resource_list import ResourceList


def make_plugins_section(config: ConfigState) -> ResourceList:
    """Create the plugins section widget."""
    items = [
        {
            "name": p.id,
            "description": f"{p.name} - {p.description}" if p.description else p.name,
        }
        for p in config.available_plugins
    ]
    return ResourceList(
        title="Plugins",
        domain="plugins",
        items=items,
        selected=config.selected_plugins,
    )
