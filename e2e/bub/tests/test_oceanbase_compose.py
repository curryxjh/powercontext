from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

_COMPOSE = Path(__file__).parents[1] / "compose.oceanbase.yaml"


def test_oceanbase_tenant_password_is_alphanumeric_for_bootstrap() -> None:
    compose = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    password = compose["services"]["oceanbase"]["environment"]["OB_TENANT_PASSWORD"]

    assert re.fullmatch(r"[A-Za-z0-9]+", password)


def test_oceanbase_application_url_uses_the_bootstrap_password() -> None:
    compose = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    password = compose["services"]["oceanbase"]["environment"]["OB_TENANT_PASSWORD"]
    url = compose["services"]["powercontext"]["environment"]["POWERCONTEXT_SERVER_DATABASE_URL"]

    assert unquote(urlsplit(url).password or "") == password
