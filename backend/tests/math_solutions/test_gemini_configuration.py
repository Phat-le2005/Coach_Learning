"""One server-side Gemini credential drives OCR and answer-grounded grading."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.ai.dependencies import create_ai_provider
from app.ai.gemini_provider import GeminiProvider
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkPoint, InkStroke
from app.math_ocr.dependencies import get_ocr_adapter
from app.math_ocr.gemini_adapter import GeminiMathOCRAdapter


def configured(monkeypatch, **values):
    for name in ("AI_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    return Settings(
        _env_file=None, database_name="test_db", database_user="test_user",
        app_env="development", ai_provider="gemini", math_ocr_provider="gemini",
        **values,
    )


@pytest.mark.parametrize("name", ["AI_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEYS"])
def test_env_key_is_shared_by_ocr_and_grading(monkeypatch, tmp_path, name):
    settings = configured(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(f"AI_API_KEY=\n{name}=fixture-gemini-key\n", encoding="utf-8")
    settings = Settings(
        _env_file=env_file, database_name="test_db", database_user="test_user",
        app_env="development", ai_provider="gemini", math_ocr_provider="gemini",
    )
    ocr = get_ocr_adapter(settings)
    grading = create_ai_provider(settings)
    assert isinstance(ocr, GeminiMathOCRAdapter)
    assert isinstance(grading, GeminiProvider)
    assert ocr.api_key == grading._api_key == "fixture-gemini-key"
    assert "fixture-gemini-key" not in repr(settings)


def test_explicit_ai_key_has_precedence(monkeypatch):
    settings = configured(monkeypatch, ai_api_key="shared-key", gemini_api_key="other-key")
    assert get_ocr_adapter(settings).api_key == "shared-key"
    assert create_ai_provider(settings)._api_key == "shared-key"


def test_request_settings_do_not_borrow_global_key_or_use_mock(monkeypatch):
    settings = configured(monkeypatch)
    adapter = get_ocr_adapter(settings)
    assert adapter.api_key == ""
    with pytest.raises(ApplicationError) as error:
        adapter.recognize([])
    assert error.value.code == "OCR_NOT_CONFIGURED"


def test_configured_model_is_tried_first_and_provider_errors_are_private(monkeypatch, caplog):
    settings = configured(monkeypatch, gemini_api_key="private-fixture-key")
    adapter = get_ocr_adapter(settings)
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("403 api_key private-fixture-key")
    stroke = InkStroke(
        id=uuid4(), tool="PEN", color="#000000", width=2,
        points=[InkPoint(x=0.1, y=0.1), InkPoint(x=0.2, y=0.2)],
    )
    monkeypatch.setattr("app.math_ocr.gemini_adapter._LAST_WORKING_MODEL", "different-model")
    with patch("app.math_ocr.gemini_adapter._get_genai_client", return_value=client):
        with pytest.raises(ApplicationError) as error:
            adapter.recognize([stroke])
    assert client.models.generate_content.call_args.kwargs["model"] == settings.gemini_ocr_model
    assert error.value.code == "OCR_API_KEY_INVALID"
    assert "private-fixture-key" not in error.value.message
    assert "private-fixture-key" not in caplog.text
