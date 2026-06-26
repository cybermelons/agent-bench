# agent-bench — measurement report

> An enterprise agent platform earns the right to standardize on a pattern by measuring it, not by taste.

## Provenance & honesty

> **These are DEMONSTRATION numbers, NOT a real-model benchmark.**
>
> They were produced by the `fake` backend (FakeLLM backend (offline deterministic, no real model)). Treat every rate, latency, and token count below as an illustration of *how the measure-then-standardize workflow reads*, not as a measured comparison of LangGraph vs. CrewAI on a live model.

- **backend:** `fake`
- **model:** `claude-3-5-sonnet-latest`
- **synthetic:** `true`
- **synthetic_reason:** FakeLLM backend (offline deterministic, no real model)
- **frameworks:** crewai, langgraph
- **specs:** langgraph-baseline, crewai-baseline
- **questions:** 2
- **runs:** 4
- **personas_used:** False

## Metrics by group

| group | synthetic? | n | gate_rate | cited_expected_rate | judge_pass_rate | mean_latency_s | mean_tokens_in | mean_tokens_out | mean_iterations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `crewai` | yes | 2 | 1.00 | 0.50 | 0.50 | 0.0168 | 100.0 | 20.0 | 1.00 |
| `langgraph` | yes | 2 | 0.50 | 0.50 | 0.50 | 0.0032 | 350.0 | 70.0 | 3.50 |

## What this shows

`crewai` hits the success gate more often (1.00) than `langgraph` (0.50), and reaches it in fewer iterations (1.00 mean for `crewai`); judge pass-rate is identical across every group (0.50).

**Read this as a workflow demonstration, not a benchmark.** Under the deterministic FakeLLM backend every model call returns a fixed canned answer with fixed token counts, so the cross-group differences above are artefacts of how many loop iterations each adapter's termination path takes, not of model quality. For example `langgraph`'s higher `mean_tokens_in` (350.0 vs. 100.0 for `crewai`) reflects extra FakeLLM loop turns, not a real token-cost gap. The shape of the table — one measured row per framework, an honesty flag, and defaults justified against it — is the deliverable; swap a real client in behind the `LLMClient` seam to populate it with genuine numbers.

## How this justifies the blended defaults

The blended defaults live in `porcelain/types.py` (`TerminationPolicy`: `max_iterations`, `timeout_s`, `max_retries`, `success_gate`) and `porcelain/retrieval.py` (`search(k=4)`). Each carries a comment pointing back to this report. **Because the current numbers are synthetic, those comments DEMONSTRATE the measure-then-standardize workflow — they are not tuned production values.** When a real backend populates this table, the same comments become the audit trail from a chosen default to the run that justified it.

## Limitations

- **Two frameworks only** (LangGraph, CrewAI) — not a survey of the ecosystem.
- **Tiny fictional corpus** and a **single task shape** (RAG-over-docs Q&A) — not a representative workload.
- **Synthetic / persona numbers** when `synthetic` is true: the model behind the seam is FakeLLM (or Claude wearing another product's persona prompt, labelled `claude-as-<persona>`), so this is **NOT a vendor benchmark** of any model against another.
- The value here is the **platform and the workflow** — pluggable adapters, a measured eval harness, and defaults justified by that measurement — not the specific numbers in this run.
