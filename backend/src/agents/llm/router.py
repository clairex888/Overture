"""LLM Router -- intelligent multi-provider dispatch with fallback."""

import logging
from typing import Any

from src.agents.llm.anthropic_provider import AnthropicProvider
from src.agents.llm.base import BaseLLMProvider, LLMMessage, LLMResponse
from src.agents.llm.openai_provider import OpenAIProvider
from src.config import settings

logger = logging.getLogger(__name__)

# Mapping from task type to the *preferred* provider name.  The router will
# try this provider first and fall back to the other if it fails.
DEFAULT_TASK_ROUTING: dict[str, str] = {
    # Deep reasoning / chain-of-thought tasks favour Claude
    "reasoning": "anthropic",
    "analysis": "anthropic",
    "risk_assessment": "anthropic",
    "strategy": "anthropic",
    # Fast structured extraction tasks favour GPT
    "extraction": "openai",
    "summarization": "openai",
    "classification": "openai",
    "data_formatting": "openai",
}


class LLMRouter:
    """Routes LLM requests to the appropriate provider with automatic fallback.

    The router lazily instantiates provider instances and caches them for the
    lifetime of the process.  It exposes three main entry-points:

    * ``chat`` -- send a chat request, optionally specifying a provider name.
    * ``chat_for_task`` -- pick the best provider for a named task type.
    * ``get_provider`` -- retrieve a raw ``BaseLLMProvider`` instance.
    """

    def __init__(
        self,
        task_routing: dict[str, str] | None = None,
    ) -> None:
        self._providers: dict[str, BaseLLMProvider] = {}
        self._task_routing = task_routing or DEFAULT_TASK_ROUTING
        self._default_provider = settings.default_llm_provider

    # --------------------------------------------------------------------- #
    # Provider management
    # --------------------------------------------------------------------- #

    def _init_provider(self, name: str) -> BaseLLMProvider:
        """Create and cache a provider instance by name."""

        if name in self._providers:
            return self._providers[name]

        if name == "openai":
            provider = OpenAIProvider()
        elif name == "anthropic":
            provider = AnthropicProvider()
        else:
            raise ValueError(f"Unknown LLM provider: {name!r}")

        self._providers[name] = provider
        logger.info("Initialised LLM provider: %s", name)
        return provider

    def get_provider(self, provider_name: str | None = None) -> BaseLLMProvider:
        """Return the requested (or default) provider instance.

        Args:
            provider_name: ``"openai"`` or ``"anthropic"``.  When *None* the
                configured default provider is used.

        Returns:
            A ready-to-use ``BaseLLMProvider``.
        """
        name = provider_name or self._default_provider
        return self._init_provider(name)

    def _get_fallback_name(self, primary: str) -> str | None:
        """Return the name of the *other* provider to use as a fallback."""
        if primary == "openai":
            return "anthropic"
        if primary == "anthropic":
            return "openai"
        return None

    # --------------------------------------------------------------------- #
    # Chat routing
    # --------------------------------------------------------------------- #

    async def chat(
        self,
        messages: list[LLMMessage],
        provider: str | None = None,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        fallback: bool = True,
    ) -> LLMResponse:
        """Send a chat request, optionally falling back to another provider.

        Args:
            messages: Conversation messages.
            provider: Explicit provider name.  ``None`` uses the default.
            tools: Tool / function definitions for function-calling.
            temperature: Sampling temperature.
            max_tokens: Generation limit.
            fallback: If *True* (the default) and the primary provider raises
                an exception, the request is retried on the alternate provider.

        Returns:
            An ``LLMResponse`` from whichever provider succeeded.
        """

        primary_name = provider or self._default_provider
        primary = self._init_provider(primary_name)

        try:
            return await primary.chat(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            if not fallback:
                raise

            fallback_name = self._get_fallback_name(primary_name)
            if fallback_name is None:
                raise

            logger.warning(
                "Provider %s failed; falling back to %s",
                primary_name,
                fallback_name,
                exc_info=True,
            )
            fallback_provider = self._init_provider(fallback_name)
            return await fallback_provider.chat(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )

    async def chat_for_task(
        self,
        task_type: str,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        fallback: bool = True,
    ) -> LLMResponse:
        """Pick the best provider for *task_type* and send a chat request.

        The task-to-provider mapping is defined by ``DEFAULT_TASK_ROUTING``
        (or a custom mapping passed at construction time).  If the task type
        is unknown the default provider is used.

        Args:
            task_type: A short label such as ``"reasoning"``, ``"extraction"``,
                ``"analysis"``, etc.
            messages: Conversation messages.
            tools: Tool / function definitions.
            temperature: Sampling temperature.
            max_tokens: Generation limit.
            fallback: Whether to try the alternate provider on failure.

        Returns:
            An ``LLMResponse``.
        """

        preferred = self._task_routing.get(task_type, self._default_provider)

        logger.debug(
            "Task %r routed to provider %s",
            task_type,
            preferred,
        )

        return await self.chat(
            messages,
            provider=preferred,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            fallback=fallback,
        )

    # --------------------------------------------------------------------- #
    # Structured output routing
    # --------------------------------------------------------------------- #

    async def structured_output(
        self,
        messages: list[LLMMessage],
        response_format: type,
        provider: str | None = None,
        temperature: float = 0.3,
        fallback: bool = True,
    ) -> Any:
        """Request structured output, with optional provider fallback.

        Args:
            messages: Conversation messages.
            response_format: A Pydantic model (or compatible type) describing
                the desired output.
            provider: Explicit provider name.
            temperature: Sampling temperature.
            fallback: Whether to fall back on failure.

        Returns:
            An instance of *response_format*.
        """

        primary_name = provider or self._default_provider
        primary = self._init_provider(primary_name)

        try:
            return await primary.structured_output(
                messages,
                response_format=response_format,
                temperature=temperature,
            )
        except Exception:
            if not fallback:
                raise

            fallback_name = self._get_fallback_name(primary_name)
            if fallback_name is None:
                raise

            logger.warning(
                "Provider %s structured_output failed; falling back to %s",
                primary_name,
                fallback_name,
                exc_info=True,
            )
            fallback_provider = self._init_provider(fallback_name)
            return await fallback_provider.structured_output(
                messages,
                response_format=response_format,
                temperature=temperature,
            )


# -------------------------------------------------------------------------
# Module-level singleton
# -------------------------------------------------------------------------

llm_router = LLMRouter()
