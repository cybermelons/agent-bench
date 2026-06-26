"""
porcelain.runner — the one entry point that turns a spec + question into a result.

``run_spec`` is the thin orchestration seam:

    spec (path or AgentSpec)
        │  AgentSpec.from_yaml if a path
        ▼
    CorpusRetriever(spec.corpus)
        │
        ▼
    get_adapter(spec.framework)(spec, retriever, llm)
        │  llm = injected (tests) or FakeLLM/RealAnthropicClient by key
        ▼
    adapter.run(question)  ──▶  AgentResult

Termination is honored uniformly because ``timeout_s`` and ``max_iterations``
live on ``spec.termination`` and are read by the shared base-class guard inside
``adapter.run`` — the runner just passes the spec through, so both frameworks
obey the same contract.

LLM selection
-------------
* an explicit ``llm=`` argument always wins (this is how tests inject FakeLLM);
* otherwise, if ``ANTHROPIC_API_KEY`` is set, a :class:`RealAnthropicClient`;
* otherwise a :class:`FakeLLM` so an offline, no-key run still produces a
  deterministic result instead of crashing.
"""

from __future__ import annotations

import os
from pathlib import Path

from adapters import get_adapter
from porcelain.llm import FakeLLM, LLMClient, RealAnthropicClient
from porcelain.retrieval import CorpusRetriever
from porcelain.types import AgentResult, AgentSpec


def _resolve_spec(spec_or_path: AgentSpec | str | Path) -> AgentSpec:
    """Coerce a path or an AgentSpec into an AgentSpec."""
    if isinstance(spec_or_path, AgentSpec):
        return spec_or_path
    return AgentSpec.from_yaml(spec_or_path)


def _default_llm() -> LLMClient:
    """Pick a default LLM client: real if a key is present, else the fake."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return RealAnthropicClient()
    return FakeLLM()


def run_spec(
    spec_or_path: AgentSpec | str | Path,
    question: str,
    llm: LLMClient | None = None,
) -> AgentResult:
    """
    Load a spec, build the adapter, and run a single *question*.

    Parameters
    ----------
    spec_or_path : AgentSpec | str | Path
        An ``AgentSpec`` instance, or a path to a YAML spec file.
    question : str
        The natural-language question to answer.
    llm : LLMClient | None
        Optional LLM client.  Injected directly when provided (tests pass a
        ``FakeLLM`` here); otherwise a :class:`RealAnthropicClient` is used when
        ``ANTHROPIC_API_KEY`` is set, falling back to :class:`FakeLLM` offline.

    Returns
    -------
    AgentResult
    """
    spec = _resolve_spec(spec_or_path)
    retriever = CorpusRetriever(spec.corpus)
    client: LLMClient = llm if llm is not None else _default_llm()

    adapter_cls = get_adapter(spec.framework)
    adapter = adapter_cls(spec, retriever, client)
    return adapter.run(question)
