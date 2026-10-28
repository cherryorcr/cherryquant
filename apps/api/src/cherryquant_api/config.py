"""Runtime configuration for optional language-model strategy drafting.

The API intentionally reads credentials only from process environment.  This
module exposes a small, non-secret summary for health checks and diagnostics;
the raw key is never returned, logged, or included in strategy metadata.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_float(value: str | None, default: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class LLMConfig:
    requested_provider: str
    base_url: str
    api_key: str
    model: str | None
    timeout_seconds: float

    @property
    def effective_provider(self) -> str:
        if self.requested_provider == "mock" or not self.api_key:
            return "mock"
        return "jackbuddy"

    @property
    def api_key_configured(self) -> bool:
        return bool(self.api_key)

    def public_summary(self) -> dict[str, object]:
        """Return diagnostic fields that are safe to expose to the UI."""

        return {
            "requested_provider": self.requested_provider,
            "provider": self.effective_provider,
            "base_url": self.base_url,
            "model": self.model or "auto",
            "api_key_configured": self.api_key_configured,
            "timeout_seconds": self.timeout_seconds,
        }


def load_llm_config() -> LLMConfig:
    requested_provider = os.getenv("CHERRYQUANT_LLM_PROVIDER", "auto").strip().lower() or "auto"
    base_url = os.getenv("JACKBUDDY_BASE_URL", "https://jackbuddy.xin/v1").strip().rstrip("/")
    if not base_url:
        base_url = "https://jackbuddy.xin/v1"
    api_key = os.getenv("JACKBUDDY_API_KEY", "").strip()
    model = os.getenv("JACKBUDDY_MODEL", "").strip() or None
    timeout_seconds = _positive_float(os.getenv("JACKBUDDY_TIMEOUT_SECONDS"), 45.0)
    return LLMConfig(
        requested_provider=requested_provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )
