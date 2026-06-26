"""
adapters.base — abstract Adapter: the shared run() wrapper both frameworks use.

Why this lives in ``adapters/`` and not ``porcelain/``
-----------------------------------------------------
``porcelain`` is the stable, import-light public surface; ``porcelain.types``
and ``porcelain.retrieval`` both forbid framework-specific imports.  The
concrete LangGraph / CrewAI subclasses of :class:`Adapter` import
``langgraph`` / ``crewai``, so the base class belongs under ``adapters/``.
``base.py`` itself stays framework-free — it imports only ``porcelain`` and the
:class:`~porcelain.llm.LLMClient` protocol — so the dependency edge is always
``adapters -> porcelain``, never the reverse.

The contract
------------
* ``run()`` is concrete, shared, and final.  It owns timing, the uniform
  timeout + max_iterations guard, deterministic citation extraction, the
  ``cites_corpus`` gate check, and ``terminated_by`` classification — so those
  are computed *identically* regardless of framework.  That identity is the
  whole point of the porcelain comparison.
* ``_run_inner()`` is the only abstract method.  Subclasses wire the
  retrieve→generate loop in their framework (LangGraph StateGraph vs CrewAI
  crew), collect token accounting, count iterations, and return a small
  :class:`_RawRun`.  They MUST NOT compute terminated_by, latency, or
  citations — the base owns those.
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from porcelain.llm import LLMClient
from porcelain.retrieval import CorpusRetriever
from porcelain.types import AgentResult, AgentSpec, Citation, TerminatedBy


# ---------------------------------------------------------------------------
# _RawRun — the framework-specific half's output
# ---------------------------------------------------------------------------

@dataclass
class _RawRun:
    """
    The minimal, framework-agnostic result of a single ``_run_inner`` call.

    Carries only what the framework alone can know — the answer text, how many
    loops it ran, and token usage.  Everything else (citations, latency,
    terminated_by) is derived by the shared :meth:`Adapter.run`.
    """

    answer: str
    iterations: int
    tokens_in: int
    tokens_out: int


# ---------------------------------------------------------------------------
# _TimeoutSignal — internal control-flow marker for the timeout guard
# ---------------------------------------------------------------------------

class _TimeoutSignal(Exception):
    """Raised inside the shared guard when the wall-clock budget is exceeded."""


# ---------------------------------------------------------------------------
# Adapter (abstract base)
# ---------------------------------------------------------------------------

# Regex matching the exact label form the retriever emits in format_context:
#   [doc_id: oncall-policy]
# The shared system prompt instructs the model to cite using this same syntax,
# so extraction matches retriever output 1:1.
_CITATION_RE = re.compile(r"\[doc_id:\s*([A-Za-z0-9._-]+)\s*\]")


class Adapter(ABC):
    """
    Abstract base for every framework adapter.

    Subclasses implement exactly one method, :meth:`_run_inner`.  The shared
    :meth:`run` wraps it with timing, the termination contract, and citation
    extraction.
    """

    def __init__(
        self,
        spec: AgentSpec,
        retriever: CorpusRetriever,
        llm: LLMClient,
    ) -> None:
        self.spec = spec
        self.retriever = retriever
        self.llm = llm
        self.valid_doc_ids: set[str] = retriever.doc_ids

    # ------------------------------------------------------------------
    # Framework-specific (the ONLY thing subclasses override)
    # ------------------------------------------------------------------

    @abstractmethod
    def _run_inner(self, question: str) -> _RawRun:
        """
        Build and invoke the framework graph/crew for *question*.

        Implementations use ``self.llm`` for every model call and
        ``self.retriever`` for retrieval, and return a :class:`_RawRun`.  They
        MUST NOT compute terminated_by, latency, or citations.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared prompt template builder
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        question: str,
        context: str,
    ) -> tuple[str, list[dict]]:
        """
        Build the (system, messages) pair shared by both frameworks.

        The system prompt instructs the model to cite sources using exactly the
        ``[doc_id: X]`` syntax the retriever emits, so the deterministic
        extractor in :meth:`extract_citations` matches its output 1:1.

        Returns
        -------
        (system, messages) : tuple[str, list[dict]]
        """
        system = (
            "You are a precise question-answering assistant for Meridian "
            "Systems. Answer the user's question using ONLY the retrieved "
            "context provided below. Each passage is labelled with its source "
            "in the form [doc_id: X].\n\n"
            "You MUST cite every source you use with that exact bracket syntax "
            "— for example, write [doc_id: oncall-policy] inline immediately "
            "after the sentence it supports. Do not invent doc_ids; only cite "
            "labels that appear in the context. If the context does not contain "
            "the answer, say so and cite nothing.\n\n"
            "Retrieved context:\n"
            f"{context}"
        )
        messages = [{"role": "user", "content": question}]
        return system, messages

    # ------------------------------------------------------------------
    # Shared, deterministic citation extraction (NOT overridable)
    # ------------------------------------------------------------------

    def extract_citations(self, answer: str) -> list[Citation]:
        """
        Extract corpus citations from a model *answer*, deterministically.

        Rule:

        1. Regex-scan for ``[doc_id: X]`` labels — the same form the retriever
           emits and the system prompt instructs the model to use.
        2. De-duplicate, preserving first-seen order.
        3. Keep only ids that are actually in ``self.valid_doc_ids``.  A
           hallucinated ``[doc_id: foo]`` that isn't in the corpus is dropped,
           so ``cites_corpus`` stays honest.

        ``snippet`` is left None — ``doc_id`` is the load-bearing field.
        """
        kept: list[str] = []
        seen: set[str] = set()
        for match in _CITATION_RE.finditer(answer):
            doc_id = match.group(1)
            if doc_id in seen:
                continue
            seen.add(doc_id)
            if doc_id in self.valid_doc_ids:
                kept.append(doc_id)
        return [Citation(doc_id=doc_id, snippet=None) for doc_id in kept]

    # ------------------------------------------------------------------
    # Shared run() wrapper — CONCRETE, FINAL.  Do not override.
    # ------------------------------------------------------------------

    def run(self, question: str) -> AgentResult:
        """
        Run a single question and return a uniform :class:`AgentResult`.

        Owns (identically for both frameworks): timing, the uniform timeout +
        max_iterations guard, deterministic citation extraction, the
        cites_corpus gate, and terminated_by classification.
        """
        start = time.monotonic()
        policy = self.spec.termination

        try:
            raw = self._run_with_timeout(question, policy.timeout_s)

        except _TimeoutSignal:
            latency = time.monotonic() - start
            return AgentResult(
                answer="",
                citations=[],
                iterations=policy.max_iterations,
                latency_s=latency,
                tokens_in=0,
                tokens_out=0,
                terminated_by=TerminatedBy.TIMEOUT,
                error=f"timeout after {policy.timeout_s}s",
            )

        except Exception as exc:  # noqa: BLE001 — honest ERROR classification
            latency = time.monotonic() - start
            return AgentResult(
                answer="",
                citations=[],
                iterations=0,
                latency_s=latency,
                tokens_in=0,
                tokens_out=0,
                terminated_by=TerminatedBy.ERROR,
                error=str(exc),
            )

        # --- Success path: derive citations + termination reason ---
        citations = self.extract_citations(raw.answer)
        cited = any(c.doc_id in self.valid_doc_ids for c in citations)

        if policy.success_gate == "cites_corpus" and cited:
            terminated_by = TerminatedBy.GATE
        else:
            # Non-success: the loop ran to (or past) the cap without grounding.
            terminated_by = TerminatedBy.MAX_ITER

        latency = time.monotonic() - start
        return AgentResult(
            answer=raw.answer,
            citations=citations,
            iterations=raw.iterations,
            latency_s=latency,
            tokens_in=raw.tokens_in,
            tokens_out=raw.tokens_out,
            terminated_by=terminated_by,
            error=None,
        )

    # ------------------------------------------------------------------
    # Shared timeout guard
    # ------------------------------------------------------------------

    def _run_with_timeout(self, question: str, timeout_s: float) -> _RawRun:
        """
        Invoke ``_run_inner`` under a uniform wall-clock guard.

        Both frameworks honor the SAME timeout contract because this guard
        lives in the base class.  ``_run_inner`` is run on a worker thread; if
        it has not completed within *timeout_s*, a :class:`_TimeoutSignal` is
        raised to the caller (the worker is left to finish in the background —
        the FakeLLM is instant, and real model calls already bound their own
        per-request timeouts).
        """
        import threading

        result: dict[str, _RawRun] = {}
        error: dict[str, BaseException] = {}

        def _worker() -> None:
            try:
                result["v"] = self._run_inner(question)
            except BaseException as exc:  # noqa: BLE001 — re-raised on join
                error["e"] = exc

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join(timeout_s)

        if thread.is_alive():
            raise _TimeoutSignal

        if "e" in error:
            raise error["e"]
        return result["v"]
