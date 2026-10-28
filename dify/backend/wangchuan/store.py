from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Protocol

import httpx

from .settings import Settings


class PowerContextError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class MemoryStore(Protocol):
    async def ensure_scope(self, player_id: str) -> str: ...

    async def list_entries(self, scope_id: str, *, include_inactive: bool = False) -> list[dict[str, Any]]: ...

    async def search(self, scope_id: str, query: str, limit: int = 6) -> list[dict[str, Any]]: ...

    async def remember(self, scope_id: str, kind: str, text: str) -> dict[str, Any]: ...

    async def retire(self, scope_id: str, citation: dict[str, Any], reason: str) -> None: ...

    async def ready(self) -> bool: ...


class PowerContextStore:
    """Thin HTTP client for the PowerContext Server API used by the pawnshop."""

    def __init__(self, settings: Settings) -> None:
        headers = {"Accept": "application/json"}
        if settings.powercontext_token:
            headers["Authorization"] = f"Bearer {settings.powercontext_token}"
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.powercontext_url,
            headers=headers,
            timeout=settings.request_timeout,
        )
        self._scopes: dict[str, str] = {}
        self._scope_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ready(self) -> bool:
        try:
            response = await self._client.get("/health/ready", timeout=3)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def ensure_scope(self, player_id: str) -> str:
        player_id = player_id.strip()
        if not player_id:
            raise ValueError("player_id 不能为空")

        cached = self._scopes.get(player_id)
        if cached:
            return cached

        async with self._scope_lock:
            cached = self._scopes.get(player_id)
            if cached:
                return cached

            scope_id = await self._find_scope(player_id)
            if scope_id is None:
                payload = {
                    "title": f"忘川当铺 · 玩家 {player_id[:8]}",
                    "summary": "忘川当铺为单个玩家保存的典当账本，由 Dify 工作流读写。",
                    "external_references": [
                        {"kind": self._settings.external_reference_kind, "value": player_id}
                    ],
                    "idempotency_key": "wangchuan-scope-" + hashlib.sha256(player_id.encode()).hexdigest()[:40],
                }
                try:
                    created = await self._call("POST", "/v1/scopes", json=payload)
                    scope_id = str(created["scope_id"])
                except PowerContextError as exc:
                    if exc.status_code != 409:
                        raise
                    scope_id = await self._find_scope(player_id)
                    if scope_id is None:
                        raise

            self._scopes[player_id] = scope_id
            return scope_id

    async def _find_scope(self, player_id: str) -> str | None:
        cursor: str | None = None
        for _ in range(10):
            params: dict[str, Any] = {
                "query": player_id,
                "query_field": "external_reference_value",
                "limit": 100,
            }
            if cursor:
                params["cursor"] = cursor
            page = await self._call("GET", "/v1/scopes", params=params)
            for item in page.get("items") or []:
                for reference in item.get("external_references") or []:
                    if (
                        reference.get("kind") == self._settings.external_reference_kind
                        and reference.get("value") == player_id
                    ):
                        return str(item["scope_id"])
            cursor = page.get("next_cursor")
            if not cursor:
                break
        return None

    async def list_entries(self, scope_id: str, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        try:
            payload = await self._call(
                "POST",
                "/v1/memory/entries/list",
                json={"scope_id": scope_id, "include_inactive": include_inactive},
            )
        except PowerContextError as exc:
            if exc.status_code == 404:
                return []
            raise
        return list(payload.get("entries") or [])

    async def search(self, scope_id: str, query: str, limit: int = 6) -> list[dict[str, Any]]:
        try:
            payload = await self._call(
                "POST",
                "/v1/memory/search",
                json={"scope_id": scope_id, "query": query, "limit": limit, "mode": "auto"},
            )
        except PowerContextError as exc:
            # 纯 FTS 部署下中文检索可能没有候选；账本读取路径仍然可用。
            if exc.status_code in {404, 422}:
                return []
            raise
        return list(payload.get("hits") or [])

    async def remember(self, scope_id: str, kind: str, text: str) -> dict[str, Any]:
        payload = await self._call(
            "POST",
            "/v1/memory/remember",
            json={"scope_id": scope_id, "kind": kind, "text": text, "reason": "忘川当铺自动记账"},
        )
        entry = payload.get("entry")
        if not entry:
            raise PowerContextError("PowerContext 没有返回新写入的记忆条目")
        return dict(entry)

    async def retire(self, scope_id: str, citation: dict[str, Any], reason: str) -> None:
        await self._call(
            "POST",
            "/v1/memory/entries/retire",
            json={"scope_id": scope_id, "citation": citation, "reason": reason},
        )

    async def _call(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            raise PowerContextError(f"无法连接 PowerContext: {exc}") from exc

        if response.status_code >= 400:
            code: str | None = None
            message = response.text[:500]
            try:
                error = response.json().get("error") or {}
                code = error.get("code") or (error.get("details") or {}).get("code")
                message = error.get("message") or message
            except (ValueError, AttributeError):
                pass
            raise PowerContextError(message, status_code=response.status_code, code=code)

        if not response.content:
            return {}
        try:
            return dict(response.json())
        except ValueError as exc:
            raise PowerContextError("PowerContext 返回了非 JSON 响应") from exc
