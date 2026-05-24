"""Tests for ``reverie start``.

We don't actually spawn the backend or web app — we mock subprocess.Popen
and httpx so the command's wiring can be verified without booting servers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from reverie_cli.commands.start import (
    _detect_repo_root,
    _resolve_backend_python,
    start_command,
)


# ---------------------------------------------------------------------------
# Repo root detection
# ---------------------------------------------------------------------------


class TestDetectRepoRoot:
    def test_finds_root_via_apps_marker(self, tmp_path: Path):
        # Build a fake repo: tmp_path / Makefile + tmp_path / apps/.
        (tmp_path / "Makefile").write_text("# fake")
        (tmp_path / "apps").mkdir()
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)

        with patch("reverie_cli.commands.start.Path.cwd", return_value=nested):
            root = _detect_repo_root()
        assert root == tmp_path

    def test_returns_none_when_no_marker(self, tmp_path: Path):
        deeper = tmp_path / "deep"
        deeper.mkdir()
        with patch("reverie_cli.commands.start.Path.cwd", return_value=deeper):
            # On Windows, parents include the drive root which has lots of
            # things — so we patch this explicitly to a clean tree only.
            with patch.object(Path, "exists", return_value=False):
                root = _detect_repo_root()
        assert root is None


# ---------------------------------------------------------------------------
# Backend python resolution
# ---------------------------------------------------------------------------


class TestResolveBackendPython:
    def test_prefers_windows_venv_path(self, tmp_path: Path):
        venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("")  # touch
        result = _resolve_backend_python(tmp_path)
        assert result == venv_python

    def test_prefers_unix_venv_path(self, tmp_path: Path):
        venv_python = tmp_path / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("")
        result = _resolve_backend_python(tmp_path)
        assert result == venv_python


# ---------------------------------------------------------------------------
# Command surface
# ---------------------------------------------------------------------------


class TestCommandSurface:
    def test_help_lists_options(self):
        runner = CliRunner()
        result = runner.invoke(start_command, ["--help"])
        assert result.exit_code == 0
        for token in (
            "--backend-port",
            "--web-port",
            "--no-web",
            "--no-browser",
            "--dev",
            "--prod",
            "--repo",
        ):
            assert token in result.output

    def test_no_repo_root_exits_1(self, tmp_path: Path):
        runner = CliRunner()
        # Force _detect_repo_root() to return None.
        with patch(
            "reverie_cli.commands.start._detect_repo_root", return_value=None
        ):
            result = runner.invoke(start_command, [])
        assert result.exit_code == 1
        assert "could not find" in result.output

    def test_no_python_exits_1(self, tmp_path: Path):
        runner = CliRunner()
        with patch(
            "reverie_cli.commands.start._detect_repo_root",
            return_value=tmp_path,
        ), patch(
            "reverie_cli.commands.start._resolve_backend_python",
            return_value=None,
        ):
            result = runner.invoke(start_command, [])
        assert result.exit_code == 1
        assert "Python" in result.output

    def test_unhealthy_backend_terminates_and_exits_1(self, tmp_path: Path):
        """If the backend never reports healthy, start should give up cleanly
        and not leave a zombie process."""

        runner = CliRunner()
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None  # still running

        # Build a fake repo tree that satisfies _resolve_backend_python.
        venv_python = tmp_path / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("")

        with patch(
            "reverie_cli.commands.start._detect_repo_root",
            return_value=tmp_path,
        ), patch(
            "reverie_cli.commands.start._resolve_backend_python",
            return_value=venv_python,
        ), patch(
            "reverie_cli.commands.start.subprocess.Popen",
            return_value=fake_proc,
        ), patch(
            "reverie_cli.commands.start._wait_for_health", return_value=False
        ), patch(
            "reverie_cli.commands.start._terminate"
        ) as mock_term:
            result = runner.invoke(start_command, ["--no-web", "--no-browser"])

        assert result.exit_code == 1
        assert "did not become healthy" in result.output
        # Backend was terminated.
        mock_term.assert_called_with(fake_proc)
