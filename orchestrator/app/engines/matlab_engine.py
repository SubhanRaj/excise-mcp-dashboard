"""MATLAB engine stub. MCP_ENGINES.md §3 MATLAB via matlab-mcp-server —
behind ENABLE_MATLAB (default off), currently blocked: no MATLAB licence and
no matlab-mcp-server on this box.

Shape if it is ever built: an MCP-client adapter, not a subprocess-script
adapter like python_engine.py / octave_engine.py. It would spawn
`matlab-mcp-server --matlab-session-mode=new` as a stdio MCP child inside the
sandbox wrapper, call its `run`/`eval` tool with the generated MATLAB, and
pull back a saved figure (`saveas(gcf, '/scratch/chart.png')` inside the
MATLAB code). `new` session mode only — a shared session leaks state between
analysts' queries. See MCP_ENGINES.md §3 for prerequisites and the full
integration guide before writing it.
"""

from app.engines.base import RenderRequest, RenderResult
from app.schemas import EngineUnavailableError


class MatlabEngine:
    name = "matlab"
    supported_outputs: frozenset[str] = frozenset({"png", "svg", "pdf"})

    def is_available(self) -> bool:
        return False

    async def render(self, req: RenderRequest) -> RenderResult:
        raise EngineUnavailableError(self.name, reason="not configured")
