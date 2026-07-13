"""Tests for the managed background task registry and its lifecycle tools."""

import asyncio

import pytest

from kon.background import get_background_manager, reset_background_manager
from kon.tools.bash import BashParams, BashTool
from kon.tools.bash_output import BashOutputParams, BashOutputTool
from kon.tools.kill_bash import KillBashParams, KillBashTool


@pytest.fixture(autouse=True)
def _reset_manager():
    reset_background_manager()
    yield
    reset_background_manager()


async def _wait_until_done(task, tries: int = 100) -> None:
    for _ in range(tries):
        if not task.is_running:
            return
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_background_command_registers_and_completes():
    result = await BashTool().execute(
        BashParams(command="printf 'hello\\n'; exit 0", background=True)
    )
    assert result.success
    assert "Background task id: bg_1" in (result.result or "")

    manager = get_background_manager()
    task = manager.get("bg_1")
    assert task is not None

    await _wait_until_done(task)
    assert not task.is_running
    assert task.status == "completed"
    assert task.returncode == 0


@pytest.mark.asyncio
async def test_poll_completed_reports_each_task_once():
    await BashTool().execute(BashParams(command="exit 0", background=True))
    manager = get_background_manager()
    task = manager.get("bg_1")
    assert task is not None

    await _wait_until_done(task)
    completed = manager.poll_completed()
    assert [t.id for t in completed] == ["bg_1"]
    # Subsequent polls must not re-report the same completion.
    assert manager.poll_completed() == []


@pytest.mark.asyncio
async def test_bash_output_streams_new_output_incrementally():
    await BashTool().execute(
        BashParams(command="printf 'first\\n'; sleep 0.3; printf 'second\\n'", background=True)
    )
    tool = BashOutputTool()
    seen = ""

    task = get_background_manager().get("bg_1")
    assert task is not None
    for _ in range(100):
        res = await tool.execute(BashOutputParams(bash_id="bg_1"))
        seen += res.result or ""
        if "first" in seen and "second" in seen:
            break
        await asyncio.sleep(0.05)

    assert "first" in seen
    assert "second" in seen


@pytest.mark.asyncio
async def test_bash_output_reports_status_and_unknown_id():
    unknown = await BashOutputTool().execute(BashOutputParams(bash_id="bg_999"))
    assert not unknown.success
    assert "No background task" in (unknown.result or "")

    await BashTool().execute(BashParams(command="exit 3", background=True))
    task = get_background_manager().get("bg_1")
    assert task is not None
    await _wait_until_done(task)

    res = await BashOutputTool().execute(BashOutputParams(bash_id="bg_1"))
    assert res.success
    assert "failed" in (res.result or "")
    assert "exit code 3" in (res.result or "")


@pytest.mark.asyncio
async def test_kill_bash_terminates_running_task():
    await BashTool().execute(BashParams(command="sleep 30", background=True))
    manager = get_background_manager()
    task = manager.get("bg_1")
    assert task is not None
    assert task.is_running

    result = await KillBashTool().execute(KillBashParams(bash_id="bg_1"))
    assert result.success
    assert task.status == "killed"
    assert not task.is_running


@pytest.mark.asyncio
async def test_kill_bash_unknown_id_errors():
    result = await KillBashTool().execute(KillBashParams(bash_id="bg_404"))
    assert not result.success
    assert "No background task" in (result.result or "")
