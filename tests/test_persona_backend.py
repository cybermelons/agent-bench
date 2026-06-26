"""
tests.test_persona_backend — Phase 1.5 persona/claude_code backend coverage.

Three concerns, all green offline:

1. Prompt COMPOSITION — :class:`ClaudeCodeClient` prepends the persona text and
   passes the expected argv to ``subprocess.run``.  ``subprocess.run`` is
   monkeypatched to capture argv; NO real ``claude`` process is started.
2. Real-claude INTEGRATION — one end-to-end shell-out, decorated
   ``pytest.mark.skipif`` on the real binary being absent so it stays SKIPPED by
   default and the suite exits 0 offline.
3. Spec backward-compat — :class:`AgentSpec` loads with and without the new
   optional ``persona`` field.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from porcelain.llm import ClaudeCodeClient, LLMResponse
from porcelain.runner import load_persona
from porcelain.types import AgentSpec

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CLAUDE_BINARY = "/Users/cybermelon/.nvm/versions/node/v23.8.0/bin/claude"


# ---------------------------------------------------------------------------
# 1. Prompt composition (monkeypatched subprocess — no real claude call)
# ---------------------------------------------------------------------------

class _FakeProc:
    """Stand-in for subprocess.CompletedProcess."""

    def __init__(self, stdout: str = "PERSONA ANSWER", returncode: int = 0,
                 stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_persona_text_is_prepended_to_prompt(monkeypatch):
    """The composed prompt contains persona text, system text, and user text,
    and the argv is exactly [binary, -p, prompt, --max-turns, 1]."""
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _FakeProc(stdout="  composed ok  ")

    monkeypatch.setattr("porcelain.llm.subprocess.run", fake_run)

    persona = "ACT-LIKE-CURSOR persona system prompt."
    client = ClaudeCodeClient(binary=_CLAUDE_BINARY, persona_prompt=persona)

    resp = client.complete(
        system="GROUNDING SYSTEM RULES",
        messages=[{"role": "user", "content": "What is the on-call stipend?"}],
        model="ignored-model-id",
    )

    argv = captured["argv"]
    # argv structure
    assert argv[0] == _CLAUDE_BINARY
    assert argv[1] == "-p"
    assert argv[3:] == ["--max-turns", "1"]

    prompt = argv[2]
    # persona + system + user all present, persona first
    assert persona in prompt
    assert "GROUNDING SYSTEM RULES" in prompt
    assert "What is the on-call stipend?" in prompt
    assert prompt.index(persona) < prompt.index("GROUNDING SYSTEM RULES")
    assert prompt.index("GROUNDING SYSTEM RULES") < prompt.index("What is the on-call stipend?")

    # capture_output / text were requested
    assert captured["kwargs"].get("capture_output") is True
    assert captured["kwargs"].get("text") is True

    # response: stripped text + estimated tokens
    assert isinstance(resp, LLMResponse)
    assert resp.text == "composed ok"
    assert resp.tokens_in == len(prompt) // 4
    assert resp.tokens_out == len("composed ok") // 4


def test_no_persona_prompt_omits_persona_section(monkeypatch):
    """Without a persona, the prompt is just system + user (no leading None)."""
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _FakeProc(stdout="ok")

    monkeypatch.setattr("porcelain.llm.subprocess.run", fake_run)

    client = ClaudeCodeClient(binary=_CLAUDE_BINARY, persona_prompt=None)
    client.complete(
        system="SYS",
        messages=[{"role": "user", "content": "USERTEXT"}],
        model="m",
    )
    prompt = captured["argv"][2]
    assert prompt == "SYS\n\nUSERTEXT"
    assert "None" not in prompt


def test_nonzero_exit_raises_runtime_error(monkeypatch):
    def fake_run(argv, **kwargs):
        return _FakeProc(stdout="", returncode=2, stderr="boom")

    monkeypatch.setattr("porcelain.llm.subprocess.run", fake_run)
    client = ClaudeCodeClient(binary=_CLAUDE_BINARY)
    with pytest.raises(RuntimeError, match="exited 2"):
        client.complete(system="s", messages=[{"role": "user", "content": "q"}], model="m")


def test_timeout_raises_runtime_error(monkeypatch):
    import subprocess as _sp

    def fake_run(argv, **kwargs):
        raise _sp.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr("porcelain.llm.subprocess.run", fake_run)
    client = ClaudeCodeClient(binary=_CLAUDE_BINARY, timeout_s=1)
    with pytest.raises(RuntimeError, match="timed out"):
        client.complete(system="s", messages=[{"role": "user", "content": "q"}], model="m")


def test_json_usage_real_counts(monkeypatch):
    """With use_json_usage=True and a parseable JSON usage block, real counts win."""
    import json as _json

    payload = _json.dumps({
        "result": "  json answer  ",
        "usage": {"input_tokens": 123, "output_tokens": 45},
    })

    def fake_run(argv, **kwargs):
        # argv should include the json output flag
        assert "--output-format" in argv and "json" in argv
        return _FakeProc(stdout=payload)

    monkeypatch.setattr("porcelain.llm.subprocess.run", fake_run)
    client = ClaudeCodeClient(binary=_CLAUDE_BINARY, use_json_usage=True)
    resp = client.complete(system="s", messages=[{"role": "user", "content": "q"}], model="m")
    assert resp.text == "json answer"
    assert resp.tokens_in == 123
    assert resp.tokens_out == 45


def test_json_usage_falls_back_to_estimate(monkeypatch):
    """Unparseable JSON falls back to the char-based estimate, not a crash."""
    def fake_run(argv, **kwargs):
        return _FakeProc(stdout="not json at all")

    monkeypatch.setattr("porcelain.llm.subprocess.run", fake_run)
    client = ClaudeCodeClient(binary=_CLAUDE_BINARY, use_json_usage=True)
    resp = client.complete(system="s", messages=[{"role": "user", "content": "q"}], model="m")
    assert resp.text == "not json at all"
    assert resp.tokens_out == len("not json at all") // 4


# ---------------------------------------------------------------------------
# 1b. Persona loading from disk
# ---------------------------------------------------------------------------

def test_load_persona_reads_file():
    text = load_persona("claude-code")
    assert text is not None and len(text) > 0


def test_load_persona_none_returns_none():
    assert load_persona(None) is None


def test_load_persona_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_persona("this-persona-does-not-exist")


# ---------------------------------------------------------------------------
# 2. Real-claude integration — SKIPPED unless the real binary is present
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1" or not os.path.exists(_CLAUDE_BINARY),
    reason="live test: set RUN_LIVE=1 (and have the real claude binary) to run "
    "this real shell-out; gated on RUN_LIVE so it stays a skip by default",
)
def test_real_claude_shellout_smoke():
    client = ClaudeCodeClient(binary=_CLAUDE_BINARY, timeout_s=120)
    resp = client.complete(
        system="Reply with a single word.",
        messages=[{"role": "user", "content": "Say the word OK and nothing else."}],
        model="ignored",
    )
    assert isinstance(resp, LLMResponse)
    assert resp.text != ""
    # tokens_in is a len(prompt)//4 ESTIMATE; the prompt is non-trivial so > 0.
    assert resp.tokens_in > 0
    # tokens_out is len(text)//4; a 1-2 char reply ("OK") floors to 0 under the
    # estimate. Assert the contract (>= 0 and consistent with the heuristic)
    # rather than > 0, which would be false for tiny but valid outputs.
    assert resp.tokens_out == len(resp.text) // 4
    assert resp.tokens_out >= 0


# ---------------------------------------------------------------------------
# 3. AgentSpec backward compat with the optional persona field
# ---------------------------------------------------------------------------

def test_agentspec_without_persona_defaults_none():
    spec = AgentSpec(name="lg", framework="langgraph", corpus="corpus")
    assert spec.persona is None


def test_agentspec_with_persona_field():
    spec = AgentSpec(
        name="lg-cursor",
        framework="langgraph",
        corpus="corpus",
        persona="cursor",
    )
    assert spec.persona == "cursor"


def test_agentspec_from_yaml_with_persona(tmp_path):
    yaml_path = tmp_path / "spec.yaml"
    yaml_path.write_text(
        "name: lg-openai\n"
        "framework: langgraph\n"
        "corpus: corpus\n"
        "persona: openai-chatgpt\n"
    )
    spec = AgentSpec.from_yaml(yaml_path)
    assert spec.persona == "openai-chatgpt"
