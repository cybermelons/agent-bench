"""
tests.test_phase2 — the CrewAI adapter + the framework-interchange proof.

All offline: every LLM call goes through an injected :class:`FakeLLM`; the
CrewAI adapter runs a REAL ``crewai.Agent`` + ``crewai.Task`` + ``crewai.Crew``,
and retrieval is the shared :class:`CorpusRetriever`.  Nothing here needs an API
key or network.

Two things are proven:

1. ``test_crewai_adapter_gates_on_golden`` — the CrewAI adapter answers the
   golden on-call stipend question, cites ``oncall-policy``, and the base class
   classifies it ``terminated_by == GATE`` (same contract LangGraph satisfies in
   Phase 1), with token accounting flowing through the LLM shim.

2. ``test_framework_interchange_langgraph_vs_crewai`` — THE INTERCHANGE TEST.
   The same question is run through the runner against ``langgraph-baseline.yaml``
   and ``crewai-baseline.yaml`` (identical except the ``framework:`` line) with
   the SAME injected FakeLLM, and BOTH produce an AgentResult that cites
   ``oncall-policy``.  Swapping the framework is the only difference.
"""

from __future__ import annotations

import os

import pytest

from porcelain.llm import FakeLLM
from porcelain.runner import run_spec
from porcelain.types import AgentSpec, TerminatedBy

# Keep CrewAI fully offline + quiet: never phone home for tracing in tests.
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

_GOLDEN_Q = "How much is the weekend on-call stipend, and how is it paid?"


def _crewai_spec(corpus_path: str) -> AgentSpec:
    """A crewai AgentSpec pointed at the absolute corpus path (cwd-safe)."""
    return AgentSpec(
        name="crewai-phase2",
        framework="crewai",
        corpus=corpus_path,
        model="claude-3-5-sonnet-latest",
    )


# ---------------------------------------------------------------------------
# (a) CrewAI adapter answers the golden question, cites oncall-policy, GATE
# ---------------------------------------------------------------------------

def test_crewai_adapter_gates_on_golden(corpus_path):
    spec = _crewai_spec(corpus_path)

    result = run_spec(spec, _GOLDEN_Q, llm=FakeLLM())

    # Cited the expected corpus doc → honest GATE (base-class classification).
    assert [c.doc_id for c in result.citations] == ["oncall-policy"]
    assert result.cites_corpus({"oncall-policy"}) is True
    assert result.terminated_by == TerminatedBy.GATE

    # Golden answer content flowed through the CrewAI crew + the LLM shim.
    assert "$150" in result.answer
    assert "Workday" in result.answer

    # Token accounting came back through the shim (FakeLLM's fixed small ints).
    assert result.tokens_in > 0
    assert result.tokens_out > 0
    assert result.iterations >= 1
    assert result.error is None


def test_crewai_adapter_loops_to_max_iter_when_ungrounded(corpus_path):
    """An answer with no real [doc_id: ...] never gates → MAX_ITER at the cap."""
    spec = _crewai_spec(corpus_path)

    forced = FakeLLM(answers={"on-call": "The stipend is paid somehow."})
    result = run_spec(spec, _GOLDEN_Q, llm=forced)

    assert result.citations == []
    assert result.terminated_by == TerminatedBy.MAX_ITER
    # The crew was re-kicked up to the cap because the gate never fired.
    assert result.iterations == spec.termination.max_iterations


# ---------------------------------------------------------------------------
# (b) THE INTERCHANGE TEST — same agent, only the framework line differs
# ---------------------------------------------------------------------------

def test_framework_interchange_langgraph_vs_crewai(repo_root):
    """Same question, same FakeLLM, two specs differing ONLY in framework.

    Both must produce an AgentResult that cites oncall-policy — proving the
    framework swap is a one-line change over otherwise-identical declarations.
    """
    lg_spec = AgentSpec.from_yaml(repo_root / "specs" / "langgraph-baseline.yaml")
    cw_spec = AgentSpec.from_yaml(repo_root / "specs" / "crewai-baseline.yaml")

    # The two specs are identical except for the framework line.
    assert lg_spec.framework == "langgraph"
    assert cw_spec.framework == "crewai"
    assert lg_spec.model == cw_spec.model
    assert lg_spec.corpus == cw_spec.corpus
    assert lg_spec.termination.model_dump() == cw_spec.termination.model_dump()

    lg_result = run_spec(lg_spec, _GOLDEN_Q, llm=FakeLLM())
    cw_result = run_spec(cw_spec, _GOLDEN_Q, llm=FakeLLM())

    # The ONLY difference is the framework; both ground on the same corpus doc.
    assert lg_result.cites_corpus({"oncall-policy"}) is True
    assert cw_result.cites_corpus({"oncall-policy"}) is True
    assert [c.doc_id for c in lg_result.citations] == ["oncall-policy"]
    assert [c.doc_id for c in cw_result.citations] == ["oncall-policy"]
    assert lg_result.terminated_by == cw_result.terminated_by == TerminatedBy.GATE


# ---------------------------------------------------------------------------
# Offline invariant for the CrewAI path
# ---------------------------------------------------------------------------

def test_crewai_runs_offline_with_no_api_key(monkeypatch, corpus_path):
    """With no key and an injected FakeLLM, the crewai path still gates."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "ANTHROPIC_API_KEY" not in os.environ

    spec = _crewai_spec(corpus_path)
    result = run_spec(spec, _GOLDEN_Q, llm=FakeLLM())

    assert result.terminated_by == TerminatedBy.GATE
    assert result.answer  # non-empty
