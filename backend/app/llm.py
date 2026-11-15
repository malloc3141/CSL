"""OpenRouter access for pipelines.

    from app.llm import get_llm
    llm = get_llm()
    text = await llm.complete([{"role": "user", "content": "..."}])
    async for chunk in llm.stream(messages): ...
    data = await llm.complete_json(messages)          # dict
    ... = await llm.complete(messages, fast=True)     # OPENROUTER_MODEL_FAST

Every call is logged to the session's event log as `llm.call` (model, latency,
token usage when the provider reports it), which is what you need for cost and
latency numbers later.

The model ids come from backend/.env (OPENROUTER_MODEL, OPENROUTER_MODEL_FAST)
unless an override was set at runtime from the admin page (set_model_override);
the override applies from the next call on.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, AsyncIterator, Optional

from .config import Settings, get_settings
from .pipeline.base import PipelineError
from .session import current_session

Messages = list[dict[str, str]]

# Runtime override of the model ids: (model, model_fast). "" = use the .env value.
_override: tuple[str, str] = ("", "")


def set_model_override(model: str, model_fast: str) -> None:
    global _override
    _override = (model.strip(), model_fast.strip())


def model_override() -> tuple[str, str]:
    return _override


def effective_models(settings: Settings) -> tuple[str, str]:
    """(model, model_fast) in use now. model_fast is "" when fast calls use `model`."""
    return _override[0] or settings.openrouter_model, _override[1] or settings.openrouter_model_fast


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object out of a model reply (tolerates code fences and chatter)."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model output")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return data


# Ask OpenRouter to include token counts and the cost in `usage`.
USAGE_ACCOUNTING = {"usage": {"include": True}}


def reasoning_param(setting: str) -> Optional[dict[str, Any]]:
    """OpenRouter's `reasoning` request field for LLM_REASONING.

    Models such as claude-haiku-5.5 decide on their own to think before answering, and the thinking
    tokens count against max_tokens: a 300-token reply budget can be used up before any text comes
    out. "off" (the default) turns thinking off; "low" / "medium" / "high" set an effort; "default"
    sends nothing and leaves it to the model.
    """
    setting = setting.strip().lower()
    if setting == "off":
        return {"enabled": False}
    if setting in ("low", "medium", "high"):
        return {"effort": setting}
    return None


def _reasoning_only(usage: Any) -> bool:
    """True if the reply has no text because every completion token went into reasoning."""
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None) or 0
    return bool(reasoning) and reasoning >= (getattr(usage, "completion_tokens", None) or 0)


REASONING_ONLY = (
    "the model used its whole max_tokens budget for reasoning and wrote no text "
    "(set LLM_REASONING=off, or pick a model that can answer without reasoning)"
)


class LLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Any = None
        self._sem = asyncio.Semaphore(settings.llm_concurrency)

    @property
    def client(self) -> Any:
        if self._client is None:
            st = self.settings
            if not st.openrouter_api_key or not effective_models(st)[0]:
                raise PipelineError("OPENROUTER_API_KEY and OPENROUTER_MODEL must be set in backend/.env")
            from openai import AsyncOpenAI

            headers = {"X-Title": st.openrouter_app_title}
            if st.openrouter_app_url:
                headers["HTTP-Referer"] = st.openrouter_app_url
            self._client = AsyncOpenAI(
                api_key=st.openrouter_api_key,
                base_url=st.openrouter_base_url,
                default_headers=headers,
                timeout=st.llm_timeout_seconds,
                max_retries=2,
            )
        return self._client

    def _base_kwargs(
        self, name: str, messages: Messages, temperature: float, max_tokens: Optional[int]
    ) -> dict[str, Any]:
        extra: dict[str, Any] = dict(USAGE_ACCOUNTING)
        reasoning = reasoning_param(self.settings.llm_reasoning)
        if reasoning is not None:
            extra["reasoning"] = reasoning
        kwargs: dict[str, Any] = {"model": name, "messages": messages, "temperature": temperature, "extra_body": extra}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        return kwargs

    async def _create(self, kwargs: dict[str, Any]) -> Any:
        """chat.completions.create, dropping optional fields the model rejects (400/404/422).

        Not every model on OpenRouter supports response_format, and models that always reason
        may reject a request to turn reasoning off.
        """
        while True:
            try:
                return await self.client.chat.completions.create(**kwargs)
            except Exception as exc:
                if getattr(exc, "status_code", None) not in (400, 404, 422):
                    raise
                if "response_format" in kwargs:
                    kwargs.pop("response_format")
                elif "reasoning" in kwargs.get("extra_body", {}):
                    kwargs["extra_body"] = {k: v for k, v in kwargs["extra_body"].items() if k != "reasoning"}
                else:
                    raise

    def _model(self, model: Optional[str], fast: bool) -> str:
        main, quick = effective_models(self.settings)
        return model or (quick if fast and quick else main)

    def _log(self, kind: str, model: str, started: float, usage: Any, chars: int, error: Optional[str] = None) -> None:
        session = current_session.get()
        if session is None:
            return
        data: dict[str, Any] = {
            "kind": kind,
            "model": model,
            "seconds": round(time.monotonic() - started, 3),
            "outputChars": chars,
        }
        if usage is not None:
            data["promptTokens"] = getattr(usage, "prompt_tokens", None)
            data["completionTokens"] = getattr(usage, "completion_tokens", None)
            details = getattr(usage, "completion_tokens_details", None)
            reasoning = getattr(details, "reasoning_tokens", None) if details is not None else None
            if reasoning:
                data["reasoningTokens"] = reasoning
            # OpenRouter reports the charged amount (USD) in usage.cost.
            cost = getattr(usage, "cost", None)
            if isinstance(cost, (int, float)):
                data["cost"] = cost
        if error:
            data["error"] = error
        session.log("llm.call", data)

    async def stream(
        self,
        messages: Messages,
        *,
        model: Optional[str] = None,
        fast: bool = False,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Yield text chunks as the model produces them."""
        name = self._model(model, fast)
        started, usage, chars = time.monotonic(), None, 0
        kwargs = self._base_kwargs(name, messages, temperature, max_tokens)
        kwargs.update(stream=True, stream_options={"include_usage": True})
        async with self._sem:
            try:
                stream = await self._create(kwargs)
            except Exception as exc:
                self._log("stream", name, started, None, 0, repr(exc))
                raise
            try:
                async for chunk in stream:
                    if getattr(chunk, "usage", None):
                        usage = chunk.usage
                    if chunk.choices and chunk.choices[0].delta.content:
                        text = chunk.choices[0].delta.content
                        chars += len(text)
                        yield text
            finally:
                await stream.close()
                self._log("stream", name, started, usage, chars)
        if not chars and usage is not None and _reasoning_only(usage):
            raise PipelineError(REASONING_ONLY)

    async def complete(
        self,
        messages: Messages,
        *,
        model: Optional[str] = None,
        fast: bool = False,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        name = self._model(model, fast)
        started = time.monotonic()
        kwargs = self._base_kwargs(name, messages, temperature, max_tokens)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        async with self._sem:
            try:
                resp = await self._create(kwargs)
            except Exception as exc:
                self._log("complete", name, started, None, 0, repr(exc))
                raise
        text = (resp.choices[0].message.content or "") if resp.choices else ""
        usage = getattr(resp, "usage", None)
        self._log("complete", name, started, usage, len(text))
        if not text and usage is not None and _reasoning_only(usage):
            raise PipelineError(REASONING_ONLY)
        return text

    async def complete_json(
        self,
        messages: Messages,
        *,
        model: Optional[str] = None,
        fast: bool = False,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        attempts: int = 2,
    ) -> dict[str, Any]:
        """Like complete(), but returns a parsed JSON object. Retries on unparsable output."""
        last: Exception | None = None
        for _ in range(attempts):
            text = await self.complete(
                messages, model=model, fast=fast, temperature=temperature, max_tokens=max_tokens, json_mode=True
            )
            try:
                return extract_json(text)
            except ValueError as exc:
                last = exc
        raise PipelineError(f"model did not return valid JSON: {last}")


_llm: Optional[LLM] = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM(get_settings())
    return _llm


def set_llm(llm: Any) -> None:
    """Swap the client, e.g. for a fake in tests."""
    global _llm
    _llm = llm
