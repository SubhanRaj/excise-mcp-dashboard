"""GNU Octave engine. MCP_ENGINES.md §2 GNU Octave integration guide.

Verified live against a real `octave-cli` render on this box
(OPERATOR_SETUP.md §Octave, test_octave_engine.py). Two gaps surfaced only by
that live run, not documented anywhere beforehand:

- GNU Octave has no `table`/`readtable` (a MATLAB compatibility gap Octave
  itself reports as "not yet implemented"), so the query result arrives as
  plain variables instead — `sandbox/bwrap.py`'s `_octave_data_script` turns
  each column into a numeric vector or a cell array of strings, named after
  its SQL column alias.
- A new `figure()` does not inherit the `graphics_toolkit("gnuplot")` global
  default in this Octave build — it silently falls back to `fltk`, which
  needs a real display and fails print() with "requires visible figure"
  inside the sandbox's headless namespace. Setting `__graphics_toolkit__` on
  the figure object itself (not just the global default) is the fix, so the
  preamble creates the one figure the script draws into and pins its toolkit
  directly, rather than leaving that to the LLM-written body.
- `print(..., '-dpng')` / `-dpdf` route through Ghostscript in Octave's
  gnuplot toolkit, and that Ghostscript step fails inside the sandbox
  namespace ("Could not open the file", a real `EPERM` from Ghostscript's own
  process, not a bwrap bind-mount gap — plain file writes and gnuplot's own
  terminals both work fine in the same sandbox). `-dpngcairo` / `-dsvg` /
  `-dpdfcairo` — gnuplot's own cairo terminals — write the file directly and
  don't hit Ghostscript at all, so llm/prompts.py's capability line asks the
  LLM for those device flags specifically.
"""

import shutil
import subprocess
from pathlib import Path

from app.engines.base import RenderRequest, RenderResult
from app.sandbox.bwrap import run_in_sandbox
from app.schemas import RenderEmptyError

PREAMBLE = """source('/scratch/data.m');
OUT = '/scratch';
graphics_toolkit('gnuplot');
__excise_fig__ = figure('visible', 'off');
set(__excise_fig__, '__graphics_toolkit__', 'gnuplot');
"""

_OUTPUT_FILENAMES = {"png": "chart.png", "svg": "chart.svg", "pdf": "chart.pdf"}


class OctaveEngine:
    name = "octave"
    supported_outputs = frozenset({"png", "svg", "pdf"})

    def is_available(self) -> bool:
        if shutil.which("octave-cli") is None:
            return False
        try:
            result = subprocess.run(
                ["octave-cli", "--version"], capture_output=True, timeout=5, check=False
            )
        except OSError:
            return False
        return result.returncode == 0

    async def render(self, req: RenderRequest) -> RenderResult:
        full_script = PREAMBLE + req.script
        scratch_dir, stdout_tail = await run_in_sandbox(
            script=full_script, data_path=req.data_path, engine=self.name
        )

        files: dict[str, Path] = {}
        for output in req.outputs:
            filename = _OUTPUT_FILENAMES.get(output)
            if filename is None:
                continue
            path = scratch_dir / filename
            if path.exists():
                files[output] = path

        if not files:
            raise RenderEmptyError(stdout_tail)

        return RenderResult(files=files, stdout_tail=stdout_tail, engine=self.name)
