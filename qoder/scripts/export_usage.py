"""Summarise the real local usage log written by WenGu.

Every ``/api/*`` request is appended to ``data/usage.jsonl`` by the FastAPI
middleware. This script aggregates that file for the competition's usage
evidence, without inventing any numbers.

Usage::

    python scripts/export_usage.py
    python scripts/export_usage.py --out docs/usage-summary.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def summarize(rows: list[dict], days: int) -> dict:
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    recent = [row for row in rows if str(row.get("date") or "") >= cutoff]
    by_date = Counter(str(row.get("date") or "") for row in recent)
    by_route = Counter(str(row.get("pattern") or row.get("path") or "") for row in recent)
    by_status = Counter(str(row.get("status") or "") for row in recent)
    writes = [
        row
        for row in recent
        if str(row.get("method")) in {"POST", "PATCH", "PUT", "DELETE"}
        and 200 <= int(row.get("status") or 0) < 300
    ]
    learners = sorted({str(row.get("learner")) for row in recent if row.get("learner")})
    return {
        "window_days": days,
        "requests_total_logged": len(rows),
        "requests_in_window": len(recent),
        "active_days": len(by_date),
        "first_date": min(by_date) if by_date else None,
        "last_date": max(by_date) if by_date else None,
        "successful_memory_writes": len(writes),
        "learners_observed": learners,
        "by_date": dict(sorted(by_date.items())),
        "by_route": dict(by_route.most_common()),
        "by_status": dict(by_status),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=ROOT / "data" / "usage.jsonl")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    summary = summarize(read_rows(args.path), args.days)
    source = args.path.resolve()
    try:
        source = source.relative_to(ROOT)
    except ValueError:
        pass
    summary["generated_from"] = source.as_posix()
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
