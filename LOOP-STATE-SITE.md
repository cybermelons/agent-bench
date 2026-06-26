# LOOP-STATE-SITE — agent-bench demo site build

GOAL: ACHIEVED ✅ — docs/index.html is self-contained, renders the real both-framework table from
results.json, repo is PUBLIC, GitHub Pages serves it, URL returns HTTP 200.
LIVE: https://cybermelons.github.io/agent-bench/ (verified: 200, build=built, real content served).

(original) docs/index.html is a self-contained static page that tells the agent-bench story and renders
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

## Site checklist — ALL COMPLETE
- [x] docs/index.html — self-contained (29KB, zero external assets bar the GH anchor): thesis, one-line
      framework-swap, data-driven comparison table, model-pluggability seam, limitations + synthetic
      banner. Names Claude/Claude Code. Müller-Brockmann grid + overlay toggle.
- [x] data is REAL: table rendered at runtime from embedded results.json; numbers match (gate 0.5 vs 1.0,
      iter 3.5 vs 1.0, tokens 350/70 vs 100/20). Verified by headless render.
- [x] design pass: Swiss/editorial grid, grotesque type, one accent. Review SOLID.
- [x] reviewer pass: headless puppeteer render confirmed display + data fidelity + honesty + no overclaim.
- [x] publish: repo PUBLIC + Pages from /docs + URL returns 200. README links the live URL.

## Blockers
(none yet)

## Log
(newest first)
- SITE GOAL ACHIEVED: published to GitHub Pages, repo public, https://cybermelons.github.io/agent-bench/ returns 200 with real content. README links it. Site loop complete.
- Built self-contained docs/index.html (Müller-Brockmann grid, data-driven table from embedded results.json, prominent synthetic banner). Review SOLID, headless-render verified.
