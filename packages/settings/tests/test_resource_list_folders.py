"""Tests for ResourceList folder tri-state selection and indentation."""

import pytest
from textual.app import App, ComposeResult
from textual.widgets import SelectionList

from claude_tui_settings.widgets.resource_list import (
    FOLDER_VALUE_PREFIX,
    ResourceList,
    ResourceToggled,
)


class FolderTestApp(App):
    """Test app that captures ResourceToggled messages."""

    def __init__(self, items, selected, *, show_folders=True, user_items=None):
        super().__init__()
        self._items = items
        self._selected = selected
        self._show_folders = show_folders
        self._user_items = user_items
        self.toggled: list[ResourceToggled] = []

    def compose(self) -> ComposeResult:
        yield ResourceList(
            title="Test",
            domain="commands",
            items=self._items,
            selected=self._selected,
            show_folders=self._show_folders,
            user_items=self._user_items,
        )

    def on_resource_toggled(self, event: ResourceToggled) -> None:
        self.toggled.append(event)


@pytest.fixture
def folder_items():
    """Two selectable + one local item in a folder."""
    return [
        {"name": "folder/a", "folder": "folder"},
        {"name": "folder/b", "folder": "folder"},
        {"name": "folder/c", "folder": "folder", "is_local": True},
    ]


@pytest.fixture
def all_local_items():
    """All items in a folder are local."""
    return [
        {"name": "folder/x", "folder": "folder", "is_local": True},
        {"name": "folder/y", "folder": "folder", "is_local": True},
    ]


@pytest.fixture
def single_child_items():
    """Folder with one selectable child."""
    return [
        {"name": "solo/only", "folder": "solo"},
    ]


@pytest.fixture
def flat_items():
    """Items without folders for flat mode."""
    return [
        {"name": "item_a"},
        {"name": "item_b"},
    ]


@pytest.mark.asyncio
async def test_folder_select_all(folder_items):
    """Toggle empty folder selects all selectable children."""
    app = FolderTestApp(folder_items, selected=set())
    async with app.run_test() as pilot:
        sl = app.query_one(SelectionList)
        sl.toggle(f"{FOLDER_VALUE_PREFIX}folder")
        await pilot.pause()

        # Only selectable children (a, b) should be toggled; local c excluded
        assert len(app.toggled) == 2
        toggled_names = {e.name for e in app.toggled}
        assert toggled_names == {"folder/a", "folder/b"}
        assert all(e.selected for e in app.toggled)


@pytest.mark.asyncio
async def test_folder_deselect_all(folder_items):
    """Toggle fully-selected folder deselects all selectable children."""
    app = FolderTestApp(folder_items, selected={"folder/a", "folder/b"})
    async with app.run_test() as pilot:
        sl = app.query_one(SelectionList)
        sl.toggle(f"{FOLDER_VALUE_PREFIX}folder")
        await pilot.pause()

        assert len(app.toggled) == 2
        toggled_names = {e.name for e in app.toggled}
        assert toggled_names == {"folder/a", "folder/b"}
        assert all(not e.selected for e in app.toggled)


@pytest.mark.asyncio
async def test_child_toggle_updates_folder(folder_items):
    """Deselecting one child updates folder to unchecked."""
    app = FolderTestApp(folder_items, selected={"folder/a", "folder/b"})
    async with app.run_test() as pilot:
        sl = app.query_one(SelectionList)
        # Deselect one child -- folder should become partial (unchecked)
        sl.toggle("folder/a")
        await pilot.pause()

        folder_value = f"{FOLDER_VALUE_PREFIX}folder"
        assert folder_value not in set(sl.selected)


@pytest.mark.asyncio
async def test_initial_partial_state(folder_items):
    """Compose with partial selection shows ~ in folder prompt."""
    app = FolderTestApp(folder_items, selected={"folder/a"})
    async with app.run_test():
        sl = app.query_one(SelectionList)
        # Folder header is index 0
        folder_option = sl.get_option_at_index(0)
        prompt_text = str(folder_option.prompt)
        assert "~" in prompt_text


@pytest.mark.asyncio
async def test_all_local_folder_disabled(all_local_items):
    """Folder with only local children is disabled."""
    app = FolderTestApp(all_local_items, selected=set())
    async with app.run_test():
        sl = app.query_one(SelectionList)
        folder_option = sl.get_option_at_index(0)
        assert folder_option.disabled is True


@pytest.mark.asyncio
async def test_single_child_folder(single_child_items):
    """Folder with one selectable child toggles correctly."""
    app = FolderTestApp(single_child_items, selected=set())
    async with app.run_test() as pilot:
        sl = app.query_one(SelectionList)
        sl.toggle(f"{FOLDER_VALUE_PREFIX}solo")
        await pilot.pause()

        assert len(app.toggled) == 1
        assert app.toggled[0].name == "solo/only"
        assert app.toggled[0].selected is True


@pytest.mark.asyncio
async def test_local_items_excluded(folder_items):
    """Local items are not affected by folder toggle."""
    app = FolderTestApp(folder_items, selected=set())
    async with app.run_test() as pilot:
        sl = app.query_one(SelectionList)
        sl.toggle(f"{FOLDER_VALUE_PREFIX}folder")
        await pilot.pause()

        toggled_names = {e.name for e in app.toggled}
        # Local item folder/c must not appear in toggled messages
        assert "folder/c" not in toggled_names


@pytest.mark.asyncio
async def test_flat_mode_regression(flat_items):
    """show_folders=False mode continues to work unchanged."""
    app = FolderTestApp(flat_items, selected=set(), show_folders=False)
    async with app.run_test() as pilot:
        sl = app.query_one(SelectionList)
        sl.toggle("item_a")
        await pilot.pause()

        assert len(app.toggled) == 1
        assert app.toggled[0].name == "item_a"
        assert app.toggled[0].selected is True


# --- User-scope inline tests ---


@pytest.mark.asyncio
async def test_user_only_items_flat_mode():
    """User-only items appear inline as checked + disabled in flat mode."""
    items = [{"name": "project_cmd"}]
    user_items = {"user_cmd"}
    app = FolderTestApp(
        items, selected={"project_cmd"}, show_folders=False,
        user_items=user_items,
    )
    async with app.run_test():
        sl = app.query_one(SelectionList)
        # Should have 2 options: project_cmd + user_cmd
        assert sl.option_count == 2
        # user_cmd should be at index 1, checked and highlightable (not disabled)
        user_option = sl.get_option_at_index(1)
        assert user_option.value == "user_cmd"
        assert "USER" in str(user_option.prompt)
        assert user_option.disabled is False
        # Check it's in the selected set (initial_state=True)
        assert "user_cmd" in set(sl.selected)


@pytest.mark.asyncio
async def test_both_scope_item_has_user_tag_flat():
    """Item at both project and user scope gets USER tag, checked, highlightable."""
    items = [{"name": "shared_cmd"}]
    user_items = {"shared_cmd"}
    app = FolderTestApp(
        items, selected=set(), show_folders=False,
        user_items=user_items,
    )
    async with app.run_test():
        sl = app.query_one(SelectionList)
        assert sl.option_count == 1
        option = sl.get_option_at_index(0)
        assert "USER" in str(option.prompt)
        # Checked and highlightable — toggle is a no-op
        assert option.disabled is False
        assert option.initial_state is True


@pytest.mark.asyncio
async def test_user_only_items_in_folders():
    """User-only items appear under correct folder headers."""
    items = [
        {"name": "folder/a", "folder": "folder"},
    ]
    user_items = {"folder/b"}  # user-only item in same folder
    app = FolderTestApp(
        items, selected={"folder/a"}, show_folders=True,
        user_items=user_items,
    )
    async with app.run_test():
        sl = app.query_one(SelectionList)
        # folder header + folder/a + folder/b = 3 options
        assert sl.option_count == 3
        # folder/b should have USER tag and be highlightable
        user_option = sl.get_option_at_index(2)
        assert user_option.value == "folder/b"
        assert "USER" in str(user_option.prompt)
        assert user_option.disabled is False


@pytest.mark.asyncio
async def test_user_only_folder():
    """User-only items create a new folder header when needed."""
    items = []  # no project items
    user_items = {"myfolder/cmd"}
    app = FolderTestApp(
        items, selected=set(), show_folders=True,
        user_items=user_items,
    )
    async with app.run_test():
        sl = app.query_one(SelectionList)
        # folder header (disabled) + myfolder/cmd = 2 options
        assert sl.option_count == 2
        folder_option = sl.get_option_at_index(0)
        assert folder_option.disabled is True  # no selectable children
        user_option = sl.get_option_at_index(1)
        assert "USER" in str(user_option.prompt)
        assert user_option.disabled is False


@pytest.mark.asyncio
async def test_user_items_excluded_from_folder_toggle():
    """Folder toggle does not affect user-scope items."""
    items = [
        {"name": "folder/a", "folder": "folder"},
    ]
    user_items = {"folder/b"}  # user-only item in same folder
    app = FolderTestApp(
        items, selected=set(), show_folders=True,
        user_items=user_items,
    )
    async with app.run_test() as pilot:
        sl = app.query_one(SelectionList)
        sl.toggle(f"{FOLDER_VALUE_PREFIX}folder")
        await pilot.pause()

        # Only project item folder/a should be toggled
        assert len(app.toggled) == 1
        assert app.toggled[0].name == "folder/a"
        assert app.toggled[0].selected is True


@pytest.mark.asyncio
async def test_no_user_items_no_change(flat_items):
    """ResourceList without user_items works as before."""
    app = FolderTestApp(flat_items, selected=set(), show_folders=False)
    async with app.run_test():
        sl = app.query_one(SelectionList)
        assert sl.option_count == 2
        for i in range(2):
            option = sl.get_option_at_index(i)
            assert "USER" not in str(option.prompt)
