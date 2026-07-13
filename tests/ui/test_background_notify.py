"""Exercises the app's background-completion auto-notify seam (no live LLM/TUI).

Drives the real ``Kon._poll_background_tasks`` / ``_enqueue_background_steer``
methods against a minimal stand-in ``self`` and real background subprocesses,
verifying the running -> steer and idle -> pending injection paths.
"""

import asyncio
from collections import deque

import pytest

from kon import config
from kon.background import get_background_manager, reset_background_manager
from kon.monitors import get_monitor_manager, reset_monitor_manager
from kon.tools.bash import BashParams, BashTool
from kon.ui.app import Kon
from kon.ui.queue_ui import QueuedPrompt


class _FakeChat:
    def __init__(self):
        self.messages = []

    def add_info_message(self, msg, **kwargs):
        self.messages.append(msg)


class _FakeApp:
    """Minimal object exposing only what the poll methods touch."""

    def __init__(self, *, is_running: bool):
        self._is_running = is_running
        self._chat = _FakeChat()
        self._steer_queue: deque[QueuedPrompt] = deque(maxlen=5)
        self._steer_event = asyncio.Event()
        self._pending_bg_notifications: list[str] = []
        self.queue_display_updated = False

    def query_one(self, selector, cls):
        return self._chat

    def _update_queue_display(self):
        self.queue_display_updated = True

    # Bind the real implementations under test.
    _format_bg_notification = staticmethod(Kon._format_bg_notification)
    _inject_agent_notification = Kon._inject_agent_notification
    _poll_background_tasks = Kon._poll_background_tasks
    _poll_monitors = Kon._poll_monitors
    _enqueue_background_steer = Kon._enqueue_background_steer


@pytest.fixture(autouse=True)
def _reset():
    reset_background_manager()
    reset_monitor_manager()
    prev = config.notifications.enabled
    config.notifications.enabled = False  # avoid audio side effects in tests
    yield
    config.notifications.enabled = prev
    reset_background_manager()
    reset_monitor_manager()


async def _run_bg_and_wait(command: str) -> None:
    await BashTool().execute(BashParams(command=command, background=True))
    task = get_background_manager().get("bg_1")
    assert task is not None
    for _ in range(100):
        if not task.is_running:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("background task did not finish in time")


@pytest.mark.asyncio
async def test_completion_while_running_injects_steer_message():
    await _run_bg_and_wait("printf done; exit 0")
    app = _FakeApp(is_running=True)

    app._poll_background_tasks()

    # Surfaced in the transcript...
    assert any("bg_1 completed" in m for m in app._chat.messages)
    # ...and injected as a steer message with the event set so the loop breaks.
    assert len(app._steer_queue) == 1
    _display, query, _images = app._steer_queue[0]
    assert "<background-task id=bg_1 status=completed" in query
    assert 'bash_output tool with bash_id="bg_1"' in query
    assert app._steer_event.is_set()
    assert app.queue_display_updated
    # Nothing stashed for the idle path.
    assert app._pending_bg_notifications == []


@pytest.mark.asyncio
async def test_completion_while_idle_stashes_pending_notification():
    await _run_bg_and_wait("exit 3")
    app = _FakeApp(is_running=False)

    app._poll_background_tasks()

    assert any("bg_1 failed (exit 3)" in m for m in app._chat.messages)
    assert len(app._steer_queue) == 0
    assert not app._steer_event.is_set()
    assert len(app._pending_bg_notifications) == 1
    assert "status=failed exit=3" in app._pending_bg_notifications[0]


@pytest.mark.asyncio
async def test_completion_reported_only_once():
    await _run_bg_and_wait("exit 0")
    app = _FakeApp(is_running=False)

    app._poll_background_tasks()
    app._poll_background_tasks()

    assert len(app._pending_bg_notifications) == 1


@pytest.mark.asyncio
async def test_monitor_fire_injects_steer_while_running():
    mgr = get_monitor_manager()
    mgr.create_timer("wake up", delay=5, now=0.0)
    app = _FakeApp(is_running=True)

    # next_fire is anchored to a real time.monotonic() at creation, so this poll
    # (real now) is already past a 5s-from-monotonic-zero deadline.
    app._poll_monitors()

    assert len(app._steer_queue) == 1
    _display, query, _images = app._steer_queue[0]
    assert "Timer fired: wake up" in query
    assert app._steer_event.is_set()


@pytest.mark.asyncio
async def test_monitor_tool_to_app_notify_end_to_end():
    # Full chain: the agent-facing monitor tool creates a bash_status monitor,
    # a real background task finishes, and the app's real poll fires the notify.
    from kon.tools.monitor import MonitorParams, MonitorTool

    await _run_bg_and_wait("exit 0")
    created = await MonitorTool().execute(
        MonitorParams(kind="bash_status", bash_id="bg_1", description="build done")
    )
    assert created.success

    app = _FakeApp(is_running=True)
    app._poll_monitors()

    assert len(app._steer_queue) == 1
    _display, query, _images = app._steer_queue[0]
    assert "kind=bash_status bash_id=bg_1" in query
    assert "build done" in query
    # One-shot monitor is consumed.
    assert get_monitor_manager().list() == []


def test_identical_idle_notifications_are_deduped():
    # A recurring timer firing repeatedly while idle must not balloon the queue.
    app = _FakeApp(is_running=False)

    app._inject_agent_notification("<monitor id=mon_1>tick</monitor>", "Monitor mon_1 fired")
    app._inject_agent_notification("<monitor id=mon_1>tick</monitor>", "Monitor mon_1 fired")
    app._inject_agent_notification("<monitor id=mon_2>other</monitor>", "Monitor mon_2 fired")

    assert len(app._pending_bg_notifications) == 2
