"""Minimal API clients (standard library only) for generation.

Each client takes a model config and a prompt and returns a dict with the raw
response body, the HTTP status, the text, token counts and the model
identifier returned by the API. API keys are read from the environment
variable named in the config (`api_key_env`) and are never returned, logged
or written: `request_record` strips every credential header.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

SECRET_HEADERS = {"authorization", "x-api-key", "x-goog-api-key", "api-key"}


class ProviderError(Exception):
    def __init__(self, msg, status=None, retryable=False, body=None, retry_after=None):
        super().__init__(msg)
        self.status, self.retryable, self.body, self.retry_after = status, retryable, body, retry_after


def _key(cfg):
    env = cfg.get("api_key_env")
    if not env:
        return None  # e.g. a local server without authentication
    k = os.environ.get(env)
    if not k:
        raise ProviderError(f"environment variable {env} is not set")
    return k


def build_request(cfg, prompt):
    """Returns (url, headers, body) for one generation request."""
    p = cfg["provider"]
    params = dict(cfg.get("params") or {})
    key = _key(cfg)
    if p == "openai_compat":
        body = {"model": cfg["model"], "messages": [{"role": "user", "content": prompt}], **params}
        h = {"Content-Type": "application/json"}
        if key:
            h["Authorization"] = f"Bearer {key}"
        h.update(cfg.get("extra_headers") or {})
        return cfg["base_url"].rstrip("/") + "/chat/completions", h, body
    if p == "anthropic":
        body = {"model": cfg["model"], "messages": [{"role": "user", "content": prompt}], **params}
        h = {"Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"}
        return cfg.get("base_url", "https://api.anthropic.com").rstrip("/") + "/v1/messages", h, body
    if p == "gemini":
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], **params}
        h = {"Content-Type": "application/json", "x-goog-api-key": key}
        base = cfg.get("base_url", "https://generativelanguage.googleapis.com/v1beta")
        return f"{base.rstrip('/')}/models/{cfg['model']}:generateContent", h, body
    raise ProviderError(f"unknown provider {p}")


def request_record(url, headers, body):
    """What is logged: everything except credentials."""
    return {"url": url, "headers": {k: v for k, v in headers.items() if k.lower() not in SECRET_HEADERS},
            "body": body}


def parse(cfg, raw):
    p = cfg["provider"]
    if p == "openai_compat":
        ch = (raw.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        u = raw.get("usage") or {}
        det = u.get("completion_tokens_details") or {}
        return {"text": msg.get("content") or "", "finish_reason": ch.get("finish_reason"),
                "model_returned": raw.get("model"), "response_id": raw.get("id"),
                "input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens"),
                "reasoning_tokens": det.get("reasoning_tokens"), "provider_returned": raw.get("provider")}
    if p == "anthropic":
        text = "".join(b.get("text", "") for b in raw.get("content") or [] if b.get("type") == "text")
        u = raw.get("usage") or {}
        return {"text": text, "finish_reason": raw.get("stop_reason"), "model_returned": raw.get("model"),
                "response_id": raw.get("id"), "input_tokens": u.get("input_tokens"),
                "output_tokens": u.get("output_tokens"), "reasoning_tokens": None}
    if p == "gemini":
        c = (raw.get("candidates") or [{}])[0]
        parts = (c.get("content") or {}).get("parts") or []
        text = "".join(x.get("text", "") for x in parts if not x.get("thought"))
        u = raw.get("usageMetadata") or {}
        return {"text": text, "finish_reason": c.get("finishReason"), "model_returned": raw.get("modelVersion"),
                "response_id": raw.get("responseId"), "input_tokens": u.get("promptTokenCount"),
                "output_tokens": (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0),
                "reasoning_tokens": u.get("thoughtsTokenCount")}
    raise ProviderError(f"unknown provider {p}")


def send(cfg, prompt, timeout_s=600):
    """One HTTP exchange. Raises ProviderError (retryable for 408/429/5xx and
    network errors); returns (request_record, raw_json, parsed, latency_s)."""
    url, headers, body = build_request(cfg, prompt)
    rec = request_record(url, headers, body)
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            raw_bytes = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        b = e.read()[:20000].decode("utf-8", "replace")
        ra = e.headers.get("Retry-After") if e.headers else None
        raise ProviderError(f"HTTP {e.code}", status=e.code, retryable=e.code in (402, 408, 409, 429) or e.code >= 500 or (e.code == 403 and "Key limit exceeded" in b),
                            body=b,  # 402: balance held by batch reservations or a top-up pending
                            retry_after=ra) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise ProviderError(f"network: {e!r}", retryable=True) from None
    latency = time.monotonic() - t0
    try:
        raw = json.loads(raw_bytes)
    except ValueError:
        raise ProviderError("response is not JSON", status=status, retryable=True,
                            body=raw_bytes[:20000].decode("utf-8", "replace")) from None
    if isinstance(raw, dict) and raw.get("error"):  # some gateways return errors with 200
        raise ProviderError(f"API error: {json.dumps(raw['error'])[:300]}", status=status, retryable=True, body=raw)
    return rec, raw, parse(cfg, raw), latency
