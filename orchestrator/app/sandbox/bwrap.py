"""Builds and runs the bwrap sandbox command, collects artifacts. SECURITY.md
§2 Code-execution sandbox.
"""

import asyncio
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
        if Path("/opt/google/chrome").exists():
            # kaleido>=1.0 (plotly static image export) drives a real Chrome via
            # choreographer instead of the old pure-binary renderer — the box's
            # system Chrome, otherwise outside every other bind mount here.
            bwrap_cmd += ["--ro-bind", "/opt/google/chrome", "/opt/google/chrome"]
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
        "/dev/shm",  # headless Chrome (kaleido's PNG/SVG/PDF export) needs shared memory
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
    stdout_bytes, _ = await proc.communicate()
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
        raise SandboxViolationError(f"exit {proc.returncode}: {stdout_tail}")

    return run_dir, stdout_tail


def cleanup_scratch(scratch_dir: Path) -> None:
    shutil.rmtree(scratch_dir, ignore_errors=True)
