import copy
from hashlib import sha256
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select

from app.concepts.models import Concept
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.learning_evidence.models import LearningEvidenceEvent
from app.learning_evidence.skill_outcomes import KEY
from app.mastery.evidence import DeterministicMasteryEvidencePublisher
from app.mastery.models import StudentConceptMastery
from app.math_solutions.evaluator_service import MathEvaluatorService
from app.math_solutions.evidence_adapter import MathSolutionEvidenceAdapter
from app.math_solutions.models import SolutionAttempt, SolutionRubric, SolutionStep, StepRevision, MathArtifact
from app.questions.models import Question, QuestionImportBatch
from app.questions.ocr_curated import CuratedOCRImportService, digest, prepare_overlay, presentation_errors
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User


def overlay_fixture(tmp_path):
    raw = {"question_id": "source:1", "question": {"markdown": "Tìm các khoảng đơn điệu của $f(x)=2x^3-9x^2-24x+1$.", "source_spans": []},
           "solution": {"markdown": "OCR reference"}, "answer": {"markdown": ""}}
    path = tmp_path / "content.draft.pretty.json"
    path.write_text(json.dumps([raw], ensure_ascii=False), encoding="utf-8")
    question = {"subject_code": "OCR_MATH", "content": raw["question"]["markdown"], "question_type": "OPEN_RESPONSE",
                "difficulty": .45, "source": "OCR_CURATED_PA2", "source_reference": "fixture:source:1", "exam_weight": .5,
                "correct_answer": r"đồng biến trên $(-\infty;-1)$ và $(4;+\infty)$; nghịch biến trên $(-1;4)$",
                "explanation": r"$f'(x)=6x^2-18x-24$. Các nghiệm là $-1,4$.",
                "concepts": [{"code": code, "weight": weight} for code, weight in [("DERIVATIVE_RULES", .25), ("SIGN_ANALYSIS", .25), ("MONOTONICITY_CRITERION", .4), ("FUNCTION_DOMAIN", .1)]],
                "problem_types": [{"code": "MONOTONICITY", "weight": 1, "is_primary": True}],
                "learning_outcomes": [{"code": "LO", "weight": 1}]}
    criteria = [{"id": identifier, "step_type": kind, "weight": weight, "concept_codes": [code]}
                for identifier, kind, weight, code in [
                    ("domain", "ASSUMPTION", .1, "FUNCTION_DOMAIN"),
                    ("derivative", "DERIVATIVE_CALCULATION", .3, "DERIVATIVE_RULES"),
                    ("roots", "ROOT_FINDING", .2, "SIGN_ANALYSIS"),
                    ("table", "VARIATION_TABLE", .25, "SIGN_ANALYSIS"),
                    ("conclusion", "CONCLUSION", .15, "MONOTONICITY_CRITERION")]]
    corrections = [{"field": field, "before_sha256": digest(original), "after_sha256": digest(question[field]), "reason": "Explicit source-backed reference transcription"}
                   for field, original in [("explanation", raw["solution"]["markdown"]), ("correct_answer", None)]]
    item = {"dataset": "fixture", "source_id": raw["question_id"], "source_record_sha256": digest(raw),
            "question": question, "criteria": criteria, "task": "all_intervals", "corrections": corrections,
            "difficulty_basis": "CURRICULUM_DEFAULT_NOT_CALIBRATED", "review": {"status": "VERIFIED", "reviewer": "test", "notes": "CAS and source review"}}
    return {"version": 1, "sources": {"fixture": {"sha256": sha256(path.read_bytes()).hexdigest()}}, "items": [item]}, {"fixture": path}


def setup_catalog(session):
    subject = Subject(code="OCR_MATH", name="Math", grade_level=12)
    admin = User(email=f"ocr_admin_{uuid4()}@example.com", password_hash="test", role=Role.ADMIN, full_name="Admin")
    user = User(email=f"ocr_student_{uuid4()}@example.com", password_hash="test", role=Role.STUDENT, full_name="Student")
    session.add_all([subject, admin, user]); session.flush()
    student = StudentProfile(user_id=user.id)
    concepts = [Concept(subject_id=subject.id, code=code, name=code) for code in ("DERIVATIVE_RULES", "SIGN_ANALYSIS", "MONOTONICITY_CRITERION", "FUNCTION_DOMAIN")]
    chapter = Chapter(subject_id=subject.id, code="CH", name="Functions", order_index=1)
    session.add_all([student, chapter, *concepts]); session.flush()
    topic = Topic(chapter_id=chapter.id, code="TOPIC", name="Monotonicity", order_index=1)
    session.add(topic); session.flush()
    session.add_all([ProblemType(topic_id=topic.id, code="MONOTONICITY", name="Monotonicity", order_index=1),
                     LearningOutcome(subject_id=subject.id, code="LO", description="Monotonicity", grade_level=12)])
    session.commit()
    return admin, student, {c.code: c.id for c in concepts}


def test_offline_curation_rejects_changed_sources_unreviewed_edits_and_duplicates(tmp_path):
    overlay, sources = overlay_fixture(tmp_path)
    assert prepare_overlay(overlay, sources).report["ready"] == 1
    for mutate in [lambda o: o["items"][0]["question"].update(content="Changed"),
                   lambda o: o["items"][0]["review"].update(status="PENDING"),
                   lambda o: o["items"].append(copy.deepcopy(o["items"][0])),
                   lambda o: o["sources"]["fixture"].update(sha256="bad")]:
        changed = copy.deepcopy(overlay); mutate(changed)
        with pytest.raises(ValueError): prepare_overlay(changed, sources)
    assert presentation_errors(r"$y_{13;\dots; y_{15} \in [65;70)$")
    assert "TEX_OUTSIDE_MATH_DELIMITERS" in presentation_errors(r"y_8;\dots; y_{12} \in [60;65)")
    assert not presentation_errors(r"$y_8,\ldots,y_{12} \in [60;65)$")


def test_standalone_cli_preview_does_not_require_database(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    overlay, sources = overlay_fixture(tmp_path)
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(json.dumps(overlay, ensure_ascii=False), encoding="utf-8")
    report = tmp_path / "report.json"
    environment = {**os.environ, "DATABASE_HOST": "invalid.invalid", "PYTHONIOENCODING": "utf-8"}
    script = Path(__file__).resolve().parents[2] / "scripts/import_curated_ocr.py"
    result = subprocess.run([sys.executable, "-B", str(script), "--overlay", str(overlay_path),
                             "--source", f"fixture={sources['fixture']}", "--report", str(report)],
                            env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(report.read_text(encoding="utf-8"))["ready"] == 1
    assert "OFFLINE_PREVIEW" in result.stdout


def test_catalog_bridge_only_adds_missing_rows_and_is_repeatable(db_session):
    from app.questions.ocr_catalog import add_missing_cubic_catalog
    from app.curriculum.models import CurriculumVersion
    subject = Subject(code="OCR_MINIMAL", name="Original name", grade_level=12)
    db_session.add(subject); db_session.flush()
    parent = Concept(subject_id=subject.id, code="DERIVATIVE", name="Original derivative")
    db_session.add(parent); db_session.commit()
    version = db_session.get(CurriculumVersion, subject.curriculum_version_id)
    added = add_missing_cubic_catalog(db_session, subject_code=subject.code, version_code=version.code)
    assert len(added["created_concepts"]) == 4 and len(added["created_outcomes"]) == 2
    assert added["created_relations"] == ["DERIVATIVE_RULES:PART_OF:DERIVATIVE", "SIGN_ANALYSIS:PREREQUISITE:MONOTONICITY_CRITERION"]
    repeated = add_missing_cubic_catalog(db_session, subject_code=subject.code, version_code=version.code)
    assert not repeated["created_concepts"] and not repeated["created_outcomes"]
    assert subject.name == "Original name" and parent.name == "Original derivative"
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(Concept)) == 1


def test_import_is_atomic_idempotent_and_does_not_commit(db_session, tmp_path):
    admin, _, _ = setup_catalog(db_session)
    overlay, sources = overlay_fixture(tmp_path)
    prepared = prepare_overlay(overlay, sources)
    commits = []
    def committed(session): commits.append(True)
    event.listen(db_session, "after_commit", committed)
    result = CuratedOCRImportService(db_session).apply(prepared, admin)
    assert result["applied_rows"][0]["status"] == "IMPORTED"
    assert not commits
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(Question)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionImportBatch)) == 0
    result = CuratedOCRImportService(db_session).apply(prepared, admin)
    db_session.commit()
    assert CuratedOCRImportService(db_session).apply(prepared, admin)["applied_rows"][0]["status"] == "UNCHANGED"
    assert db_session.scalar(select(func.count()).select_from(SolutionRubric)) == 1
    question = db_session.scalar(select(Question))
    question.concept_links[0].weight = .01
    db_session.flush()
    with pytest.raises(ValueError, match="Existing curated question changed"):
        CuratedOCRImportService(db_session).apply(prepared, admin)


def test_curated_grade_skill_replay_override_and_reference_binding(db_session, tmp_path):
    from tests.math_solutions.test_ocr_cubic_monotonicity import ui_table
    from app.knowledge_gap.root_cause import RootCauseDiagnosticService
    from app.core.exceptions import ApplicationError
    admin, student, concepts = setup_catalog(db_session)
    overlay, sources = overlay_fixture(tmp_path)
    result = CuratedOCRImportService(db_session).apply(prepare_overlay(overlay, sources), admin)
    question = db_session.get(Question, UUID(result["applied_rows"][0]["question_id"]))
    rubric = db_session.scalar(select(SolutionRubric).where(SolutionRubric.question_id == question.id))
    from app.practice.models import PracticeSession
    practice = PracticeSession(student_id=student.id, subject_id=question.subject_id, session_type="PRACTICE", status="ACTIVE")
    db_session.add(practice); db_session.flush()
    attempt = SolutionAttempt(student_id=student.id, context_type="SELF_PRACTICE", source_kind="CANONICAL", question_id=question.id,
                              rubric_id=rubric.id, practice_session_id=practice.id, mode="INDEPENDENT_SOLUTION", status="SUBMITTED", create_idempotency_key="ocr")
    db_session.add(attempt); db_session.flush()
    for i, (kind, text, payload) in enumerate([
        ("ASSUMPTION", r"D=\mathbb{R}", None),
        ("DERIVATIVE_CALCULATION", "y'=6x^2-18x-24", None),
        ("ROOT_FINDING", "x=-1, x=4", None),
        ("VARIATION_TABLE", None, ui_table()),
        ("CONCLUSION", r"nghịch biến trên (-\infty;-1); đồng biến trên (-1;4); nghịch biến trên (4;+\infty)", None),
    ], 1):
        step = SolutionStep(attempt_id=attempt.id, step_index=i, step_type=kind)
        db_session.add(step); db_session.flush()
        rev = StepRevision(step_id=step.id, step_revision_number=1, step_index_at_revision=i, content_latex=text, change_reason="STUDENT_EDIT")
        db_session.add(rev); db_session.flush()
        if payload: db_session.add(MathArtifact(step_revision_id=rev.id, artifact_type="VARIATION_TABLE", payload=payload))
    db_session.commit()
    decision = MathEvaluatorService(db_session).evaluate_attempt(attempt.id)
    evidence = db_session.get(LearningEvidenceEvent, decision.learning_evidence_event_id)
    assert evidence.event_metadata[KEY]["concepts"][str(concepts["DERIVATIVE_RULES"])]["score"] == 1
    def states():
        return {r.concept_id: (r.mastery_score, r.attempt_count, r.correct_count) for r in db_session.scalars(select(StudentConceptMastery))}
    before = states()
    assert before[concepts["DERIVATIVE_RULES"]][1:] == (1, 1)
    assert before[concepts["MONOTONICITY_CRITERION"]][1:] == (1, 0)
    counts, _ = RootCauseDiagnosticService._historical_counts([evidence])
    assert counts[concepts["DERIVATIVE_RULES"]].correct == 1
    publisher = DeterministicMasteryEvidencePublisher()
    publisher.recalculate_student_mastery(db_session, student.id, concept_ids=set(concepts.values()))
    assert states() == before
    MathSolutionEvidenceAdapter(db_session).emit_evidence_for_decision(decision.id)
    assert states() == before
    MathSolutionEvidenceAdapter(db_session).apply_teacher_override(decision.id, admin.id, new_score=.5, new_is_correct=False, reason="Overall only")
    assert all(r.attempt_count == 0 for r in db_session.scalars(select(StudentConceptMastery)))
    question.explanation += " Changed"
    attempt.status = "SUBMITTED"
    from app.math_solutions.grading_context import resolve_grading_context
    with pytest.raises(ApplicationError) as error: resolve_grading_context(db_session, attempt)
    assert error.value.code == "GRADING_REFERENCE_CHANGED"
