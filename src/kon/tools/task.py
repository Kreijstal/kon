import asyncio

from pydantic import BaseModel, Field

from ..core.subagent import AGENT_TYPES, DEFAULT_AGENT_TYPE, available_agent_types, run_subagent
from ..core.types import ToolResult
from .base import BaseTool


def _agent_type_help() -> str:
    lines = [f"'{t.name}': {t.description}" for t in available_agent_types()]
    return " ".join(lines)


class TaskParams(BaseModel):
    description: str = Field(description="A short (3-5 word) description of the task")
    prompt: str = Field(
        description=(
            "The full task for the subagent. Be specific and self-contained: the subagent "
            "does not see the current conversation and cannot ask follow-up questions."
        )
    )
    subagent_type: str = Field(
        default=DEFAULT_AGENT_TYPE,
        description=f"Which subagent to use. Available: {', '.join(sorted(AGENT_TYPES))}.",
    )


class TaskTool(BaseTool):
    name = "task"
    tool_icon = "◆"
    params = TaskParams
    prompt_guidelines = (
        "Use the task tool to delegate a focused, self-contained piece of work to a subagent "
        "that runs autonomously with its own context window. Good for wide searches, "
        "independent investigations, or parallelizable chunks. Give it a complete prompt — it "
        "cannot see this conversation. Do simple single-step work yourself instead.",
    )
    description = (
        "Launch a subagent to autonomously handle a focused task and return a final report. "
        "The subagent has its own context window and a restricted toolset, runs to completion "
        "without user interaction, and cannot ask follow-up questions, so its prompt must be "
        f"complete and self-contained. Available subagent types — {_agent_type_help()}"
    )

    def format_call(self, params: TaskParams) -> str:
        return f"{params.subagent_type}: {params.description}"

    def format_preview(self, params: TaskParams) -> str | None:
        return f"Launch '{params.subagent_type}' subagent: {params.description}\n\n{params.prompt}"

    async def execute(
        self, params: TaskParams, cancel_event: asyncio.Event | None = None
    ) -> ToolResult:
        result = await run_subagent(
            params.prompt, agent_type=params.subagent_type, cancel_event=cancel_event
        )

        stats = f"{result.agent_type} · {result.turns} turns · {result.tool_calls} tools"

        if result.error and not result.report:
            return ToolResult(
                success=False,
                result=result.error,
                ui_summary=f"[red]subagent failed: {result.error}[/red]",
            )

        body = result.report
        if result.error:
            body = f"{result.report}\n\n[note] {result.error}"

        return ToolResult(
            success=True,
            result=body or "(subagent produced no output)",
            ui_summary=f"[dim]{stats}[/dim]",
            ui_details=result.report or None,
        )
