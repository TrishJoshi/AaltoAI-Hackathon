"""Gemini generateContent JSON completions with Pydantic validation."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"


def load_env() -> None:
    load_dotenv()


def get_api_key() -> str:
    load_env()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Copy .env.example to .env.")
    return api_key


def get_model() -> str:
    load_env()
    return os.getenv("GEMINI_MODEL") or os.getenv("OPENAI_MODEL") or DEFAULT_GEMINI_MODEL


def get_base_url() -> str:
    load_env()
    raw = os.getenv("GEMINI_BASE_URL") or DEFAULT_GEMINI_BASE_URL
    base = raw.rstrip("/")
    if ":generateContent" in base:
        base = base.split("/models/", 1)[0]
    for suffix in ("/openai", "/chat/completions", "/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base


def _retry_seconds(error_body: str, attempt: int) -> float:
    try:
        payload = json.loads(error_body)
        details = payload[0]["error"].get("details", []) if isinstance(payload, list) else payload.get("error", {}).get("details", [])
        for detail in details:
            delay = detail.get("retryDelay")
            if delay:
                return max(float(str(delay).rstrip("s")), 1.0)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass
    return float(8 * (attempt + 1))


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")
    parts = candidates[0].get("content", {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts)


def generate_content(*, system: str, contents: list[dict[str, Any]]) -> str:
    url = f"{get_base_url()}/models/{get_model()}:generateContent"
    payload: dict[str, Any] = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None

    for attempt in range(5):
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-goog-api-key": get_api_key(),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return _extract_text(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"Gemini HTTP {exc.code}: {error_body}")
            if exc.code in {429, 503} and attempt < 4:
                time.sleep(_retry_seconds(error_body, attempt))
                continue
            raise last_error from None

    raise last_error or RuntimeError("Gemini request failed")


def complete_json(
    *,
    system: str,
    user: str,
    response_model: type[T],
    retries: int = 1,
) -> T:
    """Ask the model for JSON and validate it against ``response_model``."""
    contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": user}]}]
    last_error: Exception | None = None
    last_raw = ""

    for _ in range(retries + 1):
        last_raw = generate_content(system=system, contents=contents)
        try:
            return response_model.model_validate_json(last_raw)
        except ValidationError as exc:
            last_error = exc
            contents.append({"role": "model", "parts": [{"text": last_raw}]})
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Your JSON did not match the required schema.\n"
                                f"Validation errors:\n{exc}\n"
                                "Return a corrected JSON object only."
                            )
                        }
                    ],
                }
            )

    raise RuntimeError(
        f"Model output failed {response_model.__name__} validation.\n"
        f"Last error: {last_error}\nLast raw output:\n{last_raw}"
    )
