"""
Subagents: run a nested agent loop to handle a focused task autonomously.

The `task` tool calls :func:`run_subagent`, which spins up a fresh in-memory
:class:`~kon.loop.Agent` sharing the parent's provider but with its own context
window and a restricted toolset (no recursive `task` tool). The subagent runs to
completion headlessly — its tool calls are auto-approved — and its final text is
returned to the parent as the tool result.

The parent registers a context provider (:func:`set_subagent_context_provider`)
so the tool can reach the live provider/tools without threading them through
every tool's ``execute`` signature.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..core.types import StopReason, Usage

if TYPE_CHECKING:
    from ..llm import BaseProvider
    from ..tools import BaseTool


@dataclass
class AgentType:
    name: str
    description: str
    # Allowed tool names; None means "all subagent tools".
    tools: frozenset[str] | None = None


AGENT_TYPES: dict[str, AgentType] = {
    "general": AgentType(
        name="general",
        description="General-purpose agent for multi-step tasks (read, edit, run commands).",
    ),
    "explore": AgentType(
        name="explore",
        description="Read-only agent for searching and understanding code; cannot edit files.",
        tools=frozenset({"read", "grep", "find", "web_search", "web_fetch"}),
    ),
}
DEFAULT_AGENT_TYPE = "general"

_SUBAGENT_DIRECTIVE = (
    "\n\n# Subagent\n\n"
    "You are a subagent launched by the main Kon agent to handle one focused task "
    "autonomously. Work independently with your tools. You cannot ask the user questions — "
    "there is no one to answer. When finished, reply with a concise final report of what you "
    "found or changed, with concrete results (file paths, findings, commands run, outcomes). "
    "That report is the only thing returned to the main agent, so make it self-contained."
)


@dataclass
class SubagentContext:
    provider: BaseProvider
    cwd: str
    tools: list[BaseTool]
    context_window: int | None = None
    max_output_tokens: int | None = None


@dataclass
class SubagentResult:
    report: str
    agent_type: str
    turns: int = 0
    tool_calls: int = 0
    usage: Usage | None = None
    stop_reason: StopReason = StopReason.STOP
    error: str | None = None
    activity: list[str] = field(default_factory=list)


_context_provider: Callable[[], SubagentContext | None] | None = None


def set_subagent_context_provider(provider: Callable[[], SubagentContext | None] | None) -> None:
    global _context_provider
    _context_provider = provider


def get_subagent_context() -> SubagentContext | None:
    if _context_provider is None:
        return None
    return _context_provider()


def available_agent_types() -> list[AgentType]:
    return list(AGENT_TYPES.values())


def _select_tools(base_tools: list[BaseTool], agent_type: AgentType) -> list[BaseTool]:
    # Never expose the task tool to a subagent (prevents unbounded recursion), nor
    # the monitor tool (its watches would outlive the short-lived subagent and
    # notify the main agent about work it has no context for).
    excluded = {"task", "monitor"}
    tools = [t for t in base_tools if t.name not in excluded]
    if agent_type.tools is not None:
        tools = [t for t in tools if t.name in agent_type.tools]
    return tools


async def run_subagent(
    prompt: str, *, agent_type: str = DEFAULT_AGENT_TYPE, cancel_event: asyncio.Event | None = None
) -> SubagentResult:
    resolved_type = AGENT_TYPES.get(agent_type)
    if resolved_type is None:
        valid = ", ".join(sorted(AGENT_TYPES))
        return SubagentResult(
            report="",
            agent_type=agent_type,
            stop_reason=StopReason.ERROR,
            error=f"Unknown subagent_type {agent_type!r}. Valid types: {valid}.",
        )

    ctx = get_subagent_context()
    if ctx is None:
        return SubagentResult(
            report="",
            agent_type=agent_type,
            stop_reason=StopReason.ERROR,
            error="Subagents are not available in this context.",
        )

    # Imported lazily to avoid a circular import (permissions/tools -> subagent).
    from ..events import AgentEndEvent, ToolApprovalEvent, ToolEndEvent
    from ..loop import Agent, AgentConfig, build_system_prompt
    from ..permissions import ApprovalResponse
    from ..session import Session

    tools = _select_tools(ctx.tools, resolved_type)
    system_prompt = build_system_prompt(ctx.cwd, tools=tools) + _SUBAGENT_DIRECTIVE

    session = Session.in_memory(
        cwd=ctx.cwd, system_prompt=system_prompt, tools=[t.name for t in tools]
    )
    agent = Agent(
        provider=ctx.provider,
        tools=tools,
        session=session,
        cwd=ctx.cwd,
        system_prompt=system_prompt,
        config=AgentConfig(
            context_window=ctx.context_window, max_output_tokens=ctx.max_output_tokens
        ),
    )

    result = SubagentResult(report="", agent_type=agent_type)

    try:
        async for event in agent.run(prompt, cancel_event=cancel_event):
            if isinstance(event, ToolApprovalEvent):
                # Headless subagent: auto-approve its own tool calls.
                if event.future is not None and not event.future.done():
                    event.future.set_result(ApprovalResponse.APPROVE)
            elif isinstance(event, ToolEndEvent):
                result.tool_calls += 1
                label = event.display or event.tool_name
                result.activity.append(f"{event.tool_name}: {label}" if event.display else label)
            elif isinstance(event, AgentEndEvent):
                result.turns = event.total_turns
                result.usage = event.total_usage
                result.stop_reason = event.stop_reason
    except Exception as e:  # subagent failure must not crash the parent turn
        result.stop_reason = StopReason.ERROR
        result.error = str(e)

    result.report = session.get_last_assistant_text() or ""
    if not result.report and result.error is None:
        if result.stop_reason == StopReason.INTERRUPTED:
            result.error = "Subagent was interrupted before producing a report."
        else:
            result.error = "Subagent finished without producing a final report."
    return result
