"""Thin wrappers around the chat model (OpenAI-compatible, Azure Foundry v1, the
Nexus AI APIM gateway, and the Anthropic Messages API).

When no model is configured, chat() returns None and callers fall back to
deterministic logic, so the demo always runs.
"""

from __future__ import annotations

import datetime
import json
import logging
import sys
from typing import Any

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

# A single pooled HTTP client, reused across calls with keep-alive so we don't
# open a new socket per request (which exhausts Windows ephemeral ports — WinError
# 10048 — during a 53-call audit).
_HTTP_CLIENT: "httpx.Client | None" = None


def _http() -> "httpx.Client":
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.Client(
            timeout=60,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _HTTP_CLIENT


def _trace(kind: str, request: Any, response: Any) -> None:
    """When AUDITOR_DEBUG_LLM is on, print the exact request/response for an
    outbound AI call to stderr (and append to AUDITOR_LLM_LOG if set). This is
    how you see the prompts/payloads going to the model."""
    s = get_settings()
    if not s.debug_llm:
        return
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    req = request if isinstance(request, str) else json.dumps(request, indent=2, default=str)
    res = response if isinstance(response, str) else json.dumps(response, indent=2, default=str)
    block = (f"\n===== [{ts}] {kind} =====\n"
             f"--- REQUEST ---\n{req[:6000]}\n"
             f"--- RESPONSE ---\n{res[:6000]}\n"
             f"{'=' * 52}")
    print(block, file=sys.stderr, flush=True)
    if s.llm_log_file:
        try:
            with open(s.llm_log_file, "a", encoding="utf-8") as fh:
                fh.write(block + "\n")
        except OSError as exc:
            log.warning("Could not write AUDITOR_LLM_LOG: %s", exc)


def _build_client():
    """Return an OpenAI-compatible client for the configured endpoint.

    Two endpoint styles are supported:

    * Classic Azure OpenAI  (``https://<res>.openai.azure.com``) -> ``AzureOpenAI``
      client with an API key + api-version.
    * Microsoft Foundry "v1" (``https://<res>.services.ai.azure.com/openai/v1``)
      -> the plain ``OpenAI`` client pointed at ``base_url``, authenticated with
      either an API key or a Microsoft Entra ID bearer token.

    Both expose ``.chat.completions.create(...)``.
    """
    s = get_settings()

    if s.use_gateway:
        # APIM / custom gateway (e.g. Nexus AI): the key goes in a custom header, not
        # Authorization. The endpoint is the OpenAI base_url verbatim; the client then
        # POSTs to <endpoint>/chat/completions with the api-version query param.
        from openai import OpenAI

        default_query = {"api-version": s.azure_openai_api_version} if s.azure_openai_api_version else {}
        return OpenAI(
            base_url=s.azure_openai_endpoint.rstrip("/"),
            api_key="unused",  # gateway ignores Authorization; real key is in the custom header
            default_headers={s.gateway_auth_header: s.azure_openai_key},
            default_query=default_query,
        )

    if s.is_foundry_v1:
        from openai import OpenAI  # imported lazily so mock mode needs no SDK

        base = s.azure_openai_endpoint.rstrip("/")
        if not base.endswith("/openai/v1"):
            base = base + "/openai/v1"

        if s.azure_auth_mode == "entra":
            # Microsoft Entra ID (managed identity / az login / DefaultAzureCredential).
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), "https://ai.azure.com/.default"
            )
            # The token expires; fetch a fresh one per client build.
            return OpenAI(base_url=base, api_key=token_provider())

        # API-key auth against the v1 endpoint.
        return OpenAI(base_url=base, api_key=s.azure_openai_key)

    # Classic Azure OpenAI.
    from openai import AzureOpenAI

    return AzureOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_key,
        api_version=s.azure_openai_api_version,
    )


def _gateway_chat(messages: list[dict[str, str]], model: str, temperature: float,
                  max_tokens: int, json_mode: bool) -> str | None:
    """Raw POST to the APIM gateway's OpenAI-compatible chat endpoint, mirroring the
    documented curl: the team key in the custom header, content-type JSON, the
    api-version query param, and NO Authorization header."""
    s = get_settings()
    url = s.azure_openai_endpoint.rstrip("/") + "/chat/completions"
    params = {"api-version": s.azure_openai_api_version} if s.azure_openai_api_version else {}
    headers = {s.gateway_auth_header: s.azure_openai_key, "content-type": "application/json"}

    base: dict[str, Any] = {"model": model, "messages": messages}
    if json_mode:
        base["response_format"] = {"type": "json_object"}
    dep = model.lower()
    next_gen = dep.startswith(("gpt-5", "o1", "o3", "o4"))
    cap = max(max_tokens, 2048) if next_gen else max_tokens
    # Try progressively simpler bodies — endpoints differ on which token field they accept.
    if next_gen:
        bodies = [{**base, "max_completion_tokens": cap}, {**base, "max_tokens": cap}, dict(base)]
    else:
        bodies = [{**base, "max_tokens": max_tokens, "temperature": temperature}, dict(base)]

    last_err: Exception | None = None
    for body in bodies:
        try:
            r = _http().post(url, params=params, headers=headers, json=body)
            r.raise_for_status()
            content = (r.json()["choices"][0]["message"]["content"] or "")
            _trace("Nexus AI gateway · chat.completions",
                   {"url": url, "params": params, "model": model, "messages": messages}, content)
            return content
        except Exception as e:  # noqa: BLE001 — try the next body shape
            last_err = e
    log.warning("Gateway chat call failed: %s", last_err)
    return None


def chat(messages: list[dict[str, str]], temperature: float = 0.0, max_tokens: int = 600,
         json_mode: bool = False, model: str | None = None) -> str | None:
    """Call the configured chat model. Returns None if not configured or on error.
    `model` overrides the configured deployment (used by the preflight check)."""
    s = get_settings()
    if not s.llm_available:
        return None
    if s.provider == "anthropic":
        # Target the Claude model via the APIM Anthropic endpoint.
        return anthropic_chat(messages, model=model, max_tokens=max_tokens, json_mode=json_mode)
    model = model or s.azure_openai_deployment
    if s.use_gateway:
        # APIM gateway: call it with a raw POST that mirrors the documented curl
        # exactly — ONLY the custom auth header + content-type, no Authorization
        # header (the OpenAI SDK always sends Authorization, which the gateway rejects).
        return _gateway_chat(messages, model, temperature, max_tokens, json_mode)
    try:
        client = _build_client()
        kwargs: dict[str, Any] = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        # Next-gen / reasoning models (gpt-5*, o1*, o3*, o4*) rename the token cap to
        # max_completion_tokens and only accept the default temperature. They also
        # spend part of the budget on hidden "reasoning" tokens, so a small cap can
        # leave zero tokens for the visible answer (an empty reply). We therefore (a)
        # give the budget a floor and (b) ask for minimal reasoning on these simple
        # classification/answer tasks, so output isn't eaten by reasoning.
        dep = model.lower()
        next_gen = dep.startswith(("gpt-5", "o1", "o3", "o4"))
        cap = max(max_tokens, 2048) if next_gen else max_tokens

        # Try the modern params first, then degrade: endpoints differ on whether they
        # accept reasoning_effort and max_completion_tokens vs the classic max_tokens.
        if next_gen:
            variants = [
                {**kwargs, "max_completion_tokens": cap, "reasoning_effort": "minimal"},
                {**kwargs, "max_completion_tokens": cap},
                {**kwargs, "max_tokens": cap},
            ]
            if not dep.startswith("gpt-5"):
                variants = variants[1:]  # reasoning_effort is a gpt-5 flag
        else:
            variants = [{**kwargs, "max_tokens": max_tokens, "temperature": temperature}]

        resp = None
        last_exc: Exception | None = None
        for kw in variants:
            try:
                resp = client.chat.completions.create(
                    model=model, messages=messages, **kw)
                break
            except Exception as e:  # noqa: BLE001 — try the next param shape
                last_exc = e
        if resp is None:
            raise last_exc or RuntimeError("no response")
        content = resp.choices[0].message.content or ""
        _trace("OpenAI · chat.completions",
               {"model": model, "messages": messages, **kwargs}, content)
        return content
    except Exception as exc:  # content filter blocks, network errors, quota...
        log.warning("Azure OpenAI call failed: %s", exc)
        return None


def anthropic_chat(messages: list[dict[str, str]], model: str | None = None,
                   max_tokens: int = 64, json_mode: bool = False) -> str | None:
    """Call the Nexus AI gateway's Claude (Anthropic Messages API) endpoint,
    mirroring the documented curl. The team key is sent in the custom header.

    The Messages API differs from OpenAI chat: `system` is a top-level field (not
    a message), and `messages` must be user/assistant only, start with `user`, and
    alternate. We split out system prompts and merge consecutive same-role turns.
    Returns the reply text, or None if not configured / on error."""
    s = get_settings()
    if not (s.anthropic_endpoint and s.azure_openai_key):
        return None
    model = model or s.anthropic_model
    # The gateway's messages path carries v1 twice: .../v1/anthropic/v1/messages
    url = s.anthropic_endpoint.rstrip("/") + "/v1/messages"
    headers = {
        (s.gateway_auth_header or "mtb-client_id"): s.azure_openai_key,
        "anthropic-version": s.anthropic_version,
        "content-type": "application/json",
    }

    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    convo: list[dict[str, str]] = []
    for m in messages:
        if m.get("role") not in ("user", "assistant"):
            continue
        if convo and convo[-1]["role"] == m["role"]:      # merge consecutive same-role turns
            convo[-1]["content"] += "\n" + m["content"]
        else:
            convo.append({"role": m["role"], "content": m["content"]})
    if not convo or convo[0]["role"] != "user":
        convo.insert(0, {"role": "user", "content": "(begin)"})

    payload: dict[str, Any] = {"model": model, "max_tokens": max(max_tokens, 512), "messages": convo}
    if system:
        payload["system"] = system
    try:
        r = _http().post(url, headers=headers, json=payload)
        r.raise_for_status()
        body = r.json()
        parts = [b.get("text", "") for b in body.get("content", []) if b.get("type") == "text"]
        text = " ".join(p for p in parts if p).strip()
        _trace("Nexus AI · Anthropic messages",
               {"url": url, "model": model, "system": system, "messages": convo}, body)
        return text
    except Exception as exc:
        log.warning("Anthropic gateway call failed: %s", exc)
        return None


def chat_json(messages: list[dict[str, str]], **kwargs: Any) -> dict | None:
    raw = chat(messages, json_mode=True, **kwargs)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON output: %s", raw[:200])
        return None
