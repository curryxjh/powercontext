"""Runtime settings for the WenGu study coach."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file() -> None:
    """Load ``qoder/.env`` without overriding variables already exported."""

    path = PROJECT_ROOT / ".env"
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    usage_log_path: Path
    db_path: Path
    scheduler_path: Path
    max_import_chars: int = 120_000
    max_answer_bytes: int = 6_000
    default_daily_minutes: int = 20
    default_style: str = "图示 + 生活类比"
    timezone: str = "Asia/Shanghai"
    demo_slug: str = "demo"
    feedback_slug: str = "__feedback__"
    auto_seed: bool = True

    @classmethod
    def from_env(cls, data_dir: Path | None = None) -> "Settings":
        _load_env_file()
        raw = Path(data_dir or os.environ.get("WENGU_DATA_DIR") or (PROJECT_ROOT / "data"))
        resolved = (raw if raw.is_absolute() else PROJECT_ROOT / raw).resolve()
        return cls(
            data_dir=resolved,
            usage_log_path=resolved / "usage.jsonl",
            db_path=resolved / "wengu.db",
            scheduler_path=resolved / "wengu.scheduler.db",
            max_import_chars=_env_int("WENGU_MAX_IMPORT_CHARS", 120_000),
            max_answer_bytes=_env_int("WENGU_MAX_ANSWER_BYTES", 6_000),
            default_daily_minutes=_env_int("WENGU_DEFAULT_DAILY_MINUTES", 20),
            default_style=os.environ.get("WENGU_DEFAULT_STYLE", "图示 + 生活类比"),
            timezone=os.environ.get("WENGU_TIMEZONE", "Asia/Shanghai"),
            auto_seed=os.environ.get("WENGU_AUTO_SEED", "1").strip().lower() not in {"0", "false", "no"},
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
