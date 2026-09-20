"""OpenAI-compatible JSON completions (Verda / vLLM) with Pydantic validation."""

from __future__ import annotations

import os
import re
import time
from typing import TypeVar

from dotenv import load_dotenv
from openai import APIStatusError, OpenAI
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

# Served id on the current Verda container; GET /v1/models is the source of truth.
DEFAULT_MODEL = "mistralai/Mistral-Large-3-675B-Instruct-2512-NVFP4"
_resolved_model: str | None = None


def load_env() -> None:
    load_dotenv()


def get_api_key() -> str:
    load_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env.")
    return api_key


def get_model() -> str:
    load_env()
    if _resolved_model:
        return _resolved_model
    return (os.getenv("OPENAI_MODEL") or "").strip() or DEFAULT_MODEL


def get_base_url() -> str:
    load_env()
    raw = os.getenv("OPENAI_BASE_URL") or ""
    if not raw:
        raise RuntimeError("OPENAI_BASE_URL is not set. Copy .env.example to .env.")
    base = raw.rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base


def _client() -> OpenAI:
    return OpenAI(base_url=get_base_url(), api_key=get_api_key(), timeout=180.0)


def _served_model_ids(client: OpenAI) -> list[str]:
    try:
        return [item.id for item in client.models.list().data]
    except Exception:
        return []


class QuotaExceededError(RuntimeError):
    """Raised when the inference endpoint is rate-limited or out of quota."""


def _short_http_error(code: int, body: str) -> str:
    message = " ".join(str(body).split())
    if code == 429:
        return f"Verda is rate-limiting requests (HTTP 429). {message[:240]}"
    return f"Verda HTTP {code}: {message[:320]}"


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else stripped


def chat_json(messages: list[dict[str, str]]) -> str:
    global _resolved_model
    last_error: Exception | None = None
    use_json_object = True
    client = _client()
    for attempt in range(5):
        kwargs: dict = {
            "model": get_model(),
            "messages": messages,
            "temperature": 0,
        }
        if use_json_object:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            if not content.strip():
                raise RuntimeError("Verda returned an empty message.")
            return _strip_fences(content)
        except APIStatusError as exc:
            body = ""
            try:
                body = exc.response.text
            except Exception:
                body = str(exc)
            if use_json_object and exc.status_code == 400 and "json" in body.lower():
                use_json_object = False
                continue
            if exc.status_code == 404:
                served = [item for item in _served_model_ids(client) if item != get_model()]
                if served:
                    _resolved_model = served[0]
                    continue
            summary = _short_http_error(exc.status_code, body)
            last_error = QuotaExceededError(summary) if exc.status_code == 429 else RuntimeError(summary)
            if exc.status_code in {429, 503} and attempt < 4:
                time.sleep(float(8 * (attempt + 1)))
                continue
            raise last_error from None
    raise last_error or RuntimeError("Verda request failed")


def complete_json(
    *,
    system: str,
    user: str,
    response_model: type[T],
    retries: int = 1,
) -> T:
    """Ask the model for JSON and validate it against ``response_model``."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system + "\nReturn a single JSON object only."},
        {"role": "user", "content": user},
    ]
    last_error: Exception | None = None
    last_raw = ""

    for _ in range(retries + 1):
        last_raw = chat_json(messages)
        try:
            return response_model.model_validate_json(last_raw)
        except ValidationError as exc:
            last_error = exc
            messages.append({"role": "assistant", "content": last_raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your JSON did not match the required schema.\n"
                        f"Validation errors:\n{exc}\n"
                        "Return a corrected JSON object only."
                    ),
                }
            )

    raise RuntimeError(
        f"Model output failed {response_model.__name__} validation.\n"
        f"Last error: {last_error}\nLast raw output:\n{last_raw}"
    )
