"""NaraRouter-only model construction for the GitHub Issue Agent.

The active evaluated path is NaraRouter + laguna-s-2.1 over direct HTTP
Chat Completions with ZERO client retries (controlled-evaluation rule:
provider errors must surface as provider failures, never be absorbed or
silently retried).

Failure semantics (strict):
  * Every HTTP/transport failure raises ``NaraProviderError`` with the
    exact provider message and HTTP status preserved.
  * ``classify_provider_failure`` maps any exception/message onto the
    canonical failure taxonomy used by the evaluation harness:
      PROVIDER FAILURE      auth / rate_limit / server / unavailable /
                            timeout / model_unavailable / invalid_response
      INFRASTRUCTURE ERROR  local subprocess / collection / environment
      GENUINE AGENT FAILURE model responded; patch/tests were wrong
"""

from __future__ import annotations

import json
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------

# Canonical failure categories.
PROVIDER_FAILURE = "provider_failure"
INFRA_FAILURE = "infrastructure_failure"
AGENT_FAILURE = "agent_failure"
UNKNOWN_FAILURE = "unknown_failure"

# Provider sub-categories.
_PROVIDER_HTTP_MAP = {
    401: "provider_auth_error",
    403: "provider_auth_error",
    404: "provider_model_unavailable",
    408: "provider_timeout",
    429: "provider_rate_limit",
    500: "provider_server_error",
    502: "provider_server_error",
    503: "provider_unavailable",
    504: "provider_timeout",
}

_PROVIDER_MARKERS = (
    "provider_auth_error", "provider_rate_limit", "provider_server_error",
    "provider_unavailable", "provider_timeout", "provider_model_unavailable",
    "provider_invalid_response",
)


def provider_name() -> str:
    provider = os.getenv("PROVIDER", "nara").strip().lower() or "nara"
    if provider != "nara":
        raise ValueError(f"Unsupported provider {provider!r}; only 'nara' is supported")
    return provider


def model_name() -> str:
    provider_name()
    return os.getenv("NARAROUTER_MODEL", "laguna-s-2.1").strip() or "laguna-s-2.1"


def request_timeout(default: float = 30.0) -> float:
    """LLM call timeout in seconds (>= 120s required for controlled runs)."""
    provider_name()
    configured = float(os.getenv("NARA_LLM_TIMEOUT", "120").strip() or "120")
    return max(configured, default) if default and default > configured else configured


def provider_info() -> dict:
    """Non-secret provider metadata for instrumentation and reports."""
    return {
        "provider": provider_name(),
        "requested_model": model_name(),
        "base_url": os.getenv("NARAROUTER_BASE_URL", "https://router.bynara.id/v1").strip(),
        "client_retries": 0,
    }


def pricing_note() -> str:
    return (
        f"NaraRouter {model_name()}: estimated from token counts "
        "($0.59/M input, $0.79/M output reference rate)"
    )


def classify_provider_failure(error: object) -> tuple[str, bool]:
    """Classify an exception or error message.

    Returns (failure_category, is_provider_failure) where failure_category is
    one of the canonical taxonomy values above. Never guesses: anything not
    recognizably a provider or infrastructure failure is ``unknown_failure``
    and is treated conservatively (not a clean agent failure).
    """
    if isinstance(error, NaraProviderError):
        sub = _PROVIDER_HTTP_MAP.get(error.status_code)
        if sub:
            return sub, True
        if error.error_type:
            return error.error_type, True
        return "provider_invalid_response", True

    text = ""
    if isinstance(error, BaseException):
        text = f"{type(error).__name__}: {error}"
    else:
        text = str(error or "")

    lower = text.lower()

    # Provider markers embedded in stored error strings.
    for marker in _PROVIDER_MARKERS:
        if marker in lower:
            return marker, True

    # HTTP statuses mentioned in the message (e.g. "Error code: 502").
    for code, sub in _PROVIDER_HTTP_MAP.items():
        if f"error code: {code}" in lower or f"http {code}" in lower or f"status {code}" in lower:
            return sub, True

    # Auth / quota phrases common to OpenAI-compatible routers.
    if any(k in lower for k in ("invalid api key", "invalid_api_key", "unauthorized",
                                "authentication", "quota", "billing")):
        return "provider_auth_error", True
    if "rate limit" in lower or "too many requests" in lower:
        return "provider_rate_limit", True
    if "model_not_found" in lower or "model not found" in lower or "does not exist" in lower and "model" in lower:
        return "provider_model_unavailable", True
    if any(k in lower for k in ("bad gateway", "service unavailable",
                                "overloaded", "internal server error")):
        return "provider_server_error", True
    if "timed out" in lower or "timeout" in lower or "timedout" in lower:
        if isinstance(error, (socket.timeout, TimeoutError)):
            return "provider_timeout", True
        return "provider_timeout", True
    if any(k in lower for k in ("connection", "unreachable", "urlopen error",
                                "ssl", "getaddrinfo failed", "name or service not known",
                                "newconnectionerror", "max retries exceeded with url")):
        return "provider_unavailable", True
    if "empty or invalid response" in lower or "invalid nara response" in lower:
        return "provider_invalid_response", True

    return UNKNOWN_FAILURE, False


class NaraProviderError(RuntimeError):
    """Explicit error from the NaraRouter HTTP endpoint."""

    def __init__(self, message: str, status_code: int | None = None,
                 error_type: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


class NaraChatModel(BaseChatModel):
    """Small LangChain-compatible direct HTTP Chat Completions client.

    Zero retries by design: one call, exact errors, no hidden fallback.
    """

    model: str
    api_key: str = Field(repr=False)
    base_url: str
    timeout: float = 120.0
    max_retries: int = 0

    @property
    def _llm_type(self) -> str:
        return "nararouter-chat"

    @staticmethod
    def _message_payload(message: BaseMessage) -> dict[str, str]:
        role = {"human": "user", "ai": "assistant"}.get(message.type, message.type)
        content = message.content
        if not isinstance(content, str):
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        return {"role": role, "content": content}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        payload = {
            "model": self.model,
            "messages": [self._message_payload(message) for message in messages],
            "stream": False,
        }
        request = Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status_code = response.status
                response_body = response.read().decode("utf-8")
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise NaraProviderError(
                self._error_message(body, str(error)), error.code
            ) from error
        except URLError as error:
            reason = str(error.reason)
            if isinstance(error.reason, (socket.timeout, TimeoutError)) or "timed out" in reason.lower():
                raise NaraProviderError(f"NaraRouter request timed out: {reason}",
                                        error_type="provider_timeout") from error
            raise NaraProviderError(f"NaraRouter connection failed: {reason}",
                                    error_type="provider_unavailable") from error
        except socket.timeout as error:
            raise NaraProviderError("NaraRouter request timed out",
                                    error_type="provider_timeout") from error

        try:
            data = json.loads(response_body)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise NaraProviderError(
                f"Invalid NaraRouter response (HTTP {status_code}): {response_body[:500]}",
                status_code,
                "provider_invalid_response",
            ) from error

        usage = data.get("usage") or {}
        message = AIMessage(
            content=content,
            response_metadata={"model": data.get("model", ""), "http_status": status_code},
            usage_metadata={
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    @staticmethod
    def _error_message(body: str, fallback: str) -> str:
        try:
            error = json.loads(body).get("error", {})
            return error.get("message") or fallback
        except (AttributeError, TypeError, json.JSONDecodeError):
            return body or fallback


def get_chat_model() -> NaraChatModel:
    provider_name()
    model = model_name()
    base_url = os.getenv("NARAROUTER_BASE_URL", "https://router.bynara.id/v1").strip()
    api_key = os.getenv("NARAROUTER_API_KEY", "").strip()
    print("[PROVIDER] nara")
    print(f"[MODEL] {model}")
    print(f"[BASE URL] {base_url}")
    return NaraChatModel(
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout=request_timeout(),
        max_retries=0,
    )
