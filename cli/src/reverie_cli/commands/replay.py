"""``reverie replay <run-id>`` — Phase 1 preview.

Phase 0 ships a minimal ``replay``: it fetches the run's events and prints
them sequentially, with optional throttling to mimic the original agent's
pacing. The full snapshot-restoring replay engine arrives in Phase 1.
"""

from __future__ import annotations

import time

import click
import httpx

from reverie_cli.client import ReverieClient
from reverie_cli.formatting import (
    format_duration_ms,
    format_timestamp_ms,
    make_console,
)


@click.command(
    "replay",
    short_help="Replay a recorded run's events to the terminal (Phase 1 preview).",
)
@click.argument("run_id")
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
@click.option(
    "--speed",
    type=click.Choice(["1", "2", "5", "10", "instant"]),
    default="instant",
    show_default=True,
    help="Playback speed. 'instant' prints with no delay.",
)
@click.option(
    "--limit",
    default=10_000,
    show_default=True,
    type=click.IntRange(1, 100_000),
)
def replay_command(run_id: str, backend_url: str, speed: str, limit: int) -> None:
    """Stream the events of RUN_ID to stdout, optionally throttled by SPEED.

    This is a Phase 0 preview. The full timeline scrubber, snapshot
    reconstruction, and 3D view come in later phases.
    """

    console = make_console()
    try:
        with ReverieClient(backend_url) as client:
            run = client.get_run(run_id)
            events = client.get_events(run_id, limit=limit)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            console.print(f"[red]error:[/red] run not found: {run_id}")
            raise SystemExit(1)
        console.print(f"[red]error:[/red] {exc.response.status_code} {exc.response.text}")
        raise SystemExit(1)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if not events:
        console.print(f"[dim]run {run_id} has no events to replay[/dim]")
        return

    console.print(
        f"[bold]Replaying[/bold] run {run['id']} "
        f"([dim]{len(events)} events, "
        f"goal={run.get('goal') or '—'}[/dim])"
    )

    speed_factor = 0.0 if speed == "instant" else 1.0 / float(speed)
    last_ts: int | None = None
    for i, evt in enumerate(events, start=1):
        ts = evt["timestamp"]
        if speed_factor and last_ts is not None:
            wait = (ts - last_ts) / 1000.0 * speed_factor
            if wait > 0:
                time.sleep(min(wait, 5.0))  # cap at 5s — never block forever
        last_ts = ts

        _print_event_line(console, i, evt)


def _print_event_line(console, n: int, evt: dict) -> None:
    type_ = evt["type"]
    payload = evt.get("payload", {})
    detail = ""
    kind = payload.get("_type", "")
    if kind == "goal":
        detail = payload.get("intent", "")
    elif kind == "tool":
        detail = payload.get("toolName", "")
        if payload.get("success") is False:
            detail += f" → ERROR: {payload.get('errorMessage') or ''}"
    elif kind == "subagent":
        detail = f"→ {payload.get('agentType', '?')}"
    elif kind == "validation":
        detail = f"{payload.get('checkName', '?')} = {'pass' if payload.get('passed') else 'fail'}"
    elif kind == "reasoning":
        detail = (payload.get("summary") or "").splitlines()[0][:80]
    elif kind == "retry":
        detail = f"attempt {payload.get('attempt')}: {payload.get('reason', '')}"

    duration = format_duration_ms(evt.get("durationMs"))
    indent = "  " * min(int(evt["depth"]), 8)
    console.print(
        f"[dim]{n:>4}[/dim] {format_timestamp_ms(evt['timestamp'])} "
        f"{indent}[bold]{type_}[/bold] "
        f"[dim]({duration})[/dim] "
        f"{detail}"
    )
