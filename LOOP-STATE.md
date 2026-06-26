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
- [ ] porcelain/retrieval.py — shared chunk+embed+top-k util (single source, both adapters reuse)
- [ ] porcelain/runner.py — load spec, build retriever, dispatch to adapter, enforce termination
- [ ] adapters/langgraph/ — implement Adapter.run(spec, question) -> AgentResult
- [ ] tests: spec loads + langgraph answers a golden Q with a valid citation → pytest green

## Phase 2 — crewai
- [ ] adapters/crewai/ — same Adapter.run against the same retrieval util
- [ ] tests: crewai answers same golden Q; framework swap = one YAML line → pytest green

## Phase 3 — evalkit
- [ ] evalkit/run.py — golden × both adapters, score (citation deterministic, correctness Claude judge)
- [ ] tests: subset eval runs end-to-end, emits evalkit/results.json with both frameworks

## Phase 4 — report
- [ ] report/build.py — results.json → report/results.md (metrics table, terminated_by breakdown)
- [ ] annotate porcelain default TerminationPolicy / retrieval-k with provenance citing the run
- [ ] README.md — thesis, how-to-run, comparison table, honest limits; names Claude Code/Claude

## Blockers
(none yet)

## Log
(newest first; one line per completed item)
- P0.4 specs: langgraph-baseline.yaml + crewai-baseline.yaml, both load via AgentSpec.from_yaml. PHASE 0 COMPLETE.
- P0.3 corpus: 7-doc fictional "Meridian Systems" handbook + 11-Q golden.yaml. Validated: parses, all expected_doc resolve, all answer_contains literal in their doc. Fictional domain forces retrieval (no training-data leakage). Difficulty mix: 6 easy / 3 disambiguation / 1 cross-doc / 1 table-lookup.
- P0.2 porcelain/types.py: AgentSpec/AgentResult/TerminationPolicy/Citation/TerminatedBy — import-verified in .venv, cites_corpus works. Declarative termination standardized across frameworks (the senior design point) documented per-field. venv created, pydantic+pyyaml installed.
- P0.1 foundations: pyproject(hatchling)/.gitignore/.env.example/README stub/docker-compose — toml+yaml parse OK. Note: __init__.py to be added as each package gets its first module (Phase 1/2). sentence-transformers chosen for local embeddings.
