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

_lm_cache_lock = threading.Lock()   # guards _lm_cache
_singleton_lock = threading.Lock()  # guards _singletons (never held while calling _get_or_build_lm)
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


class _FallbackLM(dspy.BaseLM):
    """Wraps a chain of dspy.LM instances; tries each on retryable failure.

    Extends dspy.BaseLM so dspy.Predict accepts it via isinstance check.
    ``Any`` in __call__ mirrors the untyped dspy.LM interface — dspy
    has no stubs, so strict typing stops at the boundary.
    """

    def __init__(
        self,
        chain: list[dspy.LM],
        retryable: tuple[type[Exception], ...] = (),
    ) -> None:
        if not chain:
            raise ValueError("chain must contain at least one LM")
        super().__init__(model=chain[0].model)
        self._chain = chain
        self._retryable = retryable or _DEFAULT_RETRYABLE

    def forward(self, prompt: Any = None, messages: Any = None, **kwargs: Any) -> Any:
        # Required by BaseLM interface; not called — __call__ handles dispatch.
        raise NotImplementedError  # pragma: no cover

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
    with _lm_cache_lock:
        if model not in _lm_cache:
            _lm_cache[model] = dspy.LM(model=model)
        return _lm_cache[model]


def _model_provider(model: str) -> str:
    return model.split("/", 1)[0]


def _provider_key_env_names(provider: str) -> tuple[str, ...]:
    return {
        "anthropic": ("ANTHROPIC_API_KEY",),
        "openai": ("OPENAI_API_KEY",),
        "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    }.get(provider, ())


def _is_model_available(model: str) -> bool:
    env_names = _provider_key_env_names(_model_provider(model))
    if not env_names:
        return True
    return any(os.environ.get(name) for name in env_names)


def _resolve_models(role: str) -> list[str]:
    """Return the fallback chain, skipping providers with no configured API key."""
    models = _DEFAULTS[role].copy()
    env_override = os.environ.get(f"{role.upper()}_MODEL")
    if env_override:
        models[0] = env_override
    available = [model for model in models if _is_model_available(model)]
    return available or [models[0]]


def _build_chain(role: str) -> "_FallbackLM":
    return _FallbackLM([_get_or_build_lm(model) for model in _resolve_models(role)])


def get_lm(role: _Role) -> "_FallbackLM":
    """Return the process-wide LM for role (thread-safe singleton).

    qualifier → Haiku 4.5 primary, Gemini 2.5 Flash + GPT-4.1-nano fallbacks.
    email     → Sonnet 4.6 primary, same fallbacks.

    Override primary with QUALIFIER_MODEL / EMAIL_MODEL env vars.
    """
    if role in _singletons:
        return _singletons[role]
    # Build outside the lock so _build_chain → _get_or_build_lm can acquire
    # _lm_cache_lock without deadlocking on _singleton_lock.
    chain = _build_chain(role)
    with _singleton_lock:
        if role not in _singletons:
            _singletons[role] = chain
        return _singletons[role]
