"""Multi-provider LLM abstraction layer for the Overture AI hedge fund system.

Quick start::

    from src.agents.llm import llm_router, LLMMessage

    response = await llm_router.chat([
        LLMMessage(role="system", content="You are a financial analyst."),
        LLMMessage(role="user", content="Summarise AAPL earnings."),
    ])

    # Or route by task type (picks the best provider automatically):
    response = await llm_router.chat_for_task(
        "analysis",
        [LLMMessage(role="user", content="Assess risk for portfolio X.")],
    )
"""

from src.agents.llm.anthropic_provider import AnthropicProvider
from src.agents.llm.base import BaseLLMProvider, LLMMessage, LLMResponse
from src.agents.llm.openai_provider import OpenAIProvider
from src.agents.llm.router import LLMRouter, llm_router

__all__ = [
    "AnthropicProvider",
    "BaseLLMProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMRouter",
    "OpenAIProvider",
    "llm_router",
]
