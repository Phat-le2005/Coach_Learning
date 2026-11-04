import base64
import json

import httpx
import pytest

from pdfmeta.gemini_client import GeminiError
from pdfmeta.local_client import LocalClient, LocalConfig, create_client, resolve_provider


@pytest.mark.parametrize("url", ["https://example.com/v1", "http://192.168.1.5:8790/v1", "http://127.0.0.1:8790/v1?token=secret", "http://user:pass@localhost:8790/v1", "http://localhost:8790/other"])
def test_local_endpoint_rejects_remote_hosts_credentials_and_redirect_targets(url):
    with pytest.raises(ValueError, match="LOOPBACK"):
        LocalConfig(base_url=url)


def test_local_provider_does_not_require_or_send_cloud_key(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("PDF_REVIEW_PROVIDER=local\nGEMINI_API_KEY=cloud-secret\nLOCAL_REVIEW_MODEL=qwen3-vl-2b-instruct\n")
    assert resolve_provider(None, env) == "local"
    client = create_client("local", env, None, tmp_path / "usage.jsonl")
    assert isinstance(client, LocalClient) and not hasattr(client.config, "api_key")
    client.close()


def test_local_preflight_identity_auth_images_schema_and_usage(tmp_path):
    (tmp_path / "local-qwen-server.key").write_text("local-secret")
    (tmp_path / "local-qwen-runtime.json").write_text(json.dumps({"served_model": "qwen3-vl-2b-instruct",
        "model_sha256": "a" * 64, "threads": 3, "gpu_layers": 0}))
    seen = []
    def handler(request):
        assert request.url.host == "127.0.0.1"
        assert request.headers["authorization"] == "Bearer local-secret"
        assert "x-goog-api-key" not in request.headers
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "qwen3-vl-2b-instruct"}]})
        body = json.loads(request.content)
        seen.append(body)
        assert body["model"] == "qwen3-vl-2b-instruct"
        assert body["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}})
    client = LocalClient(LocalConfig(runtime=tmp_path), tmp_path / "usage.jsonl", transport=httpx.MockTransport(handler))
    preflight = client.preflight()
    assert client.config.model.endswith("@" + "a" * 16) and preflight["cloud_api_calls"] == 0
    answer = client.generate([{"text": "source"}, {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(b"image").decode()}}],
        {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}, "instructions", "job")
    assert answer["result"] == {"ok": True} and client.tokens == 110
    ledger = (tmp_path / "usage.jsonl").read_text()
    assert "local-secret" not in ledger and '"cloud_api_calls": 0' in ledger
    client.close()


def test_local_redirect_and_truncation_never_become_approved_results(tmp_path):
    client = LocalClient(LocalConfig(runtime=tmp_path), tmp_path / "usage.jsonl", transport=httpx.MockTransport(
        lambda _: httpx.Response(302, headers={"location": "https://example.com"})))
    with pytest.raises(GeminiError, match="LOCAL_INFERENCE_HTTP_302"):
        client.generate([], {}, "instructions", "job")
    client.close()
    client = LocalClient(LocalConfig(runtime=tmp_path), tmp_path / "usage.jsonl", transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]})))
    assert client.generate([], {}, "instructions", "job")["status"] == "INCOMPLETE_OR_BLOCKED"
    client.close()
