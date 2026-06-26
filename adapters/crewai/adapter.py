"""
adapters.crewai.adapter — CrewAIAdapter: interface-parity stub for this phase.

This phase builds the LangGraph half plus the shared scaffolding both adapters
use.  The real CrewAI crew wiring is the CrewAI half (a later phase); for now
this class exists so:

* the ``get_adapter`` registry resolves ``spec.framework == "crewai"``, and
* the interface contract (subclass of :class:`~adapters.base.Adapter`,
  implementing ``_run_inner``) is pinned and importable without the ``crewai``
  package installed.

``_run_inner`` raises ``NotImplementedError`` until the CrewAI half lands.  The
import of ``crewai`` is deliberately deferred to call time so that importing
this module — and therefore resolving the registry — never requires the
``crewai`` package.
"""

from __future__ import annotations

from adapters.base import Adapter, _RawRun


class CrewAIAdapter(Adapter):
    """
    CrewAI :class:`~adapters.base.Adapter` — interface-parity stub.

    Inherits the entire shared contract (run(), timing, terminated_by,
    extract_citations, the gate) from the base class.  Only ``_run_inner`` is
    left for the CrewAI half; it currently raises so a real run surfaces a
    clear, honest error rather than silently producing a fake result.
    """

    def _run_inner(self, question: str) -> _RawRun:  # pragma: no cover - stub
        raise NotImplementedError(
            "CrewAIAdapter is an interface-parity stub in this phase; the "
            "CrewAI crew wiring lands in the CrewAI half. The class and "
            "registry entry exist so the runner resolves "
            "spec.framework == 'crewai'."
        )
