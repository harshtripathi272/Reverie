"""``reverie run <command...>`` — invoke any command with auto-instrumentation.

Mechanism
---------

We do NOT use ``PYTHONSTARTUP`` (it only runs in interactive mode). We use
``PYTHONPATH`` + ``sitecustomize`` instead, which is what
``opentelemetry-instrument`` and most other auto-instrumenters do.

The bootstrap directory ships a ``sitecustomize.py`` that, once it appears
on ``sys.path``, gets imported by Python's ``site.py`` before user code runs.
We prepend our directory to ``PYTHONPATH``, spawn the user's command, and
exit with its status code.

This works for any Python entrypoint:
  - ``python script.py``
  - ``python -m my_module``
  - ``python -c "..."``
  - any console script (e.g. ``my-cli`` if it's a ``[project.scripts]`` entry)

For non-Python commands the wrapper is still a no-op pass-through.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import click

from reverie_cli._bootstrap import dir_path as bootstrap_dir


@click.command(
    "run",
    context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False},
    short_help="Run a command with Reverie auto-instrumentation.",
)
@click.argument("command", nargs=-1, type=click.UNPROCESSED)
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
    help="Reverie backend URL.",
)
@click.option(
    "--agent-id",
    envvar="REVERIE_AGENT_ID",
    default=None,
    help="Agent id label written to every emitted event.",
)
@click.option(
    "--no-instrument",
    is_flag=True,
    help="Run the command without injecting Reverie instrumentation.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the command that would run, including environment additions, then exit.",
)
def run_command(
    command: tuple[str, ...],
    backend_url: str,
    agent_id: str | None,
    no_instrument: bool,
    dry_run: bool,
) -> None:
    """Run COMMAND with Reverie instrumentation.

    Examples:

      reverie run python my_agent.py

      reverie run python -m my_package.agent

      reverie run --backend http://reverie.local:8000 python script.py
    """

    if not command:
        raise click.UsageError(
            "No command given. Try: reverie run python my_agent.py"
        )

    env = _build_env(
        backend_url=backend_url,
        agent_id=agent_id,
        no_instrument=no_instrument,
    )

    resolved = _resolve_executable(command[0])
    argv: list[str] = [resolved, *command[1:]]

    if dry_run:
        _print_dry_run(argv, env)
        return

    if not no_instrument:
        click.echo(
            f"[reverie] streaming to {backend_url} (PID will be printed below)",
            err=True,
        )

    try:
        completed = subprocess.run(argv, env=env, check=False)
    except FileNotFoundError as exc:
        raise click.ClickException(f"command not found: {exc.filename or command[0]!r}") from exc

    sys.exit(completed.returncode)


# ---------------------------------------------------------------------------
# Helpers (importable for tests)
# ---------------------------------------------------------------------------


def _build_env(
    *,
    backend_url: str,
    agent_id: str | None,
    no_instrument: bool,
) -> dict[str, str]:
    """Construct the child-process environment.

    Always returns a fresh dict; never mutates ``os.environ``.
    """

    env = dict(os.environ)
    env["REVERIE_BACKEND_URL"] = backend_url
    if agent_id is not None:
        env["REVERIE_AGENT_ID"] = agent_id

    if no_instrument:
        # Keep the env vars (so user code that opts in via REVERIE_* still
        # works), but don't inject sitecustomize.
        env["REVERIE_DISABLED"] = "1"
        return env

    boot_dir = str(bootstrap_dir())
    existing = env.get("PYTHONPATH", "")
    # Avoid duplicating ourselves on repeat invocations.
    parts = existing.split(os.pathsep) if existing else []
    if boot_dir not in parts:
        parts.insert(0, boot_dir)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _resolve_executable(name: str) -> str:
    """Resolve ``name`` to an absolute path if possible.

    Special-case: ``"python"`` (and a couple of common variants) resolves to
    ``sys.executable`` — the Python interpreter that's running the
    ``reverie`` CLI itself. This is almost always what the user wants and
    avoids subtle PATH-ordering bugs on Windows where ``shutil.which("python")``
    might find a system Python that doesn't have ``reverie_openai`` installed.

    Other commands resolve via ``shutil.which`` and fall back to the original
    string if no match — the OS will produce the final FileNotFoundError.
    """

    if os.path.sep in name or (os.path.altsep and os.path.altsep in name):
        # Caller passed a path; trust it.
        return name

    # Match "python", "python3", "python3.x" — covers ~all common forms.
    base = os.path.basename(name).lower()
    if base in {"python", "python3"} or (base.startswith("python3.") and len(base) <= 10):
        # Use the same interpreter that's running the CLI. This guarantees
        # the child sees the same site-packages (including reverie_openai).
        return sys.executable

    found = shutil.which(name)
    return found or name


def _print_dry_run(argv: list[str], env: dict[str, str]) -> None:
    """Pretty-print the planned invocation. Used by ``--dry-run`` and tests."""

    relevant = {
        k: v for k, v in env.items() if k.startswith("REVERIE_") or k == "PYTHONPATH"
    }
    click.echo("would execute:")
    click.echo("  " + " ".join(shlex.quote(a) for a in argv))
    if relevant:
        click.echo("with environment additions:")
        for k in sorted(relevant):
            click.echo(f"  {k}={relevant[k]}")


def _bootstrap_dir_for_diagnostics() -> Path:
    """Exposed so tests can assert the directory exists."""

    return bootstrap_dir()
