"""Anthropic LLM provider implementation."""

import json
import logging
from typing import Any

from anthropic import AsyncAnthropic

from src.agents.llm.base import BaseLLMProvider, LLMMessage, LLMResponse
from src.config import settings

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseLLMProvider):
    """LLM provider backed by the Anthropic API (Claude models).

    Uses the async Anthropic client for non-blocking requests.  Supports both
    free-form chat completions (with optional tool use) and structured output
    via tool-use coercion.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or settings.anthropic_model
        self._client = AsyncAnthropic(api_key=self._api_key)

    # --------------------------------------------------------------------- #
    # Chat completions
    # --------------------------------------------------------------------- #

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat completion request to Anthropic.

        The Anthropic Messages API requires the system prompt to be passed as a
        separate top-level parameter, so this method extracts it from the
        message list automatically.
        """

        system_prompt, api_messages = self._split_system_prompt(messages)

        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            request_kwargs["system"] = system_prompt

        if tools:
            request_kwargs["tools"] = self._format_tools(tools)

        logger.debug(
            "Anthropic chat request: model=%s messages=%d tools=%d",
            self._model,
            len(api_messages),
            len(tools) if tools else 0,
        )

        response = await self._client.messages.create(**request_kwargs)

        content_text = self._extract_text(response.content)
        tool_calls = self._extract_tool_calls(response.content)

        return LLMResponse(
            content=content_text,
            model=response.model,
            provider="anthropic",
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
            tool_calls=tool_calls,
            raw=response,
        )

    # --------------------------------------------------------------------- #
    # Structured output
    # --------------------------------------------------------------------- #

    async def structured_output(
        self,
        messages: list[LLMMessage],
        response_format: type,
        temperature: float = 0.3,
    ) -> Any:
        """Request structured output conforming to *response_format*.

        Uses Anthropic's tool-use mechanism with a single tool whose input
        schema matches *response_format*. By forcing the model to call this
        tool we guarantee the output conforms to the desired schema.
        """

        schema = self._extract_schema(response_format)

        extraction_tool = {
            "name": "structured_response",
            "description": (
                "Return the response as a structured JSON object matching "
                "the required schema."
            ),
            "input_schema": schema,
        }

        system_prompt, api_messages = self._split_system_prompt(messages)

        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": 4096,
            "tools": [extraction_tool],
            "tool_choice": {"type": "tool", "name": "structured_response"},
        }
        if system_prompt:
            request_kwargs["system"] = system_prompt

        response = await self._client.messages.create(**request_kwargs)

        # Find the tool_use content block
        for block in response.content:
            if block.type == "tool_use" and block.name == "structured_response":
                logger.debug(
                    "Anthropic structured output: %s",
                    json.dumps(block.input)[:200],
                )
                return response_format(**block.input)

        # Fallback: attempt to parse any text content as JSON
        text = self._extract_text(response.content)
        logger.warning(
            "Anthropic did not return a tool_use block; falling back to text parsing."
        )
        parsed = json.loads(text)
        return response_format(**parsed)

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    @staticmethod
    def _split_system_prompt(
        messages: list[LLMMessage],
    ) -> tuple[str | None, list[dict[str, str]]]:
        """Separate the system prompt from user/assistant messages.

        Anthropic's Messages API expects the system prompt as a top-level
        parameter rather than inside the messages list.

        Returns:
            A tuple of ``(system_prompt, api_messages)`` where
            ``api_messages`` is a list of dicts suitable for the API.
        """
        system_prompt: str | None = None
        api_messages: list[dict[str, str]] = []

        for msg in messages:
            if msg.role == "system":
                # Concatenate multiple system messages (rare, but handle it)
                if system_prompt is None:
                    system_prompt = msg.content
                else:
                    system_prompt += f"\n\n{msg.content}"
            else:
                api_messages.append({"role": msg.role, "content": msg.content})

        return system_prompt, api_messages

    @staticmethod
    def _extract_text(content_blocks: list[Any]) -> str:
        """Concatenate all ``text`` content blocks into a single string."""
        parts: list[str] = []
        for block in content_blocks:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts)

    @staticmethod
    def _extract_tool_calls(content_blocks: list[Any]) -> list[dict[str, Any]]:
        """Extract tool-use blocks into the standardised tool_calls format."""
        tool_calls: list[dict[str, Any]] = []
        for block in content_blocks:
            if hasattr(block, "type") and block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "type": "tool_use",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input),
                        },
                    }
                )
        return tool_calls

    @staticmethod
    def _format_tools(tools: list[dict]) -> list[dict]:
        """Normalise tool definitions into Anthropic's expected format.

        Anthropic expects each tool to have ``name``, ``description``, and
        ``input_schema`` keys. If a tool is provided in the OpenAI
        function-calling format it will be converted automatically.
        """
        formatted: list[dict] = []
        for tool in tools:
            if "input_schema" in tool:
                # Already in Anthropic format
                formatted.append(tool)
            elif "function" in tool:
                # Convert from OpenAI function-calling format
                func = tool["function"]
                formatted.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {"type": "object"}),
                    }
                )
            else:
                # Assume minimal dict with name/description/parameters
                formatted.append(
                    {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "input_schema": tool.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    }
                )
        return formatted

    @staticmethod
    def _extract_schema(response_format: type) -> dict:
        """Extract a JSON-serialisable schema dict from *response_format*.

        Supports Pydantic ``BaseModel`` subclasses (via ``model_json_schema``)
        and plain dicts passed directly.
        """
        if hasattr(response_format, "model_json_schema"):
            return response_format.model_json_schema()  # type: ignore[union-attr]
        if isinstance(response_format, dict):
            return response_format  # type: ignore[return-value]
        raise TypeError(
            f"response_format must be a Pydantic model or dict, got {type(response_format)}"
        )
