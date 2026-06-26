# agent-bench

> An enterprise agent platform earns the right to standardize on a pattern by measuring it, not by taste.

## What it is

**One agent, two frameworks, measured — with defaults justified by the measurement.**

agent-bench runs a single RAG-over-docs Q&A agent on **two orchestration
frameworks** (LangGraph and CrewAI) behind a thin shared interface, evaluates
both on the same golden corpus with the same scorers, and renders a report that
makes the blended platform defaults (iteration cap, timeout, retrieval `k`,
success gate) traceable to the run that justified them.

The model behind the agent is **pluggable**: the whole pipeline runs fully
offline and keyless against a deterministic `FakeLLM`, can be driven by
**Claude** (headless `claude -p`, or the Anthropic SDK), and can host any
provider you slot in behind one seam. That pluggability is the point — see
[The model story](#the-model-story).

## Architecture

```
porcelain/   stable, framework-agnostic core (the "porcelain" over the plumbing)
  types.py       AgentSpec, AgentResult, TerminationPolicy, Citation (pydantic v2)
  llm.py         LLMClient seam: FakeLLM | ClaudeCodeClient | RealAnthropicClient
  retrieval.py   shared BM25 retriever (held constant so comparisons isolate the framework)
  runner.py      run_spec(): one entrypoint, dispatches to the right adapter

adapters/    one thin adapter per framework — translate AgentSpec -> native API -> AgentResult
  langgraph adapter, crewai adapter

evalkit/     the measurement spine
  run.py         load golden set, run every (spec x question), score, aggregate -> results.json
  judge.py       deterministic scorers + LLM-as-judge (through the same LLMClient seam)
  results.json   {meta, runs, summary} — machine-readable, honesty-flagged

report/      the human-facing layer
  build.py       results.json -> results.md (provenance banner + metrics table)
  results.md     the rendered report (one row per framework)
```

Both adapters consume the *same* `porcelain` types and the *same* retriever, so
a comparison reflects **orchestration-framework differences**, not retrieval or
schema differences. Swapping frameworks is a one-line change in an `AgentSpec`
(`framework: langgraph` -> `framework: crewai`).

## How to run

```bash
# install (editable, with dev extras)
pip install -e ".[dev]"      # or: uv pip install -e ".[dev]"

# 1. tests — fully offline, keyless (FakeLLM); nothing hits the network
python -m pytest -q

# 2. measure — run both frameworks through the golden set, write results.json
#    (env -u ANTHROPIC_API_KEY forces the offline/fake path even if a key is set)
env -u ANTHROPIC_API_KEY python -m evalkit.run --subset 2 --backend fake

# 3. report — render results.json into report/results.md
python -m report.build
```

`report.build` is standalone: if `evalkit/results.json` is missing it
auto-runs `evalkit.run --subset 2 --backend fake` first (override with
`--results` / `--out`, or `--no-autorun` to fail loudly instead).

To drive it with a real model, run `evalkit.run --backend anthropic`
(reads `ANTHROPIC_API_KEY`) or `--backend claude_code` (headless `claude -p`,
optionally `--personas <slug>`).

## The comparison table

The current rendered table lives in **[`report/results.md`](report/results.md)**.
Sample (synthetic / FakeLLM backend):

| group | synthetic? | n | gate_rate | cited_expected_rate | judge_pass_rate | mean_latency_s | mean_tokens_in | mean_tokens_out | mean_iterations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `crewai` | yes | 2 | 1.00 | 0.50 | 0.50 | 0.0161 | 100.0 | 20.0 | 1.00 |
| `langgraph` | yes | 2 | 0.50 | 0.50 | 0.50 | 0.0033 | 350.0 | 70.0 | 3.50 |

**These are demonstration numbers, not a benchmark.** Under `FakeLLM` every call
returns a fixed canned answer with fixed token counts, so the cross-group
differences are artefacts of how many loop turns each adapter takes — not model
quality. The deliverable is the *shape*: one measured row per framework, an
honesty flag, and defaults wired back to it. Regenerate with a real backend to
populate it with genuine numbers.

## The model story

The single LLM boundary is the `LLMClient` protocol in
[`porcelain/llm.py`](porcelain/llm.py). Both adapters and the judge call the
model *only* through it, which is what makes the model a swappable detail:

- **`FakeLLM`** — offline, deterministic, free. No API key, no network. This is
  what `pytest` and `--backend fake` use, so the entire platform — adapters,
  eval, judge, report — is verifiable with zero credentials.
- **`ClaudeCodeClient`** — drives headless **Claude Code** (`claude -p`). With a
  `--personas <slug>` it prepends a published system prompt so **Claude behaves
  like** another product; those rows are labelled **`claude-as-<persona>`**
  (never `gpt-4o`/`cursor`) and are flagged `synthetic` — it is Claude wearing a
  prompt, **not** a call to another vendor's model. See
  [`prompts/personas/README.md`](prompts/personas/README.md).
- **`RealAnthropicClient`** — the real **Claude** path via the official
  `anthropic` SDK (`--backend anthropic`, reads `ANTHROPIC_API_KEY`).

**Why model-pluggability is the point:** an enterprise platform shouldn't bet its
eval harness, its adapters, or its standardized defaults on one model vintage.
By isolating the model behind one seam, agent-bench proves the *platform*
offline today and lets you re-measure against a real or upgraded model tomorrow
by swapping one client — the golden set, scorers, adapters, and report are
unchanged. The honesty flag (`synthetic`) travels with the numbers end-to-end
so a synthetic run can never be mistaken for a real-model benchmark.

## Honest limitations

- **Two frameworks only** (LangGraph, CrewAI) — not an ecosystem survey.
- **Tiny fictional corpus**, **single task shape** (RAG-over-docs Q&A) — not a
  representative workload.
- **Synthetic / persona numbers** whenever `synthetic` is true: the model behind
  the seam is `FakeLLM` (or Claude wearing a persona prompt, `claude-as-<…>`).
  **This is NOT a vendor benchmark** of any model against another.
- The blended defaults' provenance comments (in `porcelain/types.py` and
  `porcelain/retrieval.py`) currently **demonstrate** the
  measure-then-standardize workflow; they are not tuned-on-a-real-model
  production values.

The value here is the **platform and the workflow**, not the specific numbers in
any one run.

## What this maps to in the JD

This repo is a compact stand-in for a **developer / agent platform** built with
**Claude Code**: a stable porcelain layer with framework adapters behind it
(reduce N integrations to one interface), an **offline-first eval harness** with
deterministic scorers and an **LLM-as-judge** (built and tested keyless), a
**model-pluggability seam** (Claude via the SDK or headless `claude -p`, with
`FakeLLM` for CI), and **defaults justified by measurement with an audit trail
and explicit honesty flags** rather than by taste. It demonstrates the platform
discipline of *measure -> standardize -> document provenance* end-to-end.
