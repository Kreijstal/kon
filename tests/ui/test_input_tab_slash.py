import asyncio

from kon.ui import prompt_history as ph
from kon.ui.input import InputBox


class _FakeSelection:
    def __init__(self, row: int, col: int) -> None:
        self.end = (row, col)
        self.start = (row, col)


class _FakeTextArea:
    def __init__(self, text: str) -> None:
        self.text = text
        self.selection = _FakeSelection(0, len(text))
        self.inserted: list[str] = []

    def clear(self) -> None:
        self.text = ""
        self.selection = _FakeSelection(0, 0)

    def insert(self, text: str) -> None:
        self.inserted.append(text)
        col = self.selection.end[1]
        self.text = self.text[:col] + text + self.text[col:]
        self.selection = _FakeSelection(0, col + len(text))


class _TestableInputBox(InputBox):
    def __init__(self, text: str = "") -> None:
        super().__init__(cwd="/tmp")
        self._fake_textarea = _FakeTextArea(text)
        self.posted_messages: list[object] = []

    def query_one(self, *args, **kwargs):  # type: ignore[override]
        return self._fake_textarea

    def post_message(self, message: object):  # type: ignore[override]
        self.posted_messages.append(message)

    def run_worker(self, work, *args, **kwargs):  # type: ignore[override]
        if asyncio.iscoroutine(work):
            asyncio.run(work)
        return None


def test_tab_applies_slash_autocomplete_selection(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ph, "_history_path", lambda: tmp_path / "prompt-history.jsonl")

    input_box = _TestableInputBox("/han")
    input_box._is_completing = True
    input_box._tab_completing = False

    input_box.action_tab_complete()

    selects = [m for m in input_box.posted_messages if isinstance(m, InputBox.CompletionSelect)]
    assert len(selects) == 1
    assert selects[0].allow_submit is False
    assert not any(isinstance(m, InputBox.CompletionMove) for m in input_box.posted_messages)


def test_tab_cycles_path_completion_alternatives(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ph, "_history_path", lambda: tmp_path / "prompt-history.jsonl")

    input_box = _TestableInputBox("src/kon/ui/s")
    input_box._is_completing = True
    input_box._tab_completing = True

    input_box.action_tab_complete()

    moves = [m for m in input_box.posted_messages if isinstance(m, InputBox.CompletionMove)]
    assert len(moves) == 1
    assert moves[0].direction == 1
    assert not any(isinstance(m, InputBox.CompletionSelect) for m in input_box.posted_messages)
