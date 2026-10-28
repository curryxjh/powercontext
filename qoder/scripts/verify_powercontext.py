"""Verify a running WenGu instance is really backed by PowerContext.

Read-only: every check hits the public HTTP API, so the same script proves the
deployed instance a reviewer is looking at. Exit code 0 means all checks pass.

Usage::

    python scripts/verify_powercontext.py
    WENGU_URL=http://127.0.0.1:8010 python scripts/verify_powercontext.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

BASE = os.environ.get("WENGU_URL", "http://127.0.0.1:8010").rstrip("/")
BEGIN = "BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1"
END = "END_POWERCONTEXT_PREPARED_CONTEXT_V1"

results: list[tuple[bool, str, str]] = []


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((ok, name, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<14} {detail}")


def main() -> int:
    print(f"WenGu / PowerContext verification against {BASE}\n")

    try:
        health = get("/api/health")
    except Exception as error:  # noqa: BLE001 - CLI should explain any failure
        print(f"FAIL  server         {error}")
        print("\nIs the server running? Start it with: python run.py")
        return 1

    version = str(health.get("powercontext_version") or "")
    check("server", health.get("status") == "ok", f"app {health.get('app_version', '?')}")
    check("powercontext", version.startswith("1.2"), f"version {version or '?'}")

    bootstrap = get("/api/bootstrap")
    learners = bootstrap.get("learners") or []
    if not learners:
        check("learner", False, "no learners; run scripts/seed_demo.py or enable WENGU_AUTO_SEED")
        return summarize()
    slugs = [learner["slug"] for learner in learners]
    slug = "demo" if "demo" in slugs else slugs[0]
    check("learner", True, f"{slug} ({len(learners)} scope(s))")

    learner = get(f"/api/learners/{urllib.parse.quote(slug)}")
    scope_id = learner["scope"]["scope_id"]
    stats = learner["view"]["stats"]
    check("scope", bool(scope_id), scope_id)
    check("knowledge", int(stats.get("items_total") or 0) > 0, f"{stats.get('items_total')} cards")
    check("review replay", int(stats.get("reviews_total") or 0) > 0, f"{stats.get('reviews_total')} reviews")

    memory = get(f"/api/learners/{urllib.parse.quote(slug)}/memory")
    kinds = memory.get("counts") or {}
    check(
        "memory entries",
        int(memory.get("total") or 0) > 0,
        f"{memory.get('total')} total · rev {memory.get('revision')} · kinds {kinds}",
    )
    source_ids = [
        (row.get("meta") or {}).get("source_id") for row in (memory.get("records") or [])
    ]
    source_ids = [source_id for source_id in source_ids if source_id]
    check("sources captured", bool(source_ids), f"{len(source_ids)} linked card(s)")

    query = urllib.parse.quote("卡点")
    proof = get(f"/api/learners/{urllib.parse.quote(slug)}/proof?q={query}")
    hits = proof.get("search", {}).get("hits") or []
    check("chinese FTS", len(hits) >= 1, f'"卡点" matched {len(hits)} memories')

    inventory = proof.get("inventory") or {}
    check("model requests", int(inventory.get("model_requests") or 0) == 0, "0 (offline, no API key)")
    check("sources", int(inventory.get("sources") or 0) >= 1, f"{inventory.get('sources')} source(s)")

    content = str(proof.get("context", {}).get("content") or "")
    items: list[dict] = []
    if BEGIN in content and END in content:
        raw = content.split(BEGIN, 1)[1].split(END, 1)[0].strip()
        try:
            items = json.loads(raw).get("items") or []
        except ValueError:
            items = []
    cited = [item for item in items if (item.get("citation") or {}).get("entry_id")]
    check("context.prepare", bool(items), f"{proof.get('context', {}).get('status')} · {len(items)} items")
    check("citations", len(cited) == len(items) and bool(items), f"{len(cited)}/{len(items)} items cite entries")

    changes = get(f"/api/learners/{urllib.parse.quote(slug)}/changes")
    revisions = changes.get("revisions") or []
    check("revision history", bool(revisions), f"{len(revisions)} revision(s) recorded")

    with urllib.request.urlopen(f"{BASE}/", timeout=15) as response:
        page = response.read().decode("utf-8")
    check("web app", "温故" in page, "index served")

    return summarize()


def summarize() -> int:
    passed = sum(1 for ok, _, _ in results if ok)
    print(f"\nResult: {passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
