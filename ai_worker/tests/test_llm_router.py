"""Tests for the multi-provider LLM router.

All tests use mock LM objects — no real API calls are made.
"""

import json
from typing import Any

import pytest

import ai_worker.llm_router as router
from ai_worker.llm_router import _build_chain, _FallbackLM, get_lm

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockLM:
    """Minimal dspy.LM stand-in for isolation tests."""

    def __init__(
        self,
        model: str,
        raises: Exception | None = None,
        result: Any = None,
    ) -> None:
        self.model = model
        self._raises = raises
        self._result = result
        self.call_count = 0
        self.history: list[Any] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.call_count += 1
        if self._raises is not None:
            raise self._raises
        return self._result


@pytest.fixture(autouse=True)
def _clear_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests from the module-level singleton caches."""
    monkeypatch.setattr(router, "_singletons", {})
    monkeypatch.setattr(router, "_lm_cache", {})


# ---------------------------------------------------------------------------
# Default role → model mapping
# ---------------------------------------------------------------------------


def test_get_lm_qualifier_returns_haiku_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []

    def _fake_build(model: str) -> _MockLM:
        built.append(model)
        return _MockLM(model)

    monkeypatch.setattr(router, "_get_or_build_lm", _fake_build)
    lm = get_lm("qualifier")
    assert "haiku" in lm.model.lower()
    assert built[0] == router._DEFAULTS["qualifier"][0]


def test_get_lm_email_returns_sonnet_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []

    def _fake_build(model: str) -> _MockLM:
        built.append(model)
        return _MockLM(model)

    monkeypatch.setattr(router, "_get_or_build_lm", _fake_build)
    lm = get_lm("email")
    assert "sonnet" in lm.model.lower()
    assert built[0] == router._DEFAULTS["email"][0]


# ---------------------------------------------------------------------------
# Singleton behaviour
# ---------------------------------------------------------------------------


def test_get_lm_returns_same_object_on_repeated_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router, "_get_or_build_lm", lambda m: _MockLM(m))
    lm1 = get_lm("qualifier")
    lm2 = get_lm("qualifier")
    assert lm1 is lm2


def test_qualifier_and_email_are_distinct_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router, "_get_or_build_lm", lambda m: _MockLM(m))
    assert get_lm("qualifier") is not get_lm("email")


# ---------------------------------------------------------------------------
# Fallback chain — tested directly on _FallbackLM
# ---------------------------------------------------------------------------


def test_fallback_chain_calls_secondary_on_primary_failure() -> None:
    primary = _MockLM("primary", raises=RuntimeError("rate limited"))
    secondary = _MockLM("secondary", result=["answer"])
    chain = _FallbackLM([primary, secondary], retryable=(RuntimeError,))

    result = chain("prompt")

    assert primary.call_count == 1
    assert secondary.call_count == 1
    assert result == ["answer"]


def test_fallback_chain_logs_fallback_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    primary = _MockLM("primary-model", raises=RuntimeError("boom"))
    secondary = _MockLM("secondary-model", result=["ok"])
    chain = _FallbackLM([primary, secondary], retryable=(RuntimeError,))

    chain("prompt")

    captured = capsys.readouterr()
    log = json.loads(captured.err.strip())
    assert log["event"] == "llm_fallback"
    assert log["from_model"] == "primary-model"
    assert log["to_model"] == "secondary-model"
    assert log["reason"] == "RuntimeError"


def test_fallback_chain_reraises_when_all_providers_fail() -> None:
    primary = _MockLM("p1", raises=RuntimeError("p1 fail"))
    secondary = _MockLM("p2", raises=RuntimeError("p2 fail"))
    chain = _FallbackLM([primary, secondary], retryable=(RuntimeError,))

    with pytest.raises(RuntimeError, match="p2 fail"):
        chain("prompt")

    assert primary.call_count == 1
    assert secondary.call_count == 1


def test_fallback_chain_does_not_catch_non_retryable_errors() -> None:
    primary = _MockLM("p1", raises=ValueError("bad input"))
    secondary = _MockLM("p2", result=["ok"])
    chain = _FallbackLM([primary, secondary], retryable=(RuntimeError,))

    with pytest.raises(ValueError, match="bad input"):
        chain("prompt")

    assert primary.call_count == 1
    assert secondary.call_count == 0  # never reached


def test_fallback_chain_succeeds_on_first_try_when_primary_works() -> None:
    primary = _MockLM("p1", result=["primary answer"])
    secondary = _MockLM("p2", result=["fallback answer"])
    chain = _FallbackLM([primary, secondary], retryable=(RuntimeError,))

    result = chain("prompt")

    assert result == ["primary answer"]
    assert primary.call_count == 1
    assert secondary.call_count == 0


# ---------------------------------------------------------------------------
# Env var overrides
# ---------------------------------------------------------------------------


def test_qualifier_model_env_var_overrides_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUALIFIER_MODEL", "openai/gpt-4o")
    built: list[str] = []

    def _fake_build(model: str) -> _MockLM:
        built.append(model)
        return _MockLM(model)

    monkeypatch.setattr(router, "_get_or_build_lm", _fake_build)
    chain = _build_chain("qualifier")

    assert built[0] == "openai/gpt-4o"
    assert chain.model == "openai/gpt-4o"
    # Fallbacks remain unchanged
    assert built[1] == router._DEFAULTS["qualifier"][1]
    assert built[2] == router._DEFAULTS["qualifier"][2]


def test_email_model_env_var_overrides_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_MODEL", "anthropic/claude-opus-4-8")
    built: list[str] = []

    def _fake_build(model: str) -> _MockLM:
        built.append(model)
        return _MockLM(model)

    monkeypatch.setattr(router, "_get_or_build_lm", _fake_build)
    chain = _build_chain("email")

    assert built[0] == "anthropic/claude-opus-4-8"
    assert chain.model == "anthropic/claude-opus-4-8"


def test_env_var_not_set_uses_default_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUALIFIER_MODEL", raising=False)
    built: list[str] = []

    def _fake_build(model: str) -> _MockLM:
        built.append(model)
        return _MockLM(model)

    monkeypatch.setattr(router, "_get_or_build_lm", _fake_build)
    _build_chain("qualifier")

    assert built[0] == router._DEFAULTS["qualifier"][0]


# ---------------------------------------------------------------------------
# _FallbackLM.model property
# ---------------------------------------------------------------------------


def test_fallback_lm_model_reflects_primary() -> None:
    primary = _MockLM("anthropic/claude-haiku-4-5-20251001")
    secondary = _MockLM("gemini/gemini-2.5-flash")
    chain = _FallbackLM([primary, secondary])
    assert chain.model == "anthropic/claude-haiku-4-5-20251001"
