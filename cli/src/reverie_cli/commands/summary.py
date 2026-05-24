"""``reverie summary`` — list clusters or fetch an AI summary for one (Phase 3)."""

from __future__ import annotations

import json

import click
import httpx

from reverie_cli.client import ReverieClient
from reverie_cli.formatting import make_console


@click.command(
    "summary",
    short_help="List clusters or fetch an AI summary for one.",
)
@click.argument("run_id")
@click.option(
    "--cluster",
    "cluster_id",
    default=None,
    help="When given, fetch (or generate) an AI summary for this cluster.",
)
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
@click.option("--refresh", is_flag=True, help="Force a fresh API call (skip the cache).")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def summary_command(
    run_id: str,
    cluster_id: str | None,
    backend_url: str,
    refresh: bool,
    as_json: bool,
) -> None:
    """Inspect AI-summarized regions of RUN_ID."""

    console = make_console()

    if cluster_id is None:
        # List the run's clusters.
        try:
            with ReverieClient(backend_url) as client:
                resp = client._client.get(f"/api/v1/runs/{run_id}/graph")  # noqa: SLF001
                resp.raise_for_status()
                bundle = resp.json()
        except httpx.HTTPStatusError as exc:
            _handle_error(console, exc)
        except httpx.HTTPError as exc:
            console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
            raise SystemExit(1)

        clusters = bundle.get("clusters") or []
        if as_json:
            click.echo(json.dumps(clusters, indent=2))
            return
        if not clusters:
            console.print("[dim]no clusters yet for this run[/dim]")
            return
        console.print(f"[bold]{len(clusters)}[/bold] clusters in run [dim]{run_id}[/dim]")
        for c in clusters:
            console.print(
                f"  [cyan]{c['type']}[/cyan] [dim]{c['id']}[/dim] "
                f"[yellow]{c['label']}[/yellow] "
                f"({len(c['memberEventIds'])} events)"
            )
        console.print(
            "\nUse [bold]reverie summary <run-id> --cluster <id>[/bold] "
            "to fetch an AI summary."
        )
        return

    # Fetch / generate summary for one cluster.
    try:
        with ReverieClient(backend_url) as client:
            params = {"refresh": "true"} if refresh else {}
            resp = client._client.post(  # noqa: SLF001
                f"/api/v1/runs/{run_id}/clusters/{cluster_id}/summary",
                params=params,
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as exc:
        _handle_error(console, exc)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(body, indent=2))
        return

    status = body.get("status", "?")
    text = body.get("summary", "")
    console.print(
        f"[bold]Cluster summary[/bold] [dim]{cluster_id}[/dim] "
        f"({body.get('memberCount', '?')} events) — model={body.get('model', '?')}"
    )
    if status == "ok":
        console.print()
        console.print(text)
    elif status == "no_api_key":
        console.print(
            "[yellow]ANTHROPIC_API_KEY is not set on the backend; "
            "no summary available.[/yellow]"
        )
    elif status == "disabled":
        console.print(
            "[yellow]AI summarization is disabled on the backend "
            "(REVERIE_AI_DISABLED).[/yellow]"
        )
    elif status == "rate_limited":
        console.print("[yellow]Anthropic API rate limit hit; try again later.[/yellow]")
    else:
        console.print(f"[red]API error:[/red] {body.get('detail', 'unknown')}")


def _handle_error(console, exc: httpx.HTTPStatusError) -> None:
    if exc.response.status_code == 404:
        body = exc.response.json() if exc.response.text else {}
        msg = body.get("error", "not found")
        console.print(f"[red]error:[/red] {msg}: {body.get('detail', '')}")
        raise SystemExit(1)
    console.print(f"[red]error:[/red] {exc.response.status_code} {exc.response.text}")
    raise SystemExit(1)
