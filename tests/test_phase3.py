"""
tests.test_phase3 — the evalkit measurement spine, fully offline (FakeLLM).

Three things are proven, all keyless/offline:

(a) ``judge_correctness`` is DETERMINISTIC under :class:`FakeLLM` — the same
    inputs yield the same grade across repeated calls, and a clearly-correct
    answer outscores a clearly-wrong one.
(b) the deterministic scorers (``citation_valid``, ``answer_contains_score``)
    return the right values on a crafted ``AgentResult``.
(c) ``evalkit.run`` on ``--subset 2`` with ``backend=fake`` writes a
    ``results.json`` whose ``summary`` contains BOTH 'langgraph' and 'crewai'
    groups, each with numeric metrics, and whose ``meta`` is honestly flagged
    synthetic.

Nothing here touches the network or needs an API key.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

from evalkit.judge import answer_contains_score, citation_valid, judge_correctness
from evalkit import run as evalrun
from porcelain.llm import FakeLLM
from porcelain.types import AgentResult, Citation, TerminatedBy

# Keep any CrewAI path quiet/offline.
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

_MODEL = "claude-3-5-sonnet-latest"


# ---------------------------------------------------------------------------
# (a) judge_correctness deterministic under FakeLLM
# ---------------------------------------------------------------------------

def test_judge_correctness_deterministic_with_fake_llm():
    question = "How much is the weekend on-call stipend, and how is it paid?"
    rubric = (
        "A correct answer states the weekend on-call stipend is $150 per day "
        "and is processed automatically through Workday."
    )
    good_answer = (
        "The weekend on-call stipend is $150 per day, processed automatically "
        "through Workday at the end of the rotation week."
    )

    llm = FakeLLM()
    g1 = judge_correctness(question, rubric, good_answer, llm=llm, model=_MODEL)
    g2 = judge_correctness(question, rubric, good_answer, llm=llm, model=_MODEL)

    # Deterministic: identical inputs → identical grade.
    assert g1 == g2
    assert set(g1) == {"score", "verdict", "reason"}
    assert 0.0 <= g1["score"] <= 1.0
    assert g1["verdict"] in {"pass", "fail"}

    # A clearly-correct answer must outscore an "I couldn't answer" one, which
    # the fallback recognises as a fail via its markers.
    bad_answer = "I could not find grounding in the corpus for this question."
    bad = judge_correctness(question, rubric, bad_answer, llm=llm, model=_MODEL)
    assert bad["verdict"] == "fail"
    assert g1["score"] > bad["score"]


def test_judge_parses_strict_json_when_present():
    """When the client returns strict JSON, the judge parses it (not fallback)."""
    forced = FakeLLM(
        answers={"grade me": '{"score": 0.9, "verdict": "pass", "reason": "ok"}'}
    )
    grade = judge_correctness(
        question="grade me please",
        rubric="anything",
        answer="some answer",
        llm=forced,
        model=_MODEL,
    )
    assert grade["score"] == 0.9
    assert grade["verdict"] == "pass"
    assert grade["reason"] == "ok"


# ---------------------------------------------------------------------------
# (b) deterministic scorers on a crafted result
# ---------------------------------------------------------------------------

def test_deterministic_scorers_on_crafted_result():
    result = AgentResult(
        answer="The stipend is $150 per day, paid via Workday.",
        citations=[Citation(doc_id="oncall-policy")],
        terminated_by=TerminatedBy.GATE,
    )
    valid_doc_ids = {"oncall-policy", "deploy-staging", "incident-response"}

    cite = citation_valid(result, valid_doc_ids, expected_doc="oncall-policy")
    assert cite == {"cited_any": True, "cited_expected": True}

    # answer_contains: both present → 1.0; one present → 0.5; none → 0.0.
    assert answer_contains_score(result.answer, ["$150", "Workday"]) == 1.0
    assert answer_contains_score(result.answer, ["$150", "Slack"]) == 0.5
    assert answer_contains_score(result.answer, ["Jira", "Slack"]) == 0.0
    # Empty requirement list → trivially satisfied.
    assert answer_contains_score(result.answer, []) == 1.0

    # A result citing a non-corpus doc, with the expected doc absent.
    wrong = AgentResult(
        answer="unrelated",
        citations=[Citation(doc_id="not-a-real-doc")],
        terminated_by=TerminatedBy.MAX_ITER,
    )
    wrong_cite = citation_valid(wrong, valid_doc_ids, expected_doc="oncall-policy")
    assert wrong_cite == {"cited_any": False, "cited_expected": False}


# ---------------------------------------------------------------------------
# (c) evalkit.run --subset 2 backend=fake → both frameworks in summary
# ---------------------------------------------------------------------------

def test_evalrun_subset_emits_both_frameworks(tmp_path):
    out = tmp_path / "results.json"
    rc = evalrun.main(
        ["--subset", "2", "--backend", "fake", "--out", str(out)]
    )
    assert rc == 0
    assert out.is_file()

    doc = json.loads(out.read_text())
    assert set(doc) == {"meta", "runs", "summary"}

    # BOTH baseline frameworks appear as summary groups (persona axis is [None]).
    summary = doc["summary"]
    assert "langgraph" in summary
    assert "crewai" in summary

    for group in ("langgraph", "crewai"):
        m = summary[group]
        # --subset 2 → exactly 2 runs per framework.
        assert m["n"] == 2
        # Every metric is numeric (computed, not None/hardcoded-string).
        for key in (
            "gate_rate", "cited_expected_rate", "mean_answer_contains",
            "judge_pass_rate", "mean_judge_score", "mean_latency_s",
            "mean_tokens_in", "mean_tokens_out", "mean_iterations",
        ):
            assert isinstance(m[key], (int, float)), key
            assert 0.0 <= m["gate_rate"] <= 1.0

    # Per-run rows are present and tie back to real AgentResult fields.
    assert len(doc["runs"]) == 4  # 2 frameworks x 2 questions
    for r in doc["runs"]:
        assert r["framework"] in {"langgraph", "crewai"}
        assert r["terminated_by"] in {t.value for t in TerminatedBy}
        assert isinstance(r["tokens_in"], int)
        assert isinstance(r["judge_score"], (int, float))

    # Honesty: FakeLLM run is flagged synthetic with a reason; no persona axis.
    meta = doc["meta"]
    assert meta["backend"] == "fake"
    assert meta["synthetic"] is True
    assert meta["synthetic_reason"]
    assert meta["personas_used"] is False
    assert meta["n_runs"] == 4


def test_evalrun_tokens_flow_from_real_results(tmp_path):
    """Token metrics in the summary come from real AgentResults (FakeLLM ints)."""
    out = tmp_path / "results.json"
    evalrun.main(["--subset", "1", "--backend", "fake", "--out", str(out)])
    doc = json.loads(out.read_text())
    # FakeLLM reports fixed positive token counts; the mean must reflect them.
    for group in ("langgraph", "crewai"):
        assert doc["summary"][group]["mean_tokens_in"] > 0
        assert doc["summary"][group]["mean_tokens_out"] > 0
