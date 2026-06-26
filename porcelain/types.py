"""
porcelain.types — canonical pydantic v2 data models for agent-bench.

This module is the stable public surface of the agent-bench platform.
Adapters (LangGraph, CrewAI) consume these types for input configuration and
produce them as output.  The evalkit and report layers consume them as input.
No framework-specific imports belong here — this module must remain
import-light so tests and type-checkers load it in milliseconds.

Design contract
---------------
* AgentSpec   — write-once declaration an app author (or YAML spec file) provides.
* AgentResult — what every adapter returns, regardless of framework.
* TerminationPolicy — declarative stop conditions; adapters translate these into
  framework-native guards so callers never reason about framework internals.
* Citation, TerminatedBy — value types shared by the above.

Defaults in this file are *provisional*.  Phase 4 will annotate each default
with eval provenance (the benchmark run that justified it).
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# TerminatedBy
# ---------------------------------------------------------------------------

class TerminatedBy(str, enum.Enum):
    """
    Reason the agent loop stopped.

    Using a str-enum (not a plain Literal) so values survive JSON
    serialisation round-trips without a custom encoder.  Adapters MUST set
    this field; "error" is the safe fallback when nothing else applies.

    Values
    ------
    gate       — the success_gate fired; the agent produced an acceptable answer.
    max_iter   — the iteration cap was reached before the gate fired.
    timeout    — wall-clock budget expired before the gate fired.
    error      — an unrecoverable exception was raised inside the adapter.
    """

    GATE = "gate"
    MAX_ITER = "max_iter"
    TIMEOUT = "timeout"
    ERROR = "error"


# ---------------------------------------------------------------------------
# TerminationPolicy
# ---------------------------------------------------------------------------

class TerminationPolicy(BaseModel):
    """
    Declarative stop conditions applied uniformly across all adapters.

    The two frameworks (LangGraph, CrewAI) expose termination through different
    APIs (recursive-graph recursion limits vs. crew max_iter / process hooks).
    By standardising stop conditions here, callers write one policy block and
    each adapter translates it into the framework's native mechanism.

    Provenance of the defaults
    --------------------------
    Each default below is annotated with a pointer to ``report/results.md``,
    the rendered output of the measurement spine.  This wiring is the POINT of
    the platform: a default is justified by the run that measured it, not by
    taste.  HONESTY CAVEAT — the numbers in ``report/results.md`` are currently
    SYNTHETIC (FakeLLM backend).  The provenance comments therefore DEMONSTRATE
    the measure-then-standardize workflow; they are NOT tuned-on-a-real-model
    production values.  Swapping a real client in behind the ``LLMClient`` seam
    (porcelain/llm.py) and re-running ``evalkit.run`` + ``report.build`` is what
    turns these into measured defaults.  Do not read the specific numbers as a
    benchmark result.
    """

    max_iterations: int = Field(
        default=6,
        ge=1,
        description=(
            "Hard cap on agent reasoning/tool-call loops before the adapter "
            "forces termination with TerminatedBy.MAX_ITER.  "
            "Default: 6.  PROVENANCE: see report/results.md (mean_iterations per "
            "group) — the run that this measure-then-standardize workflow reads "
            "from.  Numbers there are synthetic (FakeLLM), so 6 is a workflow "
            "DEMONSTRATION, not a real-model-tuned value."
        ),
    )

    timeout_s: float = Field(
        default=30.0,
        gt=0.0,
        description=(
            "Wall-clock budget in seconds for a single question.  "
            "Adapters are responsible for enforcing this via asyncio.wait_for "
            "or an equivalent mechanism; the porcelain layer does not enforce it "
            "directly.  Default: 30 s.  PROVENANCE: see report/results.md "
            "(mean_latency_s per group).  Synthetic numbers today → this is a "
            "workflow DEMONSTRATION, not a tuned production value."
        ),
    )

    max_retries: int = Field(
        default=2,
        ge=0,
        description=(
            "Number of times the adapter may retry on a *transient* failure "
            "(network timeout, rate-limit 429, etc.) before surfacing the error "
            "and setting TerminatedBy.ERROR.  Does not apply to logic errors or "
            "malformed responses.  Default: 2.  PROVENANCE: report/results.md "
            "(error/termination rows).  Synthetic today → workflow "
            "DEMONSTRATION, not a real-model-tuned value."
        ),
    )

    success_gate: Literal["cites_corpus"] = Field(
        default="cites_corpus",
        description=(
            "Name of the gate that defines a successful answer.  "
            "The adapter checks this condition after each iteration; when it "
            "passes, termination reason is set to TerminatedBy.GATE.  "
            "Currently one value is supported: 'cites_corpus' — the answer "
            "must cite at least one document from the loaded corpus (checked "
            "via AgentResult.cites_corpus).  PROVENANCE: report/results.md "
            "(gate_rate / cited_expected_rate per group) is where this gate's "
            "effect is measured; the current numbers are synthetic (FakeLLM), "
            "so this default DEMONSTRATES the workflow rather than being a "
            "real-model-tuned choice.  Additional gates ('grounded', "
            "'has_answer', etc.) are reserved for future phases; adding one "
            "will require widening this Literal and registering a checker in "
            "the adapter base class."
        ),
    )


# ---------------------------------------------------------------------------
# AgentSpec
# ---------------------------------------------------------------------------

class AgentSpec(BaseModel):
    """
    Write-once declaration an app author provides per agent under test.

    One AgentSpec fully describes a single agent variant: which framework
    adapter to run, where its corpus lives, which model to call, and what
    termination policy to enforce.  Adapters receive an AgentSpec at
    construction time and must not mutate it.

    Load from YAML with AgentSpec.from_yaml(path).
    """

    name: str = Field(
        description=(
            "Human-readable identifier for this agent variant, used as a key "
            "in benchmark reports (e.g. 'langgraph-baseline', 'crewai-v2')."
        ),
    )

    framework: Literal["langgraph", "crewai"] = Field(
        description=(
            "Which adapter runs this agent.  This is the ONE line that swaps "
            "frameworks: change 'langgraph' to 'crewai' and the evalkit will "
            "instantiate a different adapter while keeping everything else "
            "(corpus, model, termination policy) identical."
        ),
    )

    corpus: str = Field(
        default="corpus",
        description=(
            "Path to the document corpus directory, relative to the repo root.  "
            "Adapters load documents from this directory at startup; the "
            "retriever index is built from whatever files are present.  "
            "Default: 'corpus' (the checked-in sample corpus)."
        ),
    )

    model: str = Field(
        default="claude-3-5-sonnet-latest",
        # ^^^ Anthropic Claude model id.  "claude-3-5-sonnet-latest" resolves to
        # the current Sonnet 3.5 release and is safe to swap for any claude-* id.
        # See https://docs.anthropic.com/en/docs/about-claude/models for the
        # current model list.  Phase 4 may parameterise this per eval run.
        description=(
            "Anthropic Claude model id passed to the adapter's LLM client.  "
            "Defaults to 'claude-3-5-sonnet-latest' (swappable to any claude-* "
            "id supported by the Anthropic API).  Always use a Claude model here "
            "— the adapters are wired to the Anthropic SDK and do not support "
            "other providers without modification."
        ),
    )

    tools: list[str] = Field(
        default_factory=list,
        description=(
            "Named tools available to the agent beyond implicit retrieval.  "
            "Empty in v1 — retrieval is always injected by the adapter and does "
            "not appear here.  Reserved for future tools such as 'calculator' or "
            "'web_search'.  Each string must match a tool name registered in the "
            "adapter's tool registry."
        ),
    )

    persona: str | None = Field(
        default=None,
        description=(
            "Optional persona slug selecting a CL4R1T4S-style system prompt at "
            "prompts/personas/<slug>.md.  When set and a real (claude_code) "
            "backend is used, the runner loads that file and prepends it as the "
            "persona prompt, making Claude *act like* the named product (labelled "
            "honestly as 'claude-as-<slug>', NOT a real GPT/Gemini call).  None "
            "(the default) means no persona, so existing specs load unchanged."
        ),
    )

    termination: TerminationPolicy = Field(
        default_factory=TerminationPolicy,
        description=(
            "Stop conditions the adapter must enforce.  Defaults to "
            "TerminationPolicy() which uses all provisional defaults.  Override "
            "individual fields in YAML to tune per-agent behaviour."
        ),
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AgentSpec":
        """
        Load an AgentSpec from a YAML file.

        The YAML keys must match AgentSpec field names.  Nested objects
        (e.g. termination) are loaded as plain dicts and coerced by pydantic.

        Example YAML
        ------------
        name: langgraph-baseline
        framework: langgraph
        corpus: corpus
        model: claude-3-5-sonnet-latest
        termination:
          max_iterations: 8
          timeout_s: 45.0

        Parameters
        ----------
        path : str or Path
            Path to the YAML file (absolute or relative to cwd).

        Returns
        -------
        AgentSpec
        """
        raw: dict[str, Any] = yaml.safe_load(Path(path).read_text())
        return cls.model_validate(raw)


# ---------------------------------------------------------------------------
# Citation
# ---------------------------------------------------------------------------

class Citation(BaseModel):
    """
    A single document reference inside an AgentResult.

    Adapters extract citations from the agent's final answer or tool-call
    history and populate this list.  The evalkit uses the doc_id set to run
    AgentResult.cites_corpus.
    """

    doc_id: str = Field(
        description=(
            "Stable identifier for the cited document.  Must match a key in "
            "the corpus index (typically the filename without extension, or "
            "whatever the retriever uses as its document id)."
        ),
    )

    snippet: str | None = Field(
        default=None,
        description=(
            "Optional verbatim excerpt from the cited document that the agent "
            "surfaced in its answer.  Useful for qualitative review but not "
            "required for gate evaluation."
        ),
    )


# ---------------------------------------------------------------------------
# AgentResult
# ---------------------------------------------------------------------------

class AgentResult(BaseModel):
    """
    Uniform result returned by every adapter after running a single question.

    All fields have safe defaults so adapters can build a result incrementally
    (e.g. set answer first, then fill latency after timing).  The terminated_by
    field has no default and MUST be set explicitly — this is intentional: an
    adapter that forgets to set it will get a validation error at construction
    time, not a silent None at eval time.
    """

    answer: str = Field(
        description="The agent's final natural-language answer to the question.",
    )

    citations: list[Citation] = Field(
        default_factory=list,
        description=(
            "Documents the agent cited in its answer.  May be empty if the "
            "agent produced an answer without grounding (which will cause "
            "cites_corpus to return False and typically set terminated_by to "
            "TerminatedBy.MAX_ITER rather than TerminatedBy.GATE)."
        ),
    )

    iterations: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of reasoning/tool-call loops the agent completed before "
            "termination.  Used by the evalkit to compare framework efficiency."
        ),
    )

    latency_s: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Wall-clock time in seconds from question submission to result "
            "return, as measured by the adapter.  Does not include corpus "
            "indexing time (which is measured separately at startup)."
        ),
    )

    tokens_in: int = Field(
        default=0,
        ge=0,
        description=(
            "Total input tokens consumed across all LLM calls for this "
            "question, as reported by the Anthropic API usage field.  "
            "Zero if the adapter does not track token usage."
        ),
    )

    tokens_out: int = Field(
        default=0,
        ge=0,
        description=(
            "Total output tokens generated across all LLM calls for this "
            "question, as reported by the Anthropic API usage field.  "
            "Zero if the adapter does not track token usage."
        ),
    )

    terminated_by: TerminatedBy = Field(
        description=(
            "Why the agent loop stopped.  Adapters MUST set this explicitly; "
            "there is no default.  Use TerminatedBy.GATE for a successful "
            "answer, TerminatedBy.ERROR when an exception was caught, and the "
            "appropriate limit value otherwise."
        ),
    )

    error: str | None = Field(
        default=None,
        description=(
            "Human-readable error message when terminated_by is "
            "TerminatedBy.ERROR.  Should be the str() of the caught exception "
            "plus enough context for debugging.  None on successful runs."
        ),
    )

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def cites_corpus(self, valid_doc_ids: set[str]) -> bool:
        """
        Return True iff at least one citation's doc_id is in valid_doc_ids.

        Used by the 'cites_corpus' success gate in TerminationPolicy and by
        the evalkit when scoring AgentResult objects.

        Parameters
        ----------
        valid_doc_ids : set[str]
            The set of doc_ids present in the loaded corpus index.  Adapters
            and the evalkit build this set at corpus-load time.

        Returns
        -------
        bool
        """
        return any(c.doc_id in valid_doc_ids for c in self.citations)
