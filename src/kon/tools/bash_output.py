import asyncio

from pydantic import BaseModel, Field

from ..background import BackgroundTask, get_background_manager
from ..core.types import ToolResult
from .base import BaseTool


def _status_summary(task: BackgroundTask) -> str:
    if task.status == "running":
        return f"[dim]{task.id} running (pid {task.pid})[/dim]"
    if task.status == "completed":
        return f"[dim]{task.id} completed (exit 0)[/dim]"
    if task.status == "killed":
        return f"[yellow]{task.id} killed[/yellow]"
    return f"[red]{task.id} failed (exit {task.returncode})[/red]"


class BashOutputParams(BaseModel):
    bash_id: str = Field(description="The background task id returned by bash (e.g. 'bg_1')")


class BashOutputTool(BaseTool):
    name = "bash_output"
    tool_icon = "$"
    mutating = False
    params = BashOutputParams
    prompt_guidelines = (
        "Use bash_output to read new output from a background bash task (started with "
        "background=true). Repeated calls return only output produced since the last call.",
    )
    description = (
        "Retrieve output produced by a background bash task since the last check. "
        "Returns the new output plus the task's current status "
        "(running, completed, failed, or killed)."
    )

    def format_call(self, params: BashOutputParams) -> str:
        return params.bash_id

    async def execute(
        self, params: BashOutputParams, cancel_event: asyncio.Event | None = None
    ) -> ToolResult:
        task = get_background_manager().get(params.bash_id)
        if task is None:
            msg = f"No background task with id {params.bash_id!r}"
            return ToolResult(success=False, result=msg, ui_summary=f"[red]{msg}[/red]")

        task._refresh()
        new_output = task.read_new_output()

        status_line = f"Status: {task.status}"
        if task.returncode is not None:
            status_line += f" (exit code {task.returncode})"

        body = new_output if new_output else "(no new output)"
        result = f"{status_line}\n\n{body}"

        ui_details = new_output.strip() or None
        return ToolResult(
            success=True, result=result, ui_summary=_status_summary(task), ui_details=ui_details
        )
