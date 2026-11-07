"""Qwen multimodal review through a loopback llama.cpp server; never cloud fallback."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

import httpx

from .gemini_client import GeminiError, read_env
from .storage import read_json, write_json
from .paths import runtime_root


DEFAULT_RUNTIME = runtime_root()


def local_schema(value):
    """llama.cpp accepts JSON Schema constraints; don't strip string/array bounds."""
    if isinstance(value, list):
        return [local_schema(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: local_schema(v) for k, v in value.items()}
    if "enum" in result and "type" not in result and all(isinstance(v, str) for v in result["enum"]):
        result["type"] = "string"
    return result


@dataclass
class LocalConfig:
    model: str = "qwen3-vl-2b-instruct"
    base_url: str = "http://127.0.0.1:8790/v1"
    runtime: Path = DEFAULT_RUNTIME
    timeout: float = 900
    max_output_tokens: int = 4096
    max_calls: int = 3
    max_total_tokens: int = 100_000
    provider: str = "local"
    input_mode: str = "vision"
    device: str = "cpu"

    def __post_init__(self):
        if self.device not in {'cpu', 'gpu'}:
            raise ValueError('LOCAL_DEVICE_MUST_BE_CPU_OR_GPU')
        if self.input_mode not in {"vision", "metadata"}:
            raise ValueError("LOCAL_INPUT_MODE_INVALID")
        url = urlsplit(self.base_url)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
                or url.username or url.password or url.query or url.fragment or url.path.rstrip("/") != "/v1"):
            raise ValueError("LOCAL_REVIEW_REQUIRES_LOOPBACK_HTTP_V1")
        self.base_url = self.base_url.rstrip("/")


class LocalClient:
    def __init__(self, config: LocalConfig, ledger: Path, *, transport=None):
        self.config, self.ledger = config, ledger
        key_path = config.runtime / "local-qwen-server.key"
        headers = {"Authorization": "Bearer " + key_path.read_text(encoding="utf-8").strip()} if key_path.exists() else {}
        self.client = httpx.Client(timeout=config.timeout, transport=transport, trust_env=False, follow_redirects=False, headers=headers)
        self.calls, self.tokens = 0, 0
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self.served_model = config.model

    def close(self):
        self.client.close()

    def _record(self, record: dict):
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"run_id": self.run_id, "at": datetime.now(timezone.utc).isoformat(),
                                    "provider": "local", "input_mode": self.config.input_mode,
                                    "cloud_api_calls": 0, **record}) + "\n")

    def preflight(self, target: Path | None = None):
        try:
            response = self.client.get(self.config.base_url + "/models")
            response.raise_for_status()
            models = response.json().get("data", [])
        except (httpx.HTTPError, ValueError):
            raise GeminiError("LOCAL_SERVER_UNAVAILABLE_RUN_LOCAL_START") from None
        if self.served_model not in {m.get("id") for m in models}:
            raise GeminiError("LOCAL_MODEL_NOT_SERVED")
        from .local_backend import load_manifest, manifest_path
        path = manifest_path(self.config.runtime, self.config.device)
        manifest = load_manifest(self.config.runtime, self.config.device) if path.exists() else {}
        if self.config.device == 'gpu' and not manifest:
            raise GeminiError('GPU_PROFILE_MISSING_RUN_LOCAL_BACKEND_SETUP')
        # Include exact weights in shared job cache keys; a filename alone is not identity.
        if manifest.get("served_model") == self.served_model:
            self.config.model = self.served_model + "@" + manifest["model_sha256"][:16]
        result = {"schema_version": "local-model-preflight/v1", "provider": "local", "selected_model": self.config.model,
                  "served_model": self.served_model, "base_url": self.config.base_url,
                  "model_sha256": manifest.get("model_sha256"), "threads": manifest.get("threads"),
                  "gpu_layers": manifest.get("gpu_layers"), "device": self.config.device, "cloud_api_calls": 0}
        result["input_mode"] = self.config.input_mode
        if target:
            write_json(target, result)
        return result

    def generate(self, parts: list[dict], schema: dict, instruction: str, job_key: str):
        if self.calls >= self.config.max_calls or self.tokens + self.config.max_output_tokens > self.config.max_total_tokens:
            raise GeminiError("RUN_BUDGET_REACHED")
        contents = []
        if self.config.input_mode == "metadata":
            # The complete package stays in the local audit; only its compact
            # model_input goes to the model. No image bytes enter inference.
            for part in parts:
                if "text" not in part:
                    continue
                try:
                    package = json.loads(part["text"].split("\n", 1)[-1])
                except ValueError:
                    continue
                if isinstance(package, dict) and "model_input" in package:
                    contents.append({"type": "text", "text": json.dumps(package["model_input"], ensure_ascii=False)})
                    break
            if not contents:
                raise ValueError("COMPACT_MODEL_INPUT_REQUIRED")
        for part in parts:
            if self.config.input_mode == "metadata":
                break
            if "text" in part:
                contents.append({"type": "text", "text": part["text"]})
            elif "inlineData" in part:
                inline = part["inlineData"]
                if inline["mimeType"] != "image/png":
                    raise ValueError("LOCAL_IMAGE_TYPE_UNSUPPORTED")
                contents.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + inline["data"]}})
        body = {"model": self.served_model, "messages": [{"role": "system", "content": instruction},
                    {"role": "user", "content": contents}], "temperature": 0, "max_tokens": self.config.max_output_tokens,
                "stream": False, "response_format": {"type": "json_schema", "json_schema": {
                    "name": "grounded_review", "strict": True, "schema": local_schema(schema)}}}
        self.calls += 1
        started = time.perf_counter()
        try:
            response = self.client.post(self.config.base_url + "/chat/completions", json=body)
        except httpx.RequestError as error:
            self._record({"job_key": job_key, "status": "LOCAL_NETWORK_ERROR_USAGE_UNKNOWN",
                          "error_type": type(error).__name__, "error": str(error),
                          "seconds": round(time.perf_counter() - started, 3)})
            raise GeminiError("LOCAL_NETWORK_ERROR_USAGE_UNKNOWN: " + type(error).__name__ + ': ' + str(error)) from None
        if response.status_code != 200:
            self._record({"job_key": job_key, "http_status": response.status_code})
            raise GeminiError(f"LOCAL_INFERENCE_HTTP_{response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise GeminiError("LOCAL_PROVIDER_JSON_INVALID") from None
        usage = payload.get("usage", {})
        mapped_usage = {"promptTokenCount": int(usage.get("prompt_tokens", 0)),
                        "candidatesTokenCount": int(usage.get("completion_tokens", 0)),
                        "totalTokenCount": int(usage.get("total_tokens", 0))}
        self.tokens += mapped_usage["totalTokenCount"]
        seconds = round(time.perf_counter() - started, 3)
        self._record({"job_key": job_key, "status": "RESPONSE_RECEIVED", "usage": mapped_usage, "seconds": seconds})
        choices = payload.get("choices", [])
        if not choices or choices[0].get("finish_reason") != "stop":
            return {"status": "INCOMPLETE_OR_BLOCKED", "payload": payload, "usage": mapped_usage, "seconds": seconds}
        try:
            result = json.loads(choices[0]["message"]["content"])
        except (ValueError, KeyError, TypeError):
            return {"status": "INVALID_MODEL_JSON", "payload": payload, "usage": mapped_usage, "seconds": seconds}
        return {"status": "RESPONSE_RECEIVED", "result": result, "payload": payload,
                "usage": mapped_usage, "seconds": seconds}


def resolve_provider(provider: str | None, env_file: Path) -> str:
    selected = provider or read_env(env_file).get("PDF_REVIEW_PROVIDER", "gemini")
    if selected not in {"local", "gemini"}:
        raise ValueError("REVIEW_PROVIDER_MUST_BE_LOCAL_OR_GEMINI")
    return selected


def create_client(provider, env_file, model, ledger, *, local_url=None, max_calls=3,
                  max_total_tokens=100_000, max_output_tokens=4096):
    if provider == "local":
        values = read_env(env_file)
        return LocalClient(LocalConfig(model=model or values.get("LOCAL_REVIEW_MODEL") or "qwen3-vl-2b-instruct",
            base_url=local_url or values.get("LOCAL_REVIEW_URL") or "http://127.0.0.1:8790/v1",
            max_calls=max_calls, max_total_tokens=max_total_tokens, max_output_tokens=max_output_tokens), ledger)
    from .gemini_client import GeminiClient, GeminiConfig
    return GeminiClient(GeminiConfig.load(env_file, model, max_calls=max_calls,
        max_total_tokens=max_total_tokens, max_output_tokens=max_output_tokens), ledger)
