from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

from .config import llm_api_key, llm_base_url, llm_model
from .models import ToolCall
from .request_ledger import get_ledger


LLM_MAX_ATTEMPTS = 3
LLM_RETRY_BACKOFF_SECONDS = (1.0, 4.0)
LLM_REQUEST_TIMEOUT_SECONDS = 300.0


def _is_retryable_llm_error(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is not None:
        try:
            status = int(status)
        except (TypeError, ValueError):
            return False
        return status == 429 or status >= 500
    return isinstance(exc, (APIConnectionError, APITimeoutError))


class LLMResponseShapeError(RuntimeError):
    pass


def _usage_dict(usage: Any) -> dict | None:
    if usage is None:
        return None
    out = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if value is not None:
            out[key] = value
    return out or None


@dataclass(slots=True)
class AssistantMessage:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_message: dict[str, Any] = field(default_factory=dict)


class OpenAICompatibleLLM:
    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None) -> None:
        self.model = model or llm_model()
        self.base_url = base_url or llm_base_url()
        self.api_key = api_key or llm_api_key()
        if not self.api_key:
            raise RuntimeError("VIMAX_LLM_API_KEY is required for the agent LLM client")
        # SDK retries are EXPLICITLY zero: retry policy lives in this class
        # only, every attempt is ledgered and budget-gated; no hidden layer
        # may silently re-send a request.
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url,
                                  timeout=LLM_REQUEST_TIMEOUT_SECONDS,
                                  max_retries=0)
        self.ledger = get_ledger()

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantMessage:
        shape_attempts = [
            {"tools": tools or None, "tool_choice": "auto" if tools else None},
            {"tools": tools or None, "tool_choice": "auto" if tools else None},
        ]
        if tools:
            shape_attempts.append({"tools": None, "tool_choice": None})

        last_shape_error: Exception | None = None
        for shape_index, attempt in enumerate(shape_attempts):
            # every shape re-send is its OWN logical request: ledgered,
            # budget-gated and counted — shape fallbacks cannot bypass caps
            self.ledger.guard("llm_calls")
            self.ledger.bump("llm_calls")
            request_id = self.ledger.open(
                "llm_chat", role="outer_agent",
                stage=f"shape_{shape_index}",
                model=self.model,
                with_tools=bool(attempt["tools"]))
            try:
                response = await self._create_completion_with_retries(messages, attempt["tools"], attempt["tool_choice"])
                usage = getattr(response, "usage", None)
                output_tokens = getattr(usage, "completion_tokens", None)
                self.ledger.close(
                    request_id, "ok",
                    response_model=getattr(response, "model", self.model),
                    usage=_usage_dict(usage),
                    output_tokens=output_tokens)
                if output_tokens:
                    self.ledger.observe_usage(output_tokens)
                return _assistant_message_from_response(response)
            except LLMResponseShapeError as exc:
                self.ledger.error(request_id, "LLMResponseShapeError")
                last_shape_error = exc
                continue
            except Exception as exc:  # noqa: BLE001 — closed, then re-raised
                self.ledger.error(request_id, type(exc).__name__)
                raise
        assert last_shape_error is not None
        raise last_shape_error

    async def _create_completion_with_retries(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, tool_choice: str | None) -> Any:
        for attempt in range(LLM_MAX_ATTEMPTS):
            # every project-level retry attempt is gated and counted BEFORE
            # the send; the ledger closes each attempt distinctly
            self.ledger.guard("llm_attempts")
            self.ledger.bump("llm_attempts")
            attempt_id = self.ledger.open(
                "llm_attempt", role="outer_agent",
                attempt=attempt + 1, max_attempts=LLM_MAX_ATTEMPTS,
                model=self.model)
            try:
                response = await self._create_completion(messages, tools, tool_choice)
                self.ledger.close(attempt_id, "ok",
                                  response_model=getattr(response, "model", self.model))
                return response
            except Exception as exc:
                # a transport timeout leaves the outcome UNKNOWN on the server
                # side: mark right-censored in the ledger before re-raising
                self.ledger.error(
                    attempt_id, type(exc).__name__,
                    right_censored=isinstance(exc, APITimeoutError))
                if isinstance(exc, LLMResponseShapeError) or attempt == LLM_MAX_ATTEMPTS - 1 or not _is_retryable_llm_error(exc):
                    raise
                delay = LLM_RETRY_BACKOFF_SECONDS[min(attempt, len(LLM_RETRY_BACKOFF_SECONDS) - 1)]
                logging.warning("LLM call failed (%s); retrying in %.1fs (attempt %d/%d)", exc, delay, attempt + 1, LLM_MAX_ATTEMPTS)
                await asyncio.sleep(delay)

    async def _create_completion(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, tool_choice: str | None) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        # explicit per-request output cap (budget gate also checks the
        # configured value before the send; default 8192)
        max_tokens = os.environ.get("VIMAX_AGENT_MAX_TOKENS", "8192")
        try:
            kwargs["max_tokens"] = max(256, int(max_tokens))
        except ValueError:
            kwargs["max_tokens"] = 8192
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        return await self.client.chat.completions.create(**kwargs)


def _assistant_message_from_response(response: Any) -> AssistantMessage:
    message = _extract_message(response)
    text = _message_value(message, "content") or ""
    calls: list[ToolCall] = []
    for call in _message_value(message, "tool_calls") or []:
        function = _message_value(call, "function") or {}
        try:
            arguments = json.loads(_message_value(function, "arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        calls.append(ToolCall(id=_message_value(call, "id") or f"tool-{uuid4().hex[:12]}", name=_message_value(function, "name"), arguments=arguments))
    return AssistantMessage(text=text, tool_calls=calls, raw_message=_dump_message(message))


def _extract_message(response: Any) -> Any:
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError as exc:
            raise LLMResponseShapeError(f"LLM provider returned a string instead of a chat completion object: {response[:300]}") from exc
    choices = _message_value(response, "choices")
    if not choices:
        raise LLMResponseShapeError(f"LLM provider response missing choices: {str(response)[:500]}")
    first_choice = choices[0]
    message = _message_value(first_choice, "message")
    if message is None:
        raise LLMResponseShapeError(f"LLM provider response missing choice.message: {str(response)[:500]}")
    return message


def _message_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _dump_message(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump()
    return {"content": str(message)}
