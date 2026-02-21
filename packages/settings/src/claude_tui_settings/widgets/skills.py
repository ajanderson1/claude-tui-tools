"""Skills section — checkbox list, no folder grouping."""

from __future__ import annotations

from claude_tui_settings.models.config import ConfigState
from claude_tui_settings.widgets.resource_list import ResourceList


def make_skills_section(config: ConfigState) -> ResourceList:
    """Create the skills section widget."""
    items = [
        {
            "name": r.name,
            "is_local": r.is_local,
            "is_broken_symlink": r.is_broken_symlink,
        }
        for r in config.available_skills
    ]
    return ResourceList(
        title="Skills",
        domain="skills",
        items=items,
        selected=config.selected_skills,
        user_items=config.user_skills,
    )
