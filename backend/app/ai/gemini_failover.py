"""Model-first Gemini scheduling shared across worker threads and async callers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
import hashlib
import json
import logging
import os
import re
import threading
import time
import httpx
from typing import Callable, Generic, TypeVar
from uuid import uuid4

from dotenv import dotenv_values
from pydantic import SecretStr

from app.core.config import Settings

logger = logging.getLogger(__name__)
T = TypeVar("T")
MODEL_ID = re.compile(r"^gemini-[a-zA-Z0-9._-]{1,90}$")
ALIAS = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
DEFAULT_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)
GRADING_TASKS = {"OPEN_RESPONSE_EVALUATION", "STEP_REVIEW"}


@dataclass(frozen=True)
class Credential:
    id: str
    project: str
    secret: SecretStr = field(repr=False)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.secret.get_secret_value().encode()).hexdigest()


@dataclass(frozen=True)
class Choice:
    credential: Credential = field(repr=False)
    model: str
    lease: str
    snapshots: tuple = field(repr=False)


@dataclass
class Payload(Generic[T]):
    data: T
    served_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class Execution(Generic[T]):
    data: T
    model: str
    requested_model: str
    key_id: str
    project: str
    attempts: int
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class AttemptFailure(Exception):
    """Only normalized metadata; never retain provider bodies/headers/secrets."""

    def __init__(
        self,
        kind: str,
        *,
        status: int = 0,
        scope: str = "project_model",
        retry_after: float | None = None,
    ):
        super().__init__(kind)
        self.kind, self.status, self.scope, self.retry_after = (
            kind,
            status,
            scope,
            retry_after,
        )


class PoolUnavailable(Exception):
    def __init__(self, reason: str, last_kind: str = "UNAVAILABLE"):
        super().__init__(reason)
        self.reason, self.last_kind = reason, last_kind


def _csv(value: str) -> list[str]:
    return list(dict.fromkeys(x.strip() for x in value.split(",") if x.strip()))


def credentials_from_settings(settings: Settings) -> tuple[Credential, ...]:
    raw = settings.gemini_key_pool.get_secret_value().strip()
    entries = []
    if raw:
        try:
            rows = json.loads(raw)
            if not isinstance(rows, list):
                raise ValueError()
            # The application already loads this .env. Only explicitly referenced
            # GEMINI_KEY_* variables are read; arbitrary application secrets cannot
            # be used as credential references. Respect Settings(_env_file=None).
            values = {}
            paths = settings._gemini_env_file
            for path in paths if isinstance(paths, (list, tuple)) else [paths]:
                if path:
                    values.update(dotenv_values(path, interpolate=False))
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or not ALIAS.fullmatch(row.get("id", ""))
                    or not ALIAS.fullmatch(row.get("project", ""))
                ):
                    raise ValueError()
                ref = row.get("env", "")
                if ref and not re.fullmatch(r"GEMINI_KEY_[A-Z0-9_]+", ref):
                    raise ValueError()
                key = (
                    os.environ.get(ref, values.get(ref, ""))
                    if ref
                    else row.get("key", "")
                )
                if not isinstance(key, str) or not key.strip():
                    logger.warning(
                        "gemini_pool_entry_disabled key_id=%s reason=MISSING_SECRET",
                        row["id"],
                    )
                    continue
                entries.append(
                    Credential(row["id"], row["project"], SecretStr(key.strip()))
                )
        except (ValueError, TypeError, KeyError):
            raise PoolUnavailable("INVALID_POOL_CONFIGURATION") from None
    else:
        # Unlabelled credentials conservatively share one unknown quota group.
        plural = settings.ai_api_keys.get_secret_value()
        keys = (
            _csv(plural)
            if plural.strip()
            else _csv(
                ",".join(
                    (
                        settings.ai_api_key.get_secret_value(),
                        settings.gemini_api_key.get_secret_value(),
                        settings.gemini_api_keys.get_secret_value(),
                    )
                )
            )
        )
        entries = [
            Credential(f"legacy_{i + 1}", "unknown", SecretStr(key))
            for i, key in enumerate(keys)
        ]
    result, ids, fingerprints = [], set(), {}
    for entry in entries:
        if entry.id in ids:
            raise PoolUnavailable("DUPLICATE_KEY_ID")
        ids.add(entry.id)
        if entry.fingerprint in fingerprints:
            if fingerprints[entry.fingerprint] != entry.project:
                raise PoolUnavailable("CONFLICTING_PROJECT_GROUPS")
            continue
        fingerprints[entry.fingerprint] = entry.project
        result.append(entry)
    return tuple(result)


def _retry_delay(body: dict, header: str | None) -> float | None:
    if header:
        try:
            return max(0, float(header))
        except (ValueError, TypeError):
            try:
                return max(0, parsedate_to_datetime(header).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                pass
    error = body.get("error")
    details = error.get("details", []) if isinstance(error, dict) else []
    for detail in details if isinstance(details, list) else []:
        if isinstance(detail, dict):
            delay = detail.get("retryDelay", "")
            if isinstance(delay, str) and re.fullmatch(r"\d+(?:\.\d+)?s", delay):
                return float(delay[:-1])
    return None


def classify_failure(
    status: int, body: dict | None = None, retry_after: str | None = None
) -> AttemptFailure:
    body = body if isinstance(body, dict) else {}
    error = body.get("error", {})
    error = error if isinstance(error, dict) else {}
    # Parsing is private. No provider text is interpolated into logs/exceptions.
    details = error.get("details", []) or []
    details = details if isinstance(details, list) else []
    reasons = {str(d.get("reason", "")).upper() for d in details if isinstance(d, dict)}
    description = json.dumps(error, ensure_ascii=True).lower()
    if reasons & {"CONSUMER_SUSPENDED", "ACCOUNT_DISABLED", "LOCATION_POLICY_VIOLATED"}:
        return AttemptFailure("RESTRICTED", status=status, scope="fatal")
    if status == 401 or any(r.startswith("API_KEY_") for r in reasons):
        return AttemptFailure("AUTH", status=status, scope="key")
    if status == 403:
        return AttemptFailure("PERMISSION", status=status, scope="key_model")
    if status == 404:
        return AttemptFailure("MODEL_UNAVAILABLE", status=status, scope="key_model")
    if status == 429:
        global_quota = any(
            w in description for w in ("spend", "billing", "credit", 'perproject"')
        )
        kind = (
            "DAILY_QUOTA"
            if "perday" in description or "daily" in description
            else "QUOTA"
        )
        return AttemptFailure(
            kind,
            status=status,
            scope="project" if global_quota else "project_model",
            retry_after=_retry_delay(body, retry_after),
        )
    if status in {408, 500, 502, 503, 504}:
        return AttemptFailure("TRANSIENT", status=status)
    return AttemptFailure("INVALID_REQUEST", status=status, scope="fatal")


def sdk_failure(error: Exception) -> AttemptFailure:
    code = getattr(error, "code", getattr(error, "status_code", 0))
    try:
        code = int(code)
    except (ValueError, TypeError):
        code = 0
    # google-genai 3 stores the complete response JSON in details, whereas
    # earlier adapters/test doubles may expose response_json.
    body = getattr(error, "response_json", None)
    if body is None:
        body = getattr(error, "details", None)
    if code:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None)
        return classify_failure(
            code, body, headers.get("Retry-After") if headers is not None else None
        )
    if isinstance(error, (TimeoutError,)) or "timeout" in type(error).__name__.lower():
        return AttemptFailure("TIMEOUT")
    if isinstance(error, (httpx.RequestError, ConnectionError, OSError)):
        return AttemptFailure("NETWORK")
    # Unexpected programming/parser failures must not be treated as quota.
    return AttemptFailure("INVALID_REQUEST", scope="fatal")


def generation_parameters(model: str, *, temperature: float | None = None) -> dict:
    # Gemini 3 migration removes legacy sampling controls. Older models retain them.
    return (
        {"temperature": temperature}
        if temperature is not None and model.startswith("gemini-2.")
        else {}
    )


class GeminiFailoverManager:
    def __init__(
        self,
        settings: Settings,
        credentials: tuple[Credential, ...] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.settings = settings
        self.credentials = (
            credentials
            if credentials is not None
            else credentials_from_settings(settings)
        )
        self.clock, self.lock = clock, threading.RLock()
        self.circuits: dict[tuple, tuple[float, int]] = {}
        self.probes: dict[tuple, str] = {}
        self.inflight: dict[tuple, int] = {}
        self.generation = 0
        self._manifest_stamp = None
        self._manifest: dict = {}

    @classmethod
    def single_key(cls, key: str):
        settings = Settings(
            _env_file=None,
            app_env="test",
            database_name="unused",
            database_user="unused",
        )
        return cls(
            settings,
            (Credential("legacy_1", "unknown", SecretStr(key)),) if key.strip() else (),
        )

    def _capabilities(self) -> dict:
        path = self.settings.gemini_capabilities_file
        if not path:
            return {}
        try:
            stamp = (path.stat().st_mtime_ns, path.stat().st_size)
            if stamp != self._manifest_stamp:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._manifest = data if isinstance(data, dict) else {}
                self._manifest_stamp = stamp
            if float(self._manifest.get("expires_at", 0)) <= time.time():
                return {}
            credentials = self._manifest.get("credentials", {})
            return credentials if isinstance(credentials, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def plan(
        self, task: str, requested: str, *, legacy: list[str] | None = None
    ) -> list[str]:
        configured = _csv(self.settings.gemini_model_priority)
        candidates = configured or list(dict.fromkeys([requested] + (legacy or [])))
        if task in GRADING_TASKS:
            approved = _csv(self.settings.gemini_grading_models) or [requested]
            candidates = [
                m
                for m in candidates
                if m in approved
                and ("lite" not in m or m in _csv(self.settings.gemini_grading_models))
            ]
        # Explicit new model lists must use documented profiles or verified capability data.
        with self.lock:
            available = self._capabilities()

            def known(model):
                return model in DEFAULT_MODELS or any(
                    model in d.get("models", {})
                    for d in available.values()
                    if isinstance(d, dict) and isinstance(d.get("models"), dict)
                )

            return [
                m
                for m in candidates
                if (MODEL_ID.fullmatch(m) and (not configured or known(m)))
                or (
                    not configured
                    and self.settings.app_env == "test"
                    and re.fullmatch(r"[a-zA-Z0-9._-]+", m)
                )
            ]

    def attempt_timeout(self, task: str) -> float:
        if task in GRADING_TASKS:
            return self.settings.gemini_review_attempt_timeout_seconds
        if task in {"TUTOR", "HINT"}:
            return self.settings.gemini_tutor_attempt_timeout_seconds
        if task == "OCR_INK":
            return self.settings.gemini_ocr_attempt_timeout_seconds
        return self.settings.gemini_attempt_timeout_seconds

    def _verified(self, credential: Credential, model: str, task: str) -> bool:
        available = self._capabilities()
        entry = available.get(credential.id, {})
        if not isinstance(entry, dict):
            return False
        if entry.get("fingerprint") != credential.fingerprint:
            return not self.settings.gemini_require_verified_models
        models = entry.get("models", {})
        if not isinstance(models, dict):
            return False
        if model not in models:
            return False
        flags = models[model]
        if not isinstance(flags, dict):
            return False
        needed = {"generateContent", "json"} | (
            {"vision"} if task in {"OCR_INK", "OCR_PAPER"} else set()
        )
        if task == "OCR_PAPER_PDF":
            needed.add("pdf")
        capabilities = flags.get("capabilities", [])
        return (
            isinstance(capabilities, list)
            and all(isinstance(capability, str) for capability in capabilities)
            and needed <= set(capabilities)
            and flags.get("available") is True
        )

    def _scopes(self, key: Credential, model: str) -> tuple:
        return (
            ("key", key.id),
            ("pair", key.id, model),
            ("project", key.project, "*"),
            ("project", key.project, model),
        )

    def _choose(self, models, attempted, task):
        with self.lock:
            now = self.clock()
            for model in models:
                busy = False
                for key in self.credentials:
                    pair = (key.id, model)
                    if pair in attempted or not self._verified(key, model, task):
                        continue
                    scopes = self._scopes(key, model)
                    states = tuple(
                        (scope, self.circuits.get(scope)) for scope in scopes
                    )
                    if any(state and state[0] > now for _, state in states):
                        continue
                    if any(scope in self.probes for scope, state in states if state):
                        # A recovery probe is local work in progress, not an
                        # unavailable upstream. Wait within the same deadline.
                        busy = True
                        continue
                    group = (key.project, model)
                    if (
                        self.inflight.get(group, 0)
                        >= self.settings.gemini_max_inflight_per_project_model
                    ):
                        busy = True
                        continue
                    lease = uuid4().hex
                    for scope, state in states:
                        if state:
                            self.probes[scope] = lease
                    self.inflight[group] = self.inflight.get(group, 0) + 1
                    return Choice(key, model, lease, states), False
                if busy:
                    return (
                        None,
                        True,
                    )  # Do not downgrade just because local slots are busy.
            return None, False

    def _release(
        self, choice: Choice, failure: AttemptFailure | None, *, recovered=True
    ):
        with self.lock:
            key = choice.credential
            group = (key.project, choice.model)
            self.inflight[group] = max(0, self.inflight.get(group, 0) - 1)
            for scope, observed in choice.snapshots:
                if self.probes.get(scope) == choice.lease:
                    self.probes.pop(scope, None)
                # A success started before a concurrent 429 cannot erase its cooldown.
                if (
                    recovered
                    and failure is None
                    and observed
                    and self.circuits.get(scope) == observed
                ):
                    self.circuits.pop(scope, None)
            if not failure or failure.scope == "fatal":
                return
            scope = {
                "key": ("key", key.id),
                "key_model": ("pair", key.id, choice.model),
                "project": ("project", key.project, "*"),
                "project_model": ("project", key.project, choice.model),
            }[failure.scope]
            if failure.kind in {"QUOTA", "DAILY_QUOTA"}:
                if key.project == "unknown":
                    scope = ("project", key.project, "*")
                delay = (
                    failure.retry_after
                    if failure.retry_after is not None
                    else (
                        3600
                        if failure.kind == "DAILY_QUOTA"
                        else self.settings.gemini_quota_cooldown_seconds
                    )
                )
            elif failure.scope in {"key", "key_model"}:
                delay = self.settings.gemini_auth_cooldown_seconds
            else:
                delay = self.settings.gemini_cooldown_seconds
            self.generation += 1
            self.circuits[scope] = (
                max(
                    self.clock() + max(0.1, delay), self.circuits.get(scope, (0, 0))[0]
                ),
                self.generation,
            )

    def _success(self, result, choice, requested, attempts, tick, request_id, task):
        served = result.served_model
        if not isinstance(served, str) or not MODEL_ID.fullmatch(served):
            served = choice.model
        elapsed = (self.clock() - tick) * 1000
        logger.info(
            "gemini_call_success request_id=%s task=%s requested_model=%s model=%s key_id=%s project=%s attempts=%d latency_ms=%.2f",
            request_id,
            task,
            requested,
            served,
            choice.credential.id,
            choice.credential.project,
            attempts,
            elapsed,
        )
        return Execution(
            result.data,
            served,
            requested,
            choice.credential.id,
            choice.credential.project,
            attempts,
            elapsed,
            result.input_tokens,
            result.output_tokens,
            result.total_tokens,
        )

    def _failed(self, choice, failure, request_id, task):
        self._release(choice, failure)
        logger.warning(
            "gemini_failover request_id=%s task=%s model=%s key_id=%s project=%s reason=%s status=%d",
            request_id,
            task,
            choice.model,
            choice.credential.id,
            choice.credential.project,
            failure.kind,
            failure.status,
        )
        if failure.scope == "fatal":
            raise PoolUnavailable(failure.kind, failure.kind) from None

    def _unavailable(self, reason, last, request_id, task, tick, attempts):
        logger.warning(
            "gemini_call_failed request_id=%s task=%s reason=%s last_kind=%s attempts=%d latency_ms=%.2f",
            request_id,
            task,
            reason,
            last,
            attempts,
            (self.clock() - tick) * 1000,
        )
        raise PoolUnavailable(reason, last)

    async def run_async(self, task, requested, send, *, timeout, legacy=None):
        models = self.plan(task, requested, legacy=legacy)
        tick = self.clock()
        deadline = tick + timeout
        attempted = set()
        last = "UNAVAILABLE"
        request_id = uuid4().hex
        while (
            self.clock() < deadline
            and len(attempted) < self.settings.gemini_failover_max_attempts
        ):
            choice, busy = self._choose(models, attempted, task)
            if not choice:
                if busy:
                    await asyncio.sleep(min(0.025, max(0, deadline - self.clock())))
                    continue
                self._unavailable(
                    "NO_AVAILABLE_CHOICE", last, request_id, task, tick, len(attempted)
                )
            attempted.add((choice.credential.id, choice.model))
            budget = min(self.attempt_timeout(task), deadline - self.clock())
            try:
                async with asyncio.timeout(budget):
                    result = await send(choice, budget)
            except AttemptFailure as failure:
                last = failure.kind
                self._failed(choice, failure, request_id, task)
            except (TimeoutError, asyncio.TimeoutError):
                failure = AttemptFailure("TIMEOUT")
                last = failure.kind
                self._failed(choice, failure, request_id, task)
            except BaseException:
                self._release(choice, None, recovered=False)
                raise
            else:
                self._release(choice, None)
                if self.clock() >= deadline:
                    raise PoolUnavailable("DEADLINE", "TIMEOUT")
                return self._success(
                    result, choice, requested, len(attempted), tick, request_id, task
                )
        self._unavailable(
            "ATTEMPT_LIMIT" if self.clock() < deadline else "DEADLINE",
            last,
            request_id,
            task,
            tick,
            len(attempted),
        )


_MANAGERS: dict[int, GeminiFailoverManager] = {}
_MANAGER_LOCK = threading.Lock()


def get_gemini_manager(settings: Settings) -> GeminiFailoverManager:
    with _MANAGER_LOCK:
        key = id(settings)
        if key not in _MANAGERS:
            _MANAGERS[key] = GeminiFailoverManager(settings)
        return _MANAGERS[key]
