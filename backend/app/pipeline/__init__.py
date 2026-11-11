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
    "InitResult",
    "Pipeline",
    "PipelineError",
    "SpeakerDecision",
    "StateUpdate",
    "TextSink",
    "load_pipeline",
]


def load_pipeline(settings: Settings) -> Pipeline:
    """PIPELINE=mock | baseline | package.module:ClassName"""
    spec = settings.pipeline.strip()
    if spec == "mock":
        from .mock import MockPipeline

        return MockPipeline()
    if spec == "baseline":
        from .baseline import BaselinePipeline

        return BaselinePipeline()
    module_name, _, class_name = spec.partition(":")
    if not class_name:
        raise ValueError(f"PIPELINE must be 'mock', 'baseline' or 'module:Class', got {spec!r}")
    pipeline = getattr(importlib.import_module(module_name), class_name)()
    if not isinstance(pipeline, Pipeline):
        raise TypeError(f"{spec} does not implement the Pipeline interface (see app/pipeline/base.py)")
    return pipeline
