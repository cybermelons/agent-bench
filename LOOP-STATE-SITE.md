# LOOP-STATE-SITE — agent-bench demo site build

GOAL: docs/index.html is a self-contained static page that tells the agent-bench story and renders
the real both-framework comparison table from the committed results.json; GitHub Pages serves it at
a public URL; the URL returns HTTP 200 — or stop after 15 turns.

Build rules (same as the platform loop):
- One topmost-unchecked item per turn (find → do → check → remember → go again).
- Delegate build to a sonnet subagent via workflow; separate reviewer verifies before checking a box.
- Honesty discipline carries over: the page MUST show the synthetic/demonstration caveat prominently;
  personas (if shown) labeled claude-as-<persona>; no claim of a real-vendor benchmark.
- Atomic commit per checkpoint; push.

## Decisions (locked)
- Single self-contained docs/index.html (inline CSS/JS, results.json embedded inline — no fetch, so it
  also works opened as a file). No build step, no framework.
- Aesthetic: tasteful technical/editorial (Müller-Brockmann grid leaning) — I choose, user reacts.
- Static data only (the committed FakeLLM results.json). No live calls from the page.
- Repo goes PUBLIC; Pages from /docs on main (or gh-pages) — set during publish step.

## Site checklist
- [ ] docs/index.html — self-contained: thesis, the one-line framework-swap story (show the two specs
      diff), the comparison table rendered from embedded results.json, the model-pluggability seam
      explanation, honest limitations + synthetic banner. Names Claude/Claude Code.
- [ ] data is REAL: table numbers match evalkit/results.json exactly (gate_rate 0.5 vs 1.0 etc.).
- [ ] design pass: grid, type, one accent color; readable, intentional, not templated.
- [ ] reviewer pass: renders correctly (headless screenshot/DOM check), honesty caveat present, no
      overclaiming, links work.
- [ ] publish: repo public + GitHub Pages enabled (source /docs) + URL returns 200. Put URL in README.

## Blockers
(none yet)

## Log
(newest first)
