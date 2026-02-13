"""OpenAI LLM provider implementation."""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from src.agents.llm.base import BaseLLMProvider, LLMMessage, LLMResponse
from src.config import settings

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """LLM provider backed by the OpenAI API (GPT-4o, etc.).

    Uses the async OpenAI client for non-blocking requests. Supports both
    free-form chat completions (with optional tool use) and structured output
    via JSON mode.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_model
        self._client = AsyncOpenAI(api_key=self._api_key)

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
        """Send a chat completion request to OpenAI.

        If *tools* are provided they are forwarded as OpenAI function-calling
        tool definitions. The response may contain ``tool_calls`` that the
        caller is expected to handle.
        """

        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            request_kwargs["tools"] = self._format_tools(tools)
            request_kwargs["tool_choice"] = "auto"

        logger.debug(
            "OpenAI chat request: model=%s messages=%d tools=%d",
            self._model,
            len(messages),
            len(tools) if tools else 0,
        )

        response = await self._client.chat.completions.create(**request_kwargs)
        choice = response.choices[0]

        # Extract tool calls if any
        tool_calls: list[dict[str, Any]] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                )

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            provider="openai",
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": (
                    response.usage.completion_tokens if response.usage else 0
                ),
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
        """Request structured JSON output conforming to *response_format*.

        Uses OpenAI's JSON mode combined with an explicit instruction in the
        system prompt to return data matching the target schema. The raw JSON
        string is then validated and parsed into an instance of
        *response_format* (expected to be a Pydantic ``BaseModel`` subclass).
        """

        schema = self._extract_schema(response_format)
        schema_instruction = (
            "You MUST respond with valid JSON that conforms exactly to this "
            f"JSON schema:\n{json.dumps(schema, indent=2)}\n"
            "Do not include any text outside the JSON object."
        )

        augmented_messages = self._inject_schema_instruction(
            messages, schema_instruction
        )

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": m.role, "content": m.content} for m in augmented_messages
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        raw_content = response.choices[0].message.content or "{}"

        logger.debug("OpenAI structured output raw: %s", raw_content[:200])

        parsed = json.loads(raw_content)
        return response_format(**parsed)

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    @staticmethod
    def _format_tools(tools: list[dict]) -> list[dict]:
        """Normalise tool definitions into the OpenAI function-calling format.

        If a tool dict already has the ``type`` key it is assumed to be in the
        correct format; otherwise it is wrapped as a ``function`` tool.
        """
        formatted: list[dict] = []
        for tool in tools:
            if "type" in tool:
                formatted.append(tool)
            else:
                formatted.append(
                    {
                        "type": "function",
                        "function": tool,
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

    @staticmethod
    def _inject_schema_instruction(
        messages: list[LLMMessage],
        instruction: str,
    ) -> list[LLMMessage]:
        """Prepend or augment the system message with *instruction*.

        If the first message already has role ``system`` the instruction is
        appended to it. Otherwise a new system message is inserted at the
        beginning.
        """
        augmented = list(messages)
        if augmented and augmented[0].role == "system":
            augmented[0] = LLMMessage(
                role="system",
                content=f"{augmented[0].content}\n\n{instruction}",
            )
        else:
            augmented.insert(0, LLMMessage(role="system", content=instruction))
        return augmented
