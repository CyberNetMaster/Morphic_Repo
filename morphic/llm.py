"""Thin LLM adapter. The rest of the code calls `complete_json()` only.

The provider is chosen by `config.LLM_PROVIDER` ("gemini" or "claude").
Keys are read from .env: GEMINI_API_KEY or ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from . import config


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


class LLMError(RuntimeError):
    pass


_LOG = logging.getLogger(__name__)
_AGENT_LOCK = threading.Lock()
_AGENT_GATE_PATH = Path(__file__).resolve().parents[1] / ".plans/live_runs/agent-llm.lock"


def wait_for_agent_slot() -> None:
    """Space request starts across threads and local agent worker processes.

    Only a monotonic timestamp is stored, never prompts or credentials. Lock the
    first byte while waiting/reserving a slot; release it before the HTTP call.
    """
    with _AGENT_LOCK:
        _AGENT_GATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _AGENT_GATE_PATH.open("a+b") as gate:
            gate.seek(0, 2)
            if gate.tell() == 0:
                gate.write(b" ")
                gate.flush()
            if os.name == "nt":
                import msvcrt

                while True:
                    gate.seek(0)
                    try:
                        msvcrt.locking(gate.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
            else:
                import fcntl

                fcntl.flock(gate.fileno(), fcntl.LOCK_EX)
            try:
                gate.seek(1)
                stamp = gate.read().strip()
                if stamp:
                    elapsed = time.monotonic() - float(stamp)
                    delay = config.AGENT_LLM_INTERVAL_S - max(0.0, elapsed)
                    if delay > 0:
                        time.sleep(delay)
                gate.seek(1)
                gate.truncate()
                gate.write(str(time.monotonic()).encode("ascii"))
                gate.flush()
            finally:
                if os.name == "nt":
                    gate.seek(0)
                    msvcrt.locking(gate.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(gate.fileno(), fcntl.LOCK_UN)


def request_timeout_budget(timeout_s: float) -> float:
    """Worst-case HTTP attempt time plus all transport backoff delays."""
    return (timeout_s * (1 + config.LLM_HTTP_RETRIES)
            + config.LLM_BACKOFF_INITIAL_S * (2 ** config.LLM_HTTP_RETRIES - 1))


def _status_code(exc: Exception) -> int | None:
    for code in (getattr(exc, "code", None), getattr(exc, "status_code", None),
                 getattr(getattr(exc, "response", None), "status_code", None)):
        if isinstance(code, int):
            return code
    return None


def _key(name: str) -> str:
    # Read only this checkout's .env; never copy credentials into the environment.
    key = (dotenv_values(Path(__file__).resolve().parents[1] / ".env").get(name) or "").strip()
    if not key:
        raise LLMError(f"{name} is not set in .env")
    return key


def _complete_gemini(system: str, user: str, timeout_s: float) -> LLMResult:
    from google import genai
    from google.genai import types

    model = config.LLM_MODELS["gemini"]
    client = genai.Client(
        api_key=_key("GEMINI_API_KEY"),
        http_options=types.HttpOptions(timeout=int(timeout_s * 1000),
                                       retry_options=types.HttpRetryOptions(attempts=1)),
    )
    try:
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
            ),
        )
    finally:
        client.close()
    return LLMResult(text=resp.text or "", provider="gemini", model=model)


def _complete_claude(system: str, user: str, timeout_s: float) -> LLMResult:
    import anthropic

    model = config.LLM_MODELS["claude"]
    client = anthropic.Anthropic(api_key=_key("ANTHROPIC_API_KEY"), timeout=timeout_s,
                                max_retries=0)
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    finally:
        client.close()
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return LLMResult(text=text, provider="claude", model=model)


_PROVIDERS = {"gemini": _complete_gemini, "claude": _complete_claude}


def complete(system: str, user: str, timeout_s: float | None = None, *,
             before_attempt=None) -> LLMResult:
    """Return text; retry HTTP 429/503 four times before the caller falls back.

    ``before_attempt`` reserves an agent request slot, including transport retries.
    SDK retries are disabled so the attempt count and spacing remain under our control.
    """
    fn = _PROVIDERS.get(config.LLM_PROVIDER)
    if fn is None:
        raise LLMError(f"unknown LLM_PROVIDER {config.LLM_PROVIDER!r}")
    for attempt in range(config.LLM_HTTP_RETRIES + 1):
        if before_attempt is not None:
            before_attempt()
        try:
            return fn(system, user, timeout_s or config.LLM_TIMEOUT_S)
        except LLMError:
            raise
        except Exception as exc:
            code = _status_code(exc)
            if code in (429, 503) and attempt < config.LLM_HTTP_RETRIES:
                delay = config.LLM_BACKOFF_INITIAL_S * 2 ** attempt
                _LOG.info("%s HTTP %s; retry %s/%s in %g s", config.LLM_PROVIDER,
                          code, attempt + 1, config.LLM_HTTP_RETRIES, delay)
                time.sleep(delay)
                continue
            # SDK exceptions can include request URLs. Never save their raw text.
            status = f", status {code}" if code is not None else ""
            raise LLMError(f"{config.LLM_PROVIDER} request failed "
                           f"({type(exc).__name__}{status}; {attempt + 1} attempts)") from None


def complete_json(system: str, user: str, timeout_s: float | None = None) -> dict:
    """Ask for JSON and parse it. Strips code fences if the model adds them."""
    res = complete(system, user, timeout_s)
    text = res.text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)
