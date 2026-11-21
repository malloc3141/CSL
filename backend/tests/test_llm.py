from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm import LLM, REASONING_ONLY, InvalidModelJSON, reasoning_param
from app.pipeline.base import PipelineError
from helpers import make_settings


class BadRequest(Exception):
    status_code = 400


def usage(completion: int, reasoning: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=completion,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )


class FakeStream:
    def __init__(self, texts: list[str], final_usage: SimpleNamespace):
        self.chunks = [
            SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content=t))]) for t in texts
        ] + [SimpleNamespace(usage=final_usage, choices=[])]

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for c in self.chunks:
            yield c

    async def close(self):
        pass


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append({**kwargs, "extra_body": dict(kwargs.get("extra_body") or {})})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def make_llm(tmp_path, replies, **settings) -> tuple[LLM, FakeCompletions]:
    llm = LLM(make_settings(tmp_path, openrouter_api_key="k", openrouter_model="m", **settings))
    completions = FakeCompletions(replies)
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return llm, completions


def reply(text: str, u: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=u)


def test_reasoning_param():
    assert reasoning_param("off") == {"enabled": False}
    assert reasoning_param("High") == {"effort": "high"}
    assert reasoning_param("default") is None


async def test_reasoning_is_off_by_default_and_dropped_if_rejected(tmp_path):
    llm, fake = make_llm(tmp_path, [BadRequest("reasoning cannot be disabled"), reply("hi", usage(2))])
    assert await llm.complete([{"role": "user", "content": "x"}]) == "hi"
    assert fake.calls[0]["extra_body"]["reasoning"] == {"enabled": False}
    assert "reasoning" not in fake.calls[1]["extra_body"]
    assert fake.calls[1]["extra_body"]["usage"] == {"include": True}

    llm, fake = make_llm(tmp_path, [reply("hi", usage(2))], llm_reasoning="default")
    await llm.complete([{"role": "user", "content": "x"}])
    assert "reasoning" not in fake.calls[0]["extra_body"]


async def test_json_mode_fallback_still_works(tmp_path):
    llm, fake = make_llm(tmp_path, [BadRequest("no response_format"), reply('{"a": 1}', usage(5))])
    assert await llm.complete_json([{"role": "user", "content": "x"}], attempts=1) == {"a": 1}
    assert "response_format" in fake.calls[0] and "response_format" not in fake.calls[1]
    assert fake.calls[1]["extra_body"]["reasoning"] == {"enabled": False}


async def test_malformed_output_has_a_distinct_error_after_json_retries(tmp_path):
    llm, fake = make_llm(tmp_path, [reply("unstructured", usage(1)), reply("{unfinished", usage(2))])
    with pytest.raises(InvalidModelJSON):
        await llm.complete_json([{"role": "user", "content": "x"}])
    assert len(fake.calls) == 2


async def test_reply_eaten_by_reasoning_gives_a_clear_error(tmp_path):
    llm, _ = make_llm(tmp_path, [FakeStream([], usage(300, 300))], llm_reasoning="default")
    with pytest.raises(PipelineError, match="reasoning"):
        async for _ in llm.stream([{"role": "user", "content": "x"}], max_tokens=300):
            pass

    llm, _ = make_llm(tmp_path, [reply("", usage(100, 100))], llm_reasoning="default")
    with pytest.raises(PipelineError) as err:
        await llm.complete([{"role": "user", "content": "x"}], max_tokens=100)
    assert str(err.value) == REASONING_ONLY

    llm, fake = make_llm(tmp_path, [FakeStream(["Hel", "lo"], usage(5))])
    assert [c async for c in llm.stream([{"role": "user", "content": "x"}])] == ["Hel", "lo"]
    assert fake.calls[0]["stream"] and fake.calls[0]["stream_options"] == {"include_usage": True}


async def test_session_id_is_sent_for_sticky_caching_and_dropped_if_rejected(tmp_path):
    from app.session import Session, current_session

    llm, fake = make_llm(tmp_path, [reply("hi", usage(2))])
    await llm.complete([{"role": "user", "content": "x"}])
    assert "session_id" not in fake.calls[0]["extra_body"]  # no session: nothing to key on

    token = current_session.set(Session("sess-123", "topic", "en", 60))
    try:
        llm, fake = make_llm(
            tmp_path, [BadRequest("no reasoning"), BadRequest("no session_id"), reply("hi", usage(2))]
        )
        assert await llm.complete([{"role": "user", "content": "x"}]) == "hi"
        assert fake.calls[0]["extra_body"]["session_id"] == "sess-123"
        assert "reasoning" not in fake.calls[1]["extra_body"] and fake.calls[1]["extra_body"]["session_id"] == "sess-123"
        assert "session_id" not in fake.calls[2]["extra_body"]
    finally:
        current_session.reset(token)
