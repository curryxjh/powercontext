from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    powercontext_url: str
    powercontext_token: str | None
    request_timeout: float
    external_reference_kind: str

    @classmethod
    def from_env(cls) -> Settings:
        token = _env("POWERCONTEXT_TOKEN")
        return cls(
            powercontext_url=_env("POWERCONTEXT_URL", "http://127.0.0.1:8000").rstrip("/"),
            powercontext_token=token or None,
            request_timeout=float(_env("POWERCONTEXT_TIMEOUT", "15")),
            external_reference_kind=_env("PAWN_EXTERNAL_KIND", "wangchuan.player"),
        )
