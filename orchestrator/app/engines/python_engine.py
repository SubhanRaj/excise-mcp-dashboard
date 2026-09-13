"""Matplotlib / Plotly / pandas engine. MCP_ENGINES.md §1 Python — implemented.

Output files are left under the sandbox run's scratch dir and returned by
path; there is no web/ artifact disk to copy them into yet (Milestone 5) and
no sweep timer yet (Milestone 6) — OPERATOR_SETUP.md / ROADMAP.md already
track the sweep as a Milestone 6 item.

Static export (png/svg/pdf) works through matplotlib's plt.savefig, which has
no extra runtime dependency. Plotly's own static export (fig.write_image)
needs kaleido>=1.0, which drives a real headless Chrome (the box's own
/opt/google/chrome, bind-mounted read-only by sandbox/bwrap.py) instead of the
old pure-binary renderer — it fails to launch inside the bwrap sandbox even
with /dev/shm mounted, and a live render showed it repeatedly OOM-killing the
render's cgroup instead of just erroring. llm/prompts.py no longer offers
fig.write_image() to the model, and render() below rejects a script that
calls it anyway before a sandboxed process ever runs.
"""

import importlib.util
from pathlib import Path

from app.engines.base import RenderRequest, RenderResult
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

        if plotly_json is None and not files:
            raise RenderEmptyError(stdout_tail)

        return RenderResult(
            plotly_json=plotly_json, files=files, stdout_tail=stdout_tail, engine=self.name
        )
