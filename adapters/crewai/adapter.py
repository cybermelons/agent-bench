"""
adapters.crewai.adapter — CrewAIAdapter: a real CrewAI Agent + Task + Crew.

This adapter is the CrewAI half of the porcelain comparison.  It mirrors the
STRUCTURE of :mod:`adapters.langgraph.adapter` — retrieve via the shared
``CorpusRetriever``, generate through the shared ``self.llm`` seam, bound the
loop by ``self.spec.termination.max_iterations``, gate via the base-class
citation extractor — but expresses the orchestration as a genuine CrewAI crew
(``crewai.Agent`` + ``crewai.Task`` + ``crewai.Crew``) rather than a LangGraph
StateGraph.  Only ``_run_inner`` is implemented; the base ``Adapter`` owns
timing, terminated_by, citation extraction, and the cites_corpus gate.

Two hard requirements drive the design (so the comparison stays
apples-to-apples with LangGraph):

1. Retrieval MUST be the shared :class:`~porcelain.retrieval.CorpusRetriever`,
   not CrewAI's own tools/RAG/knowledge subsystem.  So retrieval is done in
   plain Python here (``self.retriever.search`` + ``format_context``) and the
   resulting context is INJECTED into the CrewAI ``Task`` description.  CrewAI
   never sees a corpus directory or runs its own retriever.

2. The model call MUST route through ``self.llm.complete`` so the injected
   FakeLLM works in tests and token accounting is identical to LangGraph.
   CrewAI insists on driving its agents through a ``crewai.BaseLLM`` object, so
   we wrap ``self.llm`` in the thinnest possible shim — ``_ShimLLM`` — that
   implements the single abstract ``call(...)`` method by delegating straight
   to ``self.llm.complete(...)``.  The shim translates CrewAI's assembled
   message list back into the ``(system, messages)`` shape ``self.llm`` expects,
   records the per-call token counts, and returns the answer text.  The actual
   model call therefore always goes through ``self.llm`` — CrewAI provides the
   Agent/Task/Crew orchestration, but never the LLM transport.

The import of ``crewai`` stays at module top here (this module is only imported
when ``get_adapter('crewai')`` is called, which already implies crewai is
needed); ``import adapters`` itself stays crewai-free because the registry defers
this import to call time.
"""

from __future__ import annotations

from crewai import Agent, BaseLLM, Crew, Process, Task

from adapters.base import Adapter, _RawRun


# ---------------------------------------------------------------------------
# _ShimLLM — the thinnest crewai BaseLLM that delegates to self.llm.complete
# ---------------------------------------------------------------------------

class _ShimLLM(BaseLLM):
    """A ``crewai.BaseLLM`` whose every call routes through a porcelain ``LLMClient``.

    CrewAI agents must be driven by a ``crewai.BaseLLM`` instance; it owns the
    transport to the model.  We do NOT want CrewAI's litellm transport — we want
    the SAME ``self.llm.complete`` seam LangGraph uses, so FakeLLM works offline
    and token accounting matches.  This shim is that bridge: its ``call`` method
    is the only thing CrewAI invokes for generation, and it forwards verbatim to
    ``inner.complete``.

    ``BaseLLM`` is a pydantic model, so the porcelain client and the token
    accumulators are stored via ``object.__setattr__`` to sidestep field
    validation (they are plumbing, not declared model fields).

    Token accounting
    ----------------
    CrewAI does not surface token usage to the adapter, so the shim accumulates
    ``tokens_in`` / ``tokens_out`` from each ``LLMResponse`` it returns.  The
    adapter reads these back after ``crew.kickoff()`` — exactly the counts the
    porcelain ``self.llm`` reported, identical to the LangGraph path.
    """

    def __init__(self, inner, model: str) -> None:  # noqa: ANN001 — porcelain LLMClient
        # BaseLLM (pydantic) requires `model`; pass it through so CrewAI is happy.
        super().__init__(model=model)
        # Plumbing fields, not pydantic-declared → set around validation.
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_model", model)
        object.__setattr__(self, "tokens_in", 0)
        object.__setattr__(self, "tokens_out", 0)
        object.__setattr__(self, "calls", 0)

    @staticmethod
    def _split(messages) -> tuple[str, list[dict]]:  # noqa: ANN001
        """Translate CrewAI's call payload into (system, user-messages).

        CrewAI passes either a plain string or a list of ``{"role", "content"}``
        dicts.  Everything with ``role == "system"`` is concatenated into the
        ``system`` string; every other message is forwarded as a user message so
        ``self.llm.complete`` sees the same grounding context + the question
        CrewAI assembled from the Task.
        """
        if isinstance(messages, str):
            return "", [{"role": "user", "content": messages}]

        system_parts: list[str] = []
        fwd: list[dict] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Flatten content blocks to text.
                content = "\n".join(
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            if content is None:
                content = ""
            if role == "system":
                if content:
                    system_parts.append(content)
            else:
                # Map crewai's 'assistant'/'tool' onto 'user' for the porcelain
                # client, which only distinguishes user content for the blob.
                fwd.append({"role": "user", "content": content})
        if not fwd:
            fwd = [{"role": "user", "content": ""}]
        return "\n\n".join(system_parts), fwd

    def call(
        self,
        messages,  # noqa: ANN001 — str | list[LLMMessage]
        tools=None,  # noqa: ANN001
        callbacks=None,  # noqa: ANN001
        available_functions=None,  # noqa: ANN001
        from_task=None,  # noqa: ANN001
        from_agent=None,  # noqa: ANN001
        response_model=None,  # noqa: ANN001
    ) -> str:
        """The one method CrewAI calls — delegate to the porcelain LLMClient."""
        system, fwd = self._split(messages)
        resp = self._inner.complete(
            system=system,
            messages=fwd,
            model=self._model,
        )
        object.__setattr__(self, "tokens_in", self.tokens_in + resp.tokens_in)
        object.__setattr__(self, "tokens_out", self.tokens_out + resp.tokens_out)
        object.__setattr__(self, "calls", self.calls + 1)
        return resp.text

    # CrewAI calls this to decide whether to use its function-calling path; we
    # never expose tools, so always report no native function calling.
    def supports_function_calling(self) -> bool:  # noqa: D401
        return False


# ---------------------------------------------------------------------------
# CrewAIAdapter
# ---------------------------------------------------------------------------

class CrewAIAdapter(Adapter):
    """
    :class:`~adapters.base.Adapter` implemented on a real CrewAI crew.

    Per question, ``_run_inner``:

    1. retrieves with the shared ``CorpusRetriever``
       (``self.retriever.search(question, k=4)`` + ``format_context``);
    2. injects that context (and the shared grounding/citation system prompt)
       into a CrewAI ``Task`` for a CrewAI ``Agent`` whose ``llm`` is the
       ``_ShimLLM`` bridging to ``self.llm``;
    3. runs the loop up to ``max_iterations`` times, re-kicking the crew until
       the answer cites a real corpus doc (the same gate LangGraph uses) or the
       cap is reached;
    4. returns a ``_RawRun`` with the answer, the iteration count, and the
       token totals the shim accumulated.

    The base ``Adapter`` owns timing, the timeout guard, the authoritative
    terminated_by classification, and citation extraction — none of that is
    duplicated here.
    """

    def _run_inner(self, question: str) -> _RawRun:
        max_iterations = self.spec.termination.max_iterations

        # --- retrieve (shared CorpusRetriever — NOT crewai's RAG) ----------
        chunks = self.retriever.search(question, k=4)
        context = self.retriever.format_context(chunks)

        # The shared grounding/citation system prompt.  We reuse the base-class
        # builder so the prompt is byte-identical to LangGraph's, then inject it
        # into the CrewAI Task description (CrewAI assembles its own messages
        # from the Task, and the shim forwards them to self.llm).
        system, _ = self._build_messages(question, context)

        # --- the LLM shim: every generation routes through self.llm --------
        shim = _ShimLLM(self.llm, self.spec.model)

        # --- real crewai constructs: Agent + Task + Crew -------------------
        agent = Agent(
            role="Meridian Systems knowledge assistant",
            goal=(
                "Answer the employee's question using ONLY the retrieved "
                "context, citing every source with [doc_id: X] syntax."
            ),
            backstory=(
                "A precise internal-docs assistant that never invents facts and "
                "always grounds answers in the provided corpus passages."
            ),
            llm=shim,
            max_iter=1,          # one LLM step per kickoff; our loop owns iteration
            allow_delegation=False,
            verbose=False,
        )

        task = Task(
            description=(
                f"{system}\n\n"
                f"Question: {question}\n\n"
                "Answer the question grounded in the retrieved context above, "
                "citing each source you use with its exact [doc_id: X] label."
            ),
            expected_output=(
                "A concise answer that cites at least one [doc_id: X] label "
                "drawn from the retrieved context."
            ),
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        # --- bounded loop: re-kick until cited, or max_iterations reached ---
        # This is the CrewAI analogue of LangGraph's should_continue conditional
        # edge: stop once the answer cites a real corpus doc, else loop up to the
        # cap.  The base class then makes the authoritative GATE/MAX_ITER call.
        answer = ""
        iterations = 0
        for _ in range(max_iterations):
            result = crew.kickoff()
            answer = str(result)
            iterations += 1

            citations = self.extract_citations(answer)
            cited = any(c.doc_id in self.valid_doc_ids for c in citations)
            if cited:
                break

        return _RawRun(
            answer=answer,
            iterations=iterations,
            tokens_in=shim.tokens_in,
            tokens_out=shim.tokens_out,
        )
