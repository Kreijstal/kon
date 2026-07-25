from kon.ui.autocomplete import SlashCommand
from kon.ui.floating_list import ListItem
from kon.ui.input import InputBox


class _FakeSelection:
    def __init__(self, row: int, col: int) -> None:
        self.end = (row, col)


class _FakeTextArea:
    def __init__(self, text: str) -> None:
        self.text = text
        self.selection = _FakeSelection(0, len(text))

    def clear(self) -> None:
        self.text = ""
        self.selection = _FakeSelection(0, 0)

    def insert(self, text: str) -> None:
        row, col = self.selection.end
        if row != 0:
            row = 0
            col = len(self.text)
        self.text = self.text[:col] + text + self.text[col:]
        self.selection = _FakeSelection(0, col + len(text))


class _TestableInputBox(InputBox):
    def __init__(self, text: str = "") -> None:
        super().__init__(cwd="/tmp")
        self._fake_textarea = _FakeTextArea(text)
        self.posted: list[InputBox.Submitted] = []

    def query_one(self, *args, **kwargs):  # type: ignore[override]
        return self._fake_textarea

    def post_message(self, message):  # type: ignore[override]
        if isinstance(message, InputBox.Submitted):
            self.posted.append(message)


def test_handoff_slash_command_selection_inserts_text_not_submit() -> None:
    input_box = _TestableInputBox("/")
    input_box._completion_prefix = "/"

    handoff_cmd = SlashCommand(
        "handoff", "Start focused handoff in new session", submit_on_select=False
    )
    input_box.apply_slash_command(ListItem(value=handoff_cmd, label="/handoff", description=""))

    assert input_box.posted == []
    assert input_box._fake_textarea.text == "/handoff "


def test_tab_slash_selection_inserts_even_when_submit_on_select() -> None:
    input_box = _TestableInputBox("/cle")
    input_box._completion_prefix = "/cle"

    clear_cmd = SlashCommand("clear", "Clear the conversation", submit_on_select=True)
    input_box.apply_slash_command(
        ListItem(value=clear_cmd, label="/clear", description=""), allow_submit=False
    )

    assert input_box.posted == []
    assert input_box._fake_textarea.text == "/clear "


def test_enter_slash_selection_submits_when_submit_on_select() -> None:
    input_box = _TestableInputBox("/cle")
    input_box._completion_prefix = "/cle"

    clear_cmd = SlashCommand("clear", "Clear the conversation", submit_on_select=True)
    input_box.apply_slash_command(
        ListItem(value=clear_cmd, label="/clear", description=""), allow_submit=True
    )

    assert len(input_box.posted) == 1
    assert input_box.posted[0].text == "/clear"
    assert input_box._fake_textarea.text == ""
