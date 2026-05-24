"""CLI test config.

Adds the tests dir to ``sys.path`` so test modules can ``import _helpers``
under pytest's ``importlib`` import mode (which doesn't add the rootdir to
sys.path automatically).

We also force-disable Rich's console wrapping in subprocess tests by
exporting ``COLUMNS=200`` in the test process environment, so the table
output we assert against doesn't break across multiple lines.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

# Make sure Rich + Click runners see a wide, non-TTY terminal so output
# layout is deterministic across local + CI.
os.environ.setdefault("COLUMNS", "200")
os.environ.setdefault("LINES", "50")
