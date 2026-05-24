"""``reverie init`` — write the global config so the CLI works from anywhere.

Most users want to be able to run ``reverie start`` from inside their own
project directory, not from the Reverie checkout. This command stores the
location of the Reverie repo in ``~/.reverie/config.json`` so subsequent
commands can find it.

Behaviour:

  - Run from inside a Reverie checkout (no args) → auto-detect the repo
    path and save it.
  - Run from anywhere with ``--repo /path/to/reverie`` → save that path.
  - Run with ``--show`` → print the current config.
  - Run with ``--clear`` → delete the config file.

Idempotent. Re-running overwrites the file.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from reverie_cli.app_config import (
    AppConfig,
    detect_repo_path,
    load_config,
    save_config,
)
from reverie_cli import app_config as _cfg_mod
from reverie_cli.formatting import make_console


@click.command(
    "init",
    short_help="Save the Reverie repo path so the CLI works from anywhere.",
)
@click.option(
    "--repo",
    "repo",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Path to the Reverie repo. Defaults to auto-detect from cwd.",
)
@click.option(
    "--backend",
    "backend_url",
    default=None,
    help="Default backend URL stored in the config.",
)
@click.option(
    "--data-dir",
    "data_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Override where the SQLite event log lives (defaults to repo/data).",
)
@click.option(
    "--show",
    is_flag=True,
    help="Print the current config and exit.",
)
@click.option(
    "--clear",
    is_flag=True,
    help="Delete the config file.",
)
def init_command(
    repo: Path | None,
    backend_url: str | None,
    data_dir: Path | None,
    show: bool,
    clear: bool,
) -> None:
    """Save the Reverie repo path so the CLI works from anywhere."""

    console = make_console()

    if show:
        cfg = load_config()
        as_dict = cfg.to_dict()
        if not any(k for k in as_dict if k != "version"):
            console.print(
                "[dim]No config saved yet. Run[/dim] [bold]reverie init[/bold] "
                "[dim]from inside the Reverie repo, or pass --repo.[/dim]"
            )
            return
        console.print(f"[bold]Config[/bold]: [dim]{_cfg_mod.CONFIG_FILE}[/dim]")
        console.print(json.dumps(as_dict, indent=2))
        return

    if clear:
        if _cfg_mod.CONFIG_FILE.exists():
            _cfg_mod.CONFIG_FILE.unlink()
            console.print(f"[green]ok[/green] removed {_cfg_mod.CONFIG_FILE}")
        else:
            console.print(f"[dim]no config to clear at {_cfg_mod.CONFIG_FILE}[/dim]")
        return

    # Save mode.
    repo_path = repo.resolve() if repo is not None else detect_repo_path()
    if repo_path is None:
        console.print(
            "[red]error:[/red] could not auto-detect the Reverie repo from "
            "the current directory.\n"
            "Run [bold]reverie init[/bold] from inside the Reverie checkout, "
            "or pass [bold]--repo /path/to/reverie[/bold]."
        )
        raise SystemExit(1)

    if not (repo_path / "apps" / "api").exists():
        console.print(
            f"[yellow]warning:[/yellow] {repo_path} doesn't look like a "
            "Reverie repo (missing apps/api). Saving anyway."
        )

    # Preserve existing values not being overridden by this invocation.
    existing = load_config()
    cfg = AppConfig(
        repo_path=repo_path,
        backend_url=backend_url or existing.backend_url,
        data_dir=(data_dir.resolve() if data_dir is not None else existing.data_dir),
    )
    path = save_config(cfg)
    console.print(f"[green]ok[/green] saved [bold]{path}[/bold]")
    console.print(f"     repo:    [cyan]{cfg.repo_path}[/cyan]")
    if cfg.backend_url:
        console.print(f"     backend: [cyan]{cfg.backend_url}[/cyan]")
    if cfg.data_dir:
        console.print(f"     data:    [cyan]{cfg.data_dir}[/cyan]")
    console.print()
    console.print(
        "[dim]You can now run[/dim] [bold]reverie start[/bold] [dim]from "
        "anywhere on your machine.[/dim]"
    )
