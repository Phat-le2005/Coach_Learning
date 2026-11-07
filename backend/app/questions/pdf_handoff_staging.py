"""Read-only source verification and non-importable staging for the 200-question handoff.

Structural readiness is deliberately separate from academic approval. This module
does not import database, application settings, OCR, or grading services.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any


DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
DEFAULT_SOURCE = DATA_ROOT / "Toan12_200_cau_20261104"
DEFAULT_OUTPUT = DATA_ROOT / "questions/math/grade12/pdf_handoff_200_v0_1/staging/v0_1"
METADATA = "01_metadata_200_cau/metadata.final.jsonl"
MANIFEST_SHA256 = "b9ffda4779aa69a79f3e6595075dd9f5b21e8b7be4057045cd5cdd44238811b1"
METADATA_SHA256 = "6f94f6646d985bf0a96b078b3268101bce52949b6ad5acc7b4b0f7ff2e709a83"
OUTPUT_FILES = ("source_package.json", "candidate_questions.json", "review_queue.json", "validation_report.json")
CHAPTERS = ("derivative_applications", "integrals", "grouped_statistics", "probability")
POLICY = {
    "academic_approval_established": False,
    "rights_status": "REVIEW_REQUIRED",
    "production_release_eligible": 0,
    "database_import_allowed": False,
    "canonical_snapshot_allowed": False,
    "step_grading_allowed": False,
    "true_false_policy": "KEEP_WHOLE_SOURCE_QUESTION_NEVER_SPLIT",
    "missing_taxonomy_policy": "DO_NOT_INVENT_MAPPING_OR_DIFFICULTY",
}


class HandoffValidationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def safe_file(root: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if (not relative or "\\" in relative or posix.is_absolute()
            or PureWindowsPath(relative).drive or ".." in posix.parts
            or posix.as_posix() != relative):
        raise HandoffValidationError(f"Unsafe package path: {relative}")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise HandoffValidationError(f"Missing or escaped package file: {relative}")
    return resolved


def verify_source(source: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Verify all supplied bytes, including assets; never trust manifest text alone."""
    for name, expected in (("manifest.sha256", MANIFEST_SHA256), (METADATA, METADATA_SHA256)):
        if sha256_file(safe_file(source, name)) != expected:
            raise HandoffValidationError(f"Pinned source identity changed: {name}")
    declared: dict[str, str] = {}
    for line in (source / "manifest.sha256").read_text(encoding="utf-8-sig").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise HandoffValidationError("Malformed source manifest entry")
        digest, name = match.groups()
        if name in declared:
            raise HandoffValidationError(f"Duplicate source path: {name}")
        if sha256_file(safe_file(source, name)) != digest:
            raise HandoffValidationError(f"Source bytes changed: {name}")
        declared[name] = digest
    actual = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
    if actual != set(declared) | {"manifest.sha256"}:
        raise HandoffValidationError("Source package contains missing or undeclared files")
    rows = [json.loads(line) for line in (source / METADATA).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    return rows, declared


def structural_blockers(row: dict[str, Any]) -> list[str]:
    """Check structure only; never infer an answer from OCR, arithmetic, or images."""
    if row.get("usage_group") != "core_candidates":
        return ["SOURCE_IMAGE_REVIEW_REQUIRED"]
    spec = row.get("answer_spec") or {}
    kind = spec.get("kind")
    if not row.get("parts", {}).get("question", {}).get("markdown", "").strip():
        return ["MISSING_QUESTION_CONTENT"]
    if kind == "MULTIPLE_CHOICE":
        choices = row["parts"]["question"].get("choices", [])
        labels = [choice.get("label") for choice in choices]
        if (len(choices) != 4 or set(labels) != {"A", "B", "C", "D"}
                or any(not choice.get("markdown", "").strip() for choice in choices)):
            return ["INCOMPLETE_STRUCTURED_MCQ_OPTIONS"]
        if spec.get("expected_label") not in labels:
            return ["ANSWER_LABEL_NOT_IN_OPTIONS"]
        if spec.get("evidence") != "EXPLICIT_SOURCE_SOLUTION_LABEL":
            return ["MISSING_EXPLICIT_SOURCE_ANSWER_EVIDENCE"]
    elif kind == "NUMBER":
        try:
            value = Decimal(spec["expected_decimal"].replace(",", "."))
            if not value.is_finite():
                raise InvalidOperation
        except (InvalidOperation, KeyError, AttributeError):
            return ["INVALID_EXACT_DECIMAL_ANSWER"]
        if (spec.get("comparison") != "EXACT_DECIMAL_COMMA_OR_DOT"
                or spec.get("evidence") != "EXPLICIT_SOURCE_ANSWER_REGION"):
            return ["MISSING_EXACT_DECIMAL_SOURCE_CONTRACT"]
    else:
        return ["UNSUPPORTED_OR_MISSING_STRUCTURED_ANSWER"]
    return []


def validate_rows(rows: list[dict[str, Any]]) -> None:
    ids = [row["question_id"] for row in rows]
    if len(rows) != 200 or len(set(ids)) != 200:
        raise HandoffValidationError("Expected exactly 200 unique source questions")
    if Counter(row["chapter_id"] for row in rows) != Counter({chapter: 50 for chapter in CHAPTERS}):
        raise HandoffValidationError("Expected four chapters of 50 source questions")
    if Counter(row["usage_group"] for row in rows) != Counter(core_candidates=43, image_reference=157):
        raise HandoffValidationError("Source usage-group partition changed")
    for row in rows:
        if (row.get("academic_review") != "PENDING"
                or any(row.get(field) is not False for field in
                       ("publishable", "production_grade", "assessment_ready", "step_grading_ready"))):
            raise HandoffValidationError(f"Source review/release boundary changed: {row['question_id']}")


def project_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates, queue = [], []
    for row in sorted(rows, key=lambda item: item["question_id"]):
        reasons = structural_blockers(row)
        common = {
            "candidate_id": "PDF200_" + hashlib.sha256(row["question_id"].encode()).hexdigest()[:24],
            "source_question_id": row["question_id"],
            "source_collection_number": row["collection_number"],
            "source_metadata_path": METADATA,
            "source_record_semantic_sha256": hashlib.sha256(json_bytes(row)).hexdigest(),
            "chapter_id": row["chapter_id"],
        }
        if reasons:
            queue.append({**common, "status": "HOLD_SOURCE_REVIEW", "blockers": reasons})
        else:
            candidates.append({
                **common,
                "status": "STRUCTURAL_CANDIDATE",
                "question_type": "MCQ" if row["answer_spec"]["kind"] == "MULTIPLE_CHOICE" else "SHORT_ANSWER",
                "production_release_eligible": False,
                "database_import_allowed": False,
                "step_grading_ready": False,
                "promotion_blockers": ["ACADEMIC_REVIEW_PENDING", "RIGHTS_NOT_CLEARED",
                                       "TAXONOMY_MAPPING_MISSING", "DIFFICULTY_AND_EXAM_WEIGHT_MISSING",
                                       "SOURCE_PRESENTATION_REVIEW_REQUIRED", "DUPLICATE_REVIEW_REQUIRED"],
                # Verbatim semantic copy: no LaTeX, answer, scope, source page or crop rewrites.
                "source_record": row,
            })
    return candidates, queue


def verify_lineage(source: Path, rows: list[dict[str, Any]], declared: dict[str, str]) -> None:
    records: dict[str, tuple[dict[str, Any], str]] = {}
    for path in (source / "02_transcription_v2/records").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8-sig"))
        identity = record["question_id"]
        if identity in records:
            raise HandoffValidationError("Duplicate raw record identity")
        records[identity] = record, declared[path.relative_to(source).as_posix()]
    if set(records) != {row["question_id"] for row in rows}:
        raise HandoffValidationError("Curated/raw question identities differ")
    plan = json.loads((source / "03_chay_lai_pipeline/plan.relative.json").read_text(encoding="utf-8-sig"))
    documents = {doc["sha256"]: doc for doc in plan["documents"]}
    for row in rows:
        raw, raw_digest = records[row["question_id"]]
        if raw_digest != row["source_record_sha256"] or raw["source"]["sha256"] != row["source"]["sha256"]:
            raise HandoffValidationError(f"Raw source lineage mismatch: {row['question_id']}")
        doc = documents.get(row["source"]["sha256"])
        if (not doc or doc["page_count"] != row["source"]["page_count"]
                or declared.get("03_chay_lai_pipeline/" + doc["path"]) != doc["sha256"]):
            raise HandoffValidationError("Original PDF lineage mismatch")
        for part in row["parts"].values():
            for fragment in part.get("fragments", []):
                if not 1 <= fragment["page_number"] <= row["source"]["page_count"]:
                    raise HandoffValidationError("Invalid original source page")
                asset = "01_metadata_200_cau/" + fragment["source_asset"]
                if declared.get(asset) != fragment["source_asset_sha256"]:
                    raise HandoffValidationError("Source fragment asset hash mismatch")


@dataclass(frozen=True)
class StagingBundle:
    files: dict[str, Any]
    aggregate_sha256: str


def build_bundle(source: Path = DEFAULT_SOURCE) -> StagingBundle:
    rows, declared = verify_source(source)
    validate_rows(rows)
    verify_lineage(source, rows, declared)
    candidates, queue = project_rows(rows)
    types = Counter(item["question_type"] for item in candidates)
    if len(candidates) != 40 or len(queue) != 160 or types != Counter(MCQ=30, SHORT_ANSWER=10):
        raise HandoffValidationError("Expected 40 structural candidates (30 MCQ/10 numeric) and 160 held records")
    files = {
        "source_package.json": {
            "schema_version": "pdf-handoff-staging/v1",
            "package_relative_to_backend_data": "Toan12_200_cau_20261104",
            "manifest_sha256": MANIFEST_SHA256, "metadata_sha256": METADATA_SHA256,
            "source_assets": "REFERENCE_ORIGINAL_PACKAGE_DO_NOT_COPY",
            "source_asset_base": "01_metadata_200_cau",
            "policy": POLICY,
        },
        "candidate_questions.json": candidates,
        "review_queue.json": queue,
        "validation_report.json": {
            "status": "PASS_STRUCTURAL_STAGING_ONLY",
            "source_questions": 200, "source_manifest_files_verified": len(declared),
            "structural_candidates": 40, "candidate_types": dict(types),
            "held_for_source_review": 160, "academic_review_pending": 200,
            "chapters": {chapter: {
                "source_questions": 50,
                "structural_candidates": sum(x["chapter_id"] == chapter for x in candidates),
                "held": sum(x["chapter_id"] == chapter for x in queue),
            } for chapter in CHAPTERS},
            "policy": POLICY,
        },
    }
    # Sorted filename + exact deterministic UTF-8 serialization, no timestamps/absolute paths.
    digest = hashlib.sha256(b"".join(name.encode() + b"\0" + json_bytes(files[name]) for name in sorted(files))).hexdigest()
    return StagingBundle(files, digest)


def write_bundle(bundle: StagingBundle, output: Path, source: Path = DEFAULT_SOURCE) -> None:
    resolved = output.resolve()
    if resolved.is_relative_to(source.resolve()) or source.resolve().is_relative_to(resolved):
        raise HandoffValidationError("Staging output must be separate from the read-only source package")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists():
        raise HandoffValidationError("Import manifest is forbidden for this staging dataset")
    unexpected = {p.name for p in output.iterdir()} - set(OUTPUT_FILES) - {"README.md"}
    if unexpected:
        raise HandoffValidationError("Undeclared staging files: " + ", ".join(sorted(unexpected)))
    # Refuse to overwrite any existing edited output; a rerun is idempotent.
    for name, value in bundle.files.items():
        path = output / name
        if path.is_symlink():
            raise HandoffValidationError(f"Refusing to write through staging symlink: {name}")
        if path.exists() and path.read_bytes() != json_bytes(value):
            raise HandoffValidationError(f"Refusing to overwrite changed staging file: {name}")
    for name, value in bundle.files.items():
        (output / name).write_bytes(json_bytes(value))


def validate_bundle(bundle: StagingBundle, output: Path) -> None:
    if (output / "manifest.json").exists():
        raise HandoffValidationError("Import manifest is forbidden for this staging dataset")
    for name, expected in bundle.files.items():
        path = output / name
        if not path.is_file() or path.read_bytes() != json_bytes(expected):
            raise HandoffValidationError(f"Staging differs from pinned source projection: {name}")
    unexpected = {p.name for p in output.iterdir()} - set(OUTPUT_FILES) - {"README.md"}
    if unexpected:
        raise HandoffValidationError("Undeclared staging files: " + ", ".join(sorted(unexpected)))
