"""Multi-provider LLM router with per-role model selection and fallback.

Returns dspy.LM-compatible objects. Callers must use dspy.context(lm=lm) per
prediction — never dspy.configure() (CLAUDE.md §11 anti-pattern #1).
"""

import json
import os
import sys
import threading
from typing import Any, Literal

import dspy
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_none

_Role = Literal["qualifier", "email"]

# LiteLLM-specific exceptions trigger fallback; everything else propagates immediately.
try:
    from litellm.exceptions import APIError as _LiteLLMAPIError
    from litellm.exceptions import RateLimitError as _LiteLLMRateLimitError

    _DEFAULT_RETRYABLE: tuple[type[Exception], ...] = (
        _LiteLLMRateLimitError,
        _LiteLLMAPIError,
    )
except Exception:  # pragma: no cover — litellm always bundled with dspy-ai
    _DEFAULT_RETRYABLE = (Exception,)

# Primary + fallback model strings in LiteLLM provider/model format.
_DEFAULTS: dict[str, list[str]] = {
    "qualifier": [
        "anthropic/claude-haiku-4-5-20251001",
        "gemini/gemini-2.5-flash",
        "openai/gpt-4.1-nano",
    ],
    "email": [
        "anthropic/claude-sonnet-4-6",
        "gemini/gemini-2.5-flash",
        "openai/gpt-4.1-nano",
    ],
}

_lock = threading.Lock()
_lm_cache: dict[str, dspy.LM] = {}  # model string → dspy.LM singleton
_singletons: dict[str, "_FallbackLM"] = {}  # role → _FallbackLM singleton


def _log_fallback(from_model: str, to_model: str, exc: Exception) -> None:
    record = {
        "event": "llm_fallback",
        "from_model": from_model,
        "to_model": to_model,
        "reason": type(exc).__name__,
        "message": str(exc),
    }
    print(json.dumps(record), file=sys.stderr, flush=True)


class _FallbackLM:
    """Wraps a chain of dspy.LM instances; tries each on retryable failure.

    ``Any`` in history / __call__ mirrors the untyped dspy.LM interface — dspy
    has no stubs, so strict typing stops at the boundary.
    """

    def __init__(
        self,
        chain: list[dspy.LM],
        retryable: tuple[type[Exception], ...] = (),
    ) -> None:
        if not chain:
            raise ValueError("chain must contain at least one LM")
        self._chain = chain
        self._retryable = retryable or _DEFAULT_RETRYABLE

    @property
    def model(self) -> str:
        return str(self._chain[0].model)

    @property
    def history(self) -> list[Any]:
        for lm in self._chain:
            h: list[Any] = lm.history
            if h:
                return h
        return []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        for attempt in Retrying(
            stop=stop_after_attempt(len(self._chain)),
            wait=wait_none(),
            retry=retry_if_exception_type(self._retryable),
            reraise=True,
        ):
            with attempt:
                idx = attempt.retry_state.attempt_number - 1
                lm = self._chain[idx]
                try:
                    return lm(*args, **kwargs)
                except self._retryable as exc:
                    if idx < len(self._chain) - 1:
                        _log_fallback(
                            str(lm.model),
                            str(self._chain[idx + 1].model),
                            exc,
                        )
                    raise


def _get_or_build_lm(model: str) -> dspy.LM:
    """Return a dspy.LM for model, building it lazily and caching by model string."""
    if model in _lm_cache:
        return _lm_cache[model]
    with _lock:
        if model not in _lm_cache:
            _lm_cache[model] = dspy.LM(model=model)
        return _lm_cache[model]


def _build_chain(role: str) -> "_FallbackLM":
    models = _DEFAULTS[role].copy()
    env_override = os.environ.get(f"{role.upper()}_MODEL")
    if env_override:
        models[0] = env_override
    return _FallbackLM([_get_or_build_lm(m) for m in models])


def get_lm(role: _Role) -> "_FallbackLM":
    """Return the process-wide LM for role (thread-safe singleton).

    qualifier → Haiku 4.5 primary, Gemini 2.5 Flash + GPT-4.1-nano fallbacks.
    email     → Sonnet 4.6 primary, same fallbacks.

    Override primary with QUALIFIER_MODEL / EMAIL_MODEL env vars.
    """
    if role in _singletons:
        return _singletons[role]
    with _lock:
        if role not in _singletons:
            _singletons[role] = _build_chain(role)
        return _singletons[role]
