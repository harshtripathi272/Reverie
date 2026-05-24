"""Adapter test config.

Adds the tests dir to ``sys.path`` so test modules can ``import _helpers``
under pytest's ``importlib`` import mode (which doesn't add the rootdir to
sys.path automatically).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `_helpers` importable from any test module without relative imports.
_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
