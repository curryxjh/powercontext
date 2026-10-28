from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .service import PawnshopService
from .settings import Settings
from .store import MemoryStore, PowerContextError, PowerContextStore

logger = logging.getLogger(__name__)


class ContextRequest(BaseModel):
    player_id: str = Field(min_length=1, max_length=256)
    message: str = ""


class TurnRequest(BaseModel):
    player_id: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1)
    reply: str = Field(min_length=1)


class LedgerRequest(BaseModel):
    player_id: str = Field(min_length=1, max_length=256)


class RedeemRequest(BaseModel):
    player_id: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1)


def create_app(store: MemoryStore | None = None) -> FastAPI:
    owned_store = PowerContextStore(Settings.from_env()) if store is None else None
    active_store: MemoryStore = owned_store or store  # type: ignore[assignment]
    service = PawnshopService(active_store)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owned_store is not None:
            await owned_store.aclose()

    app = FastAPI(title="忘川当铺 · 记忆适配层", version="1.0.0", lifespan=lifespan)
    app.state.service = service
    app.state.store = active_store

    @app.exception_handler(PowerContextError)
    async def powercontext_error(_: Request, exc: PowerContextError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "powercontext_unavailable", "message": str(exc)}},
        )

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_request", "message": str(exc)}},
        )

    @app.get("/", response_class=PlainTextResponse)
    async def index() -> str:
        return "忘川当铺记忆适配层已启动。Dify 请调用 /v1/session/*，健康检查见 /health。"

    @app.get("/health")
    async def health() -> JSONResponse:
        powercontext_ready = await active_store.ready()
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok" if powercontext_ready else "degraded",
                "powercontext": "ready" if powercontext_ready else "unavailable",
            },
        )

    @app.post("/v1/session/context", response_class=PlainTextResponse)
    async def session_context(body: ContextRequest) -> str:
        return await service.context(body.player_id, body.message)

    @app.post("/v1/session/turn", response_class=PlainTextResponse)
    async def session_turn(body: TurnRequest) -> str:
        return await service.turn(body.player_id, body.message, body.reply)

    @app.post("/v1/session/ledger", response_class=PlainTextResponse)
    async def session_ledger(body: LedgerRequest) -> str:
        return await service.ledger(body.player_id)

    @app.post("/v1/session/redeem", response_class=PlainTextResponse)
    async def session_redeem(body: RedeemRequest) -> str:
        return await service.redeem(body.player_id, body.message)

    return app


app = create_app()
