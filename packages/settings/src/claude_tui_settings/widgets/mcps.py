"""MCPs section — resource_list with binary availability warnings."""

from __future__ import annotations

from claude_tui_settings.models.config import ConfigState
from claude_tui_settings.widgets.resource_list import ResourceList


def make_mcps_section(config: ConfigState) -> ResourceList:
    """Create the MCPs section widget."""
    items = [
        {
            "name": m.name,
            "description": m.description,
            "binary_warning": (
                f"binary '{m.binary}' not found"
                if m.binary and not m.binary_found
                else ""
            ),
        }
        for m in config.available_mcps
    ]
    return ResourceList(
        title="MCPs",
        domain="mcps",
        items=items,
        selected=config.selected_mcps,
    )
