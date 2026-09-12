"""Wolfram Mathematica engine stub. MCP_ENGINES.md §4 Wolfram Mathematica
(`wolframscript`) — behind ENABLE_WOLFRAM (default off), currently blocked:
no Wolfram Engine or Mathematica licence on this box.

Shape if it is ever built: a subprocess-script adapter like
python_engine.py / octave_engine.py. It would write `/scratch/chart.wls`,
run `wolframscript -file /scratch/chart.wls` under the sandbox, and the
script would do `Export["/scratch/chart.png", plot]` (`.svg` / `.pdf`
likewise). Its value here would be symbolic math and exact arithmetic —
duty-rate elasticity or high-precision projection work — not charting; see
MCP_ENGINES.md §4 for the full integration guide before writing it.
"""

from app.engines.base import RenderRequest, RenderResult
from app.schemas import EngineUnavailableError


class WolframEngine:
    name = "wolfram"
    supported_outputs: frozenset[str] = frozenset({"png", "svg", "pdf"})

    def is_available(self) -> bool:
        return False

    async def render(self, req: RenderRequest) -> RenderResult:
        raise EngineUnavailableError(self.name, reason="not configured")
