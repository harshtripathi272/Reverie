"""``reverie compare <run-a> <run-b>`` — comparative debugger (Phase 4)."""

from __future__ import annotations

import json

import click
import httpx

from reverie_cli.client import ReverieClient
from reverie_cli.formatting import make_console


@click.command(
    "compare",
    short_help="Compare two runs and identify the divergence point + fault tree.",
)
@click.argument("run_a")
@click.argument("run_b")
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
@click.option(
    "--no-narrative",
    is_flag=True,
    help="Skip the AI-generated narrative (faster; no Anthropic call).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def compare_command(
    run_a: str,
    run_b: str,
    backend_url: str,
    no_narrative: bool,
    as_json: bool,
) -> None:
    """Compare RUN_A with RUN_B."""

    console = make_console()
    try:
        with ReverieClient(backend_url) as client:
            params = {"with_narrative": "false"} if no_narrative else {}
            resp = client._client.post(  # noqa: SLF001
                "/api/v1/compare",
                params=params,
                json={"runAId": run_a, "runBId": run_b},
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            err = exc.response.json() if exc.response.text else {}
            console.print(
                f"[red]error:[/red] {err.get('error', 'not found')}: "
                f"{err.get('detail', '')}"
            )
            raise SystemExit(1)
        console.print(f"[red]error:[/red] {exc.response.status_code} {exc.response.text}")
        raise SystemExit(1)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(body, indent=2))
        return

    _render(console, body, run_a, run_b)


def _render(console, body: dict, run_a: str, run_b: str) -> None:
    diff = body["diff"]
    console.print(
        f"[bold]Comparing[/bold] [cyan]{run_a[:8]}...[/cyan] (A) vs "
        f"[magenta]{run_b[:8]}...[/magenta] (B)"
    )
    console.print(
        f"  alignment score: {diff['alignmentScore']:.1f}  "
        f"(matched={diff['matchedCount']} "
        f"onlyA={diff['onlyACount']} onlyB={diff['onlyBCount']})"
    )

    # Headline numbers — token, duration, retry, failure deltas.
    token_arrow = _arrow(diff["tokenDelta"])
    dur_arrow = _arrow(diff["durationDeltaMs"])
    console.print(f"  tokens: B {token_arrow} A by {abs(diff['tokenDelta'])}")
    console.print(f"  duration: B {dur_arrow} A by {abs(diff['durationDeltaMs'])}ms")
    console.print(
        f"  retries: A={diff['retriesInA']} B={diff['retriesInB']}"
    )
    console.print(
        f"  failures: A={diff['failuresInA']} B={diff['failuresInB']}"
    )

    if diff["extraToolsInB"]:
        console.print(
            f"  [yellow]extra tools in B:[/yellow] "
            + ", ".join(diff["extraToolsInB"])
        )
    if diff["missingToolsInB"]:
        console.print(
            f"  [yellow]missing tools in B:[/yellow] "
            + ", ".join(diff["missingToolsInB"])
        )

    # Divergence point.
    console.print()
    div = diff.get("divergence")
    if div is None:
        console.print("[green]No divergence:[/green] runs aligned 1:1.")
    else:
        console.print(
            f"[bold red]Divergence at pair {div['pairIndex']}[/bold red] "
            f"-- {div['reason']}"
        )
        if div["aEventId"]:
            console.print(f"  A event id: {div['aEventId']}")
        if div["bEventId"]:
            console.print(f"  B event id: {div['bEventId']}")

    # Fault trees.
    if body.get("faultTreeA"):
        console.print()
        console.print("[bold]Fault tree (A)[/bold]")
        for eid in body["faultTreeA"]["chainEventIds"]:
            console.print(f"  -> {eid}")
    if body.get("faultTreeB"):
        console.print()
        console.print("[bold red]Fault tree (B)[/bold red]")
        for eid in body["faultTreeB"]["chainEventIds"]:
            console.print(f"  -> {eid}")

    # AI narrative (or status if unavailable).
    console.print()
    status = body.get("narrativeStatus", "skipped")
    text = body.get("narrative", "")
    if status == "ok" and text:
        console.print("[bold]AI narrative[/bold]")
        console.print(text)
    elif status == "skipped":
        console.print("[dim]AI narrative skipped (--no-narrative)[/dim]")
    elif status == "no_api_key":
        console.print(
            "[dim]AI narrative unavailable: ANTHROPIC_API_KEY not set on the backend.[/dim]"
        )
    elif status == "disabled":
        console.print("[dim]AI narrative disabled on the backend.[/dim]")
    else:
        console.print(f"[yellow]AI narrative status:[/yellow] {status}")


def _arrow(delta: int) -> str:
    if delta > 0:
        return "[red]>[/red]"
    if delta < 0:
        return "[green]<[/green]"
    return "="
