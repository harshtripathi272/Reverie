"""Tests for the SDK-id → UUID translation."""

from __future__ import annotations

import re
import uuid

from reverie_openai.idmap import to_end_uuid, to_uuid

UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def test_to_uuid_returns_valid_uuid():
    out = to_uuid("trace_abc123")
    assert UUID_V4_RE.fullmatch(out)
    # uuid.UUID must accept it.
    parsed = uuid.UUID(out)
    assert parsed.version == 4


def test_to_end_uuid_returns_valid_uuid():
    out = to_end_uuid("span_xyz")
    assert UUID_V4_RE.fullmatch(out)
    assert uuid.UUID(out).version == 4


def test_to_uuid_is_deterministic():
    a = to_uuid("trace_same")
    b = to_uuid("trace_same")
    assert a == b


def test_to_end_uuid_differs_from_start():
    sid = "span_distinct"
    assert to_uuid(sid) != to_end_uuid(sid)


def test_unique_inputs_yield_unique_outputs():
    seen = set()
    for i in range(1000):
        u = to_uuid(f"span_{i:024x}")
        assert u not in seen, f"unexpected collision at i={i}"
        seen.add(u)


def test_handles_arbitrary_strings():
    # Must accept anything stringy without crashing.
    for s in ["", "x", "trace_" + "0" * 32, "💀", "with spaces and / slashes"]:
        u = to_uuid(s)
        assert UUID_V4_RE.fullmatch(u), f"bad output for {s!r}: {u!r}"
