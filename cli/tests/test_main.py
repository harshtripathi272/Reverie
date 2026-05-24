"""Top-level CLI tests — help, version, command discovery."""

from __future__ import annotations

from click.testing import CliRunner

from reverie_cli.main import cli


def test_help_lists_all_commands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("run", "status", "runs", "replay"):
        assert cmd in result.output


def test_version_prints_semver():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_unknown_command_exits_nonzero():
    runner = CliRunner()
    result = runner.invoke(cli, ["nonsense"])
    assert result.exit_code != 0
