from __future__ import annotations

import importlib

from ..config import Settings
from .base import (
    Classroom,
    InitResult,
    Pipeline,
    PipelineError,
    SpeakerDecision,
    StateUpdate,
    TextSink,
)

__all__ = [
    "Classroom",
    "FREE_PIPELINES",
    "InitResult",
    "Pipeline",
    "PipelineError",
    "SESSION_PIPELINES",
    "SpeakerDecision",
    "StateUpdate",
    "TextSink",
    "load_pipeline",
    "make_pipeline",
]

# Pipelines a session can ask for by name: POST /api/sessions {"pipeline": "<name>"}, or the "Agents"
# selector on /dev. The server's default stays whatever PIPELINE in backend/.env says.
#
# To try your pipeline on the deployed server, add one line here and push to main. No .env change and
# no restart by hand are needed. The module is imported the first time a session asks for it;
# tests/test_session_pipeline.py checks that every entry loads.
SESSION_PIPELINES: dict[str, str] = {
    "mock": "app.pipeline.mock:MockPipeline",
    "baseline": "app.pipeline.baseline:BaselinePipeline",
    "csl": "app.pipeline.csl:CslPipeline",
    "csl-shorten": "app.pipeline.csl:CslShortenPipeline",  # csl + the prompt changes of 2026-11-23
}

# Pipelines that make no LLM calls. Sessions that ask for one of these need no access code.
FREE_PIPELINES = frozenset({"mock"})


def make_pipeline(spec: str) -> Pipeline:
    """A new pipeline from a name in SESSION_PIPELINES or from "package.module:ClassName"."""
    spec = spec.strip()
    module_name, _, class_name = SESSION_PIPELINES.get(spec, spec).partition(":")
    if not class_name:
        known = ", ".join(SESSION_PIPELINES)
        raise ValueError(f"PIPELINE must be one of {known} or 'module:Class', got {spec!r}")
    pipeline = getattr(importlib.import_module(module_name), class_name)()
    if not isinstance(pipeline, Pipeline):
        raise TypeError(f"{spec} does not implement the Pipeline interface (see app/pipeline/base.py)")
    return pipeline


def load_pipeline(settings: Settings) -> Pipeline:
    """The server's default pipeline. PIPELINE=<name in SESSION_PIPELINES> | package.module:ClassName"""
    return make_pipeline(settings.pipeline)
