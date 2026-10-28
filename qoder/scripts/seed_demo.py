"""Write (or reset) the reproducible demo learner.

The demo is created through the same PowerContext path as real usage. Stop the
web server before running this against the same data directory.

Usage::

    python scripts/seed_demo.py
    python scripts/seed_demo.py --force   # retire old demo memories, seed again
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.memory_store import MemoryStore  # noqa: E402
from app.seed import seed_demo  # noqa: E402


async def run(force: bool) -> int:
    settings = Settings.from_env()
    store = MemoryStore(settings)
    await store.start()
    try:
        result = await seed_demo(store, settings, force=force)
    finally:
        await store.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="retire the existing demo scope first")
    args = parser.parse_args()
    return asyncio.run(run(args.force))


if __name__ == "__main__":
    raise SystemExit(main())
