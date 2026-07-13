import asyncio

from pydantic import BaseModel, Field

from ..background import get_background_manager
from ..core.types import ToolResult
from .base import BaseTool


class KillBashParams(BaseModel):
    bash_id: str = Field(description="The background task id to terminate (e.g. 'bg_1')")


class KillBashTool(BaseTool):
    name = "kill_bash"
    tool_icon = "$"
    # Terminating an agent-started background task is a management action, not a
    # destructive edit; allow it without an approval prompt.
    mutating = False
    params = KillBashParams
    prompt_guidelines = (
        "Use kill_bash to stop a background bash task once you no longer need it "
        "(e.g. a dev server started with background=true).",
    )
    description = (
        "Terminate a running background bash task by its id. "
        "Kills the whole process group started by the background command."
    )

    def format_call(self, params: KillBashParams) -> str:
        return params.bash_id

    async def execute(
        self, params: KillBashParams, cancel_event: asyncio.Event | None = None
    ) -> ToolResult:
        manager = get_background_manager()
        if manager.get(params.bash_id) is None:
            msg = f"No background task with id {params.bash_id!r}"
            return ToolResult(success=False, result=msg, ui_summary=f"[red]{msg}[/red]")

        task = await manager.kill(params.bash_id)
        assert task is not None

        if task.status == "killed":
            msg = f"Killed background task {task.id} (pid {task.pid})"
            return ToolResult(success=True, result=msg, ui_summary=f"[yellow]{msg}[/yellow]")

        # Already finished before we could kill it.
        msg = f"Background task {task.id} already finished with status {task.status}"
        if task.returncode is not None:
            msg += f" (exit code {task.returncode})"
        return ToolResult(success=True, result=msg, ui_summary=f"[dim]{msg}[/dim]")
