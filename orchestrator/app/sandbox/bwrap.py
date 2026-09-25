"""Builds and runs the bwrap sandbox command, collects artifacts. SECURITY.md
§2 Code-execution sandbox.
"""

import asyncio
import contextlib
import getpass
import re
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pandas as pd
import structlog

from app.config import settings
from app.schemas import SandboxTimeoutError, SandboxViolationError

logger = structlog.get_logger()

# `timeout --signal=KILL` returns 128+SIGKILL(9) on most coreutils builds when
# it actually has to kill the child; some report a bare 124. Treat either as
# a timeout rather than a script crash.
_TIMEOUT_EXIT_CODES = {124, 137}

_ENGINE_SCRIPT_FILENAMES = {"python": "chart.py", "octave": "chart.m"}
_ENGINE_DATA_FILENAMES = {"python": "data.parquet", "octave": "data.m"}

# Matches a Python exception's own "SomeError: message" line, however deep a dotted
# module path runs (e.g. "plotly.exceptions.PlotlyError:") — the line a traceback's
# real description starts on, not necessarily its last line (see run_in_sandbox).
_EXCEPTION_LINE = re.compile(r"^[\w.]+(Error|Exception):")


def _octave_identifier(column: str) -> str:
    ident = re.sub(r"\W", "_", column)
    if not ident or ident[0].isdigit():
        ident = f"col_{ident}"
    return ident


def _octave_data_script(data_path: Path) -> str:
    """Renders the query result as plain Octave variable assignments, one per
    column. GNU Octave has no `table` type and does not implement `readtable`
    (confirmed against a live `octave-cli` render — it names that MATLAB
    function outright as not implemented, and the `octave-io` package doesn't
    add it either, only spreadsheet I/O) — each column becomes a numeric
    column vector or a cell array of strings instead, named after its SQL
    column alias.
    """
    df = pd.read_parquet(data_path)
    lines: list[str] = []
    for column in df.columns:
        name = _octave_identifier(str(column))
        series = df[column]
        if pd.api.types.is_numeric_dtype(series):
            values = ", ".join("NaN" if pd.isna(v) else repr(float(v)) for v in series)
            lines.append(f"{name} = [{values}]';")
        else:
            values = ", ".join('"' + str(v).replace('"', '""') + '"' for v in series)
            lines.append(f"{name} = {{{values}}}';")
    return "\n".join(lines) + "\n"


def _scratch_root() -> Path:
    if settings.sandbox_uid_switch_enabled:
        return Path(settings.sandbox_scratch_root)
    # ponytail: dev fallback while the excise-sandbox uid-switch is pending an
    # operator step (see config.py) — /var/tmp is world-writable+sticky so this
    # needs no setup. Upgrade path: enable the uid switch, point this back at
    # the excise-sandbox-owned directory.
    fallback = Path(f"/var/tmp/excise-orch-scratch-{getpass.getuser()}")
    fallback.mkdir(mode=0o700, parents=True, exist_ok=True)
    return fallback


def _build_command(*, run_dir: Path, venv_root: str, unit_name: str, engine: str) -> list[str]:
    bwrap_cmd = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/scratch",
        # `--clearenv` drops LANG along with everything else, leaving the C/POSIX
        # locale — Ghostscript's iconv step (reached via Octave's gnuplot print
        # path) fails outright without one. Harmless for the Python engine too.
        "--setenv",
        "LANG",
        "C.utf8",
        "--setenv",
        "MPLBACKEND",
        "Agg",
        "--setenv",
        "MPLCONFIGDIR",
        "/scratch/.mpl",
        "--setenv",
        "TMPDIR",
        "/scratch/tmp",
        # numpy/OpenBLAS defaults to one thread per CPU (24 on this box), which
        # blows past --property=TasksMax below before the chart script even
        # runs — a plot doesn't need parallel BLAS.
        "--setenv",
        "OPENBLAS_NUM_THREADS",
        "1",
        "--setenv",
        "OMP_NUM_THREADS",
        "1",
        "--setenv",
        "MKL_NUM_THREADS",
        "1",
        "--setenv",
        "NUMEXPR_NUM_THREADS",
        "1",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind",
        "/lib",
        "/lib",
    ]
    if Path("/lib64").exists():
        bwrap_cmd += ["--ro-bind", "/lib64", "/lib64"]
    if Path("/etc/alternatives").exists():
        bwrap_cmd += ["--ro-bind", "/etc/alternatives", "/etc/alternatives"]
    if engine == "python":
        # No Chrome bind-mount here: a script that calls Plotly's own
        # fig.write_image() is rejected before it ever reaches this sandbox
        # (python_engine.py) — static export runs in engines/static_render.py's
        # persistent browser, entirely outside bwrap.
        # `venv_root/bin/python` is a symlink to the pyenv-managed interpreter
        # outside the venv (pyenv installs venvs with symlinked, not copied,
        # binaries) — bind that real target too so the symlink resolves. Python's
        # own venv detection keys off the invoked path (venv_root/bin/python,
        # bound below), not this target, so site-packages still resolve to the
        # venv.
        real_python_home = str(Path(sys.executable).resolve().parents[1])
        if real_python_home not in {venv_root, "/usr"} and Path(real_python_home).exists():
            bwrap_cmd += ["--ro-bind", real_python_home, real_python_home]
        bwrap_cmd += ["--ro-bind", venv_root, venv_root]
    elif engine == "octave" and Path("/etc/fonts").exists():
        # ponytail: octave's `print()` goes through gnuplot's pngcairo/svg/pdfcairo
        # terminals, which call fontconfig for text layout — fontconfig needs
        # /etc/fonts to find its config and font sources (font files themselves
        # are under /usr/share/fonts, already covered by the /usr bind above).
        # Unverified against a real octave-cli render (not installed on this box
        # yet, OPERATOR_SETUP.md §Octave) — if a live run still fails to find a
        # font, that's the upgrade path: bind /var/cache/fontconfig too, or check
        # `fc-list` inside the sandbox.
        bwrap_cmd += ["--ro-bind", "/etc/fonts", "/etc/fonts"]
    bwrap_cmd += [
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/dev/shm",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(run_dir),
        "/scratch",
        "--chdir",
        "/scratch",
        "--cap-drop",
        "ALL",
        "--",
        *(
            [f"{venv_root}/bin/python", "/scratch/chart.py"]
            if engine == "python"
            else ["octave-cli", "--no-gui", "--norc", "--eval", "source('/scratch/chart.m')"]
        ),
    ]

    timeout_cmd = ["timeout", "--signal=KILL", str(settings.sandbox_wallclock_seconds), *bwrap_cmd]

    # --unit + --description name the transient scope so `journalctl` /
    # `systemctl --user status` (and any desktop OOM notification that reads
    # the unit's own description) identify it as ours, instead of systemd's
    # default anonymous `run-p<pid>-i<pid>.scope`.
    named = [
        f"--unit={unit_name}",
        "--description=excise-orchestrator sandboxed chart render",
    ]
    if not settings.sandbox_uid_switch_enabled:
        return [
            "systemd-run",
            "--user",
            "--scope",
            "--collect",
            *named,
            f"--property=MemoryMax={settings.sandbox_memory_mb}M",
            "--property=MemorySwapMax=0",
            "--property=TasksMax=16",
            "--property=CPUQuota=100%",
            "--",
            *timeout_cmd,
        ]
    return [
        "systemd-run",
        "--user",
        "--scope",
        "--collect",
        *named,
        f"--uid={settings.sandbox_user}",
        f"--property=MemoryMax={settings.sandbox_memory_mb}M",
        "--property=MemorySwapMax=0",
        "--property=TasksMax=16",
        "--property=CPUQuota=100%",
        "--",
        *timeout_cmd,
    ]


async def run_in_sandbox(
    *, script: str, data_path: Path, engine: str = "python"
) -> tuple[Path, str]:
    """Writes `script` + hands off data_path into a fresh scratch dir, runs it
    under bwrap, returns (scratch_dir, stdout_tail). Raises SandboxTimeoutError
    / SandboxViolationError. The caller collects declared outputs from
    scratch_dir and is responsible for removing it afterward (cleanup_scratch).

    `data_path` is always the Parquet file the pipeline wrote from the SQL
    result. For `engine="python"` it's copied in as-is; for `engine="octave"`
    it's converted to a generated `.m` variable-assignment file instead, since
    Octave has no Parquet or Excel-table reader (`_octave_data_script`).
    """
    run_id = uuid4().hex
    run_dir = _scratch_root() / run_id
    run_dir.mkdir(mode=0o700, parents=True)
    (run_dir / _ENGINE_SCRIPT_FILENAMES[engine]).write_text(script)
    if engine == "octave":
        (run_dir / _ENGINE_DATA_FILENAMES[engine]).write_text(_octave_data_script(data_path))
    else:
        shutil.copy(data_path, run_dir / _ENGINE_DATA_FILENAMES[engine])
    (run_dir / "tmp").mkdir(mode=0o700)
    (run_dir / ".mpl").mkdir(mode=0o700)

    if not settings.sandbox_uid_switch_enabled:
        logger.warning(
            "sandbox running without excise-sandbox uid separation", run_dir=str(run_dir)
        )

    unit_name = f"excise-sandbox-{run_id}.scope"
    cmd = _build_command(run_dir=run_dir, venv_root=sys.prefix, unit_name=unit_name, engine=engine)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        stdout_bytes, _ = await proc.communicate()
    except asyncio.CancelledError:
        # A client disconnect or the orchestrator shutting down cancels this
        # awaiting coroutine, but `communicate()` being cancelled does not kill
        # the process it was waiting on — `systemd-run --scope` execs straight
        # into `timeout`/bwrap, so proc.pid is that scope's own main PID.
        # Killing it here tears the scope down immediately instead of leaving
        # it to run (and hold its memory cgroup) until its own wallclock
        # timeout, or forever if the orchestrator itself was SIGKILLed first.
        proc.kill()
        with contextlib.suppress(ProcessLookupError):
            await proc.wait()
        raise
    stdout_tail = stdout_bytes.decode(errors="replace")[-4000:]

    if proc.returncode in _TIMEOUT_EXIT_CODES:
        cleanup_scratch(run_dir)
        logger.warning("sandbox wallclock timeout", unit=unit_name)
        raise SandboxTimeoutError()
    if proc.returncode != 0:
        cleanup_scratch(run_dir)
        logger.warning(
            "sandbox violation", unit=unit_name, returncode=proc.returncode, stdout=stdout_tail
        )
        # A traceback frame inside site-packages carries the real host path bwrap bound
        # in (venv_root/real_python_home, both this box's actual filesystem layout, not
        # a sandboxed alias) — the full log line above keeps it, but the exception message
        # below reaches a chat user verbatim as a failed tool result, so it gets the host
        # path stripped first.
        user_facing = stdout_tail.replace(str(Path(sys.prefix).resolve()), "<venv>").replace(
            str(Path(sys.executable).resolve().parents[1]), "<venv>"
        )
        # A full Python traceback is dozens of internal pandas/plotly stack frames with
        # no use to a chat model trying to self-correct — confirmed live, a make_chart
        # script that guessed a wrong column name came back with the whole traceback as
        # the tool result, when the one actionable line ("Value of 'x' is not the name
        # of a column... Expected one of [...] but received: shop_category") was already
        # its own last line. A plain Python exception's summary is its final printed
        # line, but Plotly's own schema-validation ValueError isn't plain: it spans many
        # lines (the real description, then a list of valid properties, then a trailing
        # location pointer like "    chart at line 6 column 1") — confirmed live, taking
        # only the last line surfaced that trailing pointer with no description at all.
        # Found backwards from the end instead: the last line that looks like
        # `SomeError: message` starts the summary, and everything after it (still
        # capped, so a genuinely huge Plotly dump doesn't reach the user whole) is kept,
        # since that's exactly the case where the description needs more than one line.
        lines = [line for line in user_facing.strip().splitlines() if line.strip()]
        error_line_index = next(
            (i for i in reversed(range(len(lines))) if _EXCEPTION_LINE.match(lines[i])),
            None,
        )
        summary = (
            "\n".join(lines[error_line_index : error_line_index + 10])
            if error_line_index is not None
            else (lines[-1] if lines else user_facing)
        )
        raise SandboxViolationError(f"exit {proc.returncode}: {summary}")

    return run_dir, stdout_tail


def cleanup_scratch(scratch_dir: Path) -> None:
    shutil.rmtree(scratch_dir, ignore_errors=True)


async def stop_orphaned_sandbox_scopes() -> None:
    """A prior orchestrator process that systemd had to SIGKILL (its own
    stop-sigterm timeout expiring while a request was still in flight) never
    got to run the CancelledError handler above — its render, if any, is left
    running as a still-active `excise-sandbox-*.scope` with no parent watching
    it. Call this once at startup so the next orchestrator sweeps up after the
    last one instead of leaving it to run until its own wallclock timeout or
    memory cap.
    """
    list_proc = await asyncio.create_subprocess_exec(
        "systemctl",
        "--user",
        "list-units",
        "--type=scope",
        "--state=active",
        "--no-legend",
        "--plain",
        "excise-sandbox-*.scope",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout_bytes, _ = await list_proc.communicate()
    units = [line.split()[0] for line in stdout_bytes.decode().splitlines() if line.strip()]
    for unit in units:
        logger.warning("stopping orphaned sandbox scope from a prior run", unit=unit)
        stop_proc = await asyncio.create_subprocess_exec("systemctl", "--user", "stop", unit)
        await stop_proc.wait()
