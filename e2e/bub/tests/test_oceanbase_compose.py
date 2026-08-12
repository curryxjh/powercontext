from __future__ import annotations

import re
from pathlib import Path


def test_oceanbase_tenant_password_is_alphanumeric_for_bootstrap() -> None:
    compose = (
        Path(__file__).parents[1] / "compose.oceanbase.yaml"
    ).read_text(encoding="utf-8")

    match = re.search(r"OB_TENANT_PASSWORD:\s*(\S+)", compose)
    assert match is not None
    assert re.fullmatch(r"[A-Za-z0-9]+", match.group(1))
