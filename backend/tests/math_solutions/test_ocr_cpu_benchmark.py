"""Safety and measurement contracts; these tests make no accuracy claims."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.exceptions import ApplicationError
import app.math_ocr.local_rapid_adapter as rapid
from scripts.benchmark_ocr_cpu import character_error_rate, load_manifest, percentile


FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "ocr_cpu_smoke"


def test_smoke_manifest_references_five_real_png_files() -> None:
    samples = load_manifest(FIXTURES / "manifest.json")
    assert len(samples) == 5
    assert {sample.group for sample in samples} == {"SMOKE"}
    assert all(sample.image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for sample in samples)


def test_manifest_rejects_unverified_handwriting_and_path_traversal(tmp_path: Path) -> None:
    image = tmp_path / "formula.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    row = {
        "id": "HAND_001", "group": "HANDWRITTEN", "image": "formula.png",
        "reference_latex": "x^2", "reference_verified": True,
        "source": "consented author-created formula",
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"samples": [row]}), encoding="utf-8")
    with pytest.raises(ValueError, match="usage_allowed"):
        load_manifest(manifest)
    row["usage_allowed"] = True
    row["image"] = "../outside.png"
    manifest.write_text(json.dumps({"samples": [row]}), encoding="utf-8")
    with pytest.raises(ValueError, match="under the manifest"):
        load_manifest(manifest)


def test_literal_cer_and_interpolated_p95() -> None:
    assert character_error_rate("x^2", "x^3") == pytest.approx(1 / 3)
    assert character_error_rate("abc", "") == 1.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == pytest.approx(3.85)
    with pytest.raises(ValueError):
        character_error_rate("", "anything")


def test_incomplete_models_fail_before_constructor_or_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(rapid, "find_spec", lambda _name: SimpleNamespace(origin=str(tmp_path / "__init__.py")))
    with pytest.raises(ApplicationError) as exc:
        rapid.inspect_cpu_model_files(tmp_path)
    assert exc.value.status_code == 503
    assert exc.value.code == "OCR_LOCAL_MODEL_UNAVAILABLE"


def test_model_constructor_receives_all_four_explicit_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import sys
    for name, minimum in rapid._MIN_MODEL_BYTES.items():
        with (tmp_path / name).open("wb") as file:
            file.seek(minimum - 1)
            file.write(b"x")
    monkeypatch.setattr(rapid, "find_spec", lambda _name: SimpleNamespace(origin=str(tmp_path / "__init__.py")))
    captured = []

    def constructor(**kwargs: Path) -> object:
        captured.append(kwargs)
        return object()

    monkeypatch.setitem(sys.modules, "rapid_latex_ocr", SimpleNamespace(LaTeXOCR=constructor))
    rapid._get_cpu_model.cache_clear()
    try:
        rapid.load_cpu_model(tmp_path)
    finally:
        rapid._get_cpu_model.cache_clear()
    assert len(captured) == 1
    assert set(captured[0]) == {"encoder_path", "decoder_path", "image_resizer_path", "tokenizer_json"}
    assert all(path.is_file() for path in captured[0].values())
