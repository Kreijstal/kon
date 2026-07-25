from kon.ui import prompt_history as ph
from kon.ui.autocomplete import SlashCommand
from kon.ui.input import InputBox


class _FakeSelection:
    def __init__(self, row: int, col: int) -> None:
        self.end = (row, col)


class _FakeTextArea:
    def __init__(self, text: str) -> None:
        self.text = text
        self.cleared = False
        self.selection = _FakeSelection(0, len(text))

    def clear(self) -> None:
        self.text = ""
        self.cleared = True
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
        self.posted_messages: list[InputBox.Submitted] = []

    def query_one(self, *args, **kwargs):  # type: ignore[override]
        return self._fake_textarea

    def post_message(self, message: InputBox.Submitted):  # type: ignore[override]
        self.posted_messages.append(message)


def test_history_recalled_skill_command_triggers_skill(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ph, "_history_path", lambda: tmp_path / "prompt-history.jsonl")

    input_box = _TestableInputBox("/newskill 1")
    input_box.set_commands(
        [
            SlashCommand(name="clear", description="Clear"),
            SlashCommand(name="newskill", description="A skill", is_skill=True),
        ]
    )

    input_box._do_submit()

    assert len(input_box.posted_messages) == 1
    message = input_box.posted_messages[0]
    assert message.text == "/newskill 1"
    assert message.selected_skill_name == "newskill"
    assert message.selected_skill_query == "1"


def test_history_recalled_skill_command_without_args(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ph, "_history_path", lambda: tmp_path / "prompt-history.jsonl")

    input_box = _TestableInputBox("/newskill")
    input_box.set_commands([SlashCommand(name="newskill", description="A skill", is_skill=True)])

    input_box._do_submit()

    message = input_box.posted_messages[0]
    assert message.selected_skill_name == "newskill"
    assert message.selected_skill_query == ""


def test_unknown_slash_text_not_treated_as_skill(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ph, "_history_path", lambda: tmp_path / "prompt-history.jsonl")

    input_box = _TestableInputBox("/notaskill hello")
    input_box.set_commands([SlashCommand(name="newskill", description="A skill", is_skill=True)])

    input_box._do_submit()

    message = input_box.posted_messages[0]
    assert message.selected_skill_name is None
    assert message.text == "/notaskill hello"


def test_builtin_command_not_treated_as_skill(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ph, "_history_path", lambda: tmp_path / "prompt-history.jsonl")

    input_box = _TestableInputBox("/clear")
    input_box.set_commands(
        [
            SlashCommand(name="clear", description="Clear"),
            SlashCommand(name="newskill", description="A skill", is_skill=True),
        ]
    )

    input_box._do_submit()

    message = input_box.posted_messages[0]
    assert message.selected_skill_name is None
    assert message.text == "/clear"
