"""
adapters — framework adapters + the get_adapter registry.

Re-exports the abstract :class:`~adapters.base.Adapter` and the
``get_adapter(framework)`` registry that maps a framework name to its concrete
adapter class.  The concrete classes are imported lazily inside ``get_adapter``
so that importing this package does not require ``langgraph`` / ``crewai`` to be
installed unless that framework is actually requested.
"""

from __future__ import annotations

from adapters.base import Adapter

__all__ = ["Adapter", "get_adapter"]


def get_adapter(framework: str) -> type[Adapter]:
    """
    Resolve a framework name to its concrete :class:`Adapter` subclass.

    Parameters
    ----------
    framework : str
        ``"langgraph"`` or ``"crewai"`` (matches ``AgentSpec.framework``).

    Returns
    -------
    type[Adapter]
        The adapter class (not an instance) — the caller constructs it with
        ``(spec, retriever, llm)``.

    Raises
    ------
    ValueError
        If *framework* is not a known adapter.

    Notes
    -----
    Imports are deferred to call time: requesting ``"langgraph"`` imports
    ``langgraph``; requesting ``"crewai"`` imports the CrewAI adapter module.
    This keeps ``import adapters`` cheap and dependency-free.
    """
    if framework == "langgraph":
        from adapters.langgraph import LangGraphAdapter

        return LangGraphAdapter
    if framework == "crewai":
        from adapters.crewai import CrewAIAdapter

        return CrewAIAdapter
    raise ValueError(
        f"Unknown framework {framework!r}; expected 'langgraph' or 'crewai'."
    )
