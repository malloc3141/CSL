"""Admin API behind ADMIN_TOKEN, used by the /admin page of the frontend.

    GET  /api/admin/sessions                 every stored session, with LLM cost
    GET  /api/admin/sessions/{id}            snapshot (messages, states) + pipeline scratch
    GET  /api/admin/sessions/{id}/events     raw event log
    GET  /api/admin/usage?tzOffset=540       LLM usage (tokens, cost, prompt-cache hit rate) by model and
                                             day, plus the OpenRouter key's spend
    GET  /api/admin/config                   models in use
    PUT  /api/admin/config                   switch models at runtime (persisted; "" = back to .env)
    GET  /api/admin/models                   OpenRouter model list with prices

All of it is off (404) when ADMIN_TOKEN is empty.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from . import openrouter
from .config import Settings
from .llm import effective_models, model_override, set_model_override
from .protocol import (
    AdminSessionDetail,
    AdminSessionRow,
    ModelConfig,
    ModelConfigUpdate,
    SessionSnapshot,
    UsageBucket,
    UsageReport,
)
from .store import Store

log = logging.getLogger("csl.admin")
OVERRIDE_KEY = "model_override"


async def load_model_override(store: Store) -> None:
    """Apply the override saved from the admin page (called at startup)."""
    raw = await store.get_config(OVERRIDE_KEY)
    data = json.loads(raw) if raw else {}
    set_model_override(data.get("model") or "", data.get("modelFast") or "")


class _Acc:
    def __init__(self, key: str):
        self.b = UsageBucket(key=key)
        self.seconds = 0.0

    def add(self, data: dict[str, Any], prices: dict[str, tuple[float, float]]) -> None:
        b = self.b
        b.calls += 1
        if data.get("error"):
            b.errors += 1
        prompt = data.get("promptTokens") or 0
        completion = data.get("completionTokens") or 0
        b.prompt_tokens += prompt
        b.completion_tokens += completion
        b.reasoning_tokens += data.get("reasoningTokens") or 0
        if isinstance(data.get("cachedTokens"), int):  # absent = the call reported no cache figure
            b.cached_tokens += data["cachedTokens"]
            b.cache_measured_tokens += prompt
        b.cache_write_tokens += data.get("cacheWriteTokens") or 0
        self.seconds += data.get("seconds") or 0.0
        if isinstance(data.get("cost"), (int, float)):
            b.cost += data["cost"]
        elif prompt or completion:
            price = prices.get(data.get("model") or "")
            if price:
                b.cost += (prompt * price[0] + completion * price[1]) / 1_000_000
                b.estimated = True
            else:
                b.unpriced_calls += 1

    def done(self) -> UsageBucket:
        self.b.avg_seconds = round(self.seconds / self.b.calls, 3) if self.b.calls else 0.0
        self.b.cost = round(self.b.cost, 6)
        if self.b.cache_measured_tokens:
            self.b.cache_hit_rate = round(self.b.cached_tokens / self.b.cache_measured_tokens, 4)
        return self.b


def _group(
    calls: list[tuple[str, float, dict[str, Any]]],
    prices: dict[str, tuple[float, float]],
    key: Callable[[str, float, dict[str, Any]], str],
) -> dict[str, UsageBucket]:
    accs: dict[str, _Acc] = {}
    for sid, ts, data in calls:
        k = key(sid, ts, data)
        accs.setdefault(k, _Acc(k)).add(data, prices)
    return {k: a.done() for k, a in accs.items()}


def admin_router(settings: Settings) -> APIRouter:
    def require_admin(authorization: Optional[str] = Header(default=None)) -> None:
        token = settings.admin_token
        if not token:
            raise HTTPException(404)
        if not authorization or not secrets.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
            raise HTTPException(401)

    router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

    def config_now(request: Request) -> ModelConfig:
        model, model_fast = effective_models(settings)
        return ModelConfig(
            pipeline=request.app.state.registry.pipeline.name,
            model=model,
            model_fast=model_fast,
            default_model=settings.openrouter_model,
            default_model_fast=settings.openrouter_model_fast,
            overridden=any(model_override()),
            api_key_set=bool(settings.openrouter_api_key),
        )

    @router.get("/sessions")
    async def sessions(request: Request) -> list[dict[str, Any]]:
        store: Store = request.app.state.store
        runners = request.app.state.registry.runners
        rows = await store.list_sessions()
        calls = await store.llm_calls()
        per_session = _group(calls, await openrouter.prices(settings) if calls else {}, lambda sid, _ts, _d: sid)
        out = []
        for row in rows:
            item = AdminSessionRow.model_validate(row)
            usage = per_session.get(item.session_id)
            if usage:
                item.llm_calls, item.cost = usage.calls, usage.cost
            runner = runners.get(item.session_id)
            if runner is not None:
                item.live = True
                item.phase = runner.session.phase
                item.pipeline = runner.session.pipeline or None
                item.message_count = len(runner.session.messages)
            out.append(item.wire())
        return out

    @router.get("/sessions/{session_id}")
    async def session_detail(session_id: str, request: Request) -> dict[str, Any]:
        # Read without loading the session into the registry (no restore, no capacity use).
        runner = request.app.state.registry.runners.get(session_id)
        if runner is not None:
            s = runner.session
            return AdminSessionDetail(snapshot=s.snapshot(), scratch=s.scratch, live=True).wire()
        raw = await request.app.state.store.load_session(session_id)
        if raw is None:
            raise HTTPException(404, "No such session.")
        payload = json.loads(raw)
        snapshot = SessionSnapshot.model_validate(payload["snapshot"])
        return AdminSessionDetail(snapshot=snapshot, scratch=payload.get("scratch") or {}, live=False).wire()

    @router.get("/sessions/{session_id}/events")
    async def session_events(session_id: str, request: Request) -> list[dict[str, Any]]:
        return await request.app.state.store.list_events(session_id)

    @router.get("/usage")
    async def usage(request: Request, tz_offset: int = Query(default=0, alias="tzOffset", ge=-720, le=840)) -> dict[str, Any]:
        calls = await request.app.state.store.llm_calls()
        prices = await openrouter.prices(settings) if calls else {}
        tz = timezone(timedelta(minutes=tz_offset))
        total = _group(calls, prices, lambda *_: "total").get("total") or UsageBucket(key="total")
        by_model = sorted(
            _group(calls, prices, lambda _s, _t, d: d.get("model") or "?").values(), key=lambda b: -b.cost
        )
        by_day = sorted(
            _group(calls, prices, lambda _s, ts, _d: datetime.fromtimestamp(ts, tz).date().isoformat()).values(),
            key=lambda b: b.key,
            reverse=True,
        )
        report = UsageReport(total=total, by_model=by_model, by_day=by_day)
        if settings.openrouter_api_key:
            try:
                report.openrouter = await openrouter.key_info(settings)
            except Exception as exc:
                log.warning("OpenRouter key info failed: %r", exc)
                report.openrouter_error = type(exc).__name__ + (
                    f" {exc.response.status_code}" if hasattr(exc, "response") else ""
                )
        return report.wire()

    @router.get("/config")
    async def get_config(request: Request) -> dict[str, Any]:
        return config_now(request).wire()

    @router.put("/config")
    async def put_config(body: ModelConfigUpdate, request: Request) -> dict[str, Any]:
        model, model_fast = body.model.strip(), body.model_fast.strip()
        wanted = [m for m in (model, model_fast) if m]
        if wanted:
            try:
                known = {m.id for m in await openrouter.list_models(settings)}
            except Exception:
                known = None  # cannot check offline; accept
            unknown = [m for m in wanted if known is not None and m not in known]
            if unknown:
                raise HTTPException(422, f"Unknown OpenRouter model: {', '.join(unknown)}")
        set_model_override(model, model_fast)
        await request.app.state.store.set_config(OVERRIDE_KEY, json.dumps({"model": model, "modelFast": model_fast}))
        log.info("model override set: model=%r model_fast=%r", model, model_fast)
        return config_now(request).wire()

    @router.get("/models")
    async def models(refresh: bool = False) -> list[dict[str, Any]]:
        try:
            return [m.wire() for m in await openrouter.list_models(settings, refresh=refresh)]
        except Exception as exc:
            log.warning("OpenRouter model list failed: %r", exc)
            raise HTTPException(502, "Could not load the OpenRouter model list.")

    return router
