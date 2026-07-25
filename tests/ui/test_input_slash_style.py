from rich.style import Style
from rich.text import Text

from kon import config
from kon.ui.input import _SKILL_TRIGGER_MARKER, _stylize_slash_commands


def test_slash_command_token_uses_badge_label_color() -> None:
    line = Text("/handoff focus this")
    _stylize_slash_commands(line, {"handoff", "clear"})

    badge = Style(color=config.ui.colors.badge.label, bold=True)
    assert any(
        start == 0 and end == len("/handoff") and style == badge
        for start, end, style in line.spans
    )


def test_unknown_slash_token_not_styled() -> None:
    line = Text("/unknown stuff")
    _stylize_slash_commands(line, {"handoff"})

    assert line.spans == []


def test_partial_command_prefix_not_styled() -> None:
    line = Text("/han")
    _stylize_slash_commands(line, {"handoff"})

    assert line.spans == []


def test_skill_marker_wrapped_command_is_styled() -> None:
    token = f"{_SKILL_TRIGGER_MARKER}/newskill{_SKILL_TRIGGER_MARKER} args"
    line = Text(token)
    _stylize_slash_commands(line, {"newskill"})

    badge = Style(color=config.ui.colors.badge.label, bold=True)
    # /newskill starts after the leading marker
    start = 1
    end = start + len("/newskill")
    assert any(s == start and e == end and style == badge for s, e, style in line.spans)
