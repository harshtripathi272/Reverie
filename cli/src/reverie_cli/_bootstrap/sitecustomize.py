"""Bootstrap loader executed by Python's ``site.py`` before user code.

The CLI prepends this file's directory to ``PYTHONPATH`` before launching
the target command. Python's ``site`` module then imports the *first*
``sitecustomize`` it finds on ``sys.path`` — which is us.

Two responsibilities, in order:

1. **Chain to any pre-existing sitecustomize.** Users may already have one
   on their interpreter (Anaconda ships one, for example). We must not
   silently break it. We re-run the import after temporarily removing our
   shadow directory from ``sys.path``.

2. **Install the Reverie OpenAI Agents SDK adapter.** Calls
   ``reverie_openai.auto()``. Any failure is logged but never raised —
   the user's program must run regardless.

Set ``REVERIE_NO_SITECUSTOMIZE_CHAIN=1`` to skip step 1.
Set ``REVERIE_DISABLED=1`` to install the adapter as a no-op (skips step 2's
network calls but keeps the rest of the wiring).
"""

from __future__ import annotations

import os
import sys


_INSTALLED_SENTINEL = "_reverie_sitecustomize_installed"


def _chain_to_user_sitecustomize() -> None:
    """Run the user's pre-existing sitecustomize, if any.

    We do this by removing our own bootstrap directory from sys.path and
    importing ``sitecustomize`` again. After import we restore sys.path.

    Care is taken NOT to leave ``sys.modules['sitecustomize']`` either
    missing or set to ``None`` — both states would break a later
    ``import sitecustomize`` from user code.
    """

    if os.environ.get("REVERIE_NO_SITECUSTOMIZE_CHAIN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return

    self_path = os.path.dirname(os.path.abspath(__file__))
    saved_path = list(sys.path)
    # Snapshot ourselves BEFORE we manipulate sys.modules.
    our_module = sys.modules.get(__name__)
    try:
        sys.path[:] = [p for p in sys.path if os.path.abspath(p) != self_path]
        # Drop the cached "us" so the next import picks up the user's module.
        sys.modules.pop("sitecustomize", None)
        try:
            import sitecustomize  # noqa: F401  (executed for side effects)
        except ImportError:
            # No user sitecustomize — that's the common case.
            pass
        except Exception as exc:  # pragma: no cover — depends on user code
            sys.stderr.write(
                f"[reverie] warning: user sitecustomize raised {exc!r}; continuing.\n"
            )
    finally:
        sys.path[:] = saved_path
        # Make sure sys.modules['sitecustomize'] is a real module.
        # If user code imported their own, leave it. Otherwise, restore us.
        cached = sys.modules.get("sitecustomize")
        if cached is None and our_module is not None:
            sys.modules["sitecustomize"] = our_module


def _install_reverie_adapter() -> None:
    """Call ``reverie_openai.auto()``. Never raises."""

    try:
        import reverie_openai  # type: ignore
    except ImportError:
        sys.stderr.write(
            "[reverie] warning: reverie_openai not installed in this interpreter; "
            "skipping instrumentation. Install it with: pip install reverie-adapter-openai\n"
        )
        return

    try:
        reverie_openai.auto()
    except Exception as exc:  # pragma: no cover — defensive
        sys.stderr.write(f"[reverie] warning: auto() raised {exc!r}; continuing.\n")


def _bootstrap() -> None:
    # Idempotent — if another mechanism already installed us, do nothing.
    if getattr(sys, _INSTALLED_SENTINEL, False):
        return
    setattr(sys, _INSTALLED_SENTINEL, True)

    _chain_to_user_sitecustomize()
    _install_reverie_adapter()


_bootstrap()
