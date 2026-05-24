"""Tests for ``reverie run``.

The dry-run path is exhaustively unit-tested with Click's CliRunner. A
separate end-to-end subprocess test in ``test_bootstrap.py`` confirms the
real injection mechanism.
"""

from __future__ import annotations

import os
import sys

from click.testing import CliRunner

from reverie_cli._bootstrap import dir_path as bootstrap_dir
from reverie_cli.commands.run import _build_env, _resolve_executable, run_command


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_run_without_args_errors():
    runner = CliRunner()
    result = runner.invoke(run_command, [])
    assert result.exit_code != 0
    assert "No command given" in result.output


def test_dry_run_prints_planned_invocation():
    runner = CliRunner()
    result = runner.invoke(run_command, ["--dry-run", "python", "script.py"])
    assert result.exit_code == 0, result.output
    assert "would execute" in result.output
    assert "script.py" in result.output
    # Bootstrap dir must appear on PYTHONPATH.
    assert "PYTHONPATH=" in result.output
    assert str(bootstrap_dir()) in result.output
    assert "REVERIE_BACKEND_URL=http://127.0.0.1:8000" in result.output


def test_dry_run_passes_through_unknown_options():
    runner = CliRunner()
    result = runner.invoke(
        run_command,
        ["--dry-run", "python", "-m", "my_module", "--", "--flag"],
    )
    assert result.exit_code == 0
    assert "-m" in result.output
    assert "my_module" in result.output


def test_dry_run_respects_custom_backend():
    runner = CliRunner()
    result = runner.invoke(
        run_command,
        [
            "--dry-run",
            "--backend",
            "http://custom.local:9999",
            "python",
            "x.py",
        ],
    )
    assert result.exit_code == 0
    assert "REVERIE_BACKEND_URL=http://custom.local:9999" in result.output


def test_no_instrument_skips_pythonpath(monkeypatch):
    # Clear PYTHONPATH so we see what the command itself adds (which should
    # be: nothing, since --no-instrument skips the bootstrap injection).
    monkeypatch.delenv("PYTHONPATH", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        run_command,
        ["--dry-run", "--no-instrument", "python", "x.py"],
    )
    assert result.exit_code == 0
    # PYTHONPATH should not be mentioned in the printed env additions.
    assert "PYTHONPATH=" not in result.output
    # But REVERIE_DISABLED must be set so user code that imports the adapter
    # also sees a no-op.
    assert "REVERIE_DISABLED=1" in result.output


# ---------------------------------------------------------------------------
# _build_env unit
# ---------------------------------------------------------------------------


class TestBuildEnv:
    def test_prepends_bootstrap_dir_to_pythonpath(self):
        env = _build_env(
            backend_url="http://x", agent_id=None, no_instrument=False
        )
        parts = env["PYTHONPATH"].split(os.pathsep)
        assert parts[0] == str(bootstrap_dir())

    def test_preserves_existing_pythonpath(self, monkeypatch):
        monkeypatch.setenv("PYTHONPATH", "/some/user/lib")
        env = _build_env(
            backend_url="http://x", agent_id=None, no_instrument=False
        )
        parts = env["PYTHONPATH"].split(os.pathsep)
        assert "/some/user/lib" in parts
        assert str(bootstrap_dir()) in parts

    def test_does_not_double_inject(self, monkeypatch):
        monkeypatch.setenv("PYTHONPATH", str(bootstrap_dir()))
        env = _build_env(
            backend_url="http://x", agent_id=None, no_instrument=False
        )
        parts = env["PYTHONPATH"].split(os.pathsep)
        # Bootstrap dir appears exactly once.
        assert parts.count(str(bootstrap_dir())) == 1

    def test_agent_id_passed_through(self):
        env = _build_env(
            backend_url="http://x", agent_id="my-agent", no_instrument=False
        )
        assert env["REVERIE_AGENT_ID"] == "my-agent"

    def test_no_instrument_omits_pythonpath_injection(self, monkeypatch):
        # Clear PYTHONPATH so we can detect whether _build_env added anything.
        monkeypatch.delenv("PYTHONPATH", raising=False)
        env = _build_env(
            backend_url="http://x", agent_id=None, no_instrument=True
        )
        # PYTHONPATH may exist from the parent env, but it must not contain
        # our bootstrap dir.
        parts = (env.get("PYTHONPATH") or "").split(os.pathsep)
        assert str(bootstrap_dir()) not in parts
        assert env["REVERIE_DISABLED"] == "1"

    def test_does_not_mutate_os_environ(self):
        before = dict(os.environ)
        _build_env(backend_url="http://x", agent_id="a", no_instrument=False)
        assert dict(os.environ) == before


# ---------------------------------------------------------------------------
# _resolve_executable
# ---------------------------------------------------------------------------


class TestResolveExecutable:
    def test_absolute_path_passthrough(self):
        # Use sys.executable as a known-good absolute path.
        assert _resolve_executable(sys.executable) == sys.executable

    def test_unknown_command_returns_input(self):
        # Some name unlikely to be on PATH. We don't crash; we hand it back
        # so the OS produces the final FileNotFoundError.
        result = _resolve_executable("nonexistent-command-xyz-12345")
        assert result == "nonexistent-command-xyz-12345"

    def test_python_resolves_to_sys_executable(self):
        # Critical: when the user types ``reverie run python ...``, we must
        # use the SAME interpreter that's running the CLI so the child sees
        # reverie_openai in its site-packages.
        assert _resolve_executable("python") == sys.executable
        assert _resolve_executable("python3") == sys.executable

    def test_versioned_python_resolves_to_sys_executable(self):
        # python3.12, python3.13, etc. — same reasoning.
        assert _resolve_executable("python3.12") == sys.executable

    def test_non_python_command_uses_which(self):
        # "node" (or anything else) should NOT be redirected to sys.executable.
        result = _resolve_executable("node")
        assert result != sys.executable
