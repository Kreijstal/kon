from textual.binding import Binding

from kon.ui.input import Kon


def test_ctrl_backspace_deletes_previous_word() -> None:
    bindings = {
        binding.key: binding.action for binding in Kon.BINDINGS if isinstance(binding, Binding)
    }

    assert bindings["ctrl+backspace"] == "delete_word_left"
