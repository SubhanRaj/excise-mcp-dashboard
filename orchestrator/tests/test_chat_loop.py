"""chat/loop.py's bounded tool loop. MCP_ENGINES.md §Chat and retrieval."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest

from app.chat import loop as chat_loop
from app.chat.loop import (
    ChartEvent,
    DoneEvent,
    HeartbeatEvent,
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
    # The whole reply streams live — a fenced sql block can't be told apart from
    # ordinary prose until most of it has arrived, and withholding a live stream
    # for that long is what broke a real turn's connection (it went silent long
    # enough for the browser to drop it as interrupted). A clean retry streams
    # right after, rather than ending the turn on the guessed, wrong query.
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
        "Let me try running the following query:\n\n"
        "```sql\nSELECT SUM(revenue) FROM excise_data;\n```"
        "Here is the total for August 2026."
    )
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
    call = ToolCall(name="make_chart", arguments={"spec": "x"})
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


async def test_a_failed_tool_call_narrated_again_on_retry_falls_back_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Confirmed live: after a real run_sql_query call failed with a Postgres column
    # error, the tools=[] retry narrated the exact same fake call again
    # (`run_sql_query(question="...")`) instead of a plain answer — the retry had no
    # holdback of its own, so the garbled text streamed straight to the user. Both
    # attempts must be held back the same way, and the final answer must state the
    # failure in plain terms plus the technical detail, not just repeat the raw
    # database error as if it were the whole reply.
    call = ToolCall(name="run_sql_query", arguments={"question": "x"})
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="", tool_calls=[call])],
            [
                _FakeChunk(content="run"),
                _FakeChunk(content="_sql"),
                _FakeChunk(content='_query(question="x")'),
            ],
            [
                _FakeChunk(content="run"),
                _FakeChunk(content="_sql"),
                _FakeChunk(content='_query(question="x")'),
            ],
        ]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=False, summary="column sv.shop_id does not exist")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert "run_sql_query(" not in tokens
    assert "column sv.shop_id does not exist" in tokens
    assert "couldn't finish this part of the analysis" in tokens
    assert isinstance(events[-1], DoneEvent)


async def test_a_slow_tool_call_emits_heartbeats_before_its_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A compound question chains several full LLM round trips inside one tool call
    # (build_sql_prompt -> generate_structured -> guard_sql -> run_sql) — long enough,
    # unheartbeated, that a client-side idle timeout dropped a real connection before the
    # turn ever reached done/error. dispatch() runs as a background task so the loop can
    # keep yielding pings while it's still in flight.
    monkeypatch.setattr(chat_loop, "_HEARTBEAT_INTERVAL_S", 0.01)
    call = ToolCall(name="run_sql_query", arguments={"question": "x"})
    ollama = _FakeOllama(
        [[_FakeChunk(content="", tool_calls=[call])], [_FakeChunk(content="Done.")]]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        await asyncio.sleep(0.05)
        return ToolResult(ok=True, summary="slow result")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(ollama)
    heartbeat_index = next(i for i, e in enumerate(events) if isinstance(e, HeartbeatEvent))
    result_index = next(i for i, e in enumerate(events) if isinstance(e, ToolResultEvent) and e.ok)
    assert heartbeat_index < result_index


async def test_make_chart_dispatches_after_run_sql_query_in_the_same_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Confirmed live: llama3.1 sometimes emits both calls for one turn at once, and
    # not always in query-then-chart order. A make_chart dispatched before its
    # run_sql_query always fails (chat/tools.py's _LAST_RESULT isn't set yet), so the
    # loop must dispatch run_sql_query first regardless of the order the model listed
    # them in.
    sql_call = ToolCall(name="run_sql_query", arguments={"question": "x"})
    chart_call = ToolCall(name="make_chart", arguments={"spec": "x"})
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="", tool_calls=[chart_call, sql_call])],
            [_FakeChunk(content="Here it is.")],
        ]
    )

    dispatched_order: list[str] = []

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        dispatched_order.append(call.name)
        return ToolResult(ok=True, summary="ok")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    await _events(ollama)
    assert dispatched_order == ["run_sql_query", "make_chart"]


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
