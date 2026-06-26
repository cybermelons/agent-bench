"""
tests.test_real_anthropic_skipif — live integration test, skipped without a key.

This is the ONLY test that may hit the real Anthropic API.  It is decorated
``pytest.mark.skipif(no ANTHROPIC_API_KEY)`` so the suite still exits 0 offline
with no key and no network.  When a key is present it runs one golden question
through :class:`RealAnthropicClient` and the real LangGraph StateGraph, then
asserts the answer is grounded in the expected corpus doc.
"""

from __future__ import annotations

import os

import pytest

from porcelain.llm import RealAnthropicClient
from porcelain.runner import run_spec
from porcelain.types import AgentSpec, TerminatedBy

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="requires ANTHROPIC_API_KEY for a live Anthropic API call",
)


def test_live_golden_q1(corpus_path, golden):
    q1 = next(q for q in golden if q["id"] == "q1")
    spec = AgentSpec(
        name="langgraph-live",
        framework="langgraph",
        corpus=corpus_path,
        model="claude-3-5-sonnet-latest",
    )

    result = run_spec(spec, q1["question"], llm=RealAnthropicClient())

    # A grounded live answer should cite the on-call policy and gate.
    assert result.terminated_by == TerminatedBy.GATE
    assert result.cites_corpus({"oncall-policy"})
    assert result.tokens_in > 0
    assert result.tokens_out > 0
