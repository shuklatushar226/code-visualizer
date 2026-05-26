"""AI explainer provider abstraction.

The `/explain` route asks an LLM to produce a one-sentence explanation
of the line currently executing. This module wraps that call behind an
ABC so the route is provider-agnostic — flipping `DSA_VIZ_AI_PROVIDER`
between "anthropic", "openai", or "fixture" swaps the implementation
without route changes.

The `fixture` provider returns a canned string and is used by tests
(no API key required). Production wires `anthropic`.
"""
from __future__ import annotations

import abc
import os
from typing import AsyncIterator, Optional


class AIProviderError(RuntimeError):
    """Raised when a provider call fails (network, rate limit, quota)."""


class AIProvider(abc.ABC):
    """Streaming text completion contract.

    Implementations yield text chunks (tokens, words, or whole strings).
    The route concatenates chunks to assemble the final cached answer and
    forwards each chunk via Server-Sent Events to the client for live
    rendering.
    """

    @abc.abstractmethod
    async def stream_explain(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int = 80,
    ) -> AsyncIterator[str]:  # pragma: no cover - abstract
        raise NotImplementedError


# ────────────────────────────────────────────────────────────────────
# Fixture: canned output. No network. Used by tests.
# ────────────────────────────────────────────────────────────────────

class FixtureProvider(AIProvider):
    """Returns a deterministic string in three chunks. Useful in tests
    to assert the SSE plumbing (chunks arrive, get concatenated, get
    cached) without paying for or depending on a real provider.
    """

    def __init__(self, canned: str = "This line assigns the next value.") -> None:
        self._canned = canned

    async def stream_explain(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 80
    ) -> AsyncIterator[str]:
        # Yield in 3 chunks so the SSE consumer sees multiple events.
        words = self._canned.split(" ")
        third = max(1, len(words) // 3)
        chunks = [
            " ".join(words[:third]),
            " " + " ".join(words[third:2 * third]),
            " " + " ".join(words[2 * third:]),
        ]
        for chunk in chunks:
            if chunk:
                yield chunk


# ────────────────────────────────────────────────────────────────────
# Anthropic (Claude Haiku 4.5 by default).
# ────────────────────────────────────────────────────────────────────

class AnthropicProvider(AIProvider):
    """Anthropic streaming via `messages.stream`.

    Lazy-imports `anthropic` so the backend doesn't hard-require the
    SDK at install time (it's in `[project.optional-dependencies] ai`).
    """

    def __init__(self, *, api_key: Optional[str] = None, model: str = "claude-haiku-4-5") -> None:
        self._api_key = api_key or os.environ.get("DSA_VIZ_AI_KEY")
        if not self._api_key:
            raise AIProviderError("DSA_VIZ_AI_KEY is unset; cannot create Anthropic provider")
        self._model = model

    async def stream_explain(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 80
    ) -> AsyncIterator[str]:
        try:
            from anthropic import AsyncAnthropic  # type: ignore
        except ImportError as e:  # pragma: no cover - import failure path
            raise AIProviderError(
                "anthropic SDK not installed; pip install 'dsa-viz-backend[ai]'"
            ) from e

        client = AsyncAnthropic(api_key=self._api_key)
        try:
            async with client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                async for chunk in stream.text_stream:
                    if chunk:
                        yield chunk
        except Exception as e:
            raise AIProviderError(f"anthropic call failed: {e}") from e


# ────────────────────────────────────────────────────────────────────
# Factory
# ────────────────────────────────────────────────────────────────────

def make_provider(provider: Optional[str] = None) -> AIProvider:
    """Resolve the configured provider. Defaults to env var or 'anthropic'.

    Raises AIProviderError if the chosen provider can't be initialized
    (e.g. missing API key for anthropic).
    """
    name = (provider or os.environ.get("DSA_VIZ_AI_PROVIDER") or "anthropic").lower()
    if name == "fixture":
        return FixtureProvider()
    if name == "anthropic":
        return AnthropicProvider()
    raise AIProviderError(f"unknown AI provider: {name!r}")
