"""Tests for the subagent runner and the task tool."""

import json
from collections.abc import AsyncIterator

import pytest

from kon.core.subagent import (
    AGENT_TYPES,
    SubagentContext,
    _select_tools,
    run_subagent,
    set_subagent_context_provider,
)
from kon.core.types import (
    Message,
    StopReason,
    StreamDone,
    StreamPart,
    TextPart,
    ToolCallDelta,
    ToolCallStart,
    ToolDefinition,
    Usage,
)
from kon.events import AgentEndEvent, TextEndEvent, ToolApprovalEvent, ToolResultEvent
from kon.llm.base import BaseProvider, LLMStream, ProviderConfig
from kon.llm.providers.mock import MockProvider
from kon.loop import Agent
from kon.permissions import ApprovalResponse
from kon.session import Session
from kon.tools import DEFAULT_TOOLS, get_tools
from kon.tools.task import TaskParams, TaskTool


@pytest.fixture(autouse=True)
def _clear_context():
    yield
    set_subagent_context_provider(None)


def _register(provider, cwd):
    set_subagent_context_provider(
        lambda: SubagentContext(provider=provider, cwd=str(cwd), tools=get_tools(DEFAULT_TOOLS))
    )


@pytest.mark.asyncio
async def test_run_subagent_returns_final_report(tmp_path):
    _register(MockProvider(scenario="simple_text"), tmp_path)

    result = await run_subagent("investigate something", agent_type="general")

    assert result.report == "Hello, world!"
    assert result.stop_reason == StopReason.STOP
    assert result.error is None


@pytest.mark.asyncio
async def test_run_subagent_unknown_type_errors(tmp_path):
    _register(MockProvider(scenario="simple_text"), tmp_path)

    result = await run_subagent("x", agent_type="does-not-exist")

    assert result.report == ""
    assert result.error is not None
    assert "Unknown subagent_type" in result.error


@pytest.mark.asyncio
async def test_run_subagent_without_context_errors():
    set_subagent_context_provider(None)

    result = await run_subagent("x")

    assert result.error is not None
    assert "not available" in result.error


def test_subagent_excludes_task_tool():
    tools = get_tools(DEFAULT_TOOLS)
    names = {t.name for t in _select_tools(tools, AGENT_TYPES["general"])}
    assert "task" not in names
    assert {"read", "edit", "bash"} <= names


def test_explore_agent_is_read_only():
    tools = get_tools(DEFAULT_TOOLS)
    names = {t.name for t in _select_tools(tools, AGENT_TYPES["explore"])}
    assert "edit" not in names
    assert "write" not in names
    assert "read" in names


@pytest.mark.asyncio
async def test_task_tool_runs_subagent_and_summarizes(tmp_path):
    _register(MockProvider(scenario="simple_text"), tmp_path)

    result = await TaskTool().execute(
        TaskParams(
            description="check thing", prompt="look into the thing", subagent_type="general"
        )
    )

    assert result.success
    assert result.result == "Hello, world!"


@pytest.mark.asyncio
async def test_task_tool_reports_unknown_type(tmp_path):
    _register(MockProvider(scenario="simple_text"), tmp_path)

    result = await TaskTool().execute(
        TaskParams(description="x", prompt="y", subagent_type="bogus")
    )

    assert not result.success


class _ScriptedProvider(BaseProvider):
    """Returns pre-scripted stream parts, one list per stream() call."""

    name = "scripted"

    def __init__(self, responses: list[list[StreamPart]]):
        super().__init__(ProviderConfig(model="scripted"))
        self._responses = list(responses)

    async def _stream_impl(
        self,
        messages: list[Message],
        *,
        system_prompt: str | None = None,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMStream:
        parts = self._responses.pop(0)

        async def iterator() -> AsyncIterator[StreamPart]:
            for part in parts:
                yield part

        stream = LLMStream()
        stream.set_iterator(iterator())
        stream._usage = Usage(input_tokens=1, output_tokens=1)
        return stream

    def should_retry_for_error(self, error: Exception) -> bool:
        return False


@pytest.mark.asyncio
async def test_parent_agent_delegates_to_subagent_through_loop(tmp_path):
    # The subagent uses its own provider that produces the final report text.
    set_subagent_context_provider(
        lambda: SubagentContext(
            provider=MockProvider(scenario="simple_text"),
            cwd=str(tmp_path),
            tools=get_tools(DEFAULT_TOOLS),
        )
    )

    task_args = json.dumps(
        {"description": "look", "prompt": "investigate", "subagent_type": "general"}
    )
    parent_provider = _ScriptedProvider(
        [
            [
                ToolCallStart(id="t1", name="task", index=0, arguments={}),
                ToolCallDelta(index=0, arguments_delta=task_args),
                StreamDone(stop_reason=StopReason.TOOL_USE),
            ],
            [
                TextPart(text="Subagent finished the investigation."),
                StreamDone(stop_reason=StopReason.STOP),
            ],
        ]
    )

    agent = Agent(
        provider=parent_provider,
        tools=get_tools(DEFAULT_TOOLS),
        session=Session.in_memory(cwd=str(tmp_path)),
        cwd=str(tmp_path),
        system_prompt="test",
    )

    tool_result_text: str | None = None
    final_text: str | None = None
    async for event in agent.run("delegate this"):
        if isinstance(event, ToolApprovalEvent) and event.future is not None:
            event.future.set_result(ApprovalResponse.APPROVE)
        elif isinstance(event, ToolResultEvent) and event.result is not None:
            tool_result_text = "".join(str(getattr(c, "text", "")) for c in event.result.content)
        elif isinstance(event, TextEndEvent):
            final_text = event.text
        elif isinstance(event, AgentEndEvent):
            assert event.stop_reason == StopReason.STOP

    # The task tool's result (fed back to the parent) is the subagent's report.
    assert tool_result_text == "Hello, world!"
    assert final_text == "Subagent finished the investigation."
