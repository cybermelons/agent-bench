"""
evalkit — the measurement spine of agent-bench.

This package runs the golden dataset (corpus/golden.yaml) through BOTH framework
adapters via porcelain.runner.run_spec, scores each AgentResult with a mix of
deterministic checks and an LLM-as-judge correctness grade (all through the same
porcelain.llm.LLMClient seam so it is keyless/offline-testable with FakeLLM),
aggregates per-framework SLA metrics, and writes evalkit/results.json.

Honesty contract
----------------
Every metric in results.json is COMPUTED from a real AgentResult produced by an
adapter — nothing is hardcoded.  When the FakeLLM backend or a claude-as-persona
axis is used, results.json's meta block carries a ``synthetic: true`` flag and
records exactly which backend/model/persona produced the numbers, so a synthetic
run can never be mistaken for a real-model benchmark.

Public surface
--------------
* judge.judge_correctness     — LLM-as-judge correctness grade (via LLMClient).
* judge.answer_contains_score — deterministic substring coverage (no model).
* judge.citation_valid        — deterministic citation validity check.
* run.evaluate / run.main     — the harness and its CLI entry point.
"""

from __future__ import annotations

from evalkit.judge import (
    answer_contains_score,
    citation_valid,
    judge_correctness,
)

__all__ = [
    "answer_contains_score",
    "citation_valid",
    "judge_correctness",
]
