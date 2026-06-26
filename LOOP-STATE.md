# LOOP-STATE — agent-bench build

GOAL: pytest exits 0 AND `python -m report.build` writes report/results.md containing a metrics
table with rows for BOTH the langgraph and crewai adapters, AND every checklist item below is
checked — or stop after 40 turns.

Build rules (from the approved plan):
- One topmost-unchecked item per turn (five-beat: find → do → check → remember → go again).
- Delegate code to a sonnet subagent (Opus orchestrates, never codes — global CLAUDE.md).
- A separate reviewer subagent verifies the diff BEFORE checking the box. Evidence in transcript.
- Commit the phase (atomic) when its checkpoint is green.
- Escalate judgment calls (framework API ambiguity, design forks) instead of guessing.

## Phase 0 — Foundations
- [x] pyproject.toml + .gitignore + .env.example + README.md stub + docker-compose.yml
- [x] porcelain/types.py — AgentSpec, AgentResult, TerminationPolicy (pydantic)
- [x] corpus/ docs (~6–10 short md) + corpus/golden.yaml (~8–12 Q/A w/ rubric + expected doc)
- [x] specs/example.yaml — one AgentSpec with a framework field (made TWO: langgraph + crewai, proving the one-line swap)

## Phase 1 — porcelain + langgraph
- [x] porcelain/retrieval.py — shared BM25 chunk+top-k util (single source, both adapters reuse)
- [x] porcelain/runner.py — load spec, build retriever, dispatch to adapter, enforce termination
- [x] adapters/langgraph/ — REAL langgraph StateGraph (retrieve->generate->gate loop); base Adapter owns timing/terminated_by/citation-extraction (CrewAI reuses)
- [x] porcelain/llm.py — LLMClient protocol + FakeLLM + RealAnthropicClient (the swappable model seam — "model doesn't matter, the platform does")
- [x] tests: 9 passed, 2 skipped OFFLINE (no key, no network) — spec loads, retriever finds oncall-policy, langgraph adapter cites oncall-policy w/ terminated_by=GATE

## Phase 1.5 — persona backend (claude -p, honestly labeled) — COMPLETE
- [x] porcelain/llm.py: ClaudeCodeClient shells out to real claude binary (~/.nvm/.../v23.8.0/bin/claude), keyless. argv=[bin,-p,prompt,--max-turns,1]. Persona prompt prepended. Token counts = len//4 ESTIMATES (documented). spec.model deliberately NOT forwarded — persona is the axis.
- [x] prompts/personas/: claude-code.md, cursor.md, openai-chatgpt.md (verbatim CL4R1T4S) + README.md provenance/honesty note (claude-as-<persona>, NOT real GPT/Gemini).
- [x] AgentSpec.persona: optional, backward-compat verified (old specs load, persona defaults None).
- [x] tests: prompt-composition tested via monkeypatched subprocess (no real call); real-claude test skipif-binary-missing. 22 passed/2 skipped offline.

## Phase 2 — crewai — COMPLETE
- [x] adapters/crewai/ — REAL crewai Agent/Task/Crew + crew.kickoff(). _ShimLLM(BaseLLM) routes model call through self.llm seam (FakeLLM works, token accounting matches langgraph). Shared CorpusRetriever; citation/terminated_by/timing inherited from base. _run_inner only.
- [x] tests: crewai gates on golden Q; INTERCHANGE test proves same Q on both frameworks differs only by the framework: line. 26 passed/2 skipped offline.

## Phase 3 — evalkit — COMPLETE
- [x] evalkit/run.py + judge.py — golden × both adapters, score: citation validity + answer_contains (deterministic), correctness via LLM-judge through the SAME LLMClient seam (keyless w/ FakeLLM). Aggregates per-group SLA metrics. results.json {meta, runs, summary}. Metrics verified REAL (hand-recomputed; gate_rate 0.5 vs 1.0 differs).
- [x] meta.synthetic honesty flag + per-group synthetic/backend stamp (survives screenshot). CLI: --subset/--backend/--personas/--out.
- [x] tests: judge deterministic, scorers correct, subset eval emits both frameworks. 30 passed/3 skipped (live tests now RUN_LIVE-gated -> skip not fail on stale key).

## Phase 4 — report
- [ ] report/build.py — results.json → report/results.md (metrics table, terminated_by breakdown)
- [ ] annotate porcelain default TerminationPolicy / retrieval-k with provenance citing the run
- [ ] README.md — thesis, how-to-run, comparison table, honest limits; names Claude Code/Claude

## Design decisions (locked)
- Eval axis: model-persona × framework grid (LangGraph + CrewAI).
- Real LLM backend: `claude -p` headless (real binary ~/.nvm/versions/node/v23.8.0/bin/claude —
  NOT the `claude→happy` alias). Keyless, uses local Claude Code. Only invoked during evalkit, never in tests.
- Personas: CL4R1T4S published system prompts (prompts/cl4r1t4s-*.md) seed each "model persona" —
  Claude wearing another product's system prompt. LABELED HONESTLY as `claude-as-<persona>` in report.
  NOT presented as real GPT/Gemini. README states: platform is model-pluggable; personas demo that
  pluggability offline; one-line adapter swap -> real OpenAI/Google clients for genuine multi-model eval.
- This is a DEMONSTRATION artifact (shows the eval platform works), not a peer-review benchmark.
- Tests: FakeLLM mock, offline/deterministic — `pytest exits 0` must hold with no key and no claude -p.

## Blockers
(none yet)

## Log
(newest first; one line per completed item)
- P3 PHASE 3 COMPLETE: evalkit (run.py + judge.py) — the measurement spine. Golden×both frameworks scored (citation+answer_contains deterministic, correctness LLM-judge via seam), results.json with real per-group SLA metrics + honesty meta. review SOLID. Fixed 2 minors: per-group synthetic stamp (screenshot-safe) + RUN_LIVE gating (live tests skip not fail on stale key). 30 passed/3 skipped.
- P2 PHASE 2 COMPLETE: real CrewAI adapter (Agent/Task/Crew/kickoff), _ShimLLM(BaseLLM)->self.llm seam, shared retriever, base-owned citation/terminated_by. Interchange test proves one-line framework swap. review verdict SOLID, 26 passed/2 skipped offline, verified independently. Minor: re-kick loop = intentional parity w/ langgraph (fair comparison).
- P1.5 persona backend: ClaudeCodeClient (real claude -p, keyless) + 3 CL4R1T4S personas + provenance README + AgentSpec.persona. 22 passed/2 skipped offline. Honesty gap closed (personas labeled claude-as-X). This is the concrete proof: "model is a swappable persona behind a 1-method seam; the platform is the deliverable."
- P1.2-4 PHASE 1 COMPLETE: porcelain/llm.py (LLMClient seam + FakeLLM + RealAnthropicClient), adapters/base.py (shared timing/citation/terminated_by), adapters/langgraph (REAL StateGraph verified), porcelain/runner.py (dispatch + termination). pytest 9 passed/2 skipped offline no-key. The model is a 1-method swappable seam — proves "I build the platform, model doesn't matter". Added Phase 1.5: claude -p + CL4R1T4S persona backend behind that seam.
- P1.1 porcelain/retrieval.py: BM25Okapi CorpusRetriever, 150w/30w-overlap chunks, deterministic, framework-free. Self-check verified independently: 7 doc_ids, top hit oncall-policy for "on-call stipend", format_context labels [doc_id:..]. Swapped sentence-transformers->rank-bm25 (right-sized for 7-doc corpus).
- P0.4 specs: langgraph-baseline.yaml + crewai-baseline.yaml, both load via AgentSpec.from_yaml. PHASE 0 COMPLETE.
- P0.3 corpus: 7-doc fictional "Meridian Systems" handbook + 11-Q golden.yaml. Validated: parses, all expected_doc resolve, all answer_contains literal in their doc. Fictional domain forces retrieval (no training-data leakage). Difficulty mix: 6 easy / 3 disambiguation / 1 cross-doc / 1 table-lookup.
- P0.2 porcelain/types.py: AgentSpec/AgentResult/TerminationPolicy/Citation/TerminatedBy — import-verified in .venv, cites_corpus works. Declarative termination standardized across frameworks (the senior design point) documented per-field. venv created, pydantic+pyyaml installed.
- P0.1 foundations: pyproject(hatchling)/.gitignore/.env.example/README stub/docker-compose — toml+yaml parse OK. Note: __init__.py to be added as each package gets its first module (Phase 1/2). sentence-transformers chosen for local embeddings.
