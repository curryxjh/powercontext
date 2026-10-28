"""Start the WenGu web app: python run.py"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402


def main() -> None:
    host = os.environ.get("WENGU_HOST", "127.0.0.1")
    port = int(os.environ.get("WENGU_PORT", "8010"))
    reload = os.environ.get("WENGU_RELOAD", "0").strip().lower() in {"1", "true", "yes"}
    print(f"温故 WenGu -> http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload, workers=1)


if __name__ == "__main__":
    main()
