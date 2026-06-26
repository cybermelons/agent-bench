# Personas — provenance & honesty note

These `.md` files are **published system prompts** collected from the
[CL4R1T4S](https://github.com/elder-plinius/CL4R1T4S) repository (an open archive
of extracted/leaked AI system prompts). They are stored here **verbatim** so the
persona text is faithful.

## What they are used for — read this

agent-bench drives its real backend with **`claude -p`** (headless Claude Code).
When a spec sets `persona: cursor` (or `openai-chatgpt`, etc.), the matching
file below is **prepended as a system prompt so Claude *behaves like* that
product** — different voice, verbosity, refusal style, formatting.

**This is Claude wearing another product's prompt. It is NOT a call to a real
GPT / Gemini / Cursor model.** The runtime never contacts another vendor's API;
the only model invoked is Claude via the local `claude` binary.

In `evalkit` results these rows are labelled **`claude-as-<persona>`**
(e.g. `claude-as-openai-chatgpt`), never `gpt-4o` or `cursor`.

## Why this is a legitimate demonstration

The point of agent-bench is to prove the **evaluation platform** — pluggable
adapters, a measured eval harness, blended defaults. The model behind the seam
is a swappable detail. Personas let the platform demonstrate model-pluggability
**offline, with no API keys**. To evaluate genuinely different vendor models,
swap a real client in behind the `LLMClient` seam (`porcelain/llm.py`) — the
rest of the harness is unchanged.

## Files

| file | source product | label in results |
|------|----------------|------------------|
| `claude-code.md` | Anthropic — Claude Code CLI | `claude-as-claude-code` |
| `cursor.md` | Cursor (itself Claude-backed) | `claude-as-cursor` |
| `openai-chatgpt.md` | OpenAI — ChatGPT (GPT-4o prompt) | `claude-as-openai-chatgpt` |
