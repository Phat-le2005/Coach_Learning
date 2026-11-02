"""Small server-side Gemini client: bounded requests, no SDK, no secret logging."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

import httpx

from .storage import write_json


ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_ENV = Path(__file__).parents[1] / ".env"


class GeminiError(ValueError):
    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.retryable = retryable


def read_env(path: Path) -> dict[str, str]:
    """Read only literal assignments; never execute/source a secret file."""
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" not in line:
                raise GeminiError("ENV_INVALID_ASSIGNMENT")
            name, value = line.split("=", 1)
            name, value = name.strip(), value.strip()
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                raise GeminiError("ENV_INVALID_NAME")
            if value[:1] in {"'", '"'}:
                if value[-1:] != value[:1]:
                    raise GeminiError("ENV_UNCLOSED_QUOTE")
                value = value[1:-1]
            else:
                value = value.split(" #", 1)[0].strip()
            values[name] = value
    return values


def provider_schema(schema):
    """Use the portable provider subset; the complete contract is enforced locally."""
    if isinstance(schema, list):
        return [provider_schema(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    result = {}
    for key, value in schema.items():
        if key in {"type", "enum", "required", "description"}:
            result[key] = value
        elif key == "properties":
            result[key] = {name: provider_schema(spec) for name, spec in value.items()}
        elif key == "items":
            result[key] = provider_schema(value)
    if "enum" in result and "type" not in result:
        result["type"] = "string"
    return result


def quota_diagnostics(response) -> dict:
    """Keep only rate-limit fields; never persist arbitrary provider error text."""
    result = {}
    try:
        error = response.json().get("error", {})
    except ValueError:
        return result
    for detail in error.get("details", []):
        kind = detail.get("@type", "")
        if kind.endswith("RetryInfo"):
            delay = detail.get("retryDelay", "")
            if re.fullmatch(r"\d+(?:\.\d+)?s", str(delay)):
                result["retry_delay_seconds"] = float(delay[:-1])
        elif kind.endswith("QuotaFailure"):
            result["quota_violations"] = [{k: v for k, v in violation.items() if k in {
                "quotaMetric", "quotaId", "quotaValue"}} for violation in detail.get("violations", [])]
    header = response.headers.get("retry-after", "")
    if header.isdigit():
        result["retry_delay_seconds"] = max(result.get("retry_delay_seconds", 0), float(header))
    return result


@dataclass
class GeminiConfig:
    api_key: str = field(repr=False)
    model: str = ""
    timeout: float = 180
    max_output_tokens: int = 8192
    max_calls: int = 20
    max_total_tokens: int = 250_000
    retries: int = 2

    @classmethod
    def load(cls, path: Path = DEFAULT_ENV, model: str | None = None, **kwargs):
        values = read_env(path)
        key = os.environ.get("GEMINI_API_KEY") or values.get("GEMINI_API_KEY", "")
        if not key or any(c.isspace() for c in key):
            raise GeminiError("GEMINI_KEY_MISSING_OR_INVALID")
        selected = model or os.environ.get("GEMINI_MODEL") or values.get("GEMINI_MODEL", "")
        if selected and not re.fullmatch(r"gemini-[a-zA-Z0-9._-]+", selected):
            raise GeminiError("GEMINI_MODEL_INVALID")
        return cls(key, selected, **kwargs)


class GeminiClient:
    def __init__(self, config: GeminiConfig, ledger: Path, *, transport=None, sleeper=time.sleep):
        self.config, self.ledger = config, ledger
        self.client = httpx.Client(timeout=config.timeout, transport=transport)
        self.sleep = sleeper
        self.calls, self.tokens = 0, 0
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")

    def close(self):
        self.client.close()

    def _record(self, record: dict):
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"run_id": self.run_id, "at": datetime.now(timezone.utc).isoformat(), **record}, ensure_ascii=False) + "\n")

    def models(self) -> list[dict]:
        result, token = [], None
        for _ in range(10):
            try:
                response = self.client.get(ENDPOINT + "/models", headers={"x-goog-api-key": self.config.api_key},
                                           params={"pageSize": 100, **({"pageToken": token} if token else {})})
            except httpx.RequestError:
                raise GeminiError("MODEL_PREFLIGHT_NETWORK_ERROR") from None
            if response.status_code != 200:
                raise GeminiError(f"MODEL_PREFLIGHT_HTTP_{response.status_code}")
            payload = response.json()
            result.extend(payload.get("models", []))
            token = payload.get("nextPageToken")
            if not token:
                return result
        raise GeminiError("MODEL_CATALOG_TOO_LARGE")

    def preflight(self, target: Path | None = None) -> dict:
        available = {m["name"].removeprefix("models/"): m for m in self.models()
                     if "generateContent" in m.get("supportedGenerationMethods", [])}
        if not self.config.model:
            self.config.model = next((m for m in ("gemini-3.6-flash", "gemini-3.8-flash", "gemini-2.5-flash") if m in available), "")
        if self.config.model not in available:
            raise GeminiError("CONFIGURED_MODEL_UNAVAILABLE_SET_GEMINI_MODEL")
        result = {"schema_version": "gemini-preflight/v1", "selected_model": self.config.model,
                  "input_token_limit": available[self.config.model].get("inputTokenLimit"),
                  "output_token_limit": available[self.config.model].get("outputTokenLimit"),
                  "available_flash_models": sorted(m for m in available if "flash" in m and not any(t in m for t in ("image", "tts", "live", "audio"))),
                  "api_key_configured": True, "generation_calls": 0}
        if target:
            write_json(target, result)
        return result

    def generate(self, parts: list[dict], schema: dict, instruction: str, job_key: str) -> dict:
        if not self.config.model:
            raise GeminiError("PREFLIGHT_REQUIRED")
        generation = {"temperature": 0, "maxOutputTokens": self.config.max_output_tokens,
                      "responseMimeType": "application/json", "responseJsonSchema": provider_schema(schema)}
        if self.config.model.startswith("gemini-2.5"):
            generation["thinkingConfig"] = {"thinkingBudget": 512}
        elif self.config.model.startswith("gemini-3"):
            generation["thinkingConfig"] = {"thinkingLevel": "low"}
        body = {"systemInstruction": {"parts": [{"text": instruction}]},
                "contents": [{"role": "user", "parts": parts}], "generationConfig": generation}
        encoded = json.dumps(body).encode("utf-8")
        if len(encoded) > 18_000_000:
            raise GeminiError("REQUEST_TOO_LARGE_SPLIT_SOURCE_WINDOW")
        for attempt in range(self.config.retries + 1):
            if self.calls >= self.config.max_calls or self.tokens + self.config.max_output_tokens > self.config.max_total_tokens:
                raise GeminiError("RUN_BUDGET_REACHED")
            self.calls += 1
            started = time.perf_counter()
            try:
                response = self.client.post(f"{ENDPOINT}/models/{self.config.model}:generateContent",
                    headers={"x-goog-api-key": self.config.api_key, "Content-Type": "application/json"}, content=encoded)
            except httpx.RequestError:
                self._record({"job_key": job_key, "model": self.config.model, "attempt": attempt + 1,
                              "status": "NETWORK_ERROR_USAGE_UNKNOWN"})
                # A timeout may still have incurred inference cost; do not replay automatically.
                raise GeminiError("NETWORK_ERROR_USAGE_UNKNOWN") from None
            metadata = {"job_key": job_key, "model": self.config.model, "attempt": attempt + 1,
                        "http_status": response.status_code, "seconds": round(time.perf_counter() - started, 3)}
            if response.status_code != 200:
                diagnostics = quota_diagnostics(response) if response.status_code == 429 else {}
                self._record({**metadata, **diagnostics})
                retryable = response.status_code == 429 or response.status_code in {500, 502, 503}
                daily_quota = any("perday" in (str(v.get("quotaMetric", ""))+str(v.get("quotaId", ""))).lower()
                                  for v in diagnostics.get("quota_violations", []))
                if daily_quota:
                    raise GeminiError("GEMINI_DAILY_QUOTA_EXHAUSTED")
                if retryable and attempt < self.config.retries:
                    delay = diagnostics.get("retry_delay_seconds", 30 if response.status_code == 429 else 2 ** (attempt + 1))
                    if delay > 55:
                        raise GeminiError("GEMINI_RATE_LIMIT_LONG_COOLDOWN", retryable=True)
                    self.sleep(max(1, delay))
                    continue
                # Never echo provider error bodies: credentials or source text may be reflected.
                raise GeminiError(f"GEMINI_HTTP_{response.status_code}", retryable=retryable)
            try:
                payload = response.json()
            except ValueError:
                self._record({**metadata, "status": "INVALID_PROVIDER_JSON_USAGE_UNKNOWN"})
                raise GeminiError("INVALID_PROVIDER_JSON_USAGE_UNKNOWN") from None
            usage = payload.get("usageMetadata", {})
            self.tokens += int(usage.get("totalTokenCount", 0))
            self._record({**metadata, "status": "RESPONSE_RECEIVED", "usage": usage})
            candidates = payload.get("candidates", [])
            if not candidates or candidates[0].get("finishReason") != "STOP":
                return {"status": "INCOMPLETE_OR_BLOCKED", "payload": payload, "usage": usage, "seconds": metadata["seconds"]}
            text = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []) if not p.get("thought"))
            try:
                result = json.loads(text)
            except ValueError:
                return {"status": "INVALID_MODEL_JSON", "payload": payload, "usage": usage, "seconds": metadata["seconds"]}
            return {"status": "RESPONSE_RECEIVED", "result": result, "payload": payload,
                    "usage": usage, "seconds": metadata["seconds"]}
        raise GeminiError("RETRIES_EXHAUSTED")


def content_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
