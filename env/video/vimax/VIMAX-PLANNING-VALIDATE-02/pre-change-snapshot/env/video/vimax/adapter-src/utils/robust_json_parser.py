# Some chat models (observed with gemini-flash-lite via the OpenAI-compatible
# endpoint) frequently emit a trailing comma before a closing `}`/`]` in
# structured JSON responses (e.g. `"variation_reason": "...",\n}`). That is
# invalid JSON, so PydanticOutputParser raises OutputParserException even
# though the payload is otherwise well-formed and semantically complete --
# and resampling burns LLM calls while often failing the same way again.
# Wrap PydanticOutputParser so a parse failure retries locally with trailing
# commas stripped before giving up.
import re
import json
from typing import List, Optional

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.outputs import Generation

def strip_trailing_commas(text: str) -> str:
    """Remove only commas immediately before a JSON closer outside strings."""
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "}]":
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output)


class TrailingCommaTolerantPydanticOutputParser(PydanticOutputParser):
    """Parse complete JSON only, with a lossless trailing-comma repair."""

    def parse_result(self, result: List[Generation], *, partial: bool = False):
        if not result:
            error = OutputParserException("Empty model output; expected a complete JSON object.")
            _record_parse_failure(None, error, None, None)
            raise error
        generation = result[0]
        finish_reason = getattr(generation, "generation_info", None) or {}
        request_id = _request_id_for_generation(generation)
        if isinstance(finish_reason, dict) and str(finish_reason.get("finish_reason", "")).lower() in {"length", "max_tokens"}:
            error = OutputParserException("Model output was truncated by the output-token limit (finish_reason=length).")
            _record_parse_failure(getattr(generation, "text", None), error, finish_reason.get("finish_reason"), request_id)
            raise error
        try:
            candidate = _extract_json_candidate(generation.text)
        except OutputParserException as error:
            _record_parse_failure(getattr(generation, "text", None), error, None, request_id)
            raise
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError as original_error:
            repaired_candidate = strip_trailing_commas(candidate)
            if repaired_candidate == candidate:
                error = OutputParserException(f"Model output is empty or incomplete JSON: {original_error.msg} at position {original_error.pos}.")
                _record_parse_failure(candidate, error, None, request_id)
                raise error from original_error
            try:
                decoded = json.loads(repaired_candidate)
            except json.JSONDecodeError as exc:
                error = OutputParserException(f"Model output is empty or incomplete JSON: {exc.msg} at position {exc.pos}.")
                _record_parse_failure(candidate, error, None, request_id)
                raise error from exc
            candidate = repaired_candidate
        if not isinstance(decoded, (dict, list)):
            error = OutputParserException("Model output JSON root must be an object or array.")
            _record_parse_failure(candidate, error, None, request_id)
            raise error
        normalized_result = [Generation(text=candidate)]
        try:
            parsed = super().parse_result(normalized_result, partial=partial)
            _record_parse_success(candidate, finish_reason, request_id)
            return parsed
        except OutputParserException as error:
            _record_parse_failure(candidate, error, None, request_id)
            raise


def _extract_json_candidate(text: str) -> str:
    """Accept plain JSON or a single fenced JSON block; retain its bytes."""
    source = str(text or "").strip()
    if not source:
        raise OutputParserException("Empty model output; expected a complete JSON object.")
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", source, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        source = fenced.group(1).strip()
    else:
        starts = [position for token in ("{", "[") if (position := source.find(token)) >= 0]
        if starts:
            start = min(starts)
            end = max(source.rfind("}"), source.rfind("]"))
            source = source[start:end + 1] if end >= start else source[start:]
    if not source:
        raise OutputParserException("Empty model output; expected a complete JSON object.")
    return source


def _request_id_for_generation(generation: Generation) -> str | None:
    info = getattr(generation, "generation_info", None)
    if isinstance(info, dict):
        value = info.get("vimax_request_id")
        if value:
            return str(value)
    message = getattr(generation, "message", None)
    metadata = getattr(message, "response_metadata", None)
    if isinstance(metadata, dict):
        value = metadata.get("vimax_request_id")
        return str(value) if value else None
    return None


def _record_parse_success(text: str, finish_reason: dict, request_id: str | None) -> None:
    try:
        from agent_runtime.request_ledger import get_ledger
        get_ledger().diagnostic(
            request_id, parse_status="success",
            finish_reason=(finish_reason.get("finish_reason")
                           or finish_reason.get("stop_reason"))
            if isinstance(finish_reason, dict) else None,
            response_chars=len(text), parse_error_type=None)
    except Exception:
        return


def _record_parse_failure(text: str | None, error: BaseException,
                          finish_reason: str | None,
                          request_id: str | None) -> None:
    try:
        from agent_runtime.request_ledger import get_ledger
        get_ledger().diagnostic(
            request_id, parse_status="error",
            parse_error_type=type(error).__name__,
            finish_reason=finish_reason,
            response_chars=len(text) if text is not None else None,
            response_text_saved_by_chat_callback=text is not None,
        )
    except Exception:
        # A parser remains usable outside the ViMax runtime; ledger failures
        # are separately reported by RequestLedger itself.
        pass
