"""
porcelain.retrieval — shared BM25 retriever for agent-bench.

This module is the single source-of-truth retriever used by BOTH framework
adapters (LangGraph, CrewAI).  By holding retrieval constant — same index,
same BM25 parameters, same chunking strategy — benchmark comparisons isolate
orchestration-framework differences from retrieval-quality differences.

Design constraints
------------------
* No framework-specific imports.  Pure Python + rank_bm25.  Adapters import
  this module; this module knows nothing about adapters.
* Deterministic: same corpus + same query → same ranked results every time.
  BM25Okapi is deterministic given fixed input order; we sort glob results by
  name to lock that order.
* doc_id convention: filename stem (e.g. "oncall-policy" for oncall-policy.md),
  matching the Citation.doc_id contract in porcelain.types.

Chunking strategy
-----------------
Fixed sliding windows of ~150 words with a 30-word overlap, split on
whitespace tokens.  This is simple, deterministic, and avoids the edge case
where a single large document produces one huge chunk that drowns out other
documents in BM25 scoring.  Markdown heading lines are kept inline (not
stripped) so heading keywords are naturally searchable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from rank_bm25 import BM25Okapi


# ---------------------------------------------------------------------------
# RetrievedChunk
# ---------------------------------------------------------------------------

@dataclass
class RetrievedChunk:
    """
    A single retrieved passage from the corpus.

    Attributes
    ----------
    doc_id : str
        Filename stem of the source document (e.g. "oncall-policy").
    text : str
        Raw text of this passage as it appears in the corpus file.
    score : float
        BM25Okapi relevance score for the query that produced this chunk.
        Higher is more relevant.  Scores are not normalized; use them for
        ranking only, not as probabilities.
    """

    doc_id: str
    text: str
    score: float


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """
    Lowercase and split on non-alphanumeric characters.

    Used both at index time (chunk tokenization) and at query time so that
    BM25 term frequencies are computed consistently.
    """
    return re.split(r"[^a-z0-9]+", text.lower())


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 150    # target words per chunk
_OVERLAP = 30        # overlap words between consecutive chunks

def _chunk_document(text: str, doc_id: str) -> list[tuple[str, str]]:
    """
    Split *text* into overlapping fixed-size word windows.

    Returns a list of (doc_id, chunk_text) pairs.  Each chunk is at most
    CHUNK_SIZE words; consecutive chunks overlap by OVERLAP words so that
    sentences straddling a boundary are represented in both adjacent chunks.

    If the entire document is shorter than CHUNK_SIZE words, it is returned
    as a single chunk.
    """
    words = text.split()
    if len(words) <= _CHUNK_SIZE:
        return [(doc_id, text)]

    chunks: list[tuple[str, str]] = []
    step = _CHUNK_SIZE - _OVERLAP
    for start in range(0, len(words), step):
        end = start + _CHUNK_SIZE
        chunk_words = words[start:end]
        chunks.append((doc_id, " ".join(chunk_words)))
        if end >= len(words):
            break
    return chunks


# ---------------------------------------------------------------------------
# CorpusRetriever
# ---------------------------------------------------------------------------

class CorpusRetriever:
    """
    BM25-based retriever over a directory of Markdown corpus files.

    Both the LangGraph and CrewAI adapters instantiate one shared
    CorpusRetriever at startup.  Retrieval is then fixed for the entire
    benchmark run — framework comparisons reflect orchestration quality,
    not retrieval quality.

    Parameters
    ----------
    corpus_dir : str
        Path to a directory containing ``*.md`` corpus files.  All files
        found at ``*.md`` (non-recursive) are indexed.  Files are loaded in
        sorted filename order to guarantee a deterministic chunk sequence.

    Raises
    ------
    FileNotFoundError
        If *corpus_dir* does not exist or contains no ``*.md`` files.
    """

    def __init__(self, corpus_dir: str) -> None:
        corpus_path = Path(corpus_dir)
        md_files = sorted(corpus_path.glob("*.md"))  # sorted → deterministic
        if not md_files:
            raise FileNotFoundError(
                f"No *.md files found in corpus directory: {corpus_dir!r}"
            )

        # Build flat list of (doc_id, chunk_text) pairs and parallel token list
        self._chunks: list[tuple[str, str]] = []
        for md_file in md_files:
            doc_id = md_file.stem
            text = md_file.read_text(encoding="utf-8")
            self._chunks.extend(_chunk_document(text, doc_id))

        # BM25 index over tokenized chunks — deterministic given fixed chunk order
        tokenized = [_tokenize(chunk_text) for _, chunk_text in self._chunks]
        self._bm25 = BM25Okapi(tokenized)

        # Materialise the doc_id set once
        self._doc_ids: set[str] = {doc_id for doc_id, _ in self._chunks}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def doc_ids(self) -> set[str]:
        """The set of all doc_ids present in the loaded corpus."""
        return self._doc_ids

    def search(self, query: str, k: int = 4) -> List[RetrievedChunk]:
        """
        Return the top-*k* chunks most relevant to *query* by BM25 score.

        Parameters
        ----------
        query : str
            Natural-language query string.  Tokenized with the same
            :func:`_tokenize` function used at index time.
        k : int
            Number of chunks to return (default 4).  If fewer chunks exist
            in the index, all chunks are returned.

            PROVENANCE of the ``k=4`` blended default: the trade-off between
            recall (higher k → more chance the expected doc is in context, see
            ``cited_expected_rate`` in report/results.md) and prompt cost
            (higher k → more ``mean_tokens_in``) is what the report measures
            per group.  HONESTY CAVEAT — the numbers in report/results.md are
            currently SYNTHETIC (FakeLLM backend), so ``k=4`` DEMONSTRATES the
            measure-then-standardize workflow; it is NOT a real-model-tuned
            value.  Re-run ``evalkit.run`` + ``report.build`` behind a real
            ``LLMClient`` to turn this into a measured choice.

        Returns
        -------
        list[RetrievedChunk]
            Ranked from highest to lowest BM25 score.
        """
        tokens = _tokenize(query)
        scores: list[float] = self._bm25.get_scores(tokens).tolist()

        # Pair each chunk with its score, sort descending, take top-k
        ranked = sorted(
            zip(scores, self._chunks),
            key=lambda x: x[0],
            reverse=True,
        )[:k]

        return [
            RetrievedChunk(doc_id=doc_id, text=chunk_text, score=score)
            for score, (doc_id, chunk_text) in ranked
        ]

    def format_context(self, chunks: List[RetrievedChunk]) -> str:
        """
        Render retrieved chunks as a prompt-ready context block.

        Each chunk is labelled with its doc_id so that the LLM can cite
        sources using ``Citation(doc_id=...)`` from ``porcelain.types``.

        Format::

            [doc_id: oncall-policy]
            <chunk text>

            [doc_id: deploy-staging]
            <chunk text>

        Parameters
        ----------
        chunks : list[RetrievedChunk]
            Chunks to render, typically the output of :meth:`search`.

        Returns
        -------
        str
            A single string ready for injection into a prompt.
        """
        parts: list[str] = []
        for chunk in chunks:
            parts.append(f"[doc_id: {chunk.doc_id}]\n{chunk.text}")
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Resolve corpus/ relative to this file's parent (repo root)
    repo_root = Path(__file__).parent.parent
    corpus_dir = str(repo_root / "corpus")

    print(f"Loading corpus from: {corpus_dir}")
    retriever = CorpusRetriever(corpus_dir)

    print(f"\ndoc_ids ({len(retriever.doc_ids)}):")
    for doc_id in sorted(retriever.doc_ids):
        print(f"  {doc_id}")

    assert len(retriever.doc_ids) == 7, (
        f"Expected 7 doc_ids, got {len(retriever.doc_ids)}"
    )

    query = "on-call stipend"
    results = retriever.search(query, k=4)
    print(f"\nTop-4 results for {query!r}:")
    for i, chunk in enumerate(results, 1):
        preview = chunk.text[:80].replace("\n", " ")
        print(f"  {i}. doc_id={chunk.doc_id!r}  score={chunk.score:.4f}  text={preview!r}...")

    top = results[0]
    assert top.doc_id == "oncall-policy", (
        f"Expected top hit 'oncall-policy', got {top.doc_id!r}"
    )

    print(f"\nformat_context sample (first 2 chunks):")
    print(retriever.format_context(results[:2]))

    print("\nAll assertions passed.")
    sys.exit(0)
