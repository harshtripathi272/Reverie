"""``reverie graph`` / ``reverie anomalies`` / ``reverie zoom`` commands.

Phase 2 CLI surface for the graph intelligence layer. Renders the DAG as
ASCII art (depth-indented) so the gate is provable from a terminal alone —
the 3D renderer is a Phase 5 concern.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import click
import httpx

from reverie_cli.client import ReverieClient
from reverie_cli.formatting import (
    format_duration_ms,
    format_timestamp_ms,
    make_console,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fetch_graph(
    client: ReverieClient, run_id: str, level: int | None
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if level is not None:
        params["level"] = level
    resp = client._client.get(f"/api/v1/runs/{run_id}/graph", params=params)  # noqa: SLF001
    resp.raise_for_status()
    return resp.json()


def _handle_http_error(console, exc: httpx.HTTPStatusError) -> None:
    if exc.response.status_code == 404:
        body = exc.response.json() if exc.response.text else {}
        console.print(
            f"[red]error:[/red] {body.get('error', 'not found')}: "
            f"{body.get('detail', '')}"
        )
        raise SystemExit(1)
    console.print(f"[red]error:[/red] {exc.response.status_code} {exc.response.text}")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# reverie graph
# ---------------------------------------------------------------------------


@click.command(
    "graph",
    short_help="Show the cognitive DAG of a run as indented ASCII.",
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
    "--level",
    type=click.IntRange(1, 4),
    default=None,
    help="Filter to nodes whose zoomLevel <= LEVEL (1=mission, 4=raw).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def graph_command(
    run_id: str,
    backend_url: str,
    level: int | None,
    as_json: bool,
) -> None:
    """Render the cognitive DAG for RUN_ID."""

    console = make_console()
    try:
        with ReverieClient(backend_url) as client:
            bundle = _fetch_graph(client, run_id, level)
    except httpx.HTTPStatusError as exc:
        _handle_http_error(console, exc)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(bundle, indent=2))
        return

    summary = bundle["summary"]
    title = (
        f"[bold]Graph[/bold] of run [dim]{bundle['runId']}[/dim] "
        f"-- {summary['totalNodes']} nodes, "
        f"{summary['totalEdges']} edges"
    )
    if level is not None:
        title += f" [yellow](zoom <= L{level})[/yellow]"
    console.print(title)

    nz = summary["nodesPerZoom"]
    console.print(
        f"  per-zoom: L1={nz.get('1', 0)} L2={nz.get('2', 0)} "
        f"L3={nz.get('3', 0)} L4={nz.get('4', 0)}"
    )

    abk = summary.get("anomaliesByKind") or {}
    if abk:
        console.print(
            "  [yellow]anomalies:[/yellow] "
            + ", ".join(f"{k}={v}" for k, v in sorted(abk.items()))
        )

    cp_len = summary.get("criticalPathLength", 0)
    if cp_len:
        console.print(f"  critical path: {cp_len} nodes")

    console.print()
    _render_tree(console, bundle["nodes"], bundle["edges"])


def _render_tree(console, nodes: list[dict], edges: list[dict]) -> None:
    """ASCII tree rendering, depth-indented, root events first."""

    by_id = {n["id"]: n for n in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        children[e["source"]].append(e["target"])
    # Order children by timestamp for deterministic, replay-faithful output.
    for k in children:
        children[k].sort(key=lambda nid: by_id[nid]["timestamp"])

    # Roots = nodes whose parent is missing from the kept set (after zoom
    # filtering, edges referencing dropped nodes are also dropped, so a node
    # whose parentId is not in by_id behaves as a root).
    in_edges: set[str] = {e["target"] for e in edges}
    roots = sorted(
        (n["id"] for n in nodes if n["id"] not in in_edges),
        key=lambda nid: by_id[nid]["timestamp"],
    )

    if not nodes:
        console.print("[dim]no nodes at this zoom level[/dim]")
        return

    seen: set[str] = set()
    for root_id in roots:
        _render_subtree(console, by_id, children, root_id, prefix="", seen=seen)


def _render_subtree(
    console,
    by_id: dict,
    children: dict[str, list[str]],
    node_id: str,
    *,
    prefix: str,
    seen: set[str],
    is_last: bool = True,
) -> None:
    if node_id in seen:
        return
    seen.add(node_id)
    node = by_id[node_id]

    branch = "`-- " if is_last else "|-- "
    type_styled = _style_type(node["type"])
    badges = []
    if node.get("onCriticalPath"):
        badges.append("[red]*[/red]")
    if node.get("anomalies"):
        kinds = ",".join(a["kind"] for a in node["anomalies"])
        badges.append(f"[yellow]! {kinds}[/yellow]")
    duration = format_duration_ms(node.get("durationMs"))
    badge_str = " ".join(badges)
    line = (
        f"{prefix}{branch}{type_styled} "
        f"[dim]({duration})[/dim] "
        f"{node.get('label', '')}"
    )
    if badge_str:
        line += f"  {badge_str}"
    console.print(line)

    next_prefix = prefix + ("    " if is_last else "|   ")
    kids = children.get(node_id, [])
    for i, kid in enumerate(kids):
        _render_subtree(
            console,
            by_id,
            children,
            kid,
            prefix=next_prefix,
            seen=seen,
            is_last=(i == len(kids) - 1),
        )


def _style_type(type_: str) -> str:
    if type_.startswith("goal."):
        return f"[bold magenta]{type_}[/bold magenta]"
    if type_.startswith("tool."):
        return f"[cyan]{type_}[/cyan]"
    if type_.startswith("retry."):
        return f"[yellow]{type_}[/yellow]"
    if type_.endswith(".failed"):
        return f"[red]{type_}[/red]"
    if type_.startswith("subagent."):
        return f"[blue]{type_}[/blue]"
    return type_


# ---------------------------------------------------------------------------
# reverie anomalies
# ---------------------------------------------------------------------------


@click.command(
    "anomalies",
    short_help="List anomaly annotations for a run.",
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
    "--kind",
    type=click.Choice(["loop", "hotspot", "bottleneck", "poison", "explosion", "abandon"]),
    default=None,
    help="Filter to one anomaly kind.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def anomalies_command(
    run_id: str,
    backend_url: str,
    kind: str | None,
    as_json: bool,
) -> None:
    """List the anomaly annotations attached to RUN_ID's nodes."""

    console = make_console()
    try:
        with ReverieClient(backend_url) as client:
            resp = client._client.get(  # noqa: SLF001
                f"/api/v1/runs/{run_id}/anomalies"
            )
            resp.raise_for_status()
            items = resp.json()
    except httpx.HTTPStatusError as exc:
        _handle_http_error(console, exc)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if kind is not None:
        items = [a for a in items if a["kind"] == kind]

    if as_json:
        click.echo(json.dumps(items, indent=2))
        return

    if not items:
        console.print("[dim]no anomalies detected for this run[/dim]")
        return

    by_kind: dict[str, list[dict]] = defaultdict(list)
    for a in items:
        by_kind[a["kind"]].append(a)

    console.print(f"[bold]{len(items)}[/bold] anomalies in run [dim]{run_id}[/dim]")
    for k in sorted(by_kind):
        anns = by_kind[k]
        console.print(f"\n[yellow]{k}[/yellow] ({len(anns)})")
        for a in anns:
            console.print(
                f"  * [{_severity_color(a['severity'])}]{a['severity']}[/]"
                f" [dim]@ {format_timestamp_ms(a['timestamp'])}[/dim]"
                f" {_style_type(a['eventType'])}"
                f" -- {a['detail']}"
            )


def _severity_color(s: str) -> str:
    return {"info": "blue", "warning": "yellow", "error": "red"}.get(s, "white")


# ---------------------------------------------------------------------------
# reverie zoom
# ---------------------------------------------------------------------------


@click.command(
    "zoom",
    short_help="Show the per-zoom-level node distribution for a run.",
)
@click.argument("run_id")
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def zoom_command(
    run_id: str,
    backend_url: str,
    as_json: bool,
) -> None:
    """Show how RUN_ID's nodes distribute across zoom levels."""

    console = make_console()
    try:
        with ReverieClient(backend_url) as client:
            bundle = _fetch_graph(client, run_id, level=None)
    except httpx.HTTPStatusError as exc:
        _handle_http_error(console, exc)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    summary = bundle["summary"]
    nz = summary["nodesPerZoom"]
    out = {
        "runId": bundle["runId"],
        "totalNodes": summary["totalNodes"],
        "perZoom": {
            "L1_mission": nz.get("1", 0),
            "L2_task": nz.get("2", 0),
            "L3_operation": nz.get("3", 0),
            "L4_raw": nz.get("4", 0),
        },
    }
    if as_json:
        click.echo(json.dumps(out, indent=2))
        return

    console.print(
        f"[bold]Zoom distribution[/bold] for run [dim]{bundle['runId']}[/dim] "
        f"-- {summary['totalNodes']} nodes total"
    )
    bars = [
        ("L1", "mission view", nz.get("1", 0)),
        ("L2", "task view", nz.get("2", 0)),
        ("L3", "operation view", nz.get("3", 0)),
        ("L4", "raw view", nz.get("4", 0)),
    ]
    max_count = max((n for _, _, n in bars), default=1) or 1
    for key, label, count in bars:
        width = int(round(count / max_count * 40)) if count else 0
        bar = "#" * width
        console.print(f"  {key} [dim]({label}):[/dim] {count:>5}  {bar}")
