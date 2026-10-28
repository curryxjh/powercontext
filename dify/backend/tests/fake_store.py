from __future__ import annotations

import copy

from wangchuan.ledger import active_pawns, max_ticket, pawn_text


class FakeMemoryStore:
    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.search_hits: list[dict] = []
        self._counter = 0

    async def ensure_scope(self, player_id: str) -> str:
        return f"scope-{player_id}"

    async def list_entries(self, scope_id: str, *, include_inactive: bool = False) -> list[dict]:
        result = []
        for entry in self.entries:
            if not include_inactive and entry["state"] != "active":
                continue
            item = copy.deepcopy(entry)
            item.pop("scope_id", None)
            result.append(item)
        return result

    async def search(self, scope_id: str, query: str, limit: int = 6) -> list[dict]:
        return copy.deepcopy(self.search_hits)

    async def remember(self, scope_id: str, kind: str, text: str) -> dict:
        self._counter += 1
        entry = {
            "scope_id": scope_id,
            "entry_id": f"entry-{self._counter}",
            "kind": kind,
            "text": text,
            "state": "active",
            "version": 1,
            "citation": {
                "entry_id": f"entry-{self._counter}",
                "entry_version_id": f"version-{self._counter}",
                "memory_ref": {"artifact_id": f"memory-{scope_id}", "revision": self._counter},
            },
        }
        self.entries.append(entry)
        return copy.deepcopy(entry)

    async def retire(self, scope_id: str, citation: dict, reason: str) -> None:
        for entry in self.entries:
            if entry["entry_id"] == citation["entry_id"]:
                entry["state"] = "inactive"
                return
        raise AssertionError("unknown citation")

    async def ready(self) -> bool:
        return True

    def seed_pawn(self, ticket: int, message: str, reply: str) -> None:
        self.entries.append(
            {
                "scope_id": "scope-demo",
                "entry_id": f"seed-{ticket}",
                "kind": "wangchuan.pawn",
                "text": pawn_text(ticket, message, reply),
                "state": "active",
                "version": 1,
                "citation": {
                    "entry_id": f"seed-{ticket}",
                    "entry_version_id": f"seed-version-{ticket}",
                    "memory_ref": {"artifact_id": "memory-demo", "revision": 1},
                },
            }
        )


def test_seeded_ledger_uses_active_entries_only() -> None:
    store = FakeMemoryStore()
    store.seed_pawn(1, "第一次看海", "海水是温的")
    assert [pawn.ticket for pawn in active_pawns(store.entries)] == [1]
    assert max_ticket(store.entries) == 1
