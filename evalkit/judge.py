"""
evalkit.judge — correctness scoring for agent-bench eval runs.

Three scorers live here, in increasing cost order:

1. ``citation_valid``        — deterministic, no model.  Did the agent cite any
   real corpus doc, and specifically the expected one?
2. ``answer_contains_score`` — deterministic, no model.  Fraction of the golden
   ``answer_contains`` required substrings present in the answer.
3. ``judge_correctness``     — LLM-as-judge.  Grades the answer against the
   golden rubric *through the same ``porcelain.llm.LLMClient`` seam* the
   adapters use, so it runs keyless/offline under :class:`FakeLLM` and
   deterministically.

LLM-judge seam + determinism
----------------------------
``judge_correctness`` calls ``llm.complete(...)`` exactly like an adapter would.
It asks the judge to answer with a single strict-JSON line
(``{"score": <0..1>, "verdict": "pass"|"fail", "reason": "..."}``) and parses
that robustly.  When the JSON cannot be found (e.g. under FakeLLM, whose canned
text is not JSON), it falls back to a deterministic keyword scan over the
answer + the judge's text, so the same inputs always yield the same grade with
no network and no key.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # import-light: only for type hints, never at runtime cost
    from porcelain.llm import LLMClient
    from porcelain.types import AgentResult


# ---------------------------------------------------------------------------
# Deterministic scorer #1: citation validity (no model)
# ---------------------------------------------------------------------------

def citation_valid(
    result: "AgentResult",
    valid_doc_ids: set[str],
    expected_doc: str,
) -> dict:
    """
    Deterministically check an AgentResult's citations against the corpus.

    Parameters
    ----------
    result : AgentResult
        The result whose ``citations`` list is inspected.
    valid_doc_ids : set[str]
        The set of doc_ids present in the loaded corpus (``retriever.doc_ids``).
    expected_doc : str
        The golden ``expected_doc`` for this question.

    Returns
    -------
    dict
        ``{"cited_any": bool, "cited_expected": bool}`` where:
        * ``cited_any``      — at least one citation is a real corpus doc, and
        * ``cited_expected`` — the specific expected doc was cited.
    """
    cited_ids = {c.doc_id for c in result.citations}
    return {
        "cited_any": bool(cited_ids & valid_doc_ids),
        "cited_expected": expected_doc in cited_ids,
    }


# ---------------------------------------------------------------------------
# Deterministic scorer #2: answer_contains coverage (no model)
# ---------------------------------------------------------------------------

def answer_contains_score(answer: str, answer_contains: Iterable[str]) -> float:
    """
    Fraction of required substrings present in *answer* (case-insensitive).

    A cheap, model-free correctness proxy: the golden dataset lists the literal
    facts (``answer_contains``) a correct answer must surface.  Returns the
    fraction present in ``[0.0, 1.0]``; an empty requirement list scores 1.0
    (nothing required → trivially satisfied).

    Parameters
    ----------
    answer : str
        The agent's answer text.
    answer_contains : Iterable[str]
        Required substrings from the golden entry.

    Returns
    -------
    float
        ``present / total`` in ``[0.0, 1.0]``.
    """
    required = [s for s in answer_contains]
    if not required:
        return 1.0
    haystack = answer.lower()
    present = sum(1 for s in required if s.lower() in haystack)
    return present / len(required)


# ---------------------------------------------------------------------------
# LLM-as-judge scorer #3: correctness against the rubric
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = (
    "You are a strict grading judge for a retrieval-augmented Q&A agent. "
    "You are given a QUESTION, a RUBRIC describing what a correct answer must "
    "state, and the agent's ANSWER. Decide whether the answer satisfies the "
    "rubric. Reply with EXACTLY ONE LINE of strict JSON and nothing else, of "
    'the form: {"score": <number between 0 and 1>, "verdict": "pass" or '
    '"fail", "reason": "<one short sentence>"}. A "pass" requires score >= '
    "0.5. Do not include any text before or after the JSON line."
)


def _build_judge_prompt(question: str, rubric: str, answer: str) -> list[dict]:
    """Compose the user message for the judge in Anthropic message shape."""
    user = (
        f"QUESTION:\n{question}\n\n"
        f"RUBRIC (what a correct answer must state):\n{rubric}\n\n"
        f"ANSWER (from the agent under test):\n{answer}\n\n"
        "Grade the ANSWER against the RUBRIC now. Respond with the single "
        "strict-JSON line described in your instructions."
    )
    return [{"role": "user", "content": user}]


# Matches the first {...} JSON object on its own (greedy-safe, single object).
_JSON_OBJ_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _parse_judge_json(text: str) -> dict | None:
    """
    Robustly extract ``{score, verdict, reason}`` from the judge's text.

    Tries a direct ``json.loads`` first, then the first ``{...}`` substring.
    Returns a normalised dict, or None when no usable JSON object is found
    (caller then falls back to the deterministic keyword scan).
    """
    candidates: list[str] = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)
    m = _JSON_OBJ_RE.search(text)
    if m:
        candidates.append(m.group(0))

    for cand in candidates:
        try:
            payload = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        if "score" not in payload and "verdict" not in payload:
            continue
        return _normalise_grade(payload)
    return None


def _normalise_grade(payload: dict) -> dict:
    """Coerce a parsed judge dict into the canonical grade shape."""
    raw_score = payload.get("score")
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = None

    verdict = payload.get("verdict")
    verdict = verdict.lower().strip() if isinstance(verdict, str) else None
    if verdict not in {"pass", "fail"}:
        verdict = None

    # Reconcile score <-> verdict when one is missing or out of range.
    if score is None and verdict is not None:
        score = 1.0 if verdict == "pass" else 0.0
    if score is not None:
        score = max(0.0, min(1.0, score))
    if verdict is None and score is not None:
        verdict = "pass" if score >= 0.5 else "fail"

    if score is None:
        score = 0.0
    if verdict is None:
        verdict = "fail"

    reason = payload.get("reason")
    reason = reason if isinstance(reason, str) else ""
    return {"score": score, "verdict": verdict, "reason": reason}


# Keyword-scan fallback: deterministic, no model assumptions.  Used when the
# judge's reply is not parseable JSON (the FakeLLM case) so judge_correctness
# stays deterministic offline.
_FAIL_MARKERS = (
    "could not find",
    "no grounding",
    "cannot answer",
    "i don't know",
    "i do not know",
    "unable to",
    "insufficient",
)


def _keyword_fallback_grade(rubric: str, answer: str) -> dict:
    """
    Deterministic non-JSON fallback grade, computed from the ANSWER only.

    Strategy: an answer is graded ``fail`` if it contains an explicit
    "couldn't answer" marker; otherwise it is graded by keyword overlap between
    the rubric's salient tokens and the answer.  The judge model's own text is
    deliberately NOT consulted here — under :class:`FakeLLM` that text is a
    canned non-JSON string with no grading signal, so grading on the answer
    alone keeps the fallback meaningful and deterministic.
    """
    answer_l = answer.lower()
    if any(m in answer_l for m in _FAIL_MARKERS):
        return {
            "score": 0.0,
            "verdict": "fail",
            "reason": "fallback: answer signalled it could not ground a response",
        }

    # Salient rubric tokens = alphanumeric words length >= 4, deduped.
    rubric_tokens = {
        t for t in re.split(r"[^a-z0-9]+", rubric.lower()) if len(t) >= 4
    }
    if not rubric_tokens:
        # Nothing to compare against; treat a non-empty answer as a weak pass.
        passed = bool(answer.strip())
        return {
            "score": 1.0 if passed else 0.0,
            "verdict": "pass" if passed else "fail",
            "reason": "fallback: empty rubric, graded on answer presence",
        }

    overlap = sum(1 for t in rubric_tokens if t in answer_l)
    score = overlap / len(rubric_tokens)
    score = max(0.0, min(1.0, score))
    return {
        "score": score,
        "verdict": "pass" if score >= 0.5 else "fail",
        "reason": (
            f"fallback: {overlap}/{len(rubric_tokens)} rubric keywords present "
            "(judge reply was not JSON)"
        ),
    }


def judge_correctness(
    question: str,
    rubric: str,
    answer: str,
    llm: "LLMClient",
    model: str,
) -> dict:
    """
    Grade *answer* against *rubric* using an LLM-as-judge through *llm*.

    The judge is called via the same ``LLMClient.complete`` seam the adapters
    use, so this runs offline/keyless under :class:`FakeLLM` and against a real
    model under :class:`RealAnthropicClient` / :class:`ClaudeCodeClient`.

    Parsing is robust: a strict-JSON line is preferred, but when the reply is
    not JSON (the FakeLLM case) a deterministic keyword scan over the rubric and
    answer is used instead — so the same inputs always produce the same grade.

    Parameters
    ----------
    question, rubric, answer : str
        The golden question, its correctness rubric, and the agent's answer.
    llm : LLMClient
        The injected client; ``llm.complete`` is called once.
    model : str
        Model id passed through to ``complete`` (ignored by FakeLLM).

    Returns
    -------
    dict
        ``{"score": float in [0,1], "verdict": "pass"|"fail", "reason": str}``.
    """
    messages = _build_judge_prompt(question, rubric, answer)
    resp = llm.complete(system=_JUDGE_SYSTEM, messages=messages, model=model)

    parsed = _parse_judge_json(resp.text)
    if parsed is not None:
        return parsed
    return _keyword_fallback_grade(rubric, answer)
