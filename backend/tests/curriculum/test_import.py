import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.curriculum.import_service import DATA_ROOT, CurriculumImportService
from app.curriculum.models import (
    Chapter,
    Curriculum,
    CurriculumImportHistory,
    ProblemType,
    ProblemTypeConcept,
)
from app.subjects.models import Subject

DATASET = "MATH_G12_GDPT2018_CORE"


def copy_dataset(tmp_path: Path) -> Path:
    target = tmp_path / "dataset"
    source = DATA_ROOT / "math" / "grade12" / "gdpt2018"
    shutil.copytree(source, target)
    return target


def test_curriculum_import_is_idempotent_and_records_provenance(
    db_session: Session,
) -> None:
    service = CurriculumImportService(db_session)
    preview = service.preview(DATASET)
    assert preview.counts["problem_types"] == 9
    assert preview.dataset_version == "1.1.0"
    assert preview.source_reference == "Thông tư 32/2018/TT-BGDĐT"
    first = service.import_dataset(DATASET)
    second = service.import_dataset(DATASET)
    assert first.created["problem_types"] == 9
    assert second.unchanged["problem_types"] == 9
    assert db_session.scalar(select(func.count()).select_from(Subject)) == 1
    assert db_session.scalar(select(func.count()).select_from(Chapter)) == 6
    assert db_session.scalar(select(func.count()).select_from(ProblemType)) == 9
    assert db_session.scalar(select(func.count()).select_from(ProblemTypeConcept)) == 19
    assert db_session.scalar(select(func.count()).select_from(CurriculumImportHistory)) == 1


@pytest.mark.parametrize("mutation,expected_code", [
    ("missing_parent", "CURRICULUM_REFERENCE_NOT_FOUND"),
    ("duplicate_code", "CURRICULUM_DUPLICATE_CODE"),
    ("cycle", "CURRICULUM_GRAPH_CYCLE"),
])
def test_curriculum_import_rejects_invalid_dataset(
    db_session: Session,
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    path = copy_dataset(tmp_path)
    if mutation == "missing_parent":
        rows = json.loads((path / "topics.json").read_text(encoding="utf-8"))
        rows[0]["chapter_code"] = "MISSING"
        (path / "topics.json").write_text(json.dumps(rows), encoding="utf-8")
    elif mutation == "duplicate_code":
        rows = json.loads((path / "chapters.json").read_text(encoding="utf-8"))
        rows.append(dict(rows[0]))
        (path / "chapters.json").write_text(json.dumps(rows), encoding="utf-8")
    else:
        rows = json.loads((path / "concept_relations.json").read_text(encoding="utf-8"))
        rows.append({
            "source_code": "DERIVATIVE",
            "target_code": "FUNCTION",
            "relation_type": "PREREQUISITE",
        })
        (path / "concept_relations.json").write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ApplicationError) as error:
        CurriculumImportService(db_session, tmp_path).preview(DATASET)
    assert error.value.code == expected_code


def test_curriculum_import_does_not_silently_move_subject_between_versions(
    db_session: Session, tmp_path: Path
) -> None:
    CurriculumImportService(db_session).import_dataset(DATASET)
    path = copy_dataset(tmp_path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    manifest.update({
        "dataset_code": "MATH_G12_OTHER_VERSION",
        "dataset_version": "2.0.0",
        "curriculum_version_code": "OTHER_VERSION",
        "curriculum_version": "other",
    })
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ApplicationError) as error:
        CurriculumImportService(db_session, tmp_path).import_dataset(
            "MATH_G12_OTHER_VERSION"
        )
    assert error.value.code == "CURRICULUM_VERSION_CONFLICT"


def test_curriculum_import_rejects_changed_content_without_new_dataset_version(
    db_session: Session, tmp_path: Path
) -> None:
    CurriculumImportService(db_session).import_dataset(DATASET)
    path = copy_dataset(tmp_path)
    rows = json.loads((path / "chapters.json").read_text(encoding="utf-8"))
    rows[0]["name"] = "Changed without version bump"
    (path / "chapters.json").write_text(json.dumps(rows), encoding="utf-8")

    with pytest.raises(ApplicationError) as error:
        CurriculumImportService(db_session, tmp_path).import_dataset(DATASET)

    assert error.value.code == "CURRICULUM_DATASET_VERSION_CONFLICT"
    assert db_session.scalar(select(Chapter.name).order_by(Chapter.order_index)) != (
        "Changed without version bump"
    )


def test_curriculum_import_rolls_back_on_mid_transaction_failure(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = CurriculumImportService(db_session)

    def fail(*args, **kwargs):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(service, "_upsert_composite", fail)
    with pytest.raises(RuntimeError):
        service.import_dataset(DATASET)
    assert db_session.scalar(
        select(func.count()).select_from(Curriculum).where(Curriculum.code == "GDPT2018")
    ) == 0
