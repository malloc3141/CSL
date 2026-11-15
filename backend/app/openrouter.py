"""Read-only OpenRouter account endpoints, for the admin page.

    await list_models(settings)   # every model with its list price, cached for an hour
    await key_info(settings)      # spend and limit of the configured API key

The LLM calls themselves go through app/llm.py.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from .config import Settings
from .protocol import ModelInfo, OpenRouterKeyInfo

MODELS_TTL_SECONDS = 3600
_models: Optional[tuple[float, list[ModelInfo]]] = None


async def _get(url: str, api_key: Optional[str] = None) -> Any:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


def _per_million(value: Any) -> float:
    try:
        price = float(value) * 1_000_000
    except (TypeError, ValueError):
        return 0.0
    return price if price > 0 else 0.0  # -1 marks variable pricing (e.g. openrouter/auto)


def _number(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) else None


async def list_models(settings: Settings, refresh: bool = False) -> list[ModelInfo]:
    global _models
    if not refresh and _models and time.monotonic() - _models[0] < MODELS_TTL_SECONDS:
        return _models[1]
    body = await _get(f"{settings.openrouter_base_url.rstrip('/')}/models")
    models = []
    for m in body.get("data") or []:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        pricing = m.get("pricing") or {}
        models.append(
            ModelInfo(
                id=m["id"],
                name=m.get("name") or m["id"],
                prompt_price=_per_million(pricing.get("prompt")),
                completion_price=_per_million(pricing.get("completion")),
                context_length=m.get("context_length") if isinstance(m.get("context_length"), int) else None,
            )
        )
    models.sort(key=lambda m: m.id)
    _models = (time.monotonic(), models)
    return models


async def prices(settings: Settings) -> dict[str, tuple[float, float]]:
    """model id -> (USD per 1M prompt tokens, USD per 1M completion tokens). Empty if unreachable."""
    try:
        return {m.id: (m.prompt_price, m.completion_price) for m in await list_models(settings)}
    except Exception:
        return {}


async def key_info(settings: Settings) -> OpenRouterKeyInfo:
    body = await _get(f"{settings.openrouter_base_url.rstrip('/')}/key", settings.openrouter_api_key)
    data = body.get("data") or {}
    return OpenRouterKeyInfo(
        label=data.get("label") if isinstance(data.get("label"), str) else None,
        usage=_number(data.get("usage")) or 0.0,
        usage_daily=_number(data.get("usage_daily")),
        usage_weekly=_number(data.get("usage_weekly")),
        usage_monthly=_number(data.get("usage_monthly")),
        limit=_number(data.get("limit")),
        limit_remaining=_number(data.get("limit_remaining")),
    )
