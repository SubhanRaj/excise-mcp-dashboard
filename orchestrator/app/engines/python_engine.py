"""Matplotlib / Plotly / pandas engine. MCP_ENGINES.md §1 Python — implemented.

Output files are left under the sandbox run's scratch dir and returned by
path; there is no web/ artifact disk to copy them into yet (Milestone 5) and
no sweep timer yet (Milestone 6) — OPERATOR_SETUP.md / ROADMAP.md already
track the sweep as a Milestone 6 item.

Static export (png/svg/pdf) has two paths. A script that builds a matplotlib
figure calls plt.savefig directly, inside the sandbox — no extra runtime
dependency. A script that builds a Plotly figure only ever calls
fig.write_json(); render() below derives any requested png/svg/pdf from that
JSON afterward, outside the sandbox, via engines/static_render.py's
persistent, isolated browser. Plotly's own in-script static export
(fig.write_image, which needs a real headless Chrome) is never called from
inside the sandbox: a live render showed Chrome repeatedly OOM-killing the
render's cgroup there instead of just erroring, so llm/prompts.py doesn't
offer fig.write_image() to the model, and render() below rejects a script
that calls it anyway before a sandboxed process ever runs.
"""

import importlib.util
from pathlib import Path

from app.engines.base import RenderRequest, RenderResult
from app.engines.static_render import get_renderer as get_static_renderer
from app.sandbox.bwrap import run_in_sandbox
from app.schemas import RenderEmptyError, SandboxViolationError

PREAMBLE = """import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go
import plotly.express as px
df = pd.read_parquet("/scratch/data.parquet")
OUT = "/scratch"
"""

_OUTPUT_FILENAMES = {
    "plotly_json": "chart.plotly.json",
    "png": "chart.png",
    "svg": "chart.svg",
    "pdf": "chart.pdf",
}


class PythonEngine:
    name = "python"
    supported_outputs = frozenset({"plotly_json", "png", "svg", "pdf"})

    def is_available(self) -> bool:
        return all(
            importlib.util.find_spec(mod) is not None
            for mod in ("matplotlib", "plotly", "pandas", "numpy")
        )

    async def render(self, req: RenderRequest) -> RenderResult:
        # Defense in depth alongside the prompt instruction above (SECURITY.md's SQL
        # guard follows the same "don't rely on the LLM alone" pattern): a script that
        # still calls Plotly's own static export launches a headless Chrome that fails
        # to start in this sandbox and has repeatedly OOM-killed the render cgroup
        # instead of just erroring — caught here, before a sandboxed process ever runs.
        if "write_image(" in req.script:
            raise SandboxViolationError(
                "fig.write_image() needs a headless Chrome this sandbox cannot launch; "
                "use plt.savefig() for a static export instead"
            )

        full_script = PREAMBLE + req.script
        scratch_dir, stdout_tail = await run_in_sandbox(script=full_script, data_path=req.data_path)

        files: dict[str, Path] = {}
        plotly_json: str | None = None
        for output in req.outputs:
            filename = _OUTPUT_FILENAMES.get(output)
            if filename is None:
                continue
            path = scratch_dir / filename
            if not path.exists():
                continue
            if output == "plotly_json":
                plotly_json = path.read_text()
            else:
                files[output] = path

        static_renderer = get_static_renderer()
        if plotly_json is not None and static_renderer.is_available():
            for output in ("png", "svg", "pdf"):
                if output in req.outputs and output not in files:
                    data = await static_renderer.render(plotly_json, output)
                    out_path = scratch_dir / _OUTPUT_FILENAMES[output]
                    out_path.write_bytes(data)
                    files[output] = out_path

        if plotly_json is None and not files:
            raise RenderEmptyError(stdout_tail)

        return RenderResult(
            plotly_json=plotly_json, files=files, stdout_tail=stdout_tail, engine=self.name
        )
