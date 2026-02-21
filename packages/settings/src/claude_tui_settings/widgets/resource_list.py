"""Reusable selection list for Commands/Agents/Skills/Plugins/MCPs/Hooks."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import SelectionList, Static
from textual.widgets.selection_list import Selection

FOLDER_VALUE_PREFIX = "__folder__"

USER_TAG = " [bold dodger_blue2](USER)[/bold dodger_blue2]"
PROJECT_TAG = " [bold yellow](PROJECT)[/bold yellow]"


class ResourceToggled(Message):
    """Message sent when a resource is toggled."""

    def __init__(self, name: str, selected: bool, domain: str) -> None:
        super().__init__()
        self.name = name
        self.selected = selected
        self.domain = domain


class ResourceList(VerticalScroll, can_focus=False):
    """A scrollable list of selection items for resource selection."""

    def __init__(
        self,
        title: str,
        domain: str,
        items: list[dict],
        selected: set[str],
        *,
        show_folders: bool = False,
        user_items: set[str] | None = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.domain = domain
        self.items = items
        self.selected = selected
        self.show_folders = show_folders
        self.user_items = user_items or set()
        # Folder↔child mappings, built during compose().
        # These are only valid until self.items is mutated; recomposition rebuilds them.
        self._folder_children: dict[str, list[str]] = {}
        self._child_folder: dict[str, str] = {}
        self._batch_toggling: bool = False
        # Per-item metadata for dynamic label rebuilding: {name: (item_dict, display_name, in_folder)}
        self._item_meta: dict[str, tuple[dict, str | None, bool]] = {}

    def compose(self) -> ComposeResult:
        yield Static(self.title, classes="section-title")

        if self.show_folders:
            yield from self._compose_with_folders()
        else:
            yield from self._compose_flat()

    def _build_label(
        self, item: dict, display_name: str | None = None, *, is_selected: bool = False,
    ) -> str:
        """Build the display label for a selection item."""
        name = display_name or item["name"]
        is_local = item.get("is_local", False)
        is_broken = item.get("is_broken_symlink", False)
        is_user = item.get("is_user_scope", False)
        description = item.get("description", "")
        binary_warning = item.get("binary_warning", "")

        label = f"[dim]{name}[/dim]" if is_user else name
        if is_local:
            label += " (local)"
        if is_user:
            label += USER_TAG
        elif not is_local and is_selected:
            label += PROJECT_TAG
        if is_broken:
            label += " [yellow]! broken symlink[/yellow]"
        if description:
            label += f" - [dim]{description}[/dim]"
        if binary_warning:
            label += f" [yellow]! {binary_warning}[/yellow]"
        return label

    def _build_folder_prompt(self, folder: str, partial: bool = False) -> str:
        """Build display prompt for a folder header."""
        if partial:
            return f"-- {folder}/ ~ --"
        return f"-- {folder}/ --"

    def _build_folder_mappings(
        self, folders: dict[str, list[dict]]
    ) -> None:
        """Build folder-child lookup dicts from grouped items.

        Only includes selectable (non-local, non-user-scope) children in
        the mappings.  Root-level items (empty folder key) are excluded
        and never participate in folder logic.
        """
        self._folder_children = {}
        self._child_folder = {}
        for folder, items in folders.items():
            if not folder:
                continue
            folder_value = f"{FOLDER_VALUE_PREFIX}{folder}"
            selectable = [
                item for item in items
                if not item.get("is_local", False)
                and not item.get("is_user_scope", False)
            ]
            child_names = [item["name"] for item in selectable]
            self._folder_children[folder_value] = child_names
            for name in child_names:
                self._child_folder[name] = folder_value

    def _user_only_items(self) -> list[dict]:
        """Return synthetic item dicts for user-scope items not in self.items."""
        item_names = {item["name"] for item in self.items}
        user_only: list[dict] = []
        for name in sorted(self.user_items - item_names):
            user_only.append({"name": name, "is_user_scope": True})
        return user_only

    def _compose_flat(self) -> ComposeResult:
        selections: list[Selection[str]] = []
        for item in self.items:
            name = item["name"]
            is_local = item.get("is_local", False)
            is_user = name in self.user_items
            # If this item also exists at user scope, tag it
            if is_user:
                item = {**item, "is_user_scope": True}
            selected = is_user or name in self.selected
            label = self._build_label(item, is_selected=selected)
            self._item_meta[name] = (item, None, False)
            selections.append(
                Selection(
                    prompt=label,
                    value=name,
                    id=name,
                    initial_state=selected,
                    disabled=is_local,
                )
            )

        # Append user-only items (not in project available items)
        for item in self._user_only_items():
            name = item["name"]
            label = self._build_label(item, is_selected=True)
            selections.append(
                Selection(
                    prompt=label,
                    value=name,
                    initial_state=True,
                )
            )

        if selections:
            yield SelectionList[str](*selections)

    def _compose_with_folders(self) -> ComposeResult:
        # Group by folder
        folders: dict[str, list[dict]] = {}
        for item in self.items:
            folder = item.get("folder", "")
            # Tag items that also exist at user scope
            if item["name"] in self.user_items:
                item = {**item, "is_user_scope": True}
            if folder not in folders:
                folders[folder] = []
            folders[folder].append(item)

        # Merge user-only items into folder structure
        item_names = {item["name"] for item in self.items}
        for name in sorted(self.user_items - item_names):
            folder = name.rsplit("/", 1)[0] if "/" in name else ""
            user_item = {"name": name, "folder": folder, "is_user_scope": True}
            if folder not in folders:
                folders[folder] = []
            folders[folder].append(user_item)

        # Build folder-child mappings (excludes user-scope and local items)
        self._build_folder_mappings(folders)

        selections: list[Selection[str]] = []
        for folder in sorted(folders.keys()):
            if folder:
                folder_value = f"{FOLDER_VALUE_PREFIX}{folder}"
                child_names = self._folder_children.get(folder_value, [])
                has_selectable = len(child_names) > 0

                # Compute initial folder state from selected set
                selected_count = sum(
                    1 for n in child_names if n in self.selected
                )
                all_selected = (
                    selected_count == len(child_names) and has_selectable
                )
                partial = 0 < selected_count < len(child_names)

                prompt = self._build_folder_prompt(folder, partial)

                selections.append(
                    Selection(
                        prompt=prompt,
                        value=folder_value,
                        id=folder_value,  # Required for replace_option_prompt()
                        initial_state=all_selected,
                        disabled=not has_selectable,
                    )
                )

            for item in sorted(folders[folder], key=lambda x: x["name"]):
                name = item["name"]
                is_local = item.get("is_local", False)
                is_user = item.get("is_user_scope", False)
                display_name = name.split("/")[-1] if "/" in name else name
                in_folder = bool(folder)
                selected = is_user or name in self.selected
                label = self._build_label(item, display_name, is_selected=selected)
                self._item_meta[name] = (item, display_name, in_folder)
                # Indent child items under their folder header
                if in_folder:
                    label = "    " + label

                # User-scope items: always checked, highlightable
                if is_user:
                    selections.append(
                        Selection(
                            prompt=label,
                            value=name,
                            id=name,
                            initial_state=True,
                        )
                    )
                else:
                    selections.append(
                        Selection(
                            prompt=label,
                            value=name,
                            id=name,
                            initial_state=name in self.selected,
                            disabled=is_local,
                        )
                    )

        if selections:
            yield SelectionList[str](*selections)

    def _update_item_label(self, sl: SelectionList, name: str, is_selected: bool) -> None:
        """Rebuild and replace an item's prompt to reflect its selection state."""
        meta = self._item_meta.get(name)
        if not meta:
            return
        item_dict, display_name, in_folder = meta
        label = self._build_label(item_dict, display_name, is_selected=is_selected)
        if in_folder:
            label = "    " + label
        sl.replace_option_prompt(name, label)

    def on_selection_list_selection_toggled(
        self, event: SelectionList.SelectionToggled
    ) -> None:
        """Handle selection toggle."""
        name = event.selection.value
        sl = event.selection_list

        if isinstance(name, str) and name.startswith(FOLDER_VALUE_PREFIX):
            self._handle_folder_toggle(sl, name)
            return

        # User-scoped items: silently re-check if user tries to uncheck
        if isinstance(name, str) and name in self.user_items:
            if name not in set(sl.selected):
                with sl.prevent(SelectionList.SelectionToggled):
                    sl.select(name)
            return

        # Normal child toggle
        is_selected = name in set(sl.selected)
        self._update_item_label(sl, name, is_selected)
        self.post_message(
            ResourceToggled(name=name, selected=is_selected, domain=self.domain)
        )

        # Update parent folder state if this child belongs to a folder.
        # _batch_toggling guard is defense-in-depth: select()/deselect() don't
        # fire SelectionToggled, so this branch is unreachable during batch ops.
        if not self._batch_toggling:
            folder_value = self._child_folder.get(name)
            if folder_value:
                self._update_folder_state(sl, folder_value)

    def _handle_folder_toggle(
        self, sl: SelectionList, folder_value: str
    ) -> None:
        """Batch select/deselect all children of a folder.

        IMPORTANT: Folder values must never be posted as ResourceToggled.
        Only child item names are posted, so folder synthetic values never
        leak into config.selected_* sets.
        """
        children = self._folder_children.get(folder_value, [])
        if not children:
            return

        # Determine target state: all selected → deselect; otherwise → select all
        current_selected = set(sl.selected)
        all_selected = all(c in current_selected for c in children)
        target_selected = not all_selected

        self._batch_toggling = True
        try:
            # Suppress SelectedChanged events during batch (select/deselect fire them)
            with sl.prevent(SelectionList.SelectedChanged):
                for child_name in children:
                    child_already = child_name in current_selected
                    if child_already == target_selected:
                        continue  # Skip children already in target state

                    if target_selected:
                        sl.select(child_name)
                    else:
                        sl.deselect(child_name)
                    self._update_item_label(sl, child_name, target_selected)
                    self.post_message(
                        ResourceToggled(
                            name=child_name,
                            selected=target_selected,
                            domain=self.domain,
                        )
                    )

                # Explicitly set folder checkbox state regardless of what
                # toggle() already did. This is an intentional double-write
                # for correctness — in the partial case, toggle() and the
                # handler may disagree on the desired state.
                if target_selected:
                    sl.select(folder_value)
                else:
                    sl.deselect(folder_value)

            # replace_option_prompt() doesn't fire events, so it's safe
            # outside the prevent() block.
            folder = folder_value.removeprefix(FOLDER_VALUE_PREFIX)
            sl.replace_option_prompt(
                folder_value,
                self._build_folder_prompt(folder, partial=False),
            )
        finally:
            self._batch_toggling = False

    def _update_folder_state(
        self, sl: SelectionList, folder_value: str
    ) -> None:
        """Update a folder header's checkbox and prompt based on children state."""
        children = self._folder_children.get(folder_value, [])
        if not children:
            return

        current_selected = set(sl.selected)
        selected_count = sum(1 for c in children if c in current_selected)
        all_selected = selected_count == len(children)
        partial = 0 < selected_count < len(children)

        # Update folder checkbox state (suppressing SelectedChanged)
        with sl.prevent(SelectionList.SelectedChanged):
            if all_selected:
                sl.select(folder_value)
            else:
                sl.deselect(folder_value)

        # replace_option_prompt() doesn't fire events, so it's safe
        # outside the prevent() block.
        folder = folder_value.removeprefix(FOLDER_VALUE_PREFIX)
        sl.replace_option_prompt(
            folder_value, self._build_folder_prompt(folder, partial=partial)
        )
