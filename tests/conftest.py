"""
tests.conftest — shared fixtures for the agent-bench test suite.

Provides:
* ``repo_root`` / ``corpus_path`` — filesystem anchors (absolute, cwd-independent).
* ``retriever`` — a built :class:`CorpusRetriever` over the checked-in corpus.
* ``fake_llm`` — a default offline :class:`FakeLLM`.
* ``golden`` — the parsed list of 11 golden Q/A dicts from corpus/golden.yaml.

All fixtures are offline and free; nothing here touches the network or needs an
API key.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from porcelain.llm import FakeLLM
from porcelain.retrieval import CorpusRetriever

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return _REPO_ROOT


@pytest.fixture(scope="session")
def corpus_path(repo_root: Path) -> str:
    """Absolute path to the checked-in corpus directory, as a string."""
    return str(repo_root / "corpus")


@pytest.fixture
def retriever(corpus_path: str) -> CorpusRetriever:
    """A CorpusRetriever built over the checked-in corpus."""
    return CorpusRetriever(corpus_path)


@pytest.fixture
def fake_llm() -> FakeLLM:
    """A default, offline, deterministic FakeLLM."""
    return FakeLLM()


@pytest.fixture(scope="session")
def golden(repo_root: Path) -> list[dict]:
    """The 11 golden Q/A entries from corpus/golden.yaml."""
    raw = yaml.safe_load((repo_root / "corpus" / "golden.yaml").read_text())
    return raw["questions"]
