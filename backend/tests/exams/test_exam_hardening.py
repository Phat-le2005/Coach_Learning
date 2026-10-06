from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.curriculum.models import Chapter, ProblemType, Topic
from app.exams.models import (
    Exam,
    ExamAttempt,
    ExamAttemptStatus,
    ExamQuestion,
    ExamStatus,
    ExamType,
)
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User


def _create_simple_exam(
    session: Session, teacher: User, title: str = "Hardening Exam", status: ExamStatus = ExamStatus.PUBLISHED
) -> tuple[Exam, Question]:
    suffix = uuid4().hex[:6].upper()
    subject = Subject(code=f"HRD-{suffix}", name="Hardening Math", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"CHP-{suffix}", name="Chapter 1", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"TOP-{suffix}", name="Topic 1", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(topic_id=topic.id, code=f"PT-{suffix}", name="PT 1", order_index=0)
    session.add(pt)
    session.flush()

    question = Question(
        subject_id=subject.id,
        content="What is 2 + 2?",
        question_type=QuestionType.SHORT_ANSWER,
        difficulty=0.2,
        correct_answer="4",
        source_type="CURRICULUM",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        created_by=teacher.id,
    )
    session.add(question)
    session.flush()

    exam = Exam(
        subject_id=subject.id,
        title=title,
        duration_minutes=30,
        exam_type=ExamType.REAL_SIMULATION,
        status=status,
        created_by=teacher.id,
        total_questions=1,
        total_points=10.0,
    )
    session.add(exam)
    session.flush()

    db_eq = ExamQuestion(exam_id=exam.id, question_id=question.id, order_index=0, points=10.0)
    session.add(db_eq)
    session.commit()
    return exam, question


def test_exam_teacher_isolation_and_blueprint_access(
    db_client: TestClient,
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    exam_bearer: Callable[[User], dict[str, str]],
) -> None:
    teacher1 = exam_user_factory(Role.TEACHER, "t1_hrd@example.com")
    teacher2 = exam_user_factory(Role.TEACHER, "t2_hrd@example.com")
    exam, _ = _create_simple_exam(db_session, teacher1, title="Teacher 1 Exam")

    headers_t2 = exam_bearer(teacher2)

    # 1. Teacher 2 cannot view details of Teacher 1 exam -> 403
    res_get = db_client.get(f"/exams/{exam.id}", headers=headers_t2)
    assert res_get.status_code == 403
    assert res_get.json()["error"]["code"] == "EXAM_ACCESS_DENIED"

    # 2. Teacher 2 cannot add section -> 403
    res_sec = db_client.post(
        f"/exams/{exam.id}/sections",
        json={"title": "Sec 1", "order_index": 0},
        headers=headers_t2,
    )
    assert res_sec.status_code == 403
    assert res_sec.json()["error"]["code"] == "EXAM_ACCESS_DENIED"

    # 3. Teacher 2 cannot generate from blueprint -> 403
    res_bp = db_client.post(f"/exams/{exam.id}/generate-from-blueprint", headers=headers_t2)
    assert res_bp.status_code == 403
    assert res_bp.json()["error"]["code"] == "EXAM_ACCESS_DENIED"

    # 4. Teacher 2 cannot publish -> 403
    res_pub = db_client.post(f"/exams/{exam.id}/publish", headers=headers_t2)
    assert res_pub.status_code == 403
    assert res_pub.json()["error"]["code"] == "EXAM_ACCESS_DENIED"

    # 5. Teacher 2 list_exams only sees their own exams
    res_list = db_client.get("/exams", headers=headers_t2)
    assert res_list.status_code == 200
    listed_ids = [e["id"] for e in res_list.json()]
    assert str(exam.id) not in listed_ids


def test_student_cannot_access_draft_exam(
    db_client: TestClient,
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    exam_bearer: Callable[[User], dict[str, str]],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_draft@example.com")
    student = exam_user_factory(Role.STUDENT, "s_draft@example.com")
    exam, _ = _create_simple_exam(db_session, teacher, title="Draft Exam", status=ExamStatus.DRAFT)

    headers_s = exam_bearer(student)

    # Student cannot view draft exam -> 404
    res_get = db_client.get(f"/exams/{exam.id}", headers=headers_s)
    assert res_get.status_code == 404
    assert res_get.json()["error"]["code"] == "EXAM_NOT_FOUND"

    # Student cannot start draft exam -> 400
    res_start = db_client.post(f"/exams/{exam.id}/start", headers=headers_s)
    assert res_start.status_code == 400
    assert res_start.json()["error"]["code"] == "EXAM_NOT_PUBLISHED"


def test_exam_bounded_pagination(
    db_client: TestClient,
    exam_user_factory: Callable[[Role, str], User],
    exam_bearer: Callable[[User], dict[str, str]],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_pagn@example.com")
    headers = exam_bearer(teacher)

    # Valid pagination
    res_ok = db_client.get("/exams?limit=10&offset=0", headers=headers)
    assert res_ok.status_code == 200

    # Limit exceeding 200 -> 422
    res_over = db_client.get("/exams?limit=250", headers=headers)
    assert res_over.status_code == 422

    # Negative offset -> 422
    res_neg = db_client.get("/exams?offset=-1", headers=headers)
    assert res_neg.status_code == 422


def test_exam_timer_projection_and_finalize_timeout(
    db_client: TestClient,
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    exam_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_tmout@example.com")
    student = exam_user_factory(Role.STUDENT, "s_tmout@example.com")
    exam, q = _create_simple_exam(db_session, teacher, title="Timeout Exam")

    headers = exam_bearer(student)

    # 1. Start exam
    res_start = db_client.post(f"/exams/{exam.id}/start", headers=headers)
    assert res_start.status_code == 200
    attempt_id = res_start.json()["attempt_id"]

    # 2. Answer question
    res_ans = db_client.post(
        f"/exams/attempts/{attempt_id}/answer",
        json={"question_id": str(q.id), "student_answer": "4"},
        headers=headers,
    )
    assert res_ans.status_code == 200

    # 3. Before expiration: finalize-timeout raises 400 EXAM_NOT_TIMED_OUT
    res_premature = db_client.post(f"/exams/attempts/{attempt_id}/finalize-timeout", headers=headers)
    assert res_premature.status_code == 400
    assert res_premature.json()["error"]["code"] == "EXAM_NOT_TIMED_OUT"

    # 4. Fast forward timer: set started_at to 35 minutes ago (> 30 min duration)
    att_row = db_session.get(ExamAttempt, UUID(attempt_id))
    assert att_row is not None
    att_row.started_at = datetime.now(timezone.utc) - timedelta(minutes=35)
    db_session.commit()

    # 5. GET /attempts/{attempt_id}: read-only projection
    res_check = db_client.get(f"/exams/attempts/{attempt_id}", headers=headers)
    assert res_check.status_code == 200
    assert res_check.json()["status"] == "TIMED_OUT"
    assert res_check.json()["time_remaining_seconds"] == 0

    # Verify database was NOT mutated on GET (still IN_PROGRESS)
    db_session.expire_all()
    att_db = db_session.get(ExamAttempt, UUID(attempt_id))
    assert att_db is not None
    assert att_db.status == ExamAttemptStatus.IN_PROGRESS

    # 6. POST /attempts/{attempt_id}/finalize-timeout: explicit mutation
    res_fin = db_client.post(f"/exams/attempts/{attempt_id}/finalize-timeout", headers=headers)
    assert res_fin.status_code == 200
    assert res_fin.json()["status"] == "TIMED_OUT"

    # Verify database IS mutated on explicit POST
    db_session.expire_all()
    att_final = db_session.get(ExamAttempt, UUID(attempt_id))
    assert att_final is not None
    assert att_final.status == ExamAttemptStatus.TIMED_OUT
    assert att_final.score == 10.0


def test_record_response_expired_raises_409(
    db_client: TestClient,
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    exam_bearer: Callable[[User], dict[str, str]],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_exp409@example.com")
    student = exam_user_factory(Role.STUDENT, "s_exp409@example.com")
    exam, q = _create_simple_exam(db_session, teacher, title="Expired 409 Exam")

    headers = exam_bearer(student)

    # Start exam
    res_start = db_client.post(f"/exams/{exam.id}/start", headers=headers)
    attempt_id = res_start.json()["attempt_id"]

    # Fast forward beyond 30 min + 60s grace
    att_row = db_session.get(ExamAttempt, UUID(attempt_id))
    assert att_row is not None
    att_row.started_at = datetime.now(timezone.utc) - timedelta(minutes=35)
    db_session.commit()

    # Answer after grace period -> 409 EXAM_TIMED_OUT
    res_ans = db_client.post(
        f"/exams/attempts/{attempt_id}/answer",
        json={"question_id": str(q.id), "student_answer": "4"},
        headers=headers,
    )
    assert res_ans.status_code == 409
    assert res_ans.json()["error"]["code"] == "EXAM_TIMED_OUT"


def test_attempt_ownership_isolation(
    db_client: TestClient,
    db_session: Session,
    exam_user_factory: Callable[[Role, str], User],
    exam_bearer: Callable[[User], dict[str, str]],
) -> None:
    teacher = exam_user_factory(Role.TEACHER, "t_own@example.com")
    s1 = exam_user_factory(Role.STUDENT, "s1_own@example.com")
    s2 = exam_user_factory(Role.STUDENT, "s2_own@example.com")
    exam, q = _create_simple_exam(db_session, teacher, title="Ownership Exam")

    headers_s1 = exam_bearer(s1)
    headers_s2 = exam_bearer(s2)

    res_start = db_client.post(f"/exams/{exam.id}/start", headers=headers_s1)
    attempt_id = res_start.json()["attempt_id"]

    # Student 2 cannot check S1's attempt -> 404
    res_check = db_client.get(f"/exams/attempts/{attempt_id}", headers=headers_s2)
    assert res_check.status_code == 404
    assert res_check.json()["error"]["code"] == "ATTEMPT_NOT_FOUND"

    # Student 2 cannot hint on S1's attempt -> 404
    res_hint = db_client.get(f"/exams/attempts/{attempt_id}/hint", headers=headers_s2)
    assert res_hint.status_code == 404
    assert res_hint.json()["error"]["code"] == "ATTEMPT_NOT_FOUND"

    # Student 2 cannot finalize timeout on S1's attempt -> 404
    res_fin = db_client.post(f"/exams/attempts/{attempt_id}/finalize-timeout", headers=headers_s2)
    assert res_fin.status_code == 404
    assert res_fin.json()["error"]["code"] == "ATTEMPT_NOT_FOUND"
