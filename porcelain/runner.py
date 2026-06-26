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

Backend / LLM selection
-----------------------
* an explicit ``llm=`` argument always wins (this is how tests inject FakeLLM);
* otherwise the ``backend`` argument picks the client constructor:
    - ``"fake"`` (default) → :class:`FakeLLM`, so existing offline tests are
      unchanged and no key/binary/network is required;
    - ``"anthropic"`` → :class:`RealAnthropicClient` (reads ``ANTHROPIC_API_KEY``);
    - ``"claude_code"`` → :class:`ClaudeCodeClient`, shelling out to the real
      headless ``claude`` binary, with ``spec.persona`` (if set) loaded from
      ``prompts/personas/<slug>.md`` as the persona prompt.

The default stays ``FakeLLM`` deliberately: Phase 1 tests must not change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from adapters import get_adapter
from porcelain.llm import ClaudeCodeClient, FakeLLM, LLMClient, RealAnthropicClient
from porcelain.retrieval import CorpusRetriever
from porcelain.types import AgentResult, AgentSpec

# Personas live alongside the package at <repo_root>/prompts/personas/<slug>.md.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PERSONA_DIR = _REPO_ROOT / "prompts" / "personas"


def _resolve_spec(spec_or_path: AgentSpec | str | Path) -> AgentSpec:
    """Coerce a path or an AgentSpec into an AgentSpec."""
    if isinstance(spec_or_path, AgentSpec):
        return spec_or_path
    return AgentSpec.from_yaml(spec_or_path)


def load_persona(slug: str | None) -> str | None:
    """Load the persona prompt text for *slug*, or None.

    Returns None when *slug* is falsy.  Raises FileNotFoundError when a slug is
    given but ``prompts/personas/<slug>.md`` does not exist — a missing persona
    is a spec error, not something to silently ignore.
    """
    if not slug:
        return None
    path = _PERSONA_DIR / f"{slug}.md"
    if not path.is_file():
        raise FileNotFoundError(
            f"persona '{slug}' not found at {path} "
            f"(available: {[p.stem for p in _PERSONA_DIR.glob('*.md')]})"
        )
    return path.read_text()


def _build_llm(backend: str, spec: AgentSpec) -> LLMClient:
    """Construct the LLM client for *backend*.

    The default ('fake') keeps offline tests deterministic and key-free.
    """
    if backend == "fake":
        return FakeLLM()
    if backend == "anthropic":
        return RealAnthropicClient()
    if backend == "claude_code":
        return ClaudeCodeClient(persona_prompt=load_persona(spec.persona))
    raise ValueError(
        f"unknown backend {backend!r}; expected 'fake', 'anthropic', "
        f"or 'claude_code'"
    )


def run_spec(
    spec_or_path: AgentSpec | str | Path,
    question: str,
    llm: LLMClient | None = None,
    backend: Literal["fake", "anthropic", "claude_code"] = "fake",
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
        ``FakeLLM`` here) and always wins over ``backend``.
    backend : {"fake", "anthropic", "claude_code"}
        Which client to construct when ``llm`` is not supplied.  Defaults to
        ``"fake"`` so existing offline runs/tests are unchanged.  ``"claude_code"``
        shells out to the real headless ``claude`` binary and applies
        ``spec.persona``.

    Returns
    -------
    AgentResult
    """
    spec = _resolve_spec(spec_or_path)
    retriever = CorpusRetriever(spec.corpus)
    client: LLMClient = llm if llm is not None else _build_llm(backend, spec)

    adapter_cls = get_adapter(spec.framework)
    adapter = adapter_cls(spec, retriever, client)
    return adapter.run(question)
