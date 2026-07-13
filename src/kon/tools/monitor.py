import asyncio
import re

from pydantic import BaseModel, Field

from ..background import get_background_manager
from ..core.types import ToolResult
from ..monitors import Monitor, get_monitor_manager
from .base import BaseTool


class MonitorParams(BaseModel):
    action: str = Field(default="create", description="One of: 'create', 'list', 'stop'.")
    kind: str | None = Field(
        default=None,
        description=(
            "For action=create, the monitor kind: "
            "'timer' (fire after a delay or on an interval), "
            "'bash_match' (fire when a background task's output matches a regex), or "
            "'bash_status' (fire when a background task finishes)."
        ),
    )
    description: str | None = Field(
        default=None, description="Short human description of what this monitor is for."
    )
    delay_seconds: float | None = Field(
        default=None, description="timer: fire once this many seconds from now."
    )
    interval_seconds: float | None = Field(
        default=None, description="timer: fire repeatedly every this many seconds."
    )
    bash_id: str | None = Field(
        default=None, description="bash_match/bash_status: the background task id to watch."
    )
    pattern: str | None = Field(
        default=None, description="bash_match: regular expression to search for in the output."
    )
    monitor_id: str | None = Field(
        default=None, description="action=stop: the monitor id to remove."
    )


def _describe(monitor: Monitor) -> str:
    return f"- {monitor.summary()}"


class MonitorTool(BaseTool):
    name = "monitor"
    tool_icon = "◷"
    # Monitors are lightweight watchers the agent manages itself; no approval prompt.
    mutating = False
    params = MonitorParams
    prompt_guidelines = (
        "Use monitor to be notified about events without polling: a timer "
        "(delay/interval), a background task finishing (bash_status), or a pattern appearing in "
        "a background task's output (bash_match, e.g. 'server listening'). You are notified "
        "automatically when a monitor fires; use action='list'/'stop' to manage them. Monitors "
        "only advance in the interactive TUI, not in one-shot headless runs.",
    )
    description = (
        "Create, list, or stop monitors that notify you when something happens — a timer "
        "elapses (delay or recurring interval), a background task finishes (bash_status), or a "
        "regex matches a background task's output (bash_match). You are notified automatically "
        "when a monitor fires, so you don't have to poll."
    )

    def format_call(self, params: MonitorParams) -> str:
        if params.action != "create":
            return f"{params.action} {params.monitor_id or ''}".strip()
        return f"create {params.kind or '?'}: {params.description or ''}".strip()

    async def execute(
        self, params: MonitorParams, cancel_event: asyncio.Event | None = None
    ) -> ToolResult:
        manager = get_monitor_manager()

        if params.action == "list":
            monitors = manager.list()
            if not monitors:
                return ToolResult(success=True, result="No active monitors.")
            body = "\n".join(_describe(m) for m in monitors)
            return ToolResult(
                success=True,
                result=f"Active monitors:\n{body}",
                ui_summary=f"[dim]{len(monitors)} active[/dim]",
            )

        if params.action == "stop":
            if not params.monitor_id:
                return self._error("monitor_id is required for action='stop'")
            removed = manager.stop(params.monitor_id)
            if removed is None:
                return self._error(f"No monitor with id {params.monitor_id!r}")
            return ToolResult(
                success=True,
                result=f"Stopped monitor {removed.id}.",
                ui_summary=f"[yellow]stopped {removed.id}[/yellow]",
            )

        if params.action != "create":
            return self._error(f"Unknown action {params.action!r}; use create/list/stop.")

        return self._create(manager, params)

    def _create(self, manager, params: MonitorParams) -> ToolResult:
        description = params.description or params.kind or "monitor"

        if params.kind == "timer":
            if params.delay_seconds is None and params.interval_seconds is None:
                return self._error("timer needs delay_seconds or interval_seconds")
            try:
                monitor = manager.create_timer(
                    description, delay=params.delay_seconds, interval=params.interval_seconds
                )
            except ValueError as e:
                return self._error(str(e))

        elif params.kind == "bash_match":
            if not params.bash_id or not params.pattern:
                return self._error("bash_match needs bash_id and pattern")
            if get_background_manager().get(params.bash_id) is None:
                return self._error(f"No background task with id {params.bash_id!r}")
            try:
                re.compile(params.pattern)
            except re.error as e:
                return self._error(f"Invalid regex pattern: {e}")
            monitor = manager.create_bash_match(
                description, bash_id=params.bash_id, pattern=params.pattern
            )

        elif params.kind == "bash_status":
            if not params.bash_id:
                return self._error("bash_status needs bash_id")
            if get_background_manager().get(params.bash_id) is None:
                return self._error(f"No background task with id {params.bash_id!r}")
            monitor = manager.create_bash_status(description, bash_id=params.bash_id)

        else:
            return self._error(
                f"Unknown monitor kind {params.kind!r}; use timer/bash_match/bash_status."
            )

        return ToolResult(
            success=True,
            result=f"Created monitor {monitor.id}: {monitor.summary()}",
            ui_summary=f"[dim]{monitor.id}[/dim]",
        )

    @staticmethod
    def _error(message: str) -> ToolResult:
        return ToolResult(success=False, result=message, ui_summary=f"[red]{message}[/red]")
