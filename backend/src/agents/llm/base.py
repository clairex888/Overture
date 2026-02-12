"""Abstract base classes for LLM provider integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMMessage:
    """A single message in a conversation with an LLM.

    Attributes:
        role: The role of the message sender ("system", "user", or "assistant").
        content: The text content of the message.
    """

    role: str
    content: str


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider.

    Attributes:
        content: The text content of the response.
        model: The model identifier that generated the response.
        provider: The provider name (e.g., "openai", "anthropic").
        usage: Token usage statistics with keys like "prompt_tokens" and
            "completion_tokens".
        tool_calls: A list of tool call dictionaries if the model invoked tools.
        raw: The raw, unprocessed response object from the provider SDK.
    """

    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: Any = None


class BaseLLMProvider(ABC):
    """Abstract base class that all LLM provider implementations must extend.

    Each provider must implement both free-form chat completions and structured
    output generation so that agent code can work uniformly across providers.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat completion request to the provider.

        Args:
            messages: Ordered conversation messages.
            tools: Optional list of tool/function definitions the model may call.
            temperature: Sampling temperature (0.0 = deterministic, higher = more
                creative).
            max_tokens: Maximum number of tokens the model should generate.

        Returns:
            A standardized ``LLMResponse``.
        """
        ...

    @abstractmethod
    async def structured_output(
        self,
        messages: list[LLMMessage],
        response_format: type,
        temperature: float = 0.3,
    ) -> Any:
        """Request a response that conforms to a specific structure.

        The provider implementation should use whatever mechanism is available
        (JSON mode, tool-use coercion, etc.) to guarantee the response matches
        ``response_format``.

        Args:
            messages: Ordered conversation messages.
            response_format: A Pydantic model or similar type describing the
                desired output schema.
            temperature: Sampling temperature (lower is recommended for
                structured output to reduce hallucination).

        Returns:
            An instance of ``response_format`` populated with the model's output.
        """
        ...
