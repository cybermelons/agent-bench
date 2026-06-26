"""
adapters.langgraph.adapter — LangGraphAdapter: a real langgraph StateGraph.

This adapter wires the retrieve→generate loop as a genuine
``langgraph.graph.StateGraph`` (not a stub):

    retrieve_node ──▶ generate_node ──▶ (conditional gate edge)
                                          │
                          cited? ─ no ───┘ loop back to generate
                          cited? ─ yes ──▶ END
                          iter >= max ───▶ END

* ``retrieve_node`` calls ``self.retriever.search`` + ``format_context`` once.
* ``generate_node`` calls ``self.llm.complete`` and accumulates tokens +
  iteration count.
* the conditional edge loops back to ``generate_node`` until the answer cites a
  corpus doc OR ``max_iterations`` is reached, then routes to ``END``.

Only ``_run_inner`` is implemented here; the base ``Adapter`` owns timing,
terminated_by, citation extraction, and the cites_corpus gate.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from adapters.base import Adapter, _RawRun


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

class _GraphState(TypedDict):
    """Mutable state threaded through the LangGraph StateGraph."""

    question: str
    context: str
    answer: str
    iterations: int
    tokens_in: int
    tokens_out: int


class LangGraphAdapter(Adapter):
    """
    :class:`~adapters.base.Adapter` implemented on a real LangGraph StateGraph.

    The compiled graph is built once per question inside ``_run_inner`` (graph
    construction is cheap and keeps per-question state isolated).  Termination
    of the generate loop is enforced here by ``max_iterations`` *and* by the
    base-class gate semantics (cite a corpus doc → stop); the base class
    additionally enforces the shared timeout and the authoritative
    terminated_by classification.
    """

    def _run_inner(self, question: str) -> _RawRun:
        max_iterations = self.spec.termination.max_iterations

        # --- nodes -----------------------------------------------------
        def retrieve_node(state: _GraphState) -> _GraphState:
            chunks = self.retriever.search(state["question"], k=4)
            state["context"] = self.retriever.format_context(chunks)
            return state

        def generate_node(state: _GraphState) -> _GraphState:
            system, messages = self._build_messages(
                state["question"], state["context"]
            )
            resp = self.llm.complete(
                system=system,
                messages=messages,
                model=self.spec.model,
            )
            state["answer"] = resp.text
            state["iterations"] += 1
            state["tokens_in"] += resp.tokens_in
            state["tokens_out"] += resp.tokens_out
            return state

        # --- conditional gate edge ------------------------------------
        def should_continue(state: _GraphState) -> str:
            # Stop once the answer cites a real corpus doc, or the cap is hit.
            citations = self.extract_citations(state["answer"])
            cited = any(c.doc_id in self.valid_doc_ids for c in citations)
            if cited or state["iterations"] >= max_iterations:
                return "end"
            return "generate"

        # --- build + compile the StateGraph ---------------------------
        graph = StateGraph(_GraphState)
        graph.add_node("retrieve", retrieve_node)
        graph.add_node("generate", generate_node)
        graph.set_entry_point("retrieve")
        graph.add_edge("retrieve", "generate")
        graph.add_conditional_edges(
            "generate",
            should_continue,
            {"generate": "generate", "end": END},
        )
        compiled = graph.compile()

        # --- invoke ----------------------------------------------------
        init: _GraphState = {
            "question": question,
            "context": "",
            "answer": "",
            "iterations": 0,
            "tokens_in": 0,
            "tokens_out": 0,
        }
        # recursion_limit must cover: retrieve + (generate * max_iterations).
        # Add headroom so the graph never raises GraphRecursionError before our
        # own should_continue gate routes to END.
        final = compiled.invoke(
            init,
            config={"recursion_limit": max_iterations * 2 + 5},
        )

        return _RawRun(
            answer=final["answer"],
            iterations=final["iterations"],
            tokens_in=final["tokens_in"],
            tokens_out=final["tokens_out"],
        )
