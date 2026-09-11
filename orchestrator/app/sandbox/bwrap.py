"""Builds and runs the bwrap sandbox command, collects artifacts. SECURITY.md
§2 Code-execution sandbox.
"""

import asyncio
import getpass
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import structlog

from app.config import settings
from app.schemas import SandboxTimeoutError, SandboxViolationError

logger = structlog.get_logger()

# `timeout --signal=KILL` returns 128+SIGKILL(9) on most coreutils builds when
# it actually has to kill the child; some report a bare 124. Treat either as
# a timeout rather than a script crash.
_TIMEOUT_EXIT_CODES = {124, 137}


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


def _build_command(*, run_dir: Path, venv_root: str) -> list[str]:
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
    bwrap_cmd += [
        "--ro-bind",
        venv_root,
        venv_root,
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
        f"{venv_root}/bin/python",
        "/scratch/chart.py",
    ]

    timeout_cmd = ["timeout", "--signal=KILL", str(settings.sandbox_wallclock_seconds), *bwrap_cmd]

    if not settings.sandbox_uid_switch_enabled:
        return [
            "systemd-run",
            "--user",
            "--scope",
            "--collect",
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
        f"--uid={settings.sandbox_user}",
        f"--property=MemoryMax={settings.sandbox_memory_mb}M",
        "--property=MemorySwapMax=0",
        "--property=TasksMax=16",
        "--property=CPUQuota=100%",
        "--",
        *timeout_cmd,
    ]


async def run_in_sandbox(*, script: str, data_path: Path) -> tuple[Path, str]:
    """Writes `script` + copies data_path into a fresh scratch dir, runs it
    under bwrap, returns (scratch_dir, stdout_tail). Raises SandboxTimeoutError
    / SandboxViolationError. The caller collects declared outputs from
    scratch_dir and is responsible for removing it afterward (cleanup_scratch).
    """
    run_dir = _scratch_root() / uuid4().hex
    run_dir.mkdir(mode=0o700, parents=True)
    (run_dir / "chart.py").write_text(script)
    shutil.copy(data_path, run_dir / "data.parquet")
    (run_dir / "tmp").mkdir(mode=0o700)
    (run_dir / ".mpl").mkdir(mode=0o700)

    if not settings.sandbox_uid_switch_enabled:
        logger.warning(
            "sandbox running without excise-sandbox uid separation", run_dir=str(run_dir)
        )

    cmd = _build_command(run_dir=run_dir, venv_root=sys.prefix)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    stdout_bytes, _ = await proc.communicate()
    stdout_tail = stdout_bytes.decode(errors="replace")[-4000:]

    if proc.returncode in _TIMEOUT_EXIT_CODES:
        cleanup_scratch(run_dir)
        raise SandboxTimeoutError()
    if proc.returncode != 0:
        cleanup_scratch(run_dir)
        raise SandboxViolationError(f"exit {proc.returncode}: {stdout_tail}")

    return run_dir, stdout_tail


def cleanup_scratch(scratch_dir: Path) -> None:
    shutil.rmtree(scratch_dir, ignore_errors=True)
