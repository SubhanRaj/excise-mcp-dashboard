"""chat/loop.py's bounded tool loop. MCP_ENGINES.md §Chat and retrieval."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest

from app.chat import loop as chat_loop
from app.chat.loop import ChartEvent, DoneEvent, ToolCallEvent, ToolResultEvent, run_chat
from app.schemas import ChartArtifact, ChatRequest, ChatToolLoopExceededError, ToolCall, ToolResult


@dataclass
class _FakeChunk:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class _FakeOllama:
    """Stands in for OllamaClient.chat_stream — each call to chat_stream()
    pops the next canned turn (a list of chunks) off the queue.
    """

    def __init__(self, turns: list[list[_FakeChunk]]) -> None:
        self._turns = list(turns)

    async def chat_stream(
        self, *, model: str, messages: object, tools: object
    ) -> AsyncIterator[object]:
        for chunk in self._turns.pop(0):
            yield chunk


def _request(message: str = "hello") -> ChatRequest:
    return ChatRequest(conversation_id="c1", message=message)


async def _events(ollama: _FakeOllama) -> list[object]:
    return [
        e
        async for e in run_chat(
            _request(),
            pool=object(),  # type: ignore[arg-type]
            ollama=ollama,  # type: ignore[arg-type]
            schema_card="(s)",
        )
    ]


async def test_a_turn_with_no_tool_call_ends_at_done() -> None:
    ollama = _FakeOllama([[_FakeChunk(content="Hi there.")]])
    events = await _events(ollama)
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].tool_calls_count == 0


async def test_a_turn_with_one_tool_call_dispatches_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = ToolCall(name="search_knowledge", arguments={"query": "MGQ"})
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="", tool_calls=[call])],
            [_FakeChunk(content="Here is what I found.")],
        ]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="found it", chart=None)

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(ollama)
    assert any(isinstance(e, ToolCallEvent) and e.name == "search_knowledge" for e in events)
    assert any(isinstance(e, ToolResultEvent) and e.summary == "found it" for e in events)
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].tool_calls_count == 1


async def test_a_tool_result_with_a_chart_emits_a_chart_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = ToolCall(name="make_chart", arguments={"spec": "x", "data_ref": "c1"})
    ollama = _FakeOllama(
        [[_FakeChunk(content="", tool_calls=[call])], [_FakeChunk(content="Done.")]]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="chart made", chart=ChartArtifact(plotly_json="{}"))

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(ollama)
    assert any(isinstance(e, ChartEvent) for e in events)


async def test_exceeding_the_tool_call_cap_raises_the_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_loop.settings, "chat_max_tool_calls", 1)
    call = ToolCall(name="search_knowledge", arguments={"query": "x"})
    # Every turn keeps calling the tool, so the loop never reaches a bare "done".
    ollama = _FakeOllama([[_FakeChunk(content="", tool_calls=[call])] for _ in range(5)])

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="again")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    with pytest.raises(ChatToolLoopExceededError):
        await _events(ollama)
