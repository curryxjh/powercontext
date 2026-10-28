from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "wangchuan.api:app",
        host=os.environ.get("PAWN_HOST", "0.0.0.0"),
        port=int(os.environ.get("PAWN_PORT", "8787")),
        log_level=os.environ.get("PAWN_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
