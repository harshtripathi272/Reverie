"""``reverie start`` — boot the backend and the 3D explorer in one shot.

Most users don't care about how the pieces fit together — they just want
"open the thing". This command takes care of:

  1. Starting the FastAPI backend (`python -m reverie_api`).
  2. Waiting for it to become healthy.
  3. Starting the web app (`pnpm -C apps/web start` or `dev`).
  4. Opening the browser to ``http://localhost:3000``.
  5. Forwarding both processes' output and tearing both down on Ctrl+C.

The subprocess plumbing is deliberately straightforward — no asyncio, no
process pools — because robust process supervision is hard and we have a
small, fixed set of children. ``subprocess.Popen`` + ``signal`` does the job.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import click
import httpx

from reverie_cli.formatting import make_console


DEFAULT_BACKEND_PORT = 8000
DEFAULT_WEB_PORT = 3000
HEALTH_TIMEOUT_SECONDS = 20.0


@click.command(
    "start",
    short_help="Start the backend and the 3D explorer with one command.",
)
@click.option(
    "--backend-port",
    type=int,
    default=DEFAULT_BACKEND_PORT,
    show_default=True,
    help="Port for the FastAPI backend.",
)
@click.option(
    "--web-port",
    type=int,
    default=DEFAULT_WEB_PORT,
    show_default=True,
    help="Port for the Next.js web app.",
)
@click.option(
    "--no-web",
    is_flag=True,
    help="Skip the web app — useful if you only want the API.",
)
@click.option(
    "--no-browser",
    is_flag=True,
    help="Don't auto-open the browser.",
)
@click.option(
    "--dev/--prod",
    "dev_mode",
    default=True,
    show_default=True,
    help="Use `next dev` (faster reload) or `next start` (production build).",
)
@click.option(
    "--repo",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help=(
        "Path to the Reverie repository root. Defaults to auto-detect by "
        "walking upward from the current directory."
    ),
)
def start_command(
    backend_port: int,
    web_port: int,
    no_web: bool,
    no_browser: bool,
    dev_mode: bool,
    repo: Path | None,
) -> None:
    """Start everything.

    Stops both processes when you Ctrl+C the foreground process.
    """

    console = make_console()

    repo_root = repo or _detect_repo_root()
    if repo_root is None:
        console.print(
            "[red]error:[/red] could not find the Reverie repo root. "
            "Pass --repo /path/to/reverie or run from inside a checkout."
        )
        raise SystemExit(1)

    # ---- Resolve the python that runs the backend.
    backend_python = _resolve_backend_python(repo_root)
    if backend_python is None:
        console.print(
            "[red]error:[/red] could not find a Python with reverie_api "
            "installed.\n"
            f"  Tried: [dim]{repo_root / '.venv' / 'Scripts' / 'python.exe'}[/dim]\n"
            f"         [dim]{repo_root / '.venv' / 'bin' / 'python'}[/dim]\n"
            "Run [bold]make install[/bold] from the repo root first."
        )
        raise SystemExit(1)

    # ---- Optional: resolve pnpm for the web app.
    pnpm = None
    if not no_web:
        pnpm = shutil.which("pnpm")
        if pnpm is None:
            console.print(
                "[yellow]warning:[/yellow] pnpm not found on PATH; "
                "skipping the web app.\n"
                "  Install it from https://pnpm.io and re-run, or pass --no-web."
            )
            no_web = True

    backend_url = f"http://127.0.0.1:{backend_port}"
    web_url = f"http://127.0.0.1:{web_port}"

    # ---- Spawn backend.
    console.print(f"[bold]Reverie[/bold] [dim]starting...[/dim]")
    console.print(f"  backend: [cyan]{backend_url}[/cyan]")

    backend_proc = subprocess.Popen(
        [str(backend_python), "-m", "reverie_api"],
        cwd=str(repo_root),
        env={
            **os.environ,
            "REVERIE_PORT": str(backend_port),
            # Disable uvicorn auto-reload in `start` — we don't want the
            # backend bouncing every time pnpm install touches a file.
            "REVERIE_ENV": "production",
        },
        # Forward stdout/stderr directly so users see startup/error logs.
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    # ---- Wait for /health to come up.
    healthy = _wait_for_health(backend_url, HEALTH_TIMEOUT_SECONDS)
    if not healthy:
        console.print(
            f"[red]error:[/red] backend did not become healthy at "
            f"{backend_url} within {HEALTH_TIMEOUT_SECONDS:.0f}s. "
            "Check the logs above."
        )
        _terminate(backend_proc)
        raise SystemExit(1)

    console.print(f"  [green]backend ready[/green]")

    # ---- Spawn web app.
    web_proc: subprocess.Popen | None = None
    if not no_web:
        web_dir = repo_root / "apps" / "web"
        if not web_dir.exists():
            console.print(
                f"[yellow]warning:[/yellow] {web_dir} not found; skipping web app."
            )
        else:
            console.print(f"  web:     [cyan]{web_url}[/cyan]")
            web_script = "dev" if dev_mode else "start"
            web_env = {
                **os.environ,
                "PORT": str(web_port),
                "NEXT_PUBLIC_BACKEND_URL": backend_url,
            }
            web_proc = subprocess.Popen(
                [pnpm, "-C", str(web_dir), web_script],
                cwd=str(repo_root),
                env=web_env,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            # Best-effort wait — web takes longer to compile but we don't
            # want to block forever on a broken setup.
            if _wait_for_health(web_url, 30.0):
                console.print(f"  [green]web ready[/green]")
            else:
                console.print(
                    f"[yellow]warning:[/yellow] web app did not respond "
                    f"within 30s; it may still be compiling."
                )

    # ---- Open the browser.
    if not no_browser and not no_web:
        try:
            webbrowser.open(web_url, new=2)
        except Exception:
            # Don't fail the whole command if the browser refuses to open.
            console.print(
                f"[dim]could not open browser; visit {web_url} manually.[/dim]"
            )

    console.print(
        "\n[bold]Ready.[/bold] [dim]Ctrl+C to stop both processes.[/dim]\n"
    )

    # ---- Wait for either process to exit (or for Ctrl+C).
    procs = [p for p in (backend_proc, web_proc) if p is not None]
    try:
        _wait_for_any(procs)
    except KeyboardInterrupt:
        console.print("\n[dim]stopping...[/dim]")
    finally:
        for p in procs:
            _terminate(p)
        console.print("[dim]stopped.[/dim]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_repo_root() -> Path | None:
    """Walk upward from the cwd looking for a marker file."""

    cwd = Path.cwd().resolve()
    candidates = [cwd, *cwd.parents]
    for c in candidates:
        if (c / "pyproject.toml").exists():
            # Strong signal: also has the apps/api directory.
            if (c / "apps" / "api").exists():
                return c
        if (c / "Makefile").exists() and (c / "apps").exists():
            return c
    return None


def _resolve_backend_python(repo_root: Path) -> Path | None:
    """Find the venv python that has ``reverie_api`` installed."""

    candidates = [
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "bin" / "python",
        repo_root / ".venv" / "bin" / "python3",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Fallback to the python running this CLI — works if the user installed
    # everything system-wide.
    if shutil.which("python"):
        return Path(sys.executable)
    return None


def _wait_for_health(url: str, timeout_seconds: float) -> bool:
    """Poll ``GET /health`` until it returns 200 or we time out."""

    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{url.rstrip('/')}/health", timeout=1.0)
            if resp.status_code == 200:
                return True
            last_error = f"HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}"
        time.sleep(0.4)
    if last_error:
        # Useful breadcrumb in the logs when we time out.
        sys.stderr.write(
            f"[reverie start] last health probe error: {last_error}\n"
        )
    return False


def _wait_for_any(procs: list[subprocess.Popen]) -> None:
    """Block until any process exits, polling every 200ms."""

    while True:
        for p in procs:
            if p.poll() is not None:
                return
        time.sleep(0.2)


def _terminate(proc: subprocess.Popen) -> None:
    """Best-effort terminate. SIGTERM, then SIGKILL after a short grace."""

    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            # Windows: send CTRL_BREAK to the process group if we created
            # one; otherwise plain terminate (which on Windows is a hard
            # kill anyway).
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    except Exception:
        pass
