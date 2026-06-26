"""
tests.test_phase4 — the reporting layer, fully offline.

Three things are proven, all keyless/offline (FakeLLM):

(a) ``report.build`` run against a results.json (generated here by the subset
    eval) writes ``results.md``;
(b) the rendered ``results.md`` contains a metrics TABLE with BOTH a 'langgraph'
    row and a 'crewai' row;
(c) the SYNTHETIC banner appears whenever ``meta.synthetic`` is true, and is
    absent (replaced by the real-measurement wording) when it is false.

Nothing here touches the network or needs an API key.
"""

from __future__ import annotations

import json
import os

from evalkit import run as evalrun
from report import build as reportbuild

# Keep any CrewAI path quiet/offline.
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")


# ---------------------------------------------------------------------------
# (a) report.build writes results.md from a real subset eval
# ---------------------------------------------------------------------------

def test_report_build_writes_results_md(tmp_path):
    results = tmp_path / "results.json"
    out = tmp_path / "results.md"

    rc = evalrun.main(["--subset", "2", "--backend", "fake", "--out", str(results)])
    assert rc == 0
    assert results.is_file()

    rc2 = reportbuild.main(["--results", str(results), "--out", str(out)])
    assert rc2 == 0
    assert out.is_file()

    text = out.read_text()
    # Thesis line is present.
    assert "earns the right to standardize" in text
    # Title present.
    assert "agent-bench" in text


# ---------------------------------------------------------------------------
# (b) rendered table has BOTH framework rows
# ---------------------------------------------------------------------------

def test_results_md_table_has_both_framework_rows(tmp_path):
    results = tmp_path / "results.json"
    out = tmp_path / "results.md"
    evalrun.main(["--subset", "2", "--backend", "fake", "--out", str(results)])
    reportbuild.main(["--results", str(results), "--out", str(out)])

    text = out.read_text()

    # There must be a Markdown table header row with the metric columns.
    assert "| group |" in text
    assert "gate_rate" in text
    assert "cited_expected_rate" in text
    assert "judge_pass_rate" in text
    assert "mean_latency_s" in text
    assert "mean_tokens_in" in text
    assert "mean_tokens_out" in text
    assert "mean_iterations" in text

    # Locate table rows (lines starting with "| `") and confirm both groups.
    row_lines = [ln for ln in text.splitlines() if ln.strip().startswith("| `")]
    rows_joined = "\n".join(row_lines)
    assert "`langgraph`" in rows_joined
    assert "`crewai`" in rows_joined

    # Each framework must own a dedicated table row.
    assert any("`langgraph`" in ln for ln in row_lines)
    assert any("`crewai`" in ln for ln in row_lines)

    # The per-group synthetic flag is visible in the table (its own column).
    assert "synthetic?" in text


# ---------------------------------------------------------------------------
# (c) synthetic banner gated on meta.synthetic
# ---------------------------------------------------------------------------

def test_synthetic_banner_appears_when_meta_synthetic(tmp_path):
    results = tmp_path / "results.json"
    out = tmp_path / "results.md"
    evalrun.main(["--subset", "2", "--backend", "fake", "--out", str(results)])

    # Sanity: the subset/fake run is flagged synthetic.
    doc = json.loads(results.read_text())
    assert doc["meta"]["synthetic"] is True

    reportbuild.main(["--results", str(results), "--out", str(out)])
    text = out.read_text()

    assert "DEMONSTRATION numbers, NOT a real-model benchmark" in text
    assert "Provenance & honesty" in text


def test_no_synthetic_banner_when_meta_not_synthetic(tmp_path):
    """A non-synthetic fixture renders the real-measurement wording, not the warning."""
    fixture = {
        "meta": {
            "backend": "anthropic",
            "model": "claude-3-5-sonnet-latest",
            "synthetic": False,
            "synthetic_reason": None,
            "frameworks": ["crewai", "langgraph"],
            "specs": ["langgraph-baseline", "crewai-baseline"],
            "n_questions": 2,
            "n_runs": 4,
            "personas_used": False,
        },
        "runs": [],
        "summary": {
            "langgraph": {
                "synthetic": False, "backend": "anthropic", "n": 2,
                "gate_rate": 0.5, "cited_expected_rate": 0.5,
                "mean_answer_contains": 0.5, "judge_pass_rate": 0.5,
                "mean_judge_score": 0.4, "mean_latency_s": 1.2,
                "mean_tokens_in": 350.0, "mean_tokens_out": 70.0,
                "mean_iterations": 3.5,
            },
            "crewai": {
                "synthetic": False, "backend": "anthropic", "n": 2,
                "gate_rate": 1.0, "cited_expected_rate": 0.5,
                "mean_answer_contains": 0.5, "judge_pass_rate": 0.5,
                "mean_judge_score": 0.4, "mean_latency_s": 0.9,
                "mean_tokens_in": 100.0, "mean_tokens_out": 20.0,
                "mean_iterations": 1.0,
            },
        },
    }
    results = tmp_path / "results.json"
    out = tmp_path / "results.md"
    results.write_text(json.dumps(fixture))

    reportbuild.main(["--results", str(results), "--out", str(out)])
    text = out.read_text()

    assert "DEMONSTRATION numbers, NOT a real-model benchmark" not in text
    assert "real-model measurements" in text
    # Both framework rows still render from the fixture summary.
    assert "`langgraph`" in text
    assert "`crewai`" in text


# ---------------------------------------------------------------------------
# (d) standalone auto-run: missing results.json regenerates it
# ---------------------------------------------------------------------------

def test_report_build_autoruns_when_results_missing(tmp_path):
    results = tmp_path / "missing-results.json"
    out = tmp_path / "results.md"
    assert not results.is_file()

    rc = reportbuild.main(["--results", str(results), "--out", str(out)])
    assert rc == 0
    # Auto-run created the results file and the report.
    assert results.is_file()
    assert out.is_file()
    text = out.read_text()
    assert "`langgraph`" in text
    assert "`crewai`" in text


def test_report_build_no_autorun_fails_clearly(tmp_path):
    results = tmp_path / "missing-results.json"
    out = tmp_path / "results.md"
    rc = reportbuild.main(
        ["--results", str(results), "--out", str(out), "--no-autorun"]
    )
    assert rc == 2
    assert not out.is_file()
