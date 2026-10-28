from __future__ import annotations

import logging

from .ledger import (
    PAWN_KIND,
    REDEEM_KIND,
    REDEEM_PATTERN,
    active_pawns,
    format_context,
    format_ledger,
    format_redeem_success,
    max_ticket,
    pawn_text,
    redemption_text,
)
from .store import MemoryStore, PowerContextError

logger = logging.getLogger(__name__)


class PawnshopService:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def context(self, player_id: str, message: str) -> str:
        scope_id = await self._store.ensure_scope(player_id)
        entries = await self._store.list_entries(scope_id, include_inactive=True)
        message = message.strip()
        hits = await self._store.search(scope_id, message, limit=6) if message else []
        active_entry_ids = {pawn.entry_id for pawn in active_pawns(entries)}
        hits = [
            hit
            for hit in hits
            if str((hit.get("citation") or {}).get("entry_id") or "") in active_entry_ids
        ]
        return format_context(entries=entries, hits=hits, next_ticket=max_ticket(entries) + 1)

    async def turn(self, player_id: str, message: str, reply: str) -> str:
        scope_id = await self._store.ensure_scope(player_id)
        message = message.strip()
        reply = reply.strip()
        if not message or not reply:
            raise ValueError("本轮缺少玩家输入或掌柜回应")
        entries = await self._store.list_entries(scope_id, include_inactive=True)
        ticket = max_ticket(entries) + 1
        await self._store.remember(scope_id, PAWN_KIND, pawn_text(ticket, message, reply))
        return str(ticket)

    async def ledger(self, player_id: str) -> str:
        scope_id = await self._store.ensure_scope(player_id)
        entries = await self._store.list_entries(scope_id, include_inactive=True)
        return format_ledger(active_pawns(entries))

    async def redeem(self, player_id: str, message: str) -> str:
        scope_id = await self._store.ensure_scope(player_id)
        entries = await self._store.list_entries(scope_id, include_inactive=True)
        pawns = active_pawns(entries)

        match = REDEEM_PATTERN.search(message)
        if match is None:
            return "赎回需要报上当票编号。\n\n" + format_ledger(pawns)

        ticket = int(match.group(1))
        pawn = next((item for item in pawns if item.ticket == ticket), None)
        if pawn is None:
            return f"账本里没有第 {ticket} 号未赎当票。\n\n" + format_ledger(pawns)

        await self._store.retire(scope_id, pawn.citation, reason=f"玩家赎回当票 #{ticket}")
        remaining = len(pawns) - 1
        try:
            await self._store.remember(scope_id, REDEEM_KIND, redemption_text(ticket, pawn))
        except PowerContextError:
            # 赎回已经生效；审计条目失败不应让玩家误以为赎回未完成。
            logger.exception("无法写入赎回记录，当票 #%s 已停用", ticket)
        return format_redeem_success(pawn, remaining)
