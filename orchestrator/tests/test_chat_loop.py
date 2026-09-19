"""chat/loop.py's bounded tool loop. MCP_ENGINES.md §Chat and retrieval."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest

from app.chat import loop as chat_loop
from app.chat.loop import (
    ChartEvent,
    DoneEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    run_chat,
)
from app.schemas import (
    ChartArtifact,
    ChatRequest,
    ChatToolArgumentError,
    ChatToolLoopExceededError,
    ToolCall,
    ToolResult,
)


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
        self, *, model: str, messages: object, tools: object, usage: object = None
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


async def test_a_bare_brace_reply_retries_once_without_tools() -> None:
    # llama3.1's tool-calling template sometimes answers a trivial message
    # with a bare "{}" instead of prose, once tool schemas are attached —
    # confirmed live against Ollama. The loop must not show that to the
    # user; it retries the same turn once with tools=[] instead.
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="{"), _FakeChunk(content="}")],
            [_FakeChunk(content="Hello! How can I help?")],
        ]
    )
    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert tokens == "Hello! How can I help?"
    assert not any(isinstance(e, ToolCallEvent) for e in events)
    assert isinstance(events[-1], DoneEvent)


async def test_a_narrated_fake_tool_call_retries_once_without_tools() -> None:
    # Confirmed live: after an earlier tool call failed, llama3.1 answered a follow-up
    # turn with the literal text `run_sql_query(question="...")` instead of either a
    # real tool_calls entry or a plain-language answer — the same template failure as
    # the bare "{}" case, just narrating a call instead of emitting nothing.
    ollama = _FakeOllama(
        [
            [
                _FakeChunk(content="run"),
                _FakeChunk(content="_sql"),
                _FakeChunk(content='_query(question="x")'),
            ],
            [_FakeChunk(content="I couldn't find that — could you rephrase?")],
        ]
    )
    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert tokens == "I couldn't find that — could you rephrase?"
    assert not any(isinstance(e, ToolCallEvent) for e in events)


async def test_a_narrated_sql_guess_with_no_tool_call_retries_once() -> None:
    # Confirmed live: asked a two-metric question, the model skipped run_sql_query
    # entirely and instead wrote "let me try running the following query" followed
    # by a guessed SQL statement against a table that doesn't exist — exactly what
    # CHAT_SYSTEM_PROMPT tells it never to do, since it has never seen the schema.
    # The preamble before the fence still streams live (it doesn't look degenerate
    # until the "```sql" marker itself arrives) — the fenced SQL is what gets
    # withheld, and a clean retry follows it rather than ending the turn on a
    # guessed, wrong query.
    ollama = _FakeOllama(
        [
            [
                _FakeChunk(content="Let me try running the following query:\n\n"),
                _FakeChunk(content="```sql\nSELECT SUM(revenue) FROM excise_data;\n```"),
            ],
            [_FakeChunk(content="Here is the total for August 2026.")],
        ]
    )
    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert tokens == (
        "Let me try running the following query:\n\nHere is the total for August 2026."
    )
    assert "SELECT" not in tokens
    assert not any(isinstance(e, ToolCallEvent) for e in events)


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


async def test_a_bad_tool_call_argument_is_fed_back_instead_of_ending_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # dispatch() raises ChatToolArgumentError for a schema-invalid call (e.g. a search_knowledge
    # call missing its required query). This used to propagate out of run_chat() uncaught and
    # kill the whole turn — the same shape a rejected/failing run_sql_query or make_chart call
    # already avoids by coming back as a failed tool result instead.
    call = ToolCall(name="search_knowledge", arguments={})
    ollama = _FakeOllama(
        [[_FakeChunk(content="", tool_calls=[call])], [_FakeChunk(content="Here's what I found.")]]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        raise ChatToolArgumentError("search_knowledge", "query is required")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(ollama)
    assert any(
        isinstance(e, ToolResultEvent) and e.ok is False and "query is required" in e.summary
        for e in events
    )
    assert isinstance(events[-1], DoneEvent)


async def test_a_silent_reply_after_a_tool_call_falls_back_to_the_tool_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Confirmed live: after a real run_sql_query call, an 8B model sometimes produces no
    # follow-up content at all — not even a bare "{}" — on either the tool-aware attempt
    # or the tools=[] retry. Before this fallback, the turn ended with a DoneEvent and
    # nothing shown past the tool call card.
    call = ToolCall(name="run_sql_query", arguments={"question": "x"})
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="", tool_calls=[call])],
            [_FakeChunk(content="")],
            [_FakeChunk(content="")],
        ]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(
            ok=True, summary="560 row(s), columns: ['count']. Preview: [{'count': 560}]"
        )

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert tokens == "560 row(s), columns: ['count']. Preview: [{'count': 560}]"
    assert isinstance(events[-1], DoneEvent)


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
