"""Versioned local editorial changes. Raw acquisition data is never modified."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading

from .storage import file_hash, read_json, write_json


class ReviewError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


class ReviewStore:
    STATUSES = {"DRAFT", "NEEDS_REVIEW", "SOURCE_VERIFIED"}
    FIELDS = {"stem_markdown", "answer_text", "solution_markdown", "formula_corrections"}

    def __init__(self, pilot: Path):
        self.pilot = pilot.resolve()
        self.source_hash = read_json(pilot / "manifest.json")["source_sha256"]
        self.candidates_path = pilot / "questions.enriched.candidates.jsonl"
        self.generation = file_hash(self.candidates_path)
        self.items = {item["question_id"]: item for item in
                      (json.loads(line) for line in self.candidates_path.read_text(encoding="utf-8").splitlines() if line.strip())}
        if any(item["source_sha256"] != self.source_hash for item in self.items.values()):
            raise ReviewError("Candidate source hashes differ from the manifest")
        self.path = pilot / "reviews" / "state.json"
        self.lock = threading.RLock()
        self._read()

    def _read(self) -> dict:
        if not self.path.exists():
            return {"schema_version": "pdf-review-state/v1", "source_sha256": self.source_hash,
                    "document_revision": 0, "reviews": {}, "history": []}
        state = read_json(self.path)
        if state["source_sha256"] != self.source_hash:
            raise ReviewError("Review history belongs to another source PDF", 409)
        return state

    def snapshot(self) -> dict:
        with self.lock:
            state = self._read()
            return {"schema_version": state["schema_version"], "source_sha256": self.source_hash,
                    "base_generation": self.generation, "document_revision": state["document_revision"],
                    "reviews": {key: {**value, "stale": value["base_generation"] != self.generation}
                                for key, value in state["reviews"].items()},
                    "history_count": len(state["history"])}

    def save(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) - {
            "question_id", "expected_revision", "status", "fields", "field_checks", "reviewer", "note"
        }:
            raise ReviewError("Unsupported review fields")
        identifier = payload.get("question_id")
        if not isinstance(identifier, str) or identifier not in self.items:
            raise ReviewError("Unknown question")
        if type(payload.get("expected_revision")) is not int or payload["expected_revision"] < 0:
            raise ReviewError("expected_revision must be a non-negative integer")
        status = payload.get("status")
        if not isinstance(status, str) or status not in self.STATUSES:
            raise ReviewError("Unsupported review status")
        fields = payload.get("fields")
        if not isinstance(fields, dict) or set(fields) != self.FIELDS:
            raise ReviewError("Provide all editorial fields")
        for key in ("stem_markdown", "answer_text", "solution_markdown"):
            if not isinstance(fields[key], str) or len(fields[key]) > 100_000:
                raise ReviewError(f"Invalid {key}")
        if not isinstance(fields["formula_corrections"], list) or len(fields["formula_corrections"]) > 100:
            raise ReviewError("Invalid formula correction list")
        valid_blocks = {b["block_id"] for b in self.items[identifier].get("ocr_evidence", [])}
        seen = set()
        for correction in fields["formula_corrections"]:
            if (not isinstance(correction, dict) or set(correction) != {"block_id", "latex"}
                    or not isinstance(correction["block_id"], str)
                    or correction["block_id"] not in valid_blocks or correction["block_id"] in seen
                    or not isinstance(correction["latex"], str) or len(correction["latex"]) > 20_000):
                raise ReviewError("Correction must reference a unique OCR block from this question")
            seen.add(correction["block_id"])
        checks = payload.get("field_checks", {})
        if (not isinstance(checks, dict) or set(checks) != {"stem", "answer", "solution"}
                or any(type(v) is not bool for v in checks.values())):
            raise ReviewError("Invalid field verification checks")
        if status == "SOURCE_VERIFIED":
            if not checks["stem"] or not checks["answer"] or not fields["stem_markdown"].strip() or not fields["answer_text"].strip():
                raise ReviewError("Cần nhập đề, đáp án và đánh dấu đã đối chiếu hai phần với nguồn")
            if any(0xE000 <= ord(c) <= 0xF8FF for c in fields["stem_markdown"] + fields["answer_text"]):
                raise ReviewError("Cần sửa ký tự bị lỗi trong đề/đáp án trước khi xác nhận")
        if checks["solution"] and not fields["solution_markdown"].strip():
            raise ReviewError("An empty solution cannot be verified")
        for key in ("reviewer", "note"):
            if not isinstance(payload.get(key, ""), str) or len(payload.get(key, "")) > 5000:
                raise ReviewError(f"Invalid {key}")
        if not payload.get("reviewer", "").strip():
            raise ReviewError("Nhập tên hoặc nhãn người biên soạn")
        with self.lock:
            if file_hash(self.candidates_path) != self.generation:
                raise ReviewError("Candidates changed; restart review server and reload before editing", 409)
            state = self._read()
            previous = state["reviews"].get(identifier)
            revision = previous["revision"] if previous else 0
            if revision != payload["expected_revision"]:
                raise ReviewError("Thẻ khác vừa lưu câu này. Bấm Nạp bản đã lưu trước khi sửa tiếp", 409)
            record = {"revision": revision + 1, "status": status, "fields": fields,
                      "field_checks": checks, "reviewer": payload["reviewer"].strip(),
                      "note": payload.get("note", ""), "base_generation": self.generation,
                      "updated_at": datetime.now(timezone.utc).isoformat(),
                      "academic_review": "PENDING", "grading_support": "NOT_ASSESSED", "publishable": False}
            state["document_revision"] += 1
            state["reviews"][identifier] = record
            state["history"].append({"document_revision": state["document_revision"], "question_id": identifier,
                                     "previous_revision": revision, "record": record})
            write_json(self.path, state)
            return {"question_id": identifier, "review": record, "document_revision": state["document_revision"]}
