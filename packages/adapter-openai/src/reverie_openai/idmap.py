"""Stable id translation between OpenAI Agents SDK and Reverie UUIDs.

The SDK uses prefix+hex ids (``trace_<32_hex>``, ``span_<24_hex>``); Reverie's
schema validates UUIDs. We deterministically project each SDK id into a
v4-shaped UUID. The projection is:

  uuid = sha256(sdk_id).digest()[:16]
         with version=4 nibble and variant=10xx bits set

This is collision-resistant for any reasonable population size, deterministic
across runs (same SDK id always maps to the same UUID), and reversible only at
the adapter — Reverie itself never sees the SDK ids.

To make end-events distinct from start-events for the same span, we hash a
salted variant: ``f"end:{span_id}"``.
"""

from __future__ import annotations

import hashlib

_END_SALT = "reverie:end:"


def _bytes_to_uuid_v4(seed: bytes) -> str:
    """Project 16+ bytes of entropy into a v4-shaped UUID string."""

    b = bytearray(seed[:16])
    # version 4 (0100) in the upper nibble of byte 6
    b[6] = (b[6] & 0x0F) | 0x40
    # variant 10xx in the upper bits of byte 8
    b[8] = (b[8] & 0x3F) | 0x80
    h = b.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def to_uuid(sdk_id: str) -> str:
    """Map any SDK id (trace, span, or arbitrary string) to a stable UUID."""

    return _bytes_to_uuid_v4(hashlib.sha256(sdk_id.encode("utf-8")).digest())


def to_end_uuid(span_id: str) -> str:
    """Map a span id to a *distinct* UUID for its end-event row.

    Salting guarantees ``to_end_uuid(x) != to_uuid(x)`` for all ``x``.
    """

    return _bytes_to_uuid_v4(
        hashlib.sha256(f"{_END_SALT}{span_id}".encode("utf-8")).digest()
    )
