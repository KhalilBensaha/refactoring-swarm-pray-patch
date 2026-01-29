"""Utilities to keep Gemini calls bounded.

Why this exists:
- The upstream `langchain_google_genai` package retries quota errors (429) up to 10 times
  with exponential backoff. In practice this can look like the program is "stuck" for a
  very long time.

This module provides:
- A small runtime patch to reduce retry attempts and maximum backoff time.
- Lightweight counters to expose basic API usage statistics.

This is intentionally simple and self-contained (no external services).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class QuotaStats:
    total_llm_calls: int = 0
    total_llm_failures: int = 0
    last_error: Optional[str] = None
    call_timestamps: list[float] = field(default_factory=list)

    def record_call(self, ok: bool, error: Optional[str] = None) -> None:
        now = time.time()
        self.total_llm_calls += 1
        self.call_timestamps.append(now)
        # Keep a short window
        if len(self.call_timestamps) > 2000:
            self.call_timestamps = self.call_timestamps[-1000:]

        if not ok:
            self.total_llm_failures += 1
            self.last_error = error

    def calls_per_minute(self) -> float:
        now = time.time()
        window = [t for t in self.call_timestamps if now - t <= 60.0]
        return float(len(window))


_STATS = QuotaStats()
_PATCHED = False


def get_quota_stats() -> QuotaStats:
    return _STATS


def configure_gemini_retry(
    *,
    max_retries: int = 3,
    max_seconds: int = 8,
    min_seconds: int = 1,
    multiplier: int = 2,
) -> None:
    """Reduce the default retry behavior in langchain_google_genai.

    The upstream library hardcodes max_retries=10 and max_seconds=60.
    We patch the retry decorator factory at runtime so quota errors fail fast.

    This avoids very long runs when the API is rate-limited or billing/quota is exhausted.
    """

    global _PATCHED
    if _PATCHED:
        return

    try:
        import logging
        import google.api_core
        from tenacity import before_sleep_log, retry, retry_if_exception_type
        from tenacity import stop_after_attempt, wait_exponential
        import langchain_google_genai.chat_models as chat_models

        logger = logging.getLogger("langchain_google_genai")

        def _create_retry_decorator() -> Callable[[Any], Any]:
            return retry(
                reraise=True,
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(
                    multiplier=multiplier,
                    min=min_seconds,
                    max=max_seconds,
                ),
                retry=(
                    retry_if_exception_type(google.api_core.exceptions.ResourceExhausted)
                    | retry_if_exception_type(google.api_core.exceptions.ServiceUnavailable)
                    | retry_if_exception_type(google.api_core.exceptions.GoogleAPIError)
                ),
                before_sleep=before_sleep_log(logger, logging.WARNING),
            )

        # Patch the factory used by _chat_with_retry/_achat_with_retry.
        chat_models._create_retry_decorator = _create_retry_decorator  # type: ignore[attr-defined]
        _PATCHED = True

    except Exception:
        # If patching fails, we simply leave defaults; agents will still log failures.
        _PATCHED = False


def invoke_llm(llm: Any, messages: Any) -> Any:
    """Invoke an LLM call and keep minimal stats.

    Note: actual retry behavior is controlled by `configure_gemini_retry()`.
    """

    try:
        result = llm.invoke(messages)
        _STATS.record_call(True)
        return result
    except Exception as e:
        _STATS.record_call(False, error=str(e))
        raise
