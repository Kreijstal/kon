"""
Monitors: lightweight events and timers that notify the agent.

A monitor watches a condition in the background and fires a one-line note to the
agent when it becomes true — the same delivery path as background-task
completions (steer message while the agent runs, folded into the next turn while
idle). Kinds:

- ``timer``       — fire once after ``delay`` seconds, or repeatedly every
                    ``interval`` seconds.
- ``bash_match``  — fire when a background task's output matches a regex.
- ``bash_status`` — fire when a background task reaches a terminal status.

Like :mod:`kon.background`, the manager is a per-process singleton and is polled
by the app's event loop, so no locking is required. Timers only advance while
that poll loop runs (i.e. in the interactive TUI).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Literal

from .background import BackgroundTaskManager, get_background_manager

MonitorKind = Literal["timer", "bash_match", "bash_status"]

_TERMINAL_STATUSES: tuple[str, ...] = ("completed", "failed", "killed")


@dataclass
class Monitor:
    id: str
    kind: MonitorKind
    description: str
    active: bool = True
    # timer
    interval: float | None = None
    next_fire: float | None = None
    # bash_match / bash_status
    bash_id: str | None = None
    pattern: str | None = None
    statuses: tuple[str, ...] | None = None
    _regex: re.Pattern[str] | None = field(default=None, repr=False)
    _bash_offset: int = field(default=0, repr=False)

    def summary(self) -> str:
        if self.kind == "timer":
            when = "recurring" if self.interval is not None else "one-shot"
            return f"{self.id} timer ({when}): {self.description}"
        return f"{self.id} {self.kind} on {self.bash_id}: {self.description}"

    def evaluate(self, now: float, bg: BackgroundTaskManager) -> str | None:
        """Return a fire message if the condition is met this tick, else None.

        Deactivates one-shot monitors after firing (and reschedules recurring
        timers).
        """
        if not self.active:
            return None
        if self.kind == "timer":
            return self._evaluate_timer(now)
        return self._evaluate_bash(bg)

    def _evaluate_timer(self, now: float) -> str | None:
        if self.next_fire is None or now < self.next_fire:
            return None
        if self.interval is not None:
            # Reschedule from now to avoid a burst of catch-up fires.
            self.next_fire = now + self.interval
        else:
            self.active = False
        return f"<monitor id={self.id} kind=timer>\nTimer fired: {self.description}\n</monitor>"

    def _evaluate_bash(self, bg: BackgroundTaskManager) -> str | None:
        task = bg.get(self.bash_id) if self.bash_id else None
        if task is None:
            # The task went away (e.g. manager reset); stop watching quietly.
            self.active = False
            return None

        if self.kind == "bash_match":
            text, self._bash_offset = task.read_from(self._bash_offset)
            if self._regex is not None and text:
                match = self._regex.search(text)
                if match:
                    self.active = False
                    line = _matched_line(text, match)
                    return (
                        f"<monitor id={self.id} kind=bash_match bash_id={self.bash_id}>\n"
                        f"Pattern {self.pattern!r} matched in background task "
                        f"{self.bash_id} output.\n"
                        f"Matched: {line}\n"
                        f'Use bash_output with bash_id="{self.bash_id}" for full output.\n'
                        "</monitor>"
                    )
            if not task.is_running:
                # Task ended without ever matching; nothing more will arrive.
                self.active = False
                return (
                    f"<monitor id={self.id} kind=bash_match bash_id={self.bash_id}>\n"
                    f"Background task {self.bash_id} ended ({task.status}) before pattern "
                    f"{self.pattern!r} matched.\n"
                    "</monitor>"
                )
            return None

        # bash_status
        targets = self.statuses or _TERMINAL_STATUSES
        if not task.is_running and task.status in targets:
            self.active = False
            exit_part = f" exit={task.returncode}" if task.returncode is not None else ""
            return (
                f"<monitor id={self.id} kind=bash_status bash_id={self.bash_id}{exit_part}>\n"
                f"Background task {self.bash_id} reached status {task.status}: "
                f"{self.description}\n"
                "</monitor>"
            )
        return None


def _matched_line(text: str, match: re.Match[str]) -> str:
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    if end == -1:
        end = len(text)
    return text[start:end].strip()[:200]


class MonitorManager:
    def __init__(self) -> None:
        self._monitors: dict[str, Monitor] = {}
        self._counter = 0

    def _new_id(self) -> str:
        self._counter += 1
        return f"mon_{self._counter}"

    def create_timer(
        self,
        description: str,
        *,
        delay: float | None = None,
        interval: float | None = None,
        now: float | None = None,
    ) -> Monitor:
        if delay is None and interval is None:
            raise ValueError("A timer needs delay or interval (seconds).")
        for value in (delay, interval):
            if value is not None and value <= 0:
                raise ValueError("Timer delay/interval must be positive.")
        now = time.monotonic() if now is None else now
        if interval is not None:
            next_fire = now + (delay if delay is not None else interval)
        else:
            next_fire = now + delay  # type: ignore[operator]
        monitor = Monitor(
            id=self._new_id(),
            kind="timer",
            description=description,
            interval=interval,
            next_fire=next_fire,
        )
        self._monitors[monitor.id] = monitor
        return monitor

    def create_bash_match(
        self, description: str, *, bash_id: str, pattern: str, start_offset: int = 0
    ) -> Monitor:
        regex = re.compile(pattern)
        monitor = Monitor(
            id=self._new_id(),
            kind="bash_match",
            description=description,
            bash_id=bash_id,
            pattern=pattern,
            _regex=regex,
            _bash_offset=start_offset,
        )
        self._monitors[monitor.id] = monitor
        return monitor

    def create_bash_status(
        self, description: str, *, bash_id: str, statuses: tuple[str, ...] | None = None
    ) -> Monitor:
        monitor = Monitor(
            id=self._new_id(),
            kind="bash_status",
            description=description,
            bash_id=bash_id,
            statuses=statuses,
        )
        self._monitors[monitor.id] = monitor
        return monitor

    def get(self, monitor_id: str) -> Monitor | None:
        return self._monitors.get(monitor_id)

    def list(self, *, active_only: bool = True) -> list[Monitor]:
        monitors = self._monitors.values()
        if active_only:
            return [m for m in monitors if m.active]
        return list(monitors)

    def stop(self, monitor_id: str) -> Monitor | None:
        return self._monitors.pop(monitor_id, None)

    def poll(self, now: float | None = None) -> list[tuple[Monitor, str]]:
        now = time.monotonic() if now is None else now
        bg = get_background_manager()
        fired: list[tuple[Monitor, str]] = []
        for monitor in list(self._monitors.values()):
            message = monitor.evaluate(now, bg)
            if message is not None:
                fired.append((monitor, message))
        # Drop monitors that fired-and-finished (one-shot timers, matched/ended
        # bash monitors) so list() only shows live watches. Recurring timers stay.
        self._monitors = {mid: m for mid, m in self._monitors.items() if m.active}
        return fired


_manager: MonitorManager | None = None


def get_monitor_manager() -> MonitorManager:
    global _manager
    if _manager is None:
        _manager = MonitorManager()
    return _manager


def reset_monitor_manager() -> None:
    """Test helper: drop all monitors."""
    global _manager
    _manager = None
