"""Agents section — resource_list with folder grouping."""

from __future__ import annotations

from claude_tui_settings.models.config import ConfigState
from claude_tui_settings.widgets.resource_list import ResourceList


def make_agents_section(config: ConfigState) -> ResourceList:
    """Create the agents section widget."""
    items = [
        {
            "name": r.name,
            "folder": r.folder,
            "is_local": r.is_local,
            "is_broken_symlink": r.is_broken_symlink,
        }
        for r in config.available_agents
    ]
    return ResourceList(
        title="Agents",
        domain="agents",
        items=items,
        selected=config.selected_agents,
        show_folders=True,
        user_items=config.user_agents,
    )
