"""
tests.test_runner_fake_llm — offline unit tests with FakeLLM injected.

These tests are the offline contract guarantee: they MUST pass with NO
ANTHROPIC_API_KEY and NO network.  Every LLM call goes through an injected
:class:`FakeLLM`; the LangGraph adapter runs a real compiled StateGraph.

Covered:
* golden q1 (on-call stipend) → cites 'oncall-policy', terminated_by == GATE,
  answer contains '$150' and 'Workday';
* an answer with no [doc_id: ...] label → empty citations → MAX_ITER;
* the no-key / no-network invariant is structurally satisfied (FakeLLM is
  injected; nothing imports or constructs the real client).
"""

from __future__ import annotations

import os

import pytest

from porcelain.llm import FakeLLM
from porcelain.runner import run_spec
from porcelain.types import AgentSpec, TerminatedBy


def _langgraph_spec(corpus_path: str) -> AgentSpec:
    """A langgraph AgentSpec pointed at the absolute corpus path (cwd-safe)."""
    return AgentSpec(
        name="langgraph-test",
        framework="langgraph",
        corpus=corpus_path,
        model="claude-3-5-sonnet-latest",
    )


# ---------------------------------------------------------------------------
# Spec + retriever sanity
# ---------------------------------------------------------------------------

def test_spec_loads_from_yaml(repo_root):
    spec = AgentSpec.from_yaml(repo_root / "specs" / "langgraph-baseline.yaml")
    assert spec.framework == "langgraph"
    assert spec.termination.max_iterations == 6
    assert spec.termination.success_gate == "cites_corpus"


def test_retriever_finds_oncall_policy_for_stipend_question(retriever):
    results = retriever.search(
        "How much is the weekend on-call stipend and how is it paid?", k=4
    )
    assert results[0].doc_id == "oncall-policy"
    assert "oncall-policy" in retriever.doc_ids


# ---------------------------------------------------------------------------
# Golden q1 through the real LangGraph StateGraph + FakeLLM → GATE
# ---------------------------------------------------------------------------

def test_golden_q1_cites_oncall_policy_and_gates(corpus_path, golden):
    q1 = next(q for q in golden if q["id"] == "q1")
    spec = _langgraph_spec(corpus_path)

    result = run_spec(spec, q1["question"], llm=FakeLLM())

    # Cited the expected corpus doc → honest GATE.
    assert [c.doc_id for c in result.citations] == ["oncall-policy"]
    assert result.cites_corpus({"oncall-policy"}) is True
    assert result.terminated_by == TerminatedBy.GATE

    # Answer carries the golden answer_contains substrings.
    for needle in q1["answer_contains"]:  # ["$150", "Workday"]
        assert needle in result.answer

    # Token accounting flowed through from FakeLLM (fixed small ints).
    assert result.tokens_in > 0
    assert result.tokens_out > 0
    assert result.iterations >= 1
    assert result.error is None


# ---------------------------------------------------------------------------
# No-citation answer → empty citations → MAX_ITER
# ---------------------------------------------------------------------------

def test_uncited_answer_yields_max_iter(corpus_path, golden):
    q1 = next(q for q in golden if q["id"] == "q1")
    spec = _langgraph_spec(corpus_path)

    # Force an answer with NO [doc_id: ...] label for this question.
    forced = FakeLLM(answers={"on-call": "The stipend is paid somehow."})
    result = run_spec(spec, q1["question"], llm=forced)

    assert result.citations == []
    assert result.cites_corpus(spec_doc_ids := {"oncall-policy"}) is False
    assert result.terminated_by == TerminatedBy.MAX_ITER
    # The loop ran to the cap because the gate never fired.
    assert result.iterations == spec.termination.max_iterations


def test_hallucinated_doc_id_is_dropped_and_max_iter(corpus_path, golden):
    q1 = next(q for q in golden if q["id"] == "q1")
    spec = _langgraph_spec(corpus_path)

    # A doc_id that is NOT in the corpus must be dropped by extract_citations,
    # keeping cites_corpus false → MAX_ITER, never GATE.
    forced = FakeLLM(answers={"on-call": "Answer [doc_id: not-a-real-doc]."})
    result = run_spec(spec, q1["question"], llm=forced)

    assert result.citations == []
    assert result.terminated_by == TerminatedBy.MAX_ITER


# ---------------------------------------------------------------------------
# Offline invariant
# ---------------------------------------------------------------------------

def test_runs_offline_with_no_api_key(monkeypatch, corpus_path):
    """With no key and an injected FakeLLM, run_spec produces a result."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "ANTHROPIC_API_KEY" not in os.environ

    spec = _langgraph_spec(corpus_path)
    result = run_spec(
        spec,
        "How much is the weekend on-call stipend?",
        llm=FakeLLM(),
    )
    assert result.terminated_by == TerminatedBy.GATE
    assert result.answer  # non-empty
