"""Thin LLM adapter. The rest of the code calls `complete_json()` only.

The provider is chosen by `config.LLM_PROVIDER` ("gemini" or "claude").
Keys are read from .env: GEMINI_API_KEY or ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from . import config


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


class LLMError(RuntimeError):
    pass


def _key(name: str) -> str:
    load_dotenv()
    key = os.environ.get(name, "").strip()
    if not key:
        raise LLMError(f"{name} is not set in .env")
    return key


def _complete_gemini(system: str, user: str, timeout_s: float) -> LLMResult:
    from google import genai
    from google.genai import types

    model = config.LLM_MODELS["gemini"]
    client = genai.Client(
        api_key=_key("GEMINI_API_KEY"),
        http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
    )
    resp = client.models.generate_content(
        model=model,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
        ),
    )
    return LLMResult(text=resp.text or "", provider="gemini", model=model)


def _complete_claude(system: str, user: str, timeout_s: float) -> LLMResult:
    import anthropic

    model = config.LLM_MODELS["claude"]
    client = anthropic.Anthropic(api_key=_key("ANTHROPIC_API_KEY"), timeout=timeout_s)
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return LLMResult(text=text, provider="claude", model=model)


_PROVIDERS = {"gemini": _complete_gemini, "claude": _complete_claude}


def complete(system: str, user: str, timeout_s: float | None = None) -> LLMResult:
    """Return the raw text answer from the configured provider."""
    fn = _PROVIDERS.get(config.LLM_PROVIDER)
    if fn is None:
        raise LLMError(f"unknown LLM_PROVIDER {config.LLM_PROVIDER!r}")
    return fn(system, user, timeout_s or config.LLM_TIMEOUT_S)


def complete_json(system: str, user: str, timeout_s: float | None = None) -> dict:
    """Ask for JSON and parse it. Strips code fences if the model adds them."""
    res = complete(system, user, timeout_s)
    text = res.text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)
