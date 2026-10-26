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

"""Behavior tests for Context Pack wire values and reconstruction."""

from __future__ import annotations

import base64
import hashlib
import json

import pytest

from powercontext.builtin.runtime.context_pack import (
    ContextPack,
    ContextPackDelta,
    ContextPackError,
    apply_context_pack_delta,
)


def test_pack_wire_digest_and_count_are_canonical() -> None:
    items = (b"alpha\n", "海洋".encode())
    pack = ContextPack.build(items)
    payload = json.loads(pack.to_bytes())
    unsigned = {
        "schema": "powercontext.context-pack.v1",
        "items": [base64.b64encode(item).decode("ascii") for item in items],
    }
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()

    assert payload == {
        **unsigned,
        "digest": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "byte_count": len(pack.to_bytes()),
    }
    assert pack.to_bytes() == json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    assert ContextPack.from_bytes(pack.to_bytes()) == pack


def test_content_chunking_is_utf8_safe_deterministic_and_bounded() -> None:
    content = "a海🙂bc海🙂"
    pack = ContextPack.from_content(content, chunk_bytes=5)

    assert b"".join(pack.items).decode() == content
    assert all(len(item) <= 5 for item in pack.items)
    assert all(item.decode("utf-8") for item in pack.items)
    assert ContextPack.from_content(content, chunk_bytes=5) == pack
    with pytest.raises(ContextPackError):
        ContextPack.from_content("海", chunk_bytes=2)
    with pytest.raises(ContextPackError):
        ContextPack.from_content("text", chunk_bytes=True)


@pytest.mark.parametrize("target_items", [(b"a", b"b", b"new"), (b"new", b"b"), (b"a", b"new"), ()])
def test_delta_reconstructs_prefix_and_suffix_changes(target_items: tuple[bytes, ...]) -> None:
    base = ContextPack.build((b"a", b"b", b"old"))
    target = ContextPack.build(target_items)
    delta = ContextPackDelta.between(base, target)

    restored_base = ContextPack.from_bytes(base.to_bytes())
    restored_delta = ContextPackDelta.from_bytes(delta.to_bytes())
    rebuilt = apply_context_pack_delta(restored_base, restored_delta)

    assert rebuilt == target
    assert delta.byte_count == len(delta.to_bytes())


def test_delta_accepts_any_valid_prefix_including_zero() -> None:
    base = ContextPack.build((b"same", b"old"))
    target = ContextPack.build((b"same", b"new"))
    delta = ContextPackDelta(base.digest, target.digest, 0, target.items)

    assert apply_context_pack_delta(base, delta) == target


@pytest.mark.parametrize("prefix_items", [True, 1.5, -1])
def test_delta_rejects_invalid_prefix_values(prefix_items: object) -> None:
    base = ContextPack.build((b"base",))
    delta = ContextPackDelta.between(base, ContextPack.build((b"target",)))
    payload = json.loads(delta.to_bytes())
    payload["prefix_items"] = prefix_items

    with pytest.raises(ContextPackError):
        ContextPackDelta.from_bytes(json.dumps(payload).encode())


def test_pack_and_delta_reject_tampered_wire_data() -> None:
    pack = ContextPack.build((b"content",))
    payload = json.loads(pack.to_bytes())
    payload["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ContextPackError):
        ContextPack.from_bytes(json.dumps(payload).encode())

    payload = json.loads(pack.to_bytes())
    payload["unexpected"] = True
    with pytest.raises(ContextPackError):
        ContextPack.from_bytes(json.dumps(payload).encode())

    payload = json.loads(pack.to_bytes())
    payload["byte_count"] += 1
    with pytest.raises(ContextPackError):
        ContextPack.from_bytes(json.dumps(payload).encode())

    payload = json.loads(pack.to_bytes())
    payload["items"] = ["not-base64!"]
    with pytest.raises(ContextPackError):
        ContextPack.from_bytes(json.dumps(payload).encode())


def test_delta_rejects_wrong_base_and_target_digest() -> None:
    base = ContextPack.build((b"base",))
    delta = ContextPackDelta.between(base, ContextPack.build((b"next",)))
    with pytest.raises(ContextPackError):
        apply_context_pack_delta(ContextPack.build((b"other",)), delta)

    invalid_target = ContextPackDelta(base.digest, "sha256:" + "0" * 64, 0, (b"next",))
    with pytest.raises(ContextPackError):
        apply_context_pack_delta(base, invalid_target)


def test_empty_pack_is_a_valid_empty_text_encoding() -> None:
    empty = ContextPack.from_content(None)

    assert empty.items == ()
    assert ContextPack.from_bytes(empty.to_bytes()) == empty
    assert b"".join(empty.items) == b""
