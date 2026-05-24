"""``reverie replay <run-id>`` — terminal replay (Phase 1).

Streams the events of a run to stdout. Two seek modes beyond plain start-to-end:

- ``--to N``        scrubs through the first N events only
- ``--jump-failure`` jumps straight to the first failure (highlighted)

Phase 5 will replace this with a 3D scrubber. Until then the terminal output
is the canonical replay UI per SRS Phase 1 gate.
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
    short_help="Replay a recorded run's events to the terminal.",
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
@click.option(
    "--to",
    "to_index",
    type=click.IntRange(0, 1_000_000),
    default=None,
    help="Stop after replaying this many events (1-based).",
)
@click.option(
    "--jump-failure",
    is_flag=True,
    help="Replay only up to (and highlighting) the first failure event.",
)
def replay_command(
    run_id: str,
    backend_url: str,
    speed: str,
    limit: int,
    to_index: int | None,
    jump_failure: bool,
) -> None:
    """Stream the events of RUN_ID to stdout."""

    console = make_console()

    try:
        with ReverieClient(backend_url) as client:
            run = client.get_run(run_id)
            events = client.get_events(run_id, limit=limit)
            failure_index: int | None = None
            if jump_failure:
                failure_index = _fetch_first_failure_index(client, run_id, console)
                if failure_index is None:
                    console.print(
                        f"[dim]run {run_id} has no failures to jump to[/dim]"
                    )
                    return
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

    # Resolve the final stop index.
    stop = len(events)
    if to_index is not None:
        stop = min(stop, to_index)
    if failure_index is not None:
        stop = min(stop, failure_index)
    events = events[:stop]

    headline = (
        f"[bold]Replaying[/bold] run {run['id']} "
        f"([dim]{len(events)}/{run['totalEvents']} events, "
        f"goal={run.get('goal') or '—'}[/dim])"
    )
    if failure_index is not None:
        headline += f" — [red]jumping to first failure at index {failure_index}[/red]"
    console.print(headline)

    speed_factor = 0.0 if speed == "instant" else 1.0 / float(speed)
    last_ts: int | None = None
    for i, evt in enumerate(events, start=1):
        ts = evt["timestamp"]
        if speed_factor and last_ts is not None:
            wait = (ts - last_ts) / 1000.0 * speed_factor
            if wait > 0:
                time.sleep(min(wait, 5.0))  # cap at 5s — never block forever
        last_ts = ts

        is_failure_target = (
            failure_index is not None and i == failure_index
        )
        _print_event_line(console, i, evt, highlight=is_failure_target)


def _fetch_first_failure_index(
    client: ReverieClient, run_id: str, console
) -> int | None:
    try:
        resp = client._client.get(  # noqa: SLF001
            f"/api/v1/runs/{run_id}/failures"
        )
    except httpx.HTTPError as exc:
        console.print(f"[red]error contacting /failures:[/red] {exc}")
        raise SystemExit(1)
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        console.print(f"[red]error:[/red] {resp.status_code} {resp.text}")
        raise SystemExit(1)
    return int(resp.json()["index"])


def _print_event_line(console, n: int, evt: dict, *, highlight: bool = False) -> None:
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
    line = (
        f"[dim]{n:>4}[/dim] {format_timestamp_ms(evt['timestamp'])} "
        f"{indent}[bold]{type_}[/bold] "
        f"[dim]({duration})[/dim] "
        f"{detail}"
    )
    if highlight:
        # Wrap the whole row in a highlight to make it impossible to miss.
        console.print(f"[bold red on yellow] FAILURE [/bold red on yellow] {line}")
    else:
        console.print(line)
