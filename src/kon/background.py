"""
Managed background shell tasks.

Kon's `bash(background=true)` spawns a detached process. Rather than fire and
forget, each detached process is registered here so the agent can:

- poll incremental output (`bash_output` tool),
- terminate it (`kill_bash` tool),
- be notified when it completes (the TUI polls `poll_completed()` and injects a
  message into the running or next turn).

The manager is a per-process singleton: one Kon process owns one set of
background tasks. Everything runs on the app's event loop, so no locking is
needed.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

BackgroundStatus = Literal["running", "completed", "failed", "killed"]

_IS_WINDOWS = sys.platform == "win32"
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][AB012]")


def _sanitize(text: str) -> str:
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "")
    return "".join(c for c in text if c >= " " or c in "\t\n")


async def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        if _IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), timeout=5)
    except (ProcessLookupError, PermissionError, OSError):
        pass


@dataclass
class BackgroundTask:
    id: str
    command: str
    proc: asyncio.subprocess.Process
    log_path: str
    status: BackgroundStatus = "running"
    returncode: int | None = None
    # Byte offset already returned by bash_output, so repeated calls stream new output.
    read_offset: int = 0
    # True once the completion transition has been surfaced to the UI/agent.
    completion_reported: bool = False
    _killed: bool = field(default=False, repr=False)

    @property
    def pid(self) -> int:
        return self.proc.pid

    def _refresh(self) -> None:
        """Sync status from the underlying process state."""
        if self.status in ("completed", "failed", "killed"):
            return
        code = self.proc.returncode
        if code is None:
            return
        self.returncode = code
        if self._killed:
            self.status = "killed"
        elif code == 0:
            self.status = "completed"
        else:
            self.status = "failed"

    @property
    def is_running(self) -> bool:
        self._refresh()
        return self.status == "running"

    def read_full_output(self) -> str:
        try:
            raw = Path(self.log_path).read_bytes()
        except OSError:
            return ""
        return _sanitize(raw.decode("utf-8", errors="replace"))

    def read_new_output(self) -> str:
        """Return output written since the last read and advance the offset."""
        try:
            data = Path(self.log_path).read_bytes()
        except OSError:
            return ""
        chunk = data[self.read_offset :]
        self.read_offset = len(data)
        return _sanitize(chunk.decode("utf-8", errors="replace"))

    def read_from(self, offset: int) -> tuple[str, int]:
        """Read output starting at ``offset`` without touching the shared read
        offset. Returns (text, new_offset). Used by monitors so they can scan
        output independently of the bash_output tool."""
        try:
            data = Path(self.log_path).read_bytes()
        except OSError:
            return "", offset
        chunk = data[offset:]
        return _sanitize(chunk.decode("utf-8", errors="replace")), len(data)


class BackgroundTaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}
        self._counter = 0

    def register(
        self, command: str, proc: asyncio.subprocess.Process, log_path: str
    ) -> BackgroundTask:
        self._counter += 1
        task_id = f"bg_{self._counter}"
        task = BackgroundTask(id=task_id, command=command, proc=proc, log_path=log_path)
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> BackgroundTask | None:
        return self._tasks.get(task_id)

    def list(self) -> list[BackgroundTask]:
        for task in self._tasks.values():
            task._refresh()
        return list(self._tasks.values())

    def running(self) -> list[BackgroundTask]:
        return [t for t in self.list() if t.status == "running"]

    def poll_completed(self) -> list[BackgroundTask]:
        """Return tasks that finished since the last poll (each reported once)."""
        done: list[BackgroundTask] = []
        for task in self._tasks.values():
            task._refresh()
            if task.status != "running" and not task.completion_reported:
                task.completion_reported = True
                done.append(task)
        return done

    async def kill(self, task_id: str) -> BackgroundTask | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if task.is_running:
            task._killed = True
            await _kill_process_tree(task.proc)
            task._refresh()
            if task.status == "running":
                # returncode may lag the kill on some platforms; force terminal state.
                task.status = "killed"
        return task

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            if task.is_running:
                task._killed = True
                await _kill_process_tree(task.proc)


_manager: BackgroundTaskManager | None = None


def get_background_manager() -> BackgroundTaskManager:
    global _manager
    if _manager is None:
        _manager = BackgroundTaskManager()
    return _manager


def reset_background_manager() -> None:
    """Test helper: drop all tracked tasks."""
    global _manager
    _manager = None
