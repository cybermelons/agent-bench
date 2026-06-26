"""
tests.test_phase1 — the four Phase-1 acceptance checks, all offline.

1. AgentSpec / specs load.
2. CorpusRetriever finds 'oncall-policy' for the stipend question.
3. The LangGraph adapter (via the runner) produces an AgentResult that cites
   'oncall-policy' with terminated_by == GATE on a golden question — using an
   injected FakeLLM (no key, no network).
4. A skipif-no-key live test stub (the real live test lives in
   test_real_anthropic_skipif.py; this one asserts the gate is wired so the
   suite documents the contract even with no key).

All non-live checks pass with NO ANTHROPIC_API_KEY and NO network.
"""

from __future__ import annotations

import os

import pytest

from porcelain.llm import FakeLLM
from porcelain.runner import run_spec
from porcelain.types import AgentSpec, TerminatedBy


# 1. Specs load -------------------------------------------------------------

def test_specs_load(repo_root):
    lg = AgentSpec.from_yaml(repo_root / "specs" / "langgraph-baseline.yaml")
    cw = AgentSpec.from_yaml(repo_root / "specs" / "crewai-baseline.yaml")
    assert lg.framework == "langgraph"
    assert cw.framework == "crewai"
    # Identical except the framework line.
    assert lg.model == cw.model
    assert lg.termination.model_dump() == cw.termination.model_dump()


# 2. Retriever finds the right doc -----------------------------------------

def test_retriever_finds_oncall_policy(retriever):
    results = retriever.search("weekend on-call stipend", k=4)
    assert results[0].doc_id == "oncall-policy"


# 3. LangGraph adapter via runner → cites oncall-policy, GATE --------------

def test_langgraph_adapter_gates_on_golden(corpus_path):
    spec = AgentSpec(
        name="langgraph-phase1",
        framework="langgraph",
        corpus=corpus_path,
        model="claude-3-5-sonnet-latest",
    )
    result = run_spec(
        spec,
        "How much is the weekend on-call stipend, and how is it paid?",
        llm=FakeLLM(),
    )
    assert "oncall-policy" in [c.doc_id for c in result.citations]
    assert result.terminated_by == TerminatedBy.GATE
    assert "$150" in result.answer
    assert "Workday" in result.answer


# 4. Live test stub (skipped without a key) --------------------------------

@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="requires ANTHROPIC_API_KEY for a live Anthropic API call",
)
def test_live_stub(corpus_path):
    from porcelain.llm import RealAnthropicClient

    spec = AgentSpec(
        name="langgraph-live-stub",
        framework="langgraph",
        corpus=corpus_path,
        model="claude-3-5-sonnet-latest",
    )
    result = run_spec(
        spec,
        "How much is the weekend on-call stipend?",
        llm=RealAnthropicClient(),
    )
    assert result.cites_corpus({"oncall-policy"})
