"""
evalkit.run — the measurement spine harness + CLI.

What it does
------------
Loads the golden dataset (corpus/golden.yaml) and a list of specs (default: both
baseline specs), then for each (spec x question) [x persona]:

1. calls ``porcelain.runner.run_spec`` to get a REAL ``AgentResult``;
2. scores it with the deterministic checks (``citation_valid``,
   ``answer_contains_score``) and the LLM-as-judge (``judge_correctness``), all
   through the same ``LLMClient`` seam so the whole thing runs offline/keyless
   under ``FakeLLM``;
3. records a per-run row.

It then aggregates per group (framework, or ``claude-as-<persona>`` when a
persona axis is used) into SLA-shaped metrics and writes ``evalkit/results.json``
as ``{meta, runs, summary}``.

Honesty
-------
Every metric is computed from a real ``AgentResult`` — nothing is hardcoded.
``meta`` records the backend (fake|claude_code|anthropic), the model id, whether
personas were used, and a ``synthetic`` flag that is True whenever the FakeLLM
backend or a claude-as-persona axis produced the numbers.

CLI
---
``python -m evalkit.run [--subset N] [--backend fake|claude_code|anthropic]
[--personas a,b] [--out evalkit/results.json] [--model MODEL]``

Default backend is ``fake`` (keyless).  ``--subset N`` limits to the first N
golden questions.  ``--personas`` is opt-in; without it the persona axis is
``[None]`` and groups are plain framework names.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import yaml

from evalkit.judge import answer_contains_score, citation_valid, judge_correctness
from porcelain.llm import ClaudeCodeClient, FakeLLM, RealAnthropicClient
from porcelain.retrieval import CorpusRetriever
from porcelain.runner import load_persona, run_spec
from porcelain.types import AgentSpec, TerminatedBy

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GOLDEN_PATH = _REPO_ROOT / "corpus" / "golden.yaml"
_DEFAULT_SPECS = (
    _REPO_ROOT / "specs" / "langgraph-baseline.yaml",
    _REPO_ROOT / "specs" / "crewai-baseline.yaml",
)
_DEFAULT_OUT = _REPO_ROOT / "evalkit" / "results.json"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_golden(subset: int | None = None) -> list[dict]:
    """Load the golden question list, optionally truncated to the first *subset*."""
    raw = yaml.safe_load(_GOLDEN_PATH.read_text())
    questions = raw["questions"]
    if subset is not None:
        questions = questions[:subset]
    return questions


def _load_specs(spec_paths: list[str | Path] | None) -> list[AgentSpec]:
    """Resolve spec paths (default: both baselines) into AgentSpec objects."""
    paths = list(spec_paths) if spec_paths else list(_DEFAULT_SPECS)
    return [AgentSpec.from_yaml(p) for p in paths]


# ---------------------------------------------------------------------------
# Backend / LLM construction (mirrors runner._build_llm, but persona-aware here
# because the eval drives the persona axis explicitly, not via spec.persona)
# ---------------------------------------------------------------------------

def _build_llm(backend: str, persona: str | None):
    """
    Construct the LLM client used for BOTH the agent run and the judge.

    Using one client for both keeps a run internally consistent: a FakeLLM run
    is judged by FakeLLM; a claude_code/persona run is judged by the same
    persona-driven client.  ``persona`` is opt-in and only meaningful for the
    real ``claude_code`` backend.
    """
    if backend == "fake":
        return FakeLLM()
    if backend == "anthropic":
        return RealAnthropicClient()
    if backend == "claude_code":
        return ClaudeCodeClient(persona_prompt=load_persona(persona))
    raise ValueError(
        f"unknown backend {backend!r}; expected 'fake', 'anthropic', "
        f"or 'claude_code'"
    )


def _group_label(framework: str, persona: str | None) -> str:
    """Group key: framework name, or ``claude-as-<persona>`` when persona set."""
    if persona is None:
        return framework
    return f"claude-as-{persona}"


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def evaluate(
    specs: list[AgentSpec],
    questions: list[dict],
    backend: str = "fake",
    personas: list[str | None] | None = None,
    model: str | None = None,
) -> dict:
    """
    Run every (spec x question) [x persona] and score each result.

    Returns the full results document ``{meta, runs, summary}``.  Every numeric
    field in ``runs`` and ``summary`` is computed from a real ``AgentResult``;
    nothing is hardcoded.

    Parameters
    ----------
    specs : list[AgentSpec]
        Specs to run (default caller passes both baselines).
    questions : list[dict]
        Golden entries (each has id/question/expected_doc/rubric/answer_contains).
    backend : {"fake", "anthropic", "claude_code"}
        Which LLM client to build for the agent run AND the judge.
    personas : list[str | None] | None
        Persona axis.  Default ``[None]`` (no persona; groups are framework
        names).  Personas other than None require the ``claude_code`` backend.
    model : str | None
        Judge model id.  Defaults to each spec's ``model`` when None.

    Returns
    -------
    dict
    """
    if personas is None:
        personas = [None]

    # Retriever cache keyed by corpus path: the corpus doc_id set is needed for
    # citation validity and is identical for specs sharing a corpus.
    retriever_cache: dict[str, CorpusRetriever] = {}

    def doc_ids_for(corpus: str) -> set[str]:
        if corpus not in retriever_cache:
            retriever_cache[corpus] = CorpusRetriever(corpus)
        return retriever_cache[corpus].doc_ids

    runs: list[dict] = []

    for persona in personas:
        llm = _build_llm(backend, persona)
        for spec in specs:
            valid_doc_ids = doc_ids_for(spec.corpus)
            judge_model = model or spec.model
            group = _group_label(spec.framework, persona)
            for q in questions:
                result = run_spec(spec, q["question"], llm=llm, backend=backend)

                cite = citation_valid(result, valid_doc_ids, q["expected_doc"])
                contains = answer_contains_score(
                    result.answer, q.get("answer_contains", [])
                )
                grade = judge_correctness(
                    question=q["question"],
                    rubric=q["rubric"],
                    answer=result.answer,
                    llm=llm,
                    model=judge_model,
                )

                runs.append(
                    {
                        "framework": spec.framework,
                        "group": group,
                        "persona": persona,
                        "question_id": q["id"],
                        "terminated_by": _terminated_value(result.terminated_by),
                        "iterations": result.iterations,
                        "latency_s": result.latency_s,
                        "tokens_in": result.tokens_in,
                        "tokens_out": result.tokens_out,
                        "cited_any": cite["cited_any"],
                        "cited_expected": cite["cited_expected"],
                        "answer_contains_score": contains,
                        "judge_score": grade["score"],
                        "judge_verdict": grade["verdict"],
                        "judge_reason": grade["reason"],
                        "error": result.error,
                    }
                )

    meta = _build_meta(
        backend=backend,
        personas=personas,
        specs=specs,
        model=model,
        n_questions=len(questions),
        n_runs=len(runs),
    )
    # Stamp each summary group with the synthetic/backend flags so the honesty
    # caveat survives even when the summary block is read or screenshotted in
    # isolation (a common dashboard pattern) — not only at the top-level meta.
    summary = _aggregate(runs, synthetic=meta["synthetic"], backend=meta["backend"])
    return {"meta": meta, "runs": runs, "summary": summary}


def _terminated_value(terminated_by: Any) -> str:
    """Normalise terminated_by (enum or str) to its string value for JSON."""
    if isinstance(terminated_by, TerminatedBy):
        return terminated_by.value
    return str(terminated_by)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _mean(values: list[float]) -> float:
    """Mean of *values*, or 0.0 for an empty list."""
    return statistics.fmean(values) if values else 0.0


def _aggregate(runs: list[dict], synthetic: bool, backend: str) -> dict:
    """
    Aggregate per-run rows into per-group SLA metrics.

    Each group is a framework name (or ``claude-as-<persona>``).  All rates and
    means are computed from the recorded run rows — there are no hardcoded
    numbers anywhere in this function.

    ``synthetic`` and ``backend`` are stamped onto every group so the honesty
    caveat travels with the numbers: under FakeLLM the token/latency means are
    not real-model measurements, and a reader who lifts a single summary group
    out of the document must still see that.
    """
    groups: dict[str, list[dict]] = {}
    for r in runs:
        groups.setdefault(r["group"], []).append(r)

    summary: dict[str, dict] = {}
    for group, rows in groups.items():
        n = len(rows)
        gate = sum(1 for r in rows if r["terminated_by"] == TerminatedBy.GATE.value)
        cited_expected = sum(1 for r in rows if r["cited_expected"])
        judge_pass = sum(1 for r in rows if r["judge_verdict"] == "pass")
        summary[group] = {
            "synthetic": synthetic,
            "backend": backend,
            "n": n,
            "gate_rate": gate / n if n else 0.0,
            "cited_expected_rate": cited_expected / n if n else 0.0,
            "mean_answer_contains": _mean([r["answer_contains_score"] for r in rows]),
            "judge_pass_rate": judge_pass / n if n else 0.0,
            "mean_judge_score": _mean([r["judge_score"] for r in rows]),
            "mean_latency_s": _mean([r["latency_s"] for r in rows]),
            "mean_tokens_in": _mean([r["tokens_in"] for r in rows]),
            "mean_tokens_out": _mean([r["tokens_out"] for r in rows]),
            "mean_iterations": _mean([r["iterations"] for r in rows]),
        }
    return summary


# ---------------------------------------------------------------------------
# Meta (honesty block)
# ---------------------------------------------------------------------------

def _build_meta(
    backend: str,
    personas: list[str | None],
    specs: list[AgentSpec],
    model: str | None,
    n_questions: int,
    n_runs: int,
) -> dict:
    """
    Build the meta/honesty block recorded at the top of results.json.

    ``synthetic`` is True whenever the numbers were NOT produced by a real model
    answering as itself: that is, whenever the FakeLLM backend is used OR a
    claude-as-persona axis is active.  This is the load-bearing honesty flag —
    a synthetic run must never be presentable as a real-model benchmark.
    """
    used_personas = any(p is not None for p in personas)
    synthetic = backend == "fake" or used_personas

    if synthetic and backend == "fake":
        synthetic_reason = "FakeLLM backend (offline deterministic, no real model)"
    elif synthetic and used_personas:
        synthetic_reason = (
            "claude-as-persona axis (Claude acting as another product, "
            "not a real call to that product)"
        )
    else:
        synthetic_reason = None

    return {
        "backend": backend,
        "model": model or (specs[0].model if specs else None),
        "personas_used": used_personas,
        "personas": [p for p in personas],
        "frameworks": sorted({s.framework for s in specs}),
        "specs": [s.name for s in specs],
        "n_questions": n_questions,
        "n_runs": n_runs,
        "synthetic": synthetic,
        "synthetic_reason": synthetic_reason,
    }


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write_results(doc: dict, out_path: str | Path) -> Path:
    """Serialise *doc* to *out_path* as pretty JSON; return the path written."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_personas(raw: str | None) -> list[str | None]:
    """Parse ``--personas a,b`` into a list; absent → ``[None]`` (no persona)."""
    if not raw:
        return [None]
    return [p.strip() for p in raw.split(",") if p.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evalkit.run",
        description="Run the golden dataset through both adapters and score it.",
    )
    parser.add_argument(
        "--subset", type=int, default=None,
        help="Limit to the first N golden questions (default: all).",
    )
    parser.add_argument(
        "--backend", choices=("fake", "claude_code", "anthropic"), default="fake",
        help="LLM backend for the agent run AND the judge (default: fake).",
    )
    parser.add_argument(
        "--personas", type=str, default=None,
        help="Comma-separated persona slugs (opt-in; requires claude_code).",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Override the judge model id (default: each spec's model).",
    )
    parser.add_argument(
        "--out", type=str, default=str(_DEFAULT_OUT),
        help="Output path for results.json (default: evalkit/results.json).",
    )
    args = parser.parse_args(argv)

    personas = _parse_personas(args.personas)
    specs = _load_specs(None)
    questions = load_golden(subset=args.subset)

    doc = evaluate(
        specs=specs,
        questions=questions,
        backend=args.backend,
        personas=personas,
        model=args.model,
    )
    out = write_results(doc, args.out)

    meta = doc["meta"]
    print(
        f"Wrote {out} — {meta['n_runs']} runs across "
        f"{len(doc['summary'])} group(s) "
        f"(backend={meta['backend']}, synthetic={meta['synthetic']})."
    )
    for group, m in doc["summary"].items():
        print(
            f"  {group}: n={m['n']} gate={m['gate_rate']:.2f} "
            f"cited_expected={m['cited_expected_rate']:.2f} "
            f"contains={m['mean_answer_contains']:.2f} "
            f"judge_pass={m['judge_pass_rate']:.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
