"""
report — the human-facing reporting layer of agent-bench.

Reads the machine-readable ``evalkit/results.json`` produced by the measurement
spine and renders ``report/results.md``: a provenance-banner-first Markdown
report whose central artefact is a per-group metrics table.  The report is the
surface that closes the project thesis — *an enterprise agent platform earns the
right to standardize on a pattern by measuring it, not by taste* — by making the
numbers (and their honesty caveats) visible next to the blended defaults they
justify.
"""
