"""IVisualizationEngine protocol, registry, and errors. MCP_ENGINES.md
§`IVisualizationEngine` — the adapter interface.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from app.schemas import EngineUnavailableError


class RenderRequest(BaseModel):
    script: str
    data_path: Path
    outputs: list[str]
    title: str
    scratch_dir: Path


class RenderResult(BaseModel):
    plotly_json: str | None = None
    files: dict[str, Path] = {}
    stdout_tail: str = ""
    engine: str


@runtime_checkable
class IVisualizationEngine(Protocol):
    name: str
    supported_outputs: frozenset[str]

    def is_available(self) -> bool: ...

    async def render(self, req: RenderRequest) -> RenderResult: ...


_ENGINES: dict[str, IVisualizationEngine] = {}


def register(engine: IVisualizationEngine) -> None:
    _ENGINES[engine.name] = engine


def get(name: str) -> IVisualizationEngine:
    eng = _ENGINES.get(name)
    if eng is None:
        raise EngineUnavailableError(name, reason="not registered")
    if not eng.is_available():
        raise EngineUnavailableError(name, reason="unavailable at runtime")
    return eng


def available() -> list[str]:
    return [n for n, e in _ENGINES.items() if e.is_available()]
