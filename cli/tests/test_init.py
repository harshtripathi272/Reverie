"""Tests for ``reverie init`` and the global config helpers.

Covers:

  - Auto-detect from inside a fake Reverie checkout.
  - Explicit ``--repo`` argument.
  - ``--show`` and ``--clear``.
  - ``resolve_repo_path`` precedence (override > env > config > auto-detect).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from reverie_cli import app_config
from reverie_cli.commands.init import init_command


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A minimal directory that ``detect_repo_path`` will recognise."""

    repo = tmp_path / "fake-reverie"
    (repo / "apps" / "api").mkdir(parents=True)
    (repo / "Makefile").write_text("# placeholder", encoding="utf-8")
    return repo


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect ``~/.reverie`` to a tmp directory so tests don't poison the
    real user's config."""

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(app_config, "CONFIG_DIR", fake_home / ".reverie")
    monkeypatch.setattr(
        app_config, "CONFIG_FILE", fake_home / ".reverie" / "config.json"
    )
    return fake_home


def test_init_save_with_explicit_repo(isolated_home: Path, fake_repo: Path):
    runner = CliRunner()
    result = runner.invoke(init_command, ["--repo", str(fake_repo)])
    assert result.exit_code == 0, result.output
    assert "saved" in result.output

    cfg_file = isolated_home / ".reverie" / "config.json"
    assert cfg_file.exists()
    raw = json.loads(cfg_file.read_text())
    assert Path(raw["repo_path"]) == fake_repo.resolve()


def test_init_auto_detects_from_cwd(
    isolated_home: Path, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(fake_repo)
    runner = CliRunner()
    result = runner.invoke(init_command, [])
    assert result.exit_code == 0, result.output

    cfg = app_config.load_config()
    assert cfg.repo_path == fake_repo.resolve()


def test_init_fails_when_no_repo_detectable(
    isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # cwd is a tmp dir that is NOT a Reverie checkout.
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(init_command, [])
    assert result.exit_code == 1
    assert "could not auto-detect" in result.output


def test_init_show_when_empty(isolated_home: Path):
    runner = CliRunner()
    result = runner.invoke(init_command, ["--show"])
    assert result.exit_code == 0
    assert "No config saved" in result.output


def test_init_show_after_save(isolated_home: Path, fake_repo: Path):
    runner = CliRunner()
    runner.invoke(init_command, ["--repo", str(fake_repo)])
    result = runner.invoke(init_command, ["--show"])
    assert result.exit_code == 0
    assert "repo_path" in result.output
    # Rich wraps long paths so check for a stable token, not the full path.
    assert "fake-reverie" in result.output


def test_init_clear(isolated_home: Path, fake_repo: Path):
    runner = CliRunner()
    runner.invoke(init_command, ["--repo", str(fake_repo)])
    cfg_file = isolated_home / ".reverie" / "config.json"
    assert cfg_file.exists()

    result = runner.invoke(init_command, ["--clear"])
    assert result.exit_code == 0
    assert not cfg_file.exists()


def test_init_clear_when_already_empty(isolated_home: Path):
    runner = CliRunner()
    result = runner.invoke(init_command, ["--clear"])
    assert result.exit_code == 0
    assert "no config" in result.output


def test_init_preserves_unrelated_fields(isolated_home: Path, fake_repo: Path):
    """Re-running init shouldn't drop a previously-saved backend_url."""

    runner = CliRunner()
    runner.invoke(
        init_command,
        ["--repo", str(fake_repo), "--backend", "http://10.0.0.5:8000"],
    )
    # Re-init with a new repo only.
    runner.invoke(init_command, ["--repo", str(fake_repo)])
    cfg = app_config.load_config()
    assert cfg.backend_url == "http://10.0.0.5:8000"


# ---------------------------------------------------------------------------
# resolve_repo_path precedence
# ---------------------------------------------------------------------------


def test_resolve_repo_uses_explicit_override(
    isolated_home: Path, fake_repo: Path, tmp_path: Path
):
    other = tmp_path / "elsewhere"
    other.mkdir()
    result = app_config.resolve_repo_path(override=other)
    assert result == other.resolve()


def test_resolve_repo_uses_env_var(
    isolated_home: Path, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("REVERIE_REPO", str(fake_repo))
    monkeypatch.chdir(fake_repo.parent)  # cwd doesn't have a checkout
    result = app_config.resolve_repo_path()
    assert result == fake_repo.resolve()


def test_resolve_repo_uses_saved_config(
    isolated_home: Path, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("REVERIE_REPO", raising=False)
    runner = CliRunner()
    runner.invoke(init_command, ["--repo", str(fake_repo)])
    monkeypatch.chdir(fake_repo.parent)
    result = app_config.resolve_repo_path()
    assert result == fake_repo.resolve()


def test_resolve_repo_falls_back_to_auto_detect(
    isolated_home: Path, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("REVERIE_REPO", raising=False)
    monkeypatch.chdir(fake_repo)
    result = app_config.resolve_repo_path()
    assert result == fake_repo.resolve()


def test_resolve_repo_returns_none_when_nothing_works(
    isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("REVERIE_REPO", raising=False)
    monkeypatch.chdir(tmp_path)
    assert app_config.resolve_repo_path() is None


def test_load_config_handles_corrupt_file(isolated_home: Path):
    cfg_dir = isolated_home / ".reverie"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text("not json", encoding="utf-8")
    # Must not raise.
    cfg = app_config.load_config()
    assert cfg.repo_path is None
