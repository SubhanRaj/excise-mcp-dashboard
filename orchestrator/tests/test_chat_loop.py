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


def _request(message: str = "hello", *, want_chart: bool = False) -> ChatRequest:
    return ChatRequest(conversation_id="c1", turn_id="t1", message=message, want_chart=want_chart)


async def _events(ollama: _FakeOllama, *, want_chart: bool = False) -> list[object]:
    return [
        e
        async for e in run_chat(
            _request(want_chart=want_chart),
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


async def test_a_markdown_filler_only_reply_retries_once_without_tools() -> None:
    # Confirmed live: asked a knowledge question with real, substantial content
    # already retrieved, the model's whole reply — all 78 completion tokens Ollama
    # reported generating — reduced to a single streamed "#" with nothing else ever
    # released. Neither the bare-"{}" check nor the tool-name-prefix check catches a
    # lone markdown heading marker.
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="#")],
            [
                _FakeChunk(
                    content="A Composite Shop holds a combined Foreign Liquor + Beer license."
                )
            ],
        ]
    )
    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert tokens == "A Composite Shop holds a combined Foreign Liquor + Beer license."
    assert not any(isinstance(e, ToolCallEvent) for e in events)


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


async def test_a_raw_tool_call_json_fragment_mid_reply_retries_once() -> None:
    # Confirmed live: a reply answered normally, then trailed off into a raw
    # `{"name": "` — a tool-call JSON object narrated as text partway through an
    # otherwise real answer, not the whole reply degenerating the way the bare
    # "{}" and narrated-call cases in _is_degenerate already catch. Streams live
    # the same way the fenced-sql-guess case does, for the same reason (holding
    # a whole generation back risks the connection dropping as interrupted).
    ollama = _FakeOllama(
        [
            [
                _FakeChunk(content="I can try searching for relevant text:\n\n"),
                _FakeChunk(content='{"name": "'),
            ],
            [_FakeChunk(content="I couldn't find anything on that.")],
        ]
    )
    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert tokens == (
        'I can try searching for relevant text:\n\n{"name": "I couldn\'t find anything on that.'
    )
    assert not any(isinstance(e, ToolCallEvent) for e in events)


async def test_a_degenerate_reply_with_no_tool_call_ever_falls_back_to_a_retry_prompt() -> None:
    # Confirmed live: a fresh conversation's first turn (a knowledge question the
    # model tried to answer directly, never calling search_knowledge) came back
    # degenerate on both the tool-aware attempt and the tools=[] retry. Before this
    # fallback, _tool_failure_fallback only fired when last_tool_result was already
    # set — with no tool ever dispatched, that condition was always false, so the
    # turn ended on a DoneEvent with not a single character ever streamed.
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="{"), _FakeChunk(content="}")],
            [_FakeChunk(content="{"), _FakeChunk(content="}")],
        ]
    )
    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert tokens != ""
    assert not any(isinstance(e, ToolCallEvent) for e in events)
    assert isinstance(events[-1], DoneEvent)


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


async def test_a_successful_run_sql_query_triggers_a_chart_when_wanted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A chart is a deterministic step after a successful run_sql_query now, never
    # something the model calls or decides on itself — triggered here by
    # ChatRequest.want_chart, the composer toggle's own field, not a tool call.
    call = ToolCall(name="run_sql_query", arguments={"question": "x"})
    ollama = _FakeOllama(
        [[_FakeChunk(content="", tool_calls=[call])], [_FakeChunk(content="Done.")]]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="5 row(s)")

    async def fake_auto_chart(conversation_id: str, question: str, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="Chart rendered.", chart=ChartArtifact(plotly_json="{}"))

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)
    monkeypatch.setattr(chat_loop, "auto_chart", fake_auto_chart)

    events = await _events(ollama, want_chart=True)
    assert any(isinstance(e, ChartEvent) for e in events)
    assert any(isinstance(e, ToolCallEvent) and e.name == "make_chart" for e in events)


async def test_a_successful_run_sql_query_skips_the_chart_when_not_wanted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = ToolCall(name="run_sql_query", arguments={"question": "x"})
    ollama = _FakeOllama(
        [[_FakeChunk(content="", tool_calls=[call])], [_FakeChunk(content="Done.")]]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="5 row(s)")

    async def fake_auto_chart(conversation_id: str, question: str, **kwargs: object) -> ToolResult:
        raise AssertionError("auto_chart must not run when want_chart is False")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)
    monkeypatch.setattr(chat_loop, "auto_chart", fake_auto_chart)

    events = await _events(ollama, want_chart=False)
    assert not any(isinstance(e, ChartEvent) for e in events)
    assert not any(isinstance(e, ToolCallEvent) and e.name == "make_chart" for e in events)


async def test_auto_chart_returning_none_is_a_silent_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A single-row run_sql_query result has nothing to chart — auto_chart returns
    # None for exactly this, and the turn shows no chart card at all, not a failed one.
    call = ToolCall(name="run_sql_query", arguments={"question": "x"})
    ollama = _FakeOllama(
        [[_FakeChunk(content="", tool_calls=[call])], [_FakeChunk(content="Done.")]]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="1 row(s)")

    async def fake_auto_chart(conversation_id: str, question: str, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)
    monkeypatch.setattr(chat_loop, "auto_chart", fake_auto_chart)

    events = await _events(ollama, want_chart=True)
    assert not any(isinstance(e, ChartEvent) for e in events)
    assert not any(isinstance(e, ToolCallEvent) and e.name == "make_chart" for e in events)


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


async def test_the_chart_step_always_runs_right_after_its_own_run_sql_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A chart is code triggered immediately after a successful run_sql_query
    # dispatch, not a second tool call the model has to sequence correctly itself —
    # there is no ordering for the model to get wrong anymore (the failure mode
    # this test used to guard against, confirmed live on llama3.1 emitting both
    # calls for one turn with no guaranteed order).
    sql_call = ToolCall(name="run_sql_query", arguments={"question": "x"})
    ollama = _FakeOllama(
        [[_FakeChunk(content="", tool_calls=[sql_call])], [_FakeChunk(content="Here it is.")]]
    )

    dispatched_order: list[str] = []

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        dispatched_order.append(call.name)
        return ToolResult(ok=True, summary="5 row(s)")

    async def fake_auto_chart(conversation_id: str, question: str, **kwargs: object) -> ToolResult:
        dispatched_order.append("make_chart")
        return ToolResult(ok=True, summary="Chart rendered.", chart=ChartArtifact(plotly_json="{}"))

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)
    monkeypatch.setattr(chat_loop, "auto_chart", fake_auto_chart)

    await _events(ollama, want_chart=True)
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


async def test_a_slow_generation_emits_heartbeats_before_its_first_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Confirmed live: a compound question's follow-up turn (deciding whether to call
    # make_chart after run_sql_query came back) can sit with no streamed content at all
    # while the model composes a tool call, long enough to cross the PHP relay's 45s idle
    # cap -- only a running tool call had a heartbeat before this, not a turn's own
    # generation.
    monkeypatch.setattr(chat_loop, "_HEARTBEAT_INTERVAL_S", 0.01)
    call = ToolCall(name="run_sql_query", arguments={"question": "x"})

    class _SlowOllama:
        def __init__(self) -> None:
            self._calls = 0

        async def chat_stream(
            self, *, model: str, messages: object, tools: object, usage: object = None
        ) -> AsyncIterator[object]:
            self._calls += 1
            await asyncio.sleep(0.05)
            if self._calls == 1:
                yield _FakeChunk(content="", tool_calls=[call])
            else:
                yield _FakeChunk(content="Done.")

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="ok")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(_SlowOllama())  # type: ignore[arg-type]
    heartbeat_index = next(i for i, e in enumerate(events) if isinstance(e, HeartbeatEvent))
    call_index = next(i for i, e in enumerate(events) if isinstance(e, ToolCallEvent))
    assert heartbeat_index < call_index


async def test_a_wrong_scope_refusal_retries_and_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Confirmed live: asked "what are the different UP Excise shop types and license
    # codes" (the department's own terminology, right in the question), the model
    # called search_knowledge, got back exactly the right content, and declined anyway
    # with "I only answer UP Excise questions" instead of using it. A tool call
    # succeeding earlier the same turn is proof the question was in scope.
    kb_call = ToolCall(name="search_knowledge", arguments={"query": "shop types"})
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="", tool_calls=[kb_call])],
            [_FakeChunk(content="I only answer UP Excise questions.")],
            [_FakeChunk(content="A Composite Shop (FL5DB) holds Foreign Liquor + Beer.")],
        ]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="[UP Excise shop types] A Composite Shop ...")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    # Same tradeoff as the chart-claim and fenced-sql retries: the check only fires
    # once the full text is in, so the first (wrong) attempt has already streamed live
    # by the time the retry runs — the retry's correct answer follows it, rather than
    # replacing it.
    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert "Composite Shop" in tokens


async def test_a_wrong_scope_refusal_retry_that_still_refuses_falls_back_to_the_tool_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kb_call = ToolCall(name="search_knowledge", arguments={"query": "shop types"})
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="", tool_calls=[kb_call])],
            [_FakeChunk(content="I only answer UP Excise questions.")],
            [_FakeChunk(content="I only answer UP Excise questions.")],
        ]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="[UP Excise shop types] A Composite Shop ...")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert tokens.endswith("[UP Excise shop types] A Composite Shop ...")
    assert isinstance(events[-1], DoneEvent)


async def test_narrating_the_tool_decision_retries_and_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CHAT_SYSTEM_PROMPT already forbids this by name ("Do not write things like
    # 'No tool call is needed'") -- confirmed live that the instruction alone isn't
    # reliable: asked a knowledge question with real content already retrieved, the
    # whole reply was "# No tool call needed here; this is just plain-language
    # shop-type information." -- the deliberation standing in for the answer.
    kb_call = ToolCall(name="search_knowledge", arguments={"query": "shop types"})
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="", tool_calls=[kb_call])],
            [_FakeChunk(content="No tool call is needed here; this is plain information.")],
            [_FakeChunk(content="A Composite Shop (FL5DB) holds Foreign Liquor + Beer.")],
        ]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="[UP Excise shop types] A Composite Shop ...")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert "Composite Shop" in tokens


async def test_a_chart_claim_retry_drops_the_claim_since_theres_no_tool_to_fix_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # There is no make_chart tool the model can call anymore — a chart claim retry
    # can only ever be fixed by the model dropping the claim, never by making a real
    # tool call (chat/tools.py's auto_chart docstring has the full history).
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="Here is a chart showing the volumes.")],
            [_FakeChunk(content="The total volume was 500 BL.")],
        ]
    )

    events = await _events(ollama, want_chart=False)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert "The total volume was 500 BL." in tokens
    assert not any(isinstance(e, ChartEvent) for e in events)
    assert not any(isinstance(e, ToolCallEvent) and e.name == "make_chart" for e in events)


async def test_a_chart_claim_retry_that_narrates_a_fake_make_chart_call_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Confirmed live: a chart-claim retry (tools attached, per the test above) can
    # itself degenerate into narrating make_chart's own call as literal `{"name":
    # "make_chart", ...}` text instead of issuing a real tool call. This shape isn't a
    # chart-claim phrase, a wrong refusal, or a narrated tool-decision -- only
    # `_needs_retry`'s own `{"name"` check catches it, so the retry's completion gate
    # has to check that too, not just `_is_degenerate`.
    sql_call = ToolCall(name="run_sql_query", arguments={"question": "x"})
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="", tool_calls=[sql_call])],
            [_FakeChunk(content="The total is fine. Here is a chart to visualize it.")],
            [_FakeChunk(content='The total is fine. {"name": "make_chart", "parameters": {}}')],
        ]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="5 row(s), columns: category, total_bl")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert tokens.endswith("5 row(s), columns: category, total_bl")
    assert not any(isinstance(e, ChartEvent) for e in events)
    assert isinstance(events[-1], DoneEvent)


async def test_a_chart_claim_retry_that_still_claims_falls_back_to_the_tool_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # If the retry (tools attached, nudged) still doesn't call make_chart, this falls
    # back the same way a doubly-degenerate reply already does -- the last real tool
    # result's own summary, rather than ending the turn on the repeated false claim.
    sql_call = ToolCall(name="run_sql_query", arguments={"question": "x"})
    ollama = _FakeOllama(
        [
            [_FakeChunk(content="", tool_calls=[sql_call])],
            [_FakeChunk(content="Here is a chart showing the volumes.")],
            [_FakeChunk(content="Here is a chart showing the volumes.")],
        ]
    )

    async def fake_dispatch(call: ToolCall, **kwargs: object) -> ToolResult:
        return ToolResult(ok=True, summary="5 row(s), columns: category, total_bl")

    monkeypatch.setattr(chat_loop, "dispatch", fake_dispatch)

    events = await _events(ollama)
    tokens = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert tokens.endswith("5 row(s), columns: category, total_bl")
    assert not any(isinstance(e, ChartEvent) for e in events)
    assert isinstance(events[-1], DoneEvent)
