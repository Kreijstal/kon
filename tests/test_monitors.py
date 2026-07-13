"""Tests for the monitor manager and the monitor tool (timers + bash conditions)."""

import asyncio

import pytest

from kon.background import get_background_manager, reset_background_manager
from kon.monitors import get_monitor_manager, reset_monitor_manager
from kon.tools.bash import BashParams, BashTool
from kon.tools.monitor import MonitorParams, MonitorTool


@pytest.fixture(autouse=True)
def _reset():
    reset_monitor_manager()
    reset_background_manager()
    yield
    reset_monitor_manager()
    reset_background_manager()


# -- manager: timers -------------------------------------------------------------


def test_one_shot_timer_fires_once_then_deactivates():
    mgr = get_monitor_manager()
    mgr.create_timer("wake me", delay=5, now=0.0)

    assert mgr.poll(now=4.0) == []  # not yet
    fired = mgr.poll(now=5.0)
    assert len(fired) == 1
    assert "Timer fired: wake me" in fired[0][1]
    # One-shot deactivates and is dropped.
    assert mgr.poll(now=10.0) == []
    assert mgr.list() == []


def test_recurring_timer_fires_repeatedly():
    mgr = get_monitor_manager()
    mgr.create_timer("tick", interval=10, now=0.0)

    assert mgr.poll(now=5.0) == []
    assert len(mgr.poll(now=10.0)) == 1
    assert mgr.poll(now=15.0) == []
    assert len(mgr.poll(now=25.0)) == 1
    # Still active (recurring).
    assert len(mgr.list()) == 1


def test_timer_requires_delay_or_interval():
    mgr = get_monitor_manager()
    with pytest.raises(ValueError):
        mgr.create_timer("bad", now=0.0)


def test_stop_removes_monitor():
    mgr = get_monitor_manager()
    monitor = mgr.create_timer("x", interval=10, now=0.0)
    assert mgr.stop(monitor.id) is not None
    assert mgr.get(monitor.id) is None
    assert mgr.poll(now=100.0) == []


# -- manager: bash conditions ----------------------------------------------------


async def _wait_done(task, tries=100):
    for _ in range(tries):
        if not task.is_running:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("task did not finish")


@pytest.mark.asyncio
async def test_bash_match_fires_when_pattern_appears():
    await BashTool().execute(
        BashParams(command="printf 'starting\\n'; printf 'server ready\\n'", background=True)
    )
    task = get_background_manager().get("bg_1")
    await _wait_done(task)

    mgr = get_monitor_manager()
    mgr.create_bash_match("ready", bash_id="bg_1", pattern="server ready")
    fired = mgr.poll()
    assert len(fired) == 1
    assert "matched" in fired[0][1]
    assert "server ready" in fired[0][1]
    # One-shot: gone afterwards.
    assert mgr.list() == []


@pytest.mark.asyncio
async def test_bash_match_reports_when_task_ends_without_match():
    await BashTool().execute(BashParams(command="printf 'nothing here\\n'", background=True))
    task = get_background_manager().get("bg_1")
    await _wait_done(task)

    mgr = get_monitor_manager()
    mgr.create_bash_match("never", bash_id="bg_1", pattern="WILL-NOT-APPEAR")
    fired = mgr.poll()
    assert len(fired) == 1
    assert "ended" in fired[0][1]
    assert mgr.list() == []


@pytest.mark.asyncio
async def test_bash_status_fires_on_completion():
    await BashTool().execute(BashParams(command="exit 2", background=True))
    task = get_background_manager().get("bg_1")

    mgr = get_monitor_manager()
    mgr.create_bash_status("done", bash_id="bg_1")

    # While running: no fire.
    if task.is_running:
        assert mgr.poll() == []
    await _wait_done(task)
    fired = mgr.poll()
    assert len(fired) == 1
    assert "reached status failed" in fired[0][1]
    assert "exit=2" in fired[0][1]


# -- tool ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_create_list_stop_timer():
    tool = MonitorTool()

    created = await tool.execute(
        MonitorParams(kind="timer", description="ping", interval_seconds=30)
    )
    assert created.success
    assert "mon_1" in created.result

    listed = await tool.execute(MonitorParams(action="list"))
    assert "mon_1" in listed.result

    stopped = await tool.execute(MonitorParams(action="stop", monitor_id="mon_1"))
    assert stopped.success

    listed2 = await tool.execute(MonitorParams(action="list"))
    assert "No active monitors" in listed2.result


@pytest.mark.asyncio
async def test_tool_timer_requires_time_arg():
    result = await MonitorTool().execute(MonitorParams(kind="timer", description="x"))
    assert not result.success
    assert "delay_seconds or interval_seconds" in result.result


@pytest.mark.asyncio
async def test_tool_bash_match_validates_task_and_regex():
    unknown = await MonitorTool().execute(
        MonitorParams(kind="bash_match", bash_id="bg_99", pattern="x")
    )
    assert not unknown.success
    assert "No background task" in unknown.result

    await BashTool().execute(BashParams(command="sleep 5", background=True))
    bad_regex = await MonitorTool().execute(
        MonitorParams(kind="bash_match", bash_id="bg_1", pattern="(")
    )
    assert not bad_regex.success
    assert "Invalid regex" in bad_regex.result


@pytest.mark.asyncio
async def test_tool_unknown_kind_and_action():
    bad_kind = await MonitorTool().execute(MonitorParams(kind="nope"))
    assert not bad_kind.success
    bad_action = await MonitorTool().execute(MonitorParams(action="frobnicate"))
    assert not bad_action.success
