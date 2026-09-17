"""pipeline.py's output-resolution guard. ROADMAP.md Milestone 4: the
pipeline falls back to a static chart when a no-Plotly-JSON engine is chosen.
"""

import json

import httpx
import pytest

from app import pipeline
from app.llm.client import OllamaClient
from app.pipeline import _resolve_outputs
from app.schemas import QueryRequest, SqlExecutionError


def test_keeps_outputs_the_engine_supports() -> None:
    assert _resolve_outputs(["png", "svg"], frozenset({"png", "svg", "pdf"})) == ["png", "svg"]


def test_drops_plotly_json_for_an_engine_that_cannot_produce_it() -> None:
    # e.g. the LLM picks octave but still asks for plotly_json — octave's
    # supported_outputs has no "plotly_json", so it's dropped.
    assert _resolve_outputs(["plotly_json"], frozenset({"png", "svg", "pdf"})) == ["png"]


def test_falls_back_to_png_when_nothing_requested_is_supported() -> None:
    assert _resolve_outputs([], frozenset({"png", "svg", "pdf"})) == ["png"]


async def test_a_zero_row_result_skips_the_narration_call(monkeypatch: pytest.MonkeyPatch) -> None:
    # A question that matches nothing (or isn't really a data question, like "hi")
    # must not hand the model an empty result set to narrate — it invents a trend
    # from nothing rather than saying there isn't one.
    sql_plan = json.dumps({"sql": "SELECT 1", "rationale": "x", "expected_columns": ["1"]})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": sql_plan})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ollama = OllamaClient("http://fake-ollama", http_client)

    async def fake_run_sql(sql: str, row_limit: int) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(pipeline, "run_sql", fake_run_sql)

    called_generate_text = False

    async def fail_if_called(*args: object, **kwargs: object) -> str:
        nonlocal called_generate_text
        called_generate_text = True
        return "hallucinated narration"

    monkeypatch.setattr(ollama, "generate_text", fail_if_called)

    response = await pipeline.run_query(
        QueryRequest(conversation_id="c1", question="hi"),
        request_id="r1",
        pool=None,  # type: ignore[arg-type] — unused: run_sql is monkeypatched above
        ollama=ollama,
        schema_card="(schema)",
    )

    assert called_generate_text is False
    assert response.summary == "No rows matched this question."
    assert response.row_count == 0


async def test_a_run_sql_failure_retries_plan_sql_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # guard_sql only proves the statement is a single read-only SELECT — a
    # hallucinated table (relation "beer_shops" does not exist) or an
    # ambiguous cast only surfaces once Postgres actually runs it. The
    # pipeline reprompts and retries once, the same shape guard_sql's own
    # rejection already gets a few lines up.
    sql_plan = json.dumps(
        {"sql": "SELECT COUNT(*) AS n", "rationale": "x", "expected_columns": ["n"]}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": sql_plan})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ollama = OllamaClient("http://fake-ollama", http_client)

    calls = 0

    async def fake_run_sql(sql: str, row_limit: int) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SqlExecutionError('relation "beer_shops" does not exist')
        return [{"n": 7}]

    async def fake_generate_text(*args: object, **kwargs: object) -> str:
        return "7."

    monkeypatch.setattr(pipeline, "run_sql", fake_run_sql)
    monkeypatch.setattr(ollama, "generate_text", fake_generate_text)

    response = await pipeline.run_query(
        QueryRequest(conversation_id="c1", question="how many beer shops"),
        request_id="r1",
        pool=None,  # type: ignore[arg-type] — unused: run_sql is monkeypatched above
        ollama=ollama,
        schema_card="(schema)",
    )

    assert calls == 2
    assert response.row_count == 1


async def test_a_single_row_result_skips_the_chart(monkeypatch: pytest.MonkeyPatch) -> None:
    # A bare COUNT(*) has no dimension to plot — asking the model for a chart script
    # anyway is how "how many beer shops in Lucknow" crashed Octave's print() with
    # "no axes object in figure": there was nothing to draw. The mock transport only
    # ever returns a SqlPlan-shaped payload, so if plan_plot ran anyway it would fail
    # PlotPlan validation and this test would error rather than silently pass.
    sql_plan = json.dumps(
        {"sql": "SELECT COUNT(*) AS n", "rationale": "x", "expected_columns": ["n"]}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": sql_plan})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ollama = OllamaClient("http://fake-ollama", http_client)

    async def fake_run_sql(sql: str, row_limit: int) -> list[dict[str, object]]:
        return [{"n": 42}]

    async def fake_generate_text(*args: object, **kwargs: object) -> str:
        return "42 shops."

    monkeypatch.setattr(pipeline, "run_sql", fake_run_sql)
    monkeypatch.setattr(ollama, "generate_text", fake_generate_text)

    response = await pipeline.run_query(
        QueryRequest(conversation_id="c1", question="how many beer shops in lucknow"),
        request_id="r1",
        pool=None,  # type: ignore[arg-type] — unused: run_sql is monkeypatched above
        ollama=ollama,
        schema_card="(schema)",
    )

    assert response.chart is None
    assert response.row_count == 1
