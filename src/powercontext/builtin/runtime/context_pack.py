# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Versioned wire format for complete and incremental prepared contexts."""

# ruff: noqa: TRY003

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any

_PACK_SCHEMA = "powercontext.context-pack.v1"
_DELTA_SCHEMA = "powercontext.context-pack-delta.v1"
_PACK_FIELDS = frozenset({"schema", "items", "digest", "byte_count"})
_DELTA_FIELDS = frozenset({"schema", "base_digest", "target_digest", "prefix_items", "appended"})


class ContextPackError(ValueError):
    """Invalid Context Pack data, encoding, or delta application."""


@dataclass(frozen=True, slots=True)
class ContextPack:
    """A complete UTF-8 context split into independently encoded chunks."""

    items: tuple[bytes, ...]
    digest: str

    @classmethod
    def build(cls, items: tuple[bytes, ...]) -> ContextPack:
        """Build a pack from valid UTF-8 chunks."""

        normalized = _validate_items(items, "items")
        return cls(items=normalized, digest=_pack_digest(normalized))

    @classmethod
    def from_content(cls, content: str | None, *, chunk_bytes: int = 512) -> ContextPack:
        """Split content deterministically without breaking a UTF-8 code point."""

        if isinstance(chunk_bytes, bool) or not isinstance(chunk_bytes, int) or chunk_bytes <= 0:
            raise ContextPackError("chunk_bytes must be a positive integer")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ContextPackError("content must be text or None")
        try:
            content.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ContextPackError("content is not valid UTF-8 text") from error
        if not content:
            return cls.build(())
        return cls.build(_chunk_content(content, chunk_bytes))

    @property
    def byte_count(self) -> int:
        """Return the exact serialized wire size, including this field."""

        _validate_pack(self)
        count = 0
        while True:
            actual = len(self._to_bytes(byte_count=count))
            if actual == count:
                return actual
            count = actual

    def to_bytes(self) -> bytes:
        """Encode a canonical compact UTF-8 JSON pack."""

        return self._to_bytes(byte_count=self.byte_count)

    @classmethod
    def from_bytes(cls, data: bytes) -> ContextPack:
        """Decode and validate a complete wire pack."""

        payload = _decode_json(data, "pack")
        _require_fields(payload, _PACK_FIELDS, "pack")
        if payload["schema"] != _PACK_SCHEMA:
            raise ContextPackError("unsupported Context Pack schema")
        items = _decode_items(payload["items"], "items")
        digest = payload["digest"]
        if not isinstance(digest, str) or digest != _pack_digest(items):
            raise ContextPackError("Context Pack digest does not match its items")
        byte_count = payload["byte_count"]
        if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count != len(data):
            raise ContextPackError("Context Pack byte_count does not match its wire size")
        return cls(items=items, digest=digest)

    def _to_bytes(self, *, byte_count: int) -> bytes:
        return _canonical_json({
            "schema": _PACK_SCHEMA,
            "items": [_encode_item(item) for item in self.items],
            "digest": self.digest,
            "byte_count": byte_count,
        })


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    """A prefix-preserving replacement from one complete pack to another."""

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack) -> ContextPackDelta:
        """Create a delta that retains the longest identical chunk prefix."""

        if not isinstance(base, ContextPack) or not isinstance(target, ContextPack):
            raise ContextPackError("delta endpoints must be ContextPack values")
        _validate_pack(base)
        _validate_pack(target)
        prefix_items = 0
        for base_item, target_item in zip(base.items, target.items, strict=False):
            if base_item != target_item:
                break
            prefix_items += 1
        return cls(base.digest, target.digest, prefix_items, target.items[prefix_items:])

    @property
    def byte_count(self) -> int:
        """Return the exact serialized wire size (not a wire field)."""

        return len(self.to_bytes())

    def to_bytes(self) -> bytes:
        """Encode a canonical compact UTF-8 JSON delta."""

        _validate_delta(self)
        return _canonical_json({
            "schema": _DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": [_encode_item(item) for item in self.appended],
        })

    @classmethod
    def from_bytes(cls, data: bytes) -> ContextPackDelta:
        """Decode and validate a wire delta."""

        payload = _decode_json(data, "delta")
        _require_fields(payload, _DELTA_FIELDS, "delta")
        if payload["schema"] != _DELTA_SCHEMA:
            raise ContextPackError("unsupported Context Pack delta schema")
        base_digest = payload["base_digest"]
        target_digest = payload["target_digest"]
        if not _valid_digest(base_digest) or not _valid_digest(target_digest):
            raise ContextPackError("Context Pack delta digests are invalid")
        prefix_items = payload["prefix_items"]
        if isinstance(prefix_items, bool) or not isinstance(prefix_items, int) or prefix_items < 0:
            raise ContextPackError("prefix_items must be a non-negative integer")
        return cls(base_digest, target_digest, prefix_items, _decode_items(payload["appended"], "appended"))


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta) -> ContextPack:
    """Validate a base and reconstruct the complete target pack from a delta."""

    if not isinstance(base, ContextPack) or not isinstance(delta, ContextPackDelta):
        raise ContextPackError("delta application requires a pack and a delta")
    _validate_pack(base)
    _validate_delta(delta)
    if base.digest != delta.base_digest:
        raise ContextPackError("base Context Pack digest does not match delta")
    if delta.prefix_items > len(base.items):
        raise ContextPackError("prefix_items exceeds the base item count")
    target = ContextPack.build(base.items[: delta.prefix_items] + delta.appended)
    if target.digest != delta.target_digest:
        raise ContextPackError("reconstructed Context Pack digest does not match delta target")
    return target


def _validate_pack(pack: ContextPack) -> None:
    items = _validate_items(pack.items, "items")
    if not isinstance(pack.digest, str) or pack.digest != _pack_digest(items):
        raise ContextPackError("Context Pack digest does not match its items")


def _validate_delta(delta: ContextPackDelta) -> None:
    if not _valid_digest(delta.base_digest) or not _valid_digest(delta.target_digest):
        raise ContextPackError("Context Pack delta digests are invalid")
    if isinstance(delta.prefix_items, bool) or not isinstance(delta.prefix_items, int) or delta.prefix_items < 0:
        raise ContextPackError("prefix_items must be a non-negative integer")
    _validate_items(delta.appended, "appended")


def _validate_items(items: Any, label: str) -> tuple[bytes, ...]:
    if not isinstance(items, tuple):
        raise ContextPackError(f"{label} must be a tuple of byte chunks")
    normalized: list[bytes] = []
    for item in items:
        if not isinstance(item, bytes):
            raise ContextPackError(f"{label} must contain byte chunks")
        try:
            item.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ContextPackError(f"{label} contains a chunk that is not valid UTF-8") from error
        normalized.append(item)
    return tuple(normalized)


def _chunk_content(content: str, chunk_bytes: int) -> tuple[bytes, ...]:
    chunks: list[bytes] = []
    current = bytearray()
    for line in content.splitlines(keepends=True):
        line_bytes = line.encode("utf-8")
        if len(line_bytes) > chunk_bytes:
            if current:
                chunks.append(bytes(current))
                current.clear()
            chunks.extend(_split_utf8_line(line, chunk_bytes))
            continue
        if current and len(current) + len(line_bytes) > chunk_bytes:
            chunks.append(bytes(current))
            current.clear()
        current.extend(line_bytes)
    if current:
        chunks.append(bytes(current))
    return tuple(chunks)


def _split_utf8_line(line: str, chunk_bytes: int) -> tuple[bytes, ...]:
    chunks: list[bytes] = []
    current = bytearray()
    for character in line:
        character_bytes = character.encode("utf-8")
        if len(character_bytes) > chunk_bytes:
            raise ContextPackError("chunk_bytes is too small for a UTF-8 code point")
        if current and len(current) + len(character_bytes) > chunk_bytes:
            chunks.append(bytes(current))
            current.clear()
        current.extend(character_bytes)
    if current:
        chunks.append(bytes(current))
    return tuple(chunks)


def _decode_items(value: Any, label: str) -> tuple[bytes, ...]:
    if not isinstance(value, list):
        raise ContextPackError(f"{label} must be a Base64 string array")
    decoded: list[bytes] = []
    for item in value:
        if not isinstance(item, str):
            raise ContextPackError(f"{label} must contain Base64 strings")
        try:
            raw = base64.b64decode(item, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ContextPackError(f"{label} contains invalid Base64") from error
        if _encode_item(raw) != item:
            raise ContextPackError(f"{label} contains non-canonical Base64")
        decoded.append(raw)
    return _validate_items(tuple(decoded), label)


def _encode_item(item: bytes) -> str:
    return base64.b64encode(item).decode("ascii")


def _pack_digest(items: tuple[bytes, ...]) -> str:
    unsigned = {"schema": _PACK_SCHEMA, "items": [_encode_item(item) for item in items]}
    return "sha256:" + hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def _valid_digest(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        return False
    return all(character in "0123456789abcdef" for character in value[7:])


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _decode_json(data: bytes, label: str) -> dict[str, Any]:
    if not isinstance(data, bytes):
        raise ContextPackError(f"{label} wire value must be bytes")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except ContextPackError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ContextPackError(f"{label} wire value is not valid JSON") from error
    if not isinstance(value, dict):
        raise ContextPackError(f"{label} wire value must be a JSON object")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContextPackError("wire JSON contains a duplicate field")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContextPackError(f"wire JSON contains invalid numeric constant {value}")


def _require_fields(payload: dict[str, Any], expected: frozenset[str], label: str) -> None:
    if payload.keys() != expected:
        raise ContextPackError(f"{label} fields do not match the wire schema")


__all__ = ["ContextPack", "ContextPackDelta", "ContextPackError", "apply_context_pack_delta"]
