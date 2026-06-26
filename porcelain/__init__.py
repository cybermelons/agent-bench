"""
porcelain — public interface for agent-bench.

Re-exports every type the rest of the codebase (adapters, evalkit, report)
should import from.  Nothing outside this package needs to know where a type
is defined internally.
"""

from porcelain.types import (
    AgentResult,
    AgentSpec,
    Citation,
    TerminatedBy,
    TerminationPolicy,
)

__all__ = [
    "AgentResult",
    "AgentSpec",
    "Citation",
    "TerminatedBy",
    "TerminationPolicy",
]
