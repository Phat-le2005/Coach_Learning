import pytest

from src.llm_normalizer import _json_object


def test_json_object_accepts_markdown_fence():
    assert _json_object("```json\n{\"ok\": true}\n```") == {"ok": True}


def test_json_object_rejects_non_object():
    with pytest.raises(ValueError):
        _json_object("[1, 2]")
