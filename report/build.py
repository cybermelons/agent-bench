"""
report.build — render evalkit/results.json into a human-facing Markdown report.

What it does
------------
Reads the ``{meta, runs, summary}`` document the measurement spine wrote to
``evalkit/results.json`` and writes ``report/results.md`` containing:

1. a title + the project thesis line;
2. a PROVENANCE / HONESTY banner built from ``meta`` (backend, model, synthetic
   flag, synthetic_reason).  When ``meta.synthetic`` is true the banner states
   plainly that these are demonstration numbers, NOT a real-model benchmark;
3. the MAIN metrics table — ONE ROW PER GROUP (langgraph, crewai, and any
   ``claude-as-<persona>`` group present), with the per-group ``synthetic`` flag
   visible in its own column;
4. a "what this shows" paragraph written from the ACTUAL numbers read out of the
   summary (FakeLLM artefacts are named as artefacts, not dressed up as findings).

Honesty
-------
This layer invents nothing.  Every number printed is read straight out of
``results.json``.  The "what this shows" paragraph is generated from those read
values, and any difference that is an artefact of the deterministic FakeLLM
backend is labelled as such.

CLI
---
``python -m report.build [--results evalkit/results.json] [--out report/results.md]``

If ``--results`` is missing on disk, the command auto-runs
``evalkit.run --subset 2 --backend fake`` to regenerate it so ``report.build``
works standalone; if that regeneration is not possible it exits non-zero with a
clear message.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_RESULTS = _REPO_ROOT / "evalkit" / "results.json"
_DEFAULT_OUT = _REPO_ROOT / "report" / "results.md"

THESIS = (
    "An enterprise agent platform earns the right to standardize on a pattern "
    "by measuring it, not by taste."
)

# Columns of the main metrics table, in render order.  Each entry is
# (summary-key, header, formatter).
_TABLE_COLUMNS: list[tuple[str, str, Any]] = [
    ("synthetic", "synthetic?", lambda v: "yes" if v else "no"),
    ("n", "n", lambda v: str(int(v))),
    ("gate_rate", "gate_rate", lambda v: f"{v:.2f}"),
    ("cited_expected_rate", "cited_expected_rate", lambda v: f"{v:.2f}"),
    ("judge_pass_rate", "judge_pass_rate", lambda v: f"{v:.2f}"),
    ("mean_latency_s", "mean_latency_s", lambda v: f"{v:.4f}"),
    ("mean_tokens_in", "mean_tokens_in", lambda v: f"{v:.1f}"),
    ("mean_tokens_out", "mean_tokens_out", lambda v: f"{v:.1f}"),
    ("mean_iterations", "mean_iterations", lambda v: f"{v:.2f}"),
]


# ---------------------------------------------------------------------------
# Loading (with standalone auto-run fallback)
# ---------------------------------------------------------------------------

def load_results(results_path: str | Path, *, autorun: bool = True) -> dict:
    """
    Load the results document, auto-running a tiny eval if it is missing.

    Parameters
    ----------
    results_path : str or Path
        Path to ``results.json``.
    autorun : bool
        When True (default) and the file is absent, run
        ``evalkit.run --subset 2 --backend fake`` to (re)create it so
        ``report.build`` works standalone.  When False, a missing file raises
        ``FileNotFoundError`` instead.

    Returns
    -------
    dict
        The ``{meta, runs, summary}`` document.

    Raises
    ------
    FileNotFoundError
        If the file is missing and either ``autorun`` is False or the auto-run
        did not produce the file.
    """
    path = Path(results_path)
    if not path.is_file():
        if not autorun:
            raise FileNotFoundError(
                f"results file not found: {path}. Run "
                f"`python -m evalkit.run --subset 2 --backend fake` first."
            )
        # Standalone convenience: regenerate a small fake-backend results.json.
        from evalkit import run as evalrun  # local import keeps report import-light

        rc = evalrun.main(
            ["--subset", "2", "--backend", "fake", "--out", str(path)]
        )
        if rc != 0 or not path.is_file():
            raise FileNotFoundError(
                f"auto-run of evalkit.run did not produce {path} (rc={rc}). "
                f"Run it manually and re-try report.build."
            )
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_banner(meta: dict) -> list[str]:
    """Render the provenance / honesty banner from ``meta``."""
    backend = meta.get("backend", "unknown")
    model = meta.get("model", "unknown")
    synthetic = bool(meta.get("synthetic"))
    reason = meta.get("synthetic_reason") or "n/a"

    lines = ["## Provenance & honesty", ""]
    if synthetic:
        lines += [
            "> **These are DEMONSTRATION numbers, NOT a real-model benchmark.**",
            ">",
            f"> They were produced by the `{backend}` backend "
            f"({reason}). Treat every rate, latency, and token count below as an "
            "illustration of *how the measure-then-standardize workflow reads*, "
            "not as a measured comparison of LangGraph vs. CrewAI on a live model.",
        ]
    else:
        lines += [
            f"> Numbers below were produced by the `{backend}` backend on a real "
            "model and are a genuine measurement (subject to the limitations at "
            "the foot of this report).",
        ]
    lines += [
        "",
        f"- **backend:** `{backend}`",
        f"- **model:** `{model}`",
        f"- **synthetic:** `{str(synthetic).lower()}`",
        f"- **synthetic_reason:** {reason}",
    ]
    # Surface the run shape when present.
    extras = []
    for key, label in (
        ("frameworks", "frameworks"),
        ("specs", "specs"),
        ("n_questions", "questions"),
        ("n_runs", "runs"),
        ("personas_used", "personas_used"),
    ):
        if key in meta:
            val = meta[key]
            if isinstance(val, list):
                val = ", ".join(str(x) for x in val)
            extras.append(f"- **{label}:** {val}")
    lines += extras
    lines.append("")
    return lines


def _render_table(summary: dict) -> list[str]:
    """Render the MAIN metrics table — one row per group."""
    header_cells = ["group"] + [h for _, h, _ in _TABLE_COLUMNS]
    sep_cells = ["---"] * len(header_cells)
    lines = [
        "## Metrics by group",
        "",
        "| " + " | ".join(header_cells) + " |",
        "| " + " | ".join(sep_cells) + " |",
    ]
    # Stable, deterministic row order: sorted group names.
    for group in sorted(summary):
        m = summary[group]
        cells = [f"`{group}`"]
        for key, _h, fmt in _TABLE_COLUMNS:
            val = m.get(key)
            cells.append("—" if val is None else fmt(val))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _render_what_this_shows(meta: dict, summary: dict) -> list[str]:
    """
    Render a "what this shows" paragraph from the ACTUAL summary numbers.

    Reads the values out of ``summary`` and narrates the cross-group contrast.
    When the backend is fake, the contrast is explicitly attributed to the
    deterministic FakeLLM, not to a real framework difference.
    """
    lines = ["## What this shows", ""]
    if not summary:
        lines += ["No groups were present in the results document.", ""]
        return lines

    synthetic = bool(meta.get("synthetic"))
    backend = meta.get("backend", "unknown")

    # Pull the headline contrasts straight from the numbers.
    gate = {g: summary[g].get("gate_rate", 0.0) for g in summary}
    iters = {g: summary[g].get("mean_iterations", 0.0) for g in summary}
    judge = {g: summary[g].get("judge_pass_rate", 0.0) for g in summary}
    tin = {g: summary[g].get("mean_tokens_in", 0.0) for g in summary}

    hi_gate = max(gate, key=gate.get)
    lo_gate = min(gate, key=gate.get)
    lo_iter = min(iters, key=iters.get)

    parts: list[str] = []
    if abs(gate[hi_gate] - gate[lo_gate]) > 1e-9:
        parts.append(
            f"`{hi_gate}` hits the success gate more often "
            f"({gate[hi_gate]:.2f}) than `{lo_gate}` ({gate[lo_gate]:.2f}), "
            f"and reaches it in fewer iterations "
            f"({iters[lo_iter]:.2f} mean for `{lo_iter}`)"
        )
    else:
        parts.append(
            f"all groups share the same gate rate ({gate[hi_gate]:.2f})"
        )

    # Judge pass rate is identical across groups under FakeLLM (same answers
    # → same deterministic grade); say so rather than implying a finding.
    judge_vals = set(round(v, 6) for v in judge.values())
    if len(judge_vals) == 1:
        only = next(iter(judge.values()))
        parts.append(
            f"judge pass-rate is identical across every group ({only:.2f})"
        )
    else:
        hi_j = max(judge, key=judge.get)
        parts.append(
            f"`{hi_j}` has the highest judge pass-rate ({judge[hi_j]:.2f})"
        )

    sentence = "; ".join(parts) + "."
    lines.append(sentence)
    lines.append("")

    if synthetic and backend == "fake":
        # Token-in differs by group only because FakeLLM emits a fixed token
        # count per call and groups differ in how many iterations (and hence
        # calls) they run — an artefact, not a model measurement.
        lo_t = min(tin, key=tin.get)
        hi_t = max(tin, key=tin.get)
        lines.append(
            "**Read this as a workflow demonstration, not a benchmark.** "
            "Under the deterministic FakeLLM backend every model call returns a "
            "fixed canned answer with fixed token counts, so the cross-group "
            "differences above are artefacts of how many loop iterations each "
            "adapter's termination path takes, not of model quality. For "
            f"example `{hi_t}`'s higher `mean_tokens_in` ({tin[hi_t]:.1f} vs. "
            f"{tin[lo_t]:.1f} for `{lo_t}`) reflects extra FakeLLM loop turns, "
            "not a real token-cost gap. The shape of the table — one measured "
            "row per framework, an honesty flag, and defaults justified against "
            "it — is the deliverable; swap a real client in behind the "
            "`LLMClient` seam to populate it with genuine numbers."
        )
    else:
        lines.append(
            "These are real-model measurements; see the limitations note for "
            "the scope (corpus size, task count) within which they hold."
        )
    lines.append("")
    return lines


def _render_defaults_note() -> list[str]:
    """Render the note tying the report back to the blended defaults."""
    return [
        "## How this justifies the blended defaults",
        "",
        "The blended defaults live in `porcelain/types.py` "
        "(`TerminationPolicy`: `max_iterations`, `timeout_s`, `max_retries`, "
        "`success_gate`) and `porcelain/retrieval.py` (`search(k=4)`). Each "
        "carries a comment pointing back to this report. **Because the current "
        "numbers are synthetic, those comments DEMONSTRATE the "
        "measure-then-standardize workflow — they are not tuned production "
        "values.** When a real backend populates this table, the same comments "
        "become the audit trail from a chosen default to the run that justified "
        "it.",
        "",
    ]


def _render_limitations(meta: dict) -> list[str]:
    """Render the honest limitations footer."""
    return [
        "## Limitations",
        "",
        "- **Two frameworks only** (LangGraph, CrewAI) — not a survey of the "
        "ecosystem.",
        "- **Tiny fictional corpus** and a **single task shape** (RAG-over-docs "
        "Q&A) — not a representative workload.",
        "- **Synthetic / persona numbers** when `synthetic` is true: the model "
        "behind the seam is FakeLLM (or Claude wearing another product's "
        "persona prompt, labelled `claude-as-<persona>`), so this is **NOT a "
        "vendor benchmark** of any model against another.",
        "- The value here is the **platform and the workflow** — pluggable "
        "adapters, a measured eval harness, and defaults justified by that "
        "measurement — not the specific numbers in this run.",
        "",
    ]


def render_markdown(doc: dict) -> str:
    """
    Render the full ``results.md`` body from a results document.

    Parameters
    ----------
    doc : dict
        The ``{meta, runs, summary}`` document loaded from results.json.

    Returns
    -------
    str
        The complete Markdown report.
    """
    meta = doc.get("meta", {})
    summary = doc.get("summary", {})

    lines: list[str] = [
        "# agent-bench — measurement report",
        "",
        f"> {THESIS}",
        "",
    ]
    lines += _render_banner(meta)
    lines += _render_table(summary)
    lines += _render_what_this_shows(meta, summary)
    lines += _render_defaults_note()
    lines += _render_limitations(meta)

    return "\n".join(lines).rstrip() + "\n"


def write_report(doc: dict, out_path: str | Path) -> Path:
    """Render *doc* and write it to *out_path*; return the path written."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(doc))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="report.build",
        description=(
            "Render evalkit/results.json into report/results.md "
            "(metrics table + provenance banner)."
        ),
    )
    parser.add_argument(
        "--results", type=str, default=str(_DEFAULT_RESULTS),
        help="Path to results.json (default: evalkit/results.json).",
    )
    parser.add_argument(
        "--out", type=str, default=str(_DEFAULT_OUT),
        help="Output path for the report (default: report/results.md).",
    )
    parser.add_argument(
        "--no-autorun", action="store_true",
        help="Fail instead of auto-running evalkit.run when results.json is absent.",
    )
    args = parser.parse_args(argv)

    try:
        doc = load_results(args.results, autorun=not args.no_autorun)
    except FileNotFoundError as exc:
        print(f"report.build: {exc}", file=sys.stderr)
        return 2

    out = write_report(doc, args.out)
    groups = sorted(doc.get("summary", {}))
    meta = doc.get("meta", {})
    print(
        f"Wrote {out} — {len(groups)} group row(s): {', '.join(groups)} "
        f"(backend={meta.get('backend')}, synthetic={meta.get('synthetic')})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
