"""End-to-end bootstrap tests — actually spawn a Python subprocess with our
PYTHONPATH and confirm ``sitecustomize.py`` fired before user code.

These tests are slower than the unit tests (~0.5–1s each on Windows) but
are the only way to validate the real injection mechanism.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from reverie_cli._bootstrap import dir_path as bootstrap_dir


SENTINEL_SCRIPT = (
    "import sys, json; "
    "print(json.dumps({"
    "'sentinel': getattr(sys, '_reverie_sitecustomize_installed', False),"
    "'has_adapter': 'reverie_openai' in sys.modules,"
    "}))"
)


def _env_with_bootstrap(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    parts = existing.split(os.pathsep) if existing else []
    if str(bootstrap_dir()) not in parts:
        parts.insert(0, str(bootstrap_dir()))
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["REVERIE_DISABLED"] = "1"  # don't make HTTP calls during tests
    if extra_env:
        env.update(extra_env)
    return env


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_bootstrap_runs_for_python_dash_c():
    """The 'python -c ...' invocation form must trigger the sitecustomize."""

    result = _run([sys.executable, "-c", SENTINEL_SCRIPT], _env_with_bootstrap())
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    payload = json.loads(result.stdout.strip())
    assert payload["sentinel"] is True
    assert payload["has_adapter"] is True


def test_bootstrap_runs_for_python_script(tmp_path):
    """The 'python script.py' invocation form must also trigger it."""

    script = tmp_path / "probe.py"
    script.write_text(SENTINEL_SCRIPT, encoding="utf-8")
    result = _run([sys.executable, str(script)], _env_with_bootstrap())
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    payload = json.loads(result.stdout.strip())
    assert payload["sentinel"] is True


def test_bootstrap_is_idempotent_within_a_process():
    """A single process must trigger the bootstrap exactly once even if its
    sitecustomize is re-imported."""

    script = (
        "import sitecustomize; "
        "import sys; "
        "first = getattr(sys, '_reverie_sitecustomize_installed', False); "
        # Force a second pass by re-executing _bootstrap manually.
        "sitecustomize._bootstrap(); "
        "print(first, 'still', getattr(sys, '_reverie_sitecustomize_installed', False))"
    )
    result = _run([sys.executable, "-c", script], _env_with_bootstrap())
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert "True still True" in result.stdout


def test_bootstrap_continues_if_user_sitecustomize_raises(tmp_path):
    """A broken user sitecustomize must NOT prevent our bootstrap from
    running and the adapter from installing."""

    user_dir = tmp_path / "user_site"
    user_dir.mkdir()
    (user_dir / "sitecustomize.py").write_text(
        "raise RuntimeError('user sitecustomize is broken')\n",
        encoding="utf-8",
    )

    env = dict(os.environ)
    # Our bootstrap dir FIRST, user's broken one SECOND. Our chain logic
    # imports the user's after removing ours from sys.path.
    parts = [str(bootstrap_dir()), str(user_dir)]
    if env.get("PYTHONPATH"):
        parts.extend(env["PYTHONPATH"].split(os.pathsep))
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["REVERIE_DISABLED"] = "1"

    result = _run([sys.executable, "-c", SENTINEL_SCRIPT], env)
    # User script may emit a warning to stderr — that's fine. Adapter must
    # still have installed.
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    payload = json.loads(result.stdout.strip())
    assert payload["sentinel"] is True
    assert payload["has_adapter"] is True


def test_no_chain_env_var_skips_user_sitecustomize(tmp_path):
    """Setting REVERIE_NO_SITECUSTOMIZE_CHAIN=1 should bypass the user's
    sitecustomize even if one is on the path."""

    user_dir = tmp_path / "user_site"
    user_dir.mkdir()
    marker = tmp_path / "user_was_called"
    (user_dir / "sitecustomize.py").write_text(
        f"open({str(marker)!r}, 'w').close()\n",
        encoding="utf-8",
    )

    env = dict(os.environ)
    parts = [str(bootstrap_dir()), str(user_dir)]
    if env.get("PYTHONPATH"):
        parts.extend(env["PYTHONPATH"].split(os.pathsep))
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["REVERIE_DISABLED"] = "1"
    env["REVERIE_NO_SITECUSTOMIZE_CHAIN"] = "1"

    result = _run([sys.executable, "-c", "print('ok')"], env)
    assert result.returncode == 0
    assert not marker.exists(), "user sitecustomize should not have been called"


def test_sitecustomize_is_a_real_module_after_chain():
    """After our chain runs, ``sys.modules['sitecustomize']`` must remain a
    real module — not None and not missing — so user code can later do
    ``import sitecustomize`` without ``ModuleNotFoundError``.
    """

    script = (
        "import sys; "
        "m = sys.modules.get('sitecustomize'); "
        "import sitecustomize as s2; "
        "print('module' if m is not None else 'missing', "
        "'reimport_ok' if s2 is not None else 'reimport_fail')"
    )
    result = _run([sys.executable, "-c", script], _env_with_bootstrap())
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert "module reimport_ok" in result.stdout


@pytest.mark.skipif(
    sys.platform == "win32" and "CI" not in os.environ,
    reason="reverie console script invocation is environment-dependent",
)
def test_reverie_run_dry_run_subprocess():
    """Smoke-test the actual ``reverie run --dry-run`` invocation as a real
    subprocess (not via Click's CliRunner)."""

    bin_dir = os.path.dirname(sys.executable)
    candidates = [
        os.path.join(bin_dir, "reverie.exe"),
        os.path.join(bin_dir, "reverie"),
    ]
    reverie = next((c for c in candidates if os.path.exists(c)), None)
    if reverie is None:
        pytest.skip("reverie console script not found")

    result = _run([reverie, "run", "--dry-run", "python", "x.py"], dict(os.environ))
    assert result.returncode == 0, result.stderr
    assert "would execute" in result.stdout
    assert "PYTHONPATH=" in result.stdout
