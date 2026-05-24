"""Top-level Click entry point.

The CLI is structured as a parent ``cli`` group that bundles all commands.
The ``[project.scripts]`` entry in pyproject.toml maps ``reverie`` →
``reverie_cli.main:cli``.
"""

from __future__ import annotations

import click

from reverie_cli import __version__
from reverie_cli.commands.replay import replay_command
from reverie_cli.commands.run import run_command
from reverie_cli.commands.runs import runs_group
from reverie_cli.commands.status import status_command


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Reverie — cognitive observability for AI agents.",
)
@click.version_option(__version__, prog_name="reverie")
def cli() -> None:
    """Top-level CLI entry point."""


# Register commands.
cli.add_command(run_command)
cli.add_command(status_command)
cli.add_command(replay_command)
cli.add_command(runs_group)


def main() -> None:
    """Console-script shim for ``[project.scripts]``."""

    cli()


if __name__ == "__main__":
    cli()
