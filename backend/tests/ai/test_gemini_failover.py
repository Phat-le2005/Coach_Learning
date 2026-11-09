"""Deterministic fault simulations; no real credentials, network or database."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
from pydantic import BaseModel, SecretStr
import pytest

from app.ai.dependencies import create_ai_provider
from app.ai.exceptions import AIOutputValidationError, AIServiceUnavailableError
from app.ai.gateway import AIGateway
from app.ai.gemini_failover import (
    AttemptFailure,
    Credential,
    DEFAULT_MODELS,
    GeminiFailoverManager,
    Payload,
    PoolUnavailable,
    classify_failure,
    credentials_from_settings,
    get_gemini_manager,
    sdk_failure,
)
from app.ai.gemini_preflight import inspect_models
from app.ai.gemini_provider import GeminiProvider
from app.ai.types import AIMessage, AITaskType
from app.core.config import Settings
from app.math_ink.schemas import InkPoint, InkStroke
from app.math_ocr.dependencies import get_ocr_adapter
from app.math_ocr.gemini_adapter import GeminiMathOCRAdapter
from app.math_paper.ocr import GeminiPaperTranscriber

M1, M2 = DEFAULT_MODELS[:2]


def config(**kwargs):
    return Settings(
        _env_file=None,
        database_name="unused",
        database_user="unused",
        app_env="test",
        ai_provider="gemini",
        **kwargs,
    )


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


def pool(*, projects=("pA", "pB"), clock=None, **kwargs):
    credentials = tuple(
        Credential(f"key{i}", p, SecretStr(f"secret-{i}"))
        for i, p in enumerate(projects)
    )
    settings = config(gemini_model_priority=f"{M1},{M2}", **kwargs)
    return GeminiFailoverManager(
        settings, credentials, **({"clock": clock} if clock else {})
    )


def run(manager, send, *, task="TUTOR", timeout=30):
    async def call(choice, budget):
        return send(choice, budget)

    return asyncio.run(manager.run_async(task, M1, call, timeout=timeout))


def test_first_success_stops_immediately():
    seen = []
    result = run(
        pool(), lambda c, b: (seen.append((c.model, c.credential.id)), Payload("ok"))[1]
    )
    assert seen == [(M1, "key0")]
    assert result.attempts == 1 and result.data == "ok"


@pytest.mark.parametrize(
    "kind,scope",
    [
        ("AUTH", "key"),
        ("PERMISSION", "key_model"),
        ("MODEL_UNAVAILABLE", "key_model"),
        ("QUOTA", "project_model"),
        ("DAILY_QUOTA", "project_model"),
        ("TRANSIENT", "project_model"),
        ("TIMEOUT", "project_model"),
        ("NETWORK", "project_model"),
        ("OUTPUT_INVALID", "project_model"),
    ],
)
def test_one_bad_choice_does_not_interrupt_available_same_model(kind, scope):
    seen = []

    def send(choice, budget):
        seen.append((choice.model, choice.credential.id))
        if choice.credential.id == "key0":
            raise AttemptFailure(kind, scope=scope)
        return Payload("ok")

    result = run(pool(), send)
    assert seen == [(M1, "key0"), (M1, "key1")]
    assert result.attempts == 2


def test_all_primary_projects_fail_then_next_model_in_order():
    seen = []

    def send(c, b):
        seen.append((c.model, c.credential.id))
        if c.model == M1:
            raise AttemptFailure("TRANSIENT")
        return Payload("ok")

    assert run(pool(), send).model == M2
    assert seen == [(M1, "key0"), (M1, "key1"), (M2, "key0")]


def test_shared_project_quota_skips_other_key_but_keeps_other_project():
    seen = []

    def send(c, b):
        seen.append(c.credential.id)
        if c.credential.project == "same":
            raise AttemptFailure("QUOTA")
        return Payload("ok")

    assert run(pool(projects=("same", "same", "other")), send).key_id == "key2"
    assert seen == ["key0", "key2"]


def test_project_wide_quota_skips_models_of_only_that_project():
    seen = []

    def send(c, b):
        seen.append((c.model, c.credential.id))
        if c.credential.id == "key0":
            raise AttemptFailure("QUOTA", scope="project")
        if c.model == M1:
            raise AttemptFailure("TRANSIENT")
        return Payload("ok")

    assert run(pool(), send).model == M2
    assert seen == [(M1, "key0"), (M1, "key1"), (M2, "key1")]


@pytest.mark.parametrize(
    "status,body,kind,scope",
    [
        (400, {}, "INVALID_REQUEST", "fatal"),
        (401, {}, "AUTH", "key"),
        (400, {"error": {"details": [{"reason": "API_KEY_INVALID"}]}}, "AUTH", "key"),
        (403, {}, "PERMISSION", "key_model"),
        (404, {}, "MODEL_UNAVAILABLE", "key_model"),
        (
            403,
            {"error": {"details": [{"reason": "CONSUMER_SUSPENDED"}]}},
            "RESTRICTED",
            "fatal",
        ),
        (
            429,
            {"error": {"message": "daily perDay limit"}},
            "DAILY_QUOTA",
            "project_model",
        ),
        (429, {"error": {"message": "billing limit"}}, "QUOTA", "project"),
        (429, {"error": "malformed"}, "QUOTA", "project_model"),
        (408, {}, "TRANSIENT", "project_model"),
        (503, {}, "TRANSIENT", "project_model"),
    ],
)
def test_failure_classification(status, body, kind, scope):
    result = classify_failure(status, body)
    assert (result.kind, result.scope) == (kind, scope)


@pytest.mark.parametrize("kind", ["INVALID_REQUEST", "RESTRICTED"])
def test_invalid_or_restricted_request_does_not_cycle_credentials(kind):
    seen = []

    def send(c, b):
        seen.append(c)
        raise AttemptFailure(kind, scope="fatal")

    with pytest.raises(PoolUnavailable, match=kind):
        run(pool(), send)
    assert len(seen) == 1


def test_retry_after_and_recovery_returns_to_preferred_model():
    clock, manager = Clock(), None
    manager = pool(clock=clock)
    seen = []

    def send(c, b):
        seen.append(c.credential.id)
        if len(seen) == 1:
            raise classify_failure(429, {"error": {"details": [{"retryDelay": "20s"}]}})
        return Payload("ok")

    assert run(manager, send).key_id == "key1"
    clock.now += 19
    assert run(manager, send).key_id == "key1"
    clock.now += 2
    assert run(manager, send).key_id == "key0"
    assert not manager.circuits
    assert classify_failure(429, {}, "30").retry_after == 30


def test_no_duplicate_pair_and_18_is_only_a_ceiling():
    manager, seen = pool(projects=tuple(f"p{i}" for i in range(12))), []

    def send(c, b):
        seen.append((c.model, c.credential.id))
        raise AttemptFailure("PERMISSION", scope="key_model")

    with pytest.raises(PoolUnavailable, match="ATTEMPT_LIMIT"):
        run(manager, send)
    assert len(seen) == len(set(seen)) == 18
    assert sum(manager.inflight.values()) == 0


def test_deadline_passes_only_remaining_budget_and_stops():
    clock, budgets = Clock(), []
    manager = pool(clock=clock)

    def send(c, b):
        budgets.append(b)
        clock.now += b
        raise AttemptFailure("TIMEOUT")

    with pytest.raises(PoolUnavailable, match="DEADLINE"):
        run(manager, send, timeout=1)
    assert budgets == [1]


def test_hanging_async_choice_times_out_then_succeeds_without_backoff():
    async def scenario():
        manager = pool(gemini_tutor_attempt_timeout_seconds=0.1)
        calls = []

        async def send(c, budget):
            calls.append(c.credential.id)
            if c.credential.id == "key0":
                await asyncio.sleep(10)
            return Payload("ok")

        start = time.monotonic()
        result = await manager.run_async("TUTOR", M1, send, timeout=0.5)
        assert result.data == "ok" and calls == ["key0", "key1"]
        assert time.monotonic() - start < 0.5

    asyncio.run(scenario())


def test_concurrent_requests_wait_for_slots_without_downgrading_or_leaking():
    async def scenario():
        manager = pool(projects=("pA",), gemini_max_inflight_per_project_model=2)
        active, peak, seen = 0, 0, []

        async def send(c, b):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            seen.append(c.model)
            await asyncio.sleep(0.01)
            active -= 1
            return Payload("ok")

        results = await asyncio.gather(
            *(manager.run_async("TUTOR", M1, send, timeout=1) for _ in range(12))
        )
        assert all(r.data == "ok" for r in results)
        assert peak == 2 and set(seen) == {M1}
        assert sum(manager.inflight.values()) == 0

    asyncio.run(scenario())


def test_sync_and_async_share_cooldown_and_one_half_open_probe():
    async def scenario():
        clock, entered, release = Clock(), asyncio.Event(), asyncio.Event()
        manager = pool(clock=clock)

        def fail(c, b):
            if c.credential.id == "key0":
                raise AttemptFailure("TRANSIENT")
            return Payload("ok")

        async def fail_async(c, b):
            return fail(c, b)

        await manager.run_async("OCR_INK", M1, fail_async, timeout=30)
        clock.now += 16
        calls = []

        async def send(c, b):
            calls.append(c.credential.id)
            if c.credential.id == "key0":
                entered.set()
                await release.wait()
            return Payload("ok")

        first = asyncio.create_task(manager.run_async("TUTOR", M1, send, timeout=30))
        await entered.wait()
        second = await manager.run_async("TUTOR", M1, send, timeout=30)
        assert second.key_id == "key1"
        release.set()
        assert (await first).key_id == "key0"
        assert calls.count("key0") == 1 and not manager.probes and not manager.circuits

    asyncio.run(scenario())


def test_concurrent_old_success_cannot_clear_new_quota_and_cancel_does_not_mark_healthy():
    manager = pool(clock=Clock())
    first, _ = manager._choose([M1], set(), "TUTOR")
    second, _ = manager._choose([M1], set(), "TUTOR")
    manager._release(second, AttemptFailure("QUOTA"))
    state = dict(manager.circuits)
    manager._release(first, None)
    assert manager.circuits == state

    async def scenario():
        clock = Clock()
        manager = pool(clock=clock)
        choice, _ = manager._choose([M1], set(), "TUTOR")
        manager._release(choice, AttemptFailure("TRANSIENT"))
        clock.now += 16
        entered = asyncio.Event()

        async def send(c, b):
            entered.set()
            await asyncio.sleep(10)

        request = asyncio.create_task(manager.run_async("TUTOR", M1, send, timeout=30))
        await entered.wait()
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert (
            manager.circuits
            and not manager.probes
            and sum(manager.inflight.values()) == 0
        )

    asyncio.run(scenario())


def test_threaded_ocr_requests_obey_shared_capacity():
    manager = pool(projects=("pA",), gemini_max_inflight_per_project_model=1)

    async def send(c, b):
        await asyncio.sleep(0.005)
        return Payload("ok")

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda _: asyncio.run(
                    manager.run_async("OCR_INK", M1, send, timeout=2)
                ),
                range(8),
            )
        )
    assert all(r.model == M1 for r in results)
    assert sum(manager.inflight.values()) == 0


def test_private_logging_and_credentials_configuration(monkeypatch, caplog, tmp_path):
    monkeypatch.setenv("GEMINI_KEY_A", "private-A")
    settings = config(
        ai_api_key="ignored-key",
        gemini_key_pool=json.dumps(
            [
                {"id": "A", "project": "pA", "env": "GEMINI_KEY_A"},
                {"id": "B", "project": "pB", "key": "private-B"},
            ]
        ),
    )
    credentials = credentials_from_settings(settings)
    assert [c.id for c in credentials] == ["A", "B"]
    assert "private-" not in repr(settings) + repr(credentials)
    manager = GeminiFailoverManager(settings)
    with caplog.at_level(logging.INFO):

        def send(c, b):
            if c.credential.id == "A":
                raise classify_failure(
                    400,
                    {
                        "error": {
                            "details": [{"reason": "API_KEY_INVALID"}],
                            "message": "private-A",
                        }
                    },
                )
            return Payload("ok")

        run(manager, send)
    assert "private-A" not in caplog.text and "private-B" not in caplog.text
    assert "latency_ms=" in caplog.text and "attempts=2" in caplog.text
    assert (
        get_ocr_adapter(settings).manager
        is create_ai_provider(settings).manager
        is get_gemini_manager(settings)
    )


def test_plural_legacy_and_shared_unknown_quota():
    settings = config(ai_api_key="old", ai_api_keys="A,B,A")
    assert [
        c.secret.get_secret_value() for c in credentials_from_settings(settings)
    ] == ["A", "B"]
    manager = GeminiFailoverManager(settings)
    calls = []

    def send(c, b):
        calls.append(c)
        raise AttemptFailure("QUOTA")

    with pytest.raises(PoolUnavailable):
        run(manager, send)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "rows",
    [
        "not-json",
        "{}",
        '[{"id":"bad/name","project":"p","key":"private"}]',
        '[{"id":"A","project":"p","env":"JWT_SECRET_KEY"}]',
        '[{"id":"A","project":"p","key":"same"},{"id":"B","project":"q","key":"same"}]',
    ],
)
def test_invalid_pool_is_controlled_and_private(rows):
    with pytest.raises(PoolUnavailable) as error:
        credentials_from_settings(config(gemini_key_pool=rows))
    assert "private" not in str(error.value)


def test_env_file_references_use_exact_settings_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        'GEMINI_KEY_A=file-private\nGEMINI_KEY_POOL=\'[{"id":"A","project":"pA","env":"GEMINI_KEY_A"}]\'\n'
    )
    settings = Settings(
        _env_file=path, app_env="test", database_name="unused", database_user="unused"
    )
    assert (
        credentials_from_settings(settings)[0].secret.get_secret_value()
        == "file-private"
    )


def manifest(tmp_path, manager, entries):
    path = tmp_path / "capabilities.json"
    path.write_text(
        json.dumps(
            {
                "expires_at": time.time() + 3600,
                "credentials": {
                    c.id: {"fingerprint": c.fingerprint, "models": entries}
                    for c in manager.credentials
                },
            }
        )
    )
    manager.settings.gemini_capabilities_file = path
    manager.settings.gemini_require_verified_models = True
    return path


def test_verified_task_compatibility_expiry_fingerprint_and_grading(tmp_path):
    manager = pool()
    manifest(
        tmp_path,
        manager,
        {
            M1: {"available": True, "capabilities": ["generateContent", "json"]},
            M2: {
                "available": True,
                "capabilities": ["generateContent", "json", "vision", "pdf"],
            },
        },
    )
    assert run(manager, lambda c, b: Payload("ok")).model == M1
    assert run(manager, lambda c, b: Payload("ok"), task="OCR_INK").model == M2
    assert run(manager, lambda c, b: Payload("ok"), task="OCR_PAPER_PDF").model == M2
    manager.settings.gemini_grading_models = M2
    assert (
        run(manager, lambda c, b: Payload("ok"), task="OPEN_RESPONSE_EVALUATION").model
        == M2
    )
    manager.settings.gemini_capabilities_file.write_text(json.dumps({"expires_at": 0}))
    with pytest.raises(PoolUnavailable):
        run(manager, lambda c, b: Payload("ok"))
    manager.settings.gemini_capabilities_file = None
    with pytest.raises(PoolUnavailable):
        run(manager, lambda c, b: Payload("ok"))


def test_grading_never_implicitly_falls_back_to_lite_or_other_model():
    manager = pool()
    assert manager.plan("OPEN_RESPONSE_EVALUATION", M1) == [M1]
    manager.settings.gemini_model_priority += ",gemini-2.5-flash-lite"
    assert manager.plan("OPEN_RESPONSE_EVALUATION", M1) == [M1]
    manager.settings.gemini_grading_models = f"{M1},gemini-2.5-flash-lite"
    assert manager.plan("OPEN_RESPONSE_EVALUATION", M1) == [M1, "gemini-2.5-flash-lite"]
    manager.settings.gemini_model_priority = "gemini-invented-model"
    assert manager.plan("TUTOR", M1) == []


class Output(BaseModel):
    value: int


def response(value=4, model=M2):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": json.dumps({"value": value})}]},
                }
            ],
            "modelVersion": model,
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 2,
                "thoughtsTokenCount": 3,
                "totalTokenCount": 15,
            },
        },
    )


@pytest.mark.parametrize("structured", [True, False])
def test_gateway_reports_actual_model_usage_and_no_outer_retries(structured):
    manager, calls, usage = pool(), [], MagicMock()

    def handler(request):
        model = request.url.path.split("/")[-1].split(":")[0]
        calls.append((model, request.headers["x-goog-api-key"]))
        body = json.loads(request.content)
        assert "temperature" not in body["generationConfig"]  # Gemini 3 parameters.
        return httpx.Response(404) if model == M1 else response()

    gateway = AIGateway(
        GeminiProvider(manager=manager, transport=httpx.MockTransport(handler)),
        manager.settings,
    )

    async def scenario():
        if structured:
            return await gateway.generate_structured(
                AITaskType.TUTOR, Output, "test", usage_service=usage
            )
        return await gateway.generate(AITaskType.TUTOR, "test", usage_service=usage)

    result = asyncio.run(scenario())
    assert result.model == M2 and len(calls) == 3
    log = usage.record_log.call_args.kwargs
    assert (log["model"], log["input_tokens"], log["output_tokens"]) == (M2, 10, 5)
    manager2 = pool()
    calls.clear()
    gateway.provider = GeminiProvider(
        manager=manager2,
        transport=httpx.MockTransport(
            lambda request: (calls.append(request.url.path), httpx.Response(503))[1]
        ),
    )
    with pytest.raises(AIServiceUnavailableError):
        asyncio.run(scenario())
    assert len(calls) == 4  # 2 models x 2 projects, never repeated by Gateway.


@pytest.mark.parametrize(
    "payload", [[], {}, {"candidates": [{"finishReason": "SAFETY"}]}]
)
def test_provider_malformed_output_or_safety_is_controlled(payload):
    provider = GeminiProvider(
        manager=pool(),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
    )
    with pytest.raises(AIOutputValidationError):
        asyncio.run(
            provider.generate_structured(
                [AIMessage(role="user", content="test")], Output, M1
            )
        )


def test_paper_and_ink_share_gateway_state_and_bound_sdk_timeout(monkeypatch):
    manager, seen = pool(), []

    # Gateway identifies an invalid key; both OCR consumers immediately avoid it.
    def handler(request):
        key = request.headers["x-goog-api-key"]
        seen.append(key)
        return httpx.Response(401) if key == "secret-0" else response()

    provider = GeminiProvider(manager=manager, transport=httpx.MockTransport(handler))
    asyncio.run(provider.generate([AIMessage(role="user", content="test")], M1))

    def paper(request):
        assert request.headers["x-goog-api-key"] == "secret-1"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": '{"suggestions":[{"page_number":1,"kind":"FORMULA","text":"2+2=5","uncertain":false}]}'
                                }
                            ]
                        },
                    }
                ]
            },
        )

    output = asyncio.run(
        GeminiPaperTranscriber(
            settings=manager.settings,
            manager=manager,
            transport=httpx.MockTransport(paper),
        ).transcribe(b"image", "image/png")
    )
    assert output.suggestions[0].text == "2+2=5"
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        text='{"latex":"2+2=5"}', model_version=M1
    )
    client.aio.__aenter__.return_value = client
    client.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text='{"latex":"2+2=5"}', model_version=M1)
    )

    def get_client(key, **kwargs):
        assert key == "secret-1"
        return client

    monkeypatch.setattr("app.math_ocr.gemini_adapter._get_genai_client", get_client)
    strokes = [
        InkStroke(
            id=uuid4(),
            tool="PEN",
            width=2,
            color="#000000",
            points=[InkPoint(x=0.1, y=0.1), InkPoint(x=0.2, y=0.2)],
        )
    ]
    result = GeminiMathOCRAdapter(settings=manager.settings, manager=manager).recognize(
        strokes
    )
    assert result.latex == "2+2=5"
    options = client.models.generate_content.call_args.kwargs["config"].http_options
    assert options.timeout <= 8000 and options.retry_options.attempts == 1
    assert seen == ["secret-0", "secret-1"]


def test_sdk_network_and_timeout_are_transient():
    assert sdk_failure(httpx.ConnectError("private")).kind == "NETWORK"
    assert sdk_failure(TimeoutError("private")).kind == "TIMEOUT"
    assert sdk_failure(RuntimeError("403 private")).kind == "INVALID_REQUEST"


def test_preflight_offline_never_constructs_http_client(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: pytest.fail("Offline preflight opened network client"),
    )
    result = asyncio.run(inspect_models(config(ai_api_key="private")))
    assert result["mode"] == "offline" and not result["verified"]
    assert "private" not in json.dumps(result)


def test_preflight_metadata_alone_not_sufficient_and_mock_probes_verify(tmp_path):
    settings = config(ai_api_key="fixture", gemini_model_priority=M1)

    def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200, json={"supportedGenerationMethods": ["generateContent"]}
            )
        parts = json.loads(request.content)["contents"][0]["parts"]
        value = (
            4
            if len(parts) == 1
            else ("red" if parts[0]["inlineData"]["mimeType"] == "image/png" else 1)
        )
        return response(value, M1)

    metadata = asyncio.run(
        inspect_models(settings, live=True, transport=httpx.MockTransport(handler))
    )
    assert not metadata["verified"]
    assert metadata["credentials"]["legacy_1"]["models"][M1]["capabilities"] == [
        "generateContent"
    ]
    probed = asyncio.run(
        inspect_models(
            settings, live=True, probe=True, transport=httpx.MockTransport(handler)
        )
    )
    assert probed["verified"]
    assert set(probed["credentials"]["legacy_1"]["models"][M1]["capabilities"]) == {
        "json",
        "vision",
        "pdf",
        "generateContent",
    }


def test_sdk_stall_is_cancelled_and_fails_over_within_total_budget(monkeypatch):
    manager = pool(gemini_ocr_attempt_timeout_seconds=0.1)
    calls, cancelled = [], []

    async def generate(**kwargs):
        calls.append(kwargs["model"])
        if len(calls) == 1:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
        return SimpleNamespace(text='{"latex":"x=1"}', model_version=M1)

    client = MagicMock()
    client.aio.__aenter__.return_value = client
    client.models.generate_content = AsyncMock(side_effect=generate)
    monkeypatch.setattr(
        "app.math_ocr.gemini_adapter._get_genai_client", lambda key, **kwargs: client
    )
    # The SDK is mocked; its stall timing must not include Windows certificate
    # store loading for an unused real transport, which varies under test load.
    adapter = GeminiMathOCRAdapter(
        settings=manager.settings,
        manager=manager,
        transport=httpx.MockTransport(
            lambda request: pytest.fail("Mock SDK opened a network request")
        ),
    )
    monkeypatch.setattr(
        adapter,
        "_rasterize_and_optimize",
        lambda strokes: (
            b"image",
            "image/png",
            {"pen_strokes": 1, "estimated_lines": 1, "crop_box": (0, 0, 794, 1123)},
        ),
    )
    tick = time.monotonic()
    result = adapter.recognize([])
    assert result.latex == "x=1" and calls == [M1, M1] and cancelled == [True]
    assert time.monotonic() - tick < 0.8
    assert sum(manager.inflight.values()) == 0


@pytest.mark.parametrize(
    "mode", ["changed-key", "unavailable", "malformed", "missing-vision"]
)
def test_strict_manifest_blocks_ineligible_models_without_network(tmp_path, mode):
    manager = pool()
    path = manifest(
        tmp_path,
        manager,
        {
            M1: {
                "available": True,
                "capabilities": ["generateContent", "json", "vision"],
            }
        },
    )
    data = json.loads(path.read_text())
    for entry in data["credentials"].values():
        if mode == "changed-key":
            entry["fingerprint"] = "old-key-fingerprint"
        elif mode == "unavailable":
            entry["models"][M1]["available"] = False
        elif mode == "malformed":
            entry["models"] = None
        else:
            entry["models"][M1]["capabilities"] = ["generateContent", "json"]
    path.write_text(json.dumps(data))
    with pytest.raises(PoolUnavailable):
        run(
            manager,
            lambda c, b: pytest.fail("Ineligible model was called"),
            task="OCR_INK",
        )


def test_paper_ocr_preserves_image_and_fails_over_to_next_model():
    manager, calls = pool(), []

    def handler(request):
        model = request.url.path.split("/")[-1].split(":")[0]
        body = json.loads(request.content)
        calls.append((model, body))
        if model == M1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": '{"suggestions":[]}'}]},
                    }
                ]
            },
        )

    output = asyncio.run(
        GeminiPaperTranscriber(
            settings=manager.settings,
            manager=manager,
            transport=httpx.MockTransport(handler),
        ).transcribe(b"unchanged image", "image/png")
    )
    assert output.suggestions == []
    assert [m for m, b in calls] == [M1, M1, M2]
    assert calls[0][1] == calls[1][1] == calls[2][1]


def test_google_network_guard_blocks_before_sending():
    async def scenario():
        async with httpx.AsyncClient(trust_env=False) as client:
            with pytest.raises(
                pytest.fail.Exception, match="Live Google API request blocked"
            ):
                await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models"
                )

    asyncio.run(scenario())


def test_recovery_probe_in_progress_waits_instead_of_failing_concurrent_requests():
    async def scenario():
        clock = Clock()
        manager = pool(projects=("pA",), clock=clock)
        manager.settings.gemini_model_priority = M1
        choice, _ = manager._choose([M1], set(), "TUTOR")
        manager._release(choice, AttemptFailure("TRANSIENT"))
        clock.now += 16
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def send(c, budget):
            calls.append(c.model)
            entered.set()
            await release.wait()
            return Payload("ok")

        first = asyncio.create_task(manager.run_async("TUTOR", M1, send, timeout=1))
        await entered.wait()
        second = asyncio.create_task(manager.run_async("TUTOR", M1, send, timeout=1))
        await asyncio.sleep(0.01)
        assert not second.done() and calls == [M1]
        release.set()
        assert all(r.data == "ok" for r in await asyncio.gather(first, second))
        assert calls == [M1, M1] and not manager.probes and not manager.circuits

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure", ["invalid-key", "quota", "server", "network", "timeout"]
)
def test_real_sdk_with_mock_transport_fails_over_and_honors_retry_info(
    monkeypatch, failure
):
    # Run the installed SDK's actual parsing/transport, not just an SDK-shaped mock.
    # Every HTTP request goes through httpx.MockTransport and the quota guard.
    clock, calls = Clock(), []
    manager = pool(clock=clock)

    def handler(request):
        key = request.headers["x-goog-api-key"]
        calls.append(key)
        if key == "secret-0":
            if failure == "network":
                raise httpx.ConnectError("private network detail", request=request)
            if failure == "timeout":
                raise httpx.ReadTimeout("private timeout detail", request=request)
            if failure == "invalid-key":
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "code": 400,
                            "status": "INVALID_ARGUMENT",
                            "details": [
                                {
                                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                                    "reason": "API_KEY_INVALID",
                                }
                            ],
                        }
                    },
                )
            if failure == "quota":
                return httpx.Response(
                    429,
                    json={
                        "error": {
                            "code": 429,
                            "status": "RESOURCE_EXHAUSTED",
                            "details": [
                                {
                                    "@type": "type.googleapis.com/google.rpc.RetryInfo",
                                    "retryDelay": "21s",
                                }
                            ],
                        }
                    },
                )
            return httpx.Response(
                503, json={"error": {"code": 503, "status": "UNAVAILABLE"}}
            )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "role": "model",
                            "parts": [{"text": '{"latex":"2+2=5"}'}],
                        },
                    }
                ],
                "modelVersion": M1,
            },
        )

    adapter = GeminiMathOCRAdapter(
        settings=manager.settings,
        manager=manager,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(
        adapter,
        "_rasterize_and_optimize",
        lambda strokes: (
            b"image",
            "image/png",
            {"pen_strokes": 1, "estimated_lines": 1, "crop_box": (0, 0, 794, 1123)},
        ),
    )
    assert adapter.recognize([]).latex == "2+2=5"
    assert calls == ["secret-0", "secret-1"]
    if failure == "quota":
        assert manager.circuits[("project", "pA", M1)][0] == clock.now + 21


def test_malformed_capability_list_is_ineligible(tmp_path):
    manager = pool()
    manifest(tmp_path, manager, {M1: {"available": True, "capabilities": [{}]}})
    with pytest.raises(PoolUnavailable):
        run(manager, lambda c, b: pytest.fail("Malformed capability was called"))


def test_invalid_candidate_shape_fails_over_and_bad_usage_does_not_drop_valid_result():
    calls, manager = [], pool()

    def handler(request):
        calls.append(request.headers["x-goog-api-key"])
        if len(calls) == 1:
            return httpx.Response(200, json={"candidates": ["malformed"]})
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": '{"value":4}'}]},
                    }
                ],
                "usageMetadata": None,
            },
        )

    provider = GeminiProvider(manager=manager, transport=httpx.MockTransport(handler))
    result = asyncio.run(
        provider.generate_structured(
            [AIMessage(role="user", content="test")], Output, M1
        )
    )
    assert result.value == 4 and calls == ["secret-0", "secret-1"]
