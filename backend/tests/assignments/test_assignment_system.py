from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentType,
    StudentAssignment,
    StudentAssignmentStatus,
)
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, ProblemTypeConcept, Topic
from app.mastery.models import StudentProblemTypeMastery
from app.knowledge_gap.models import RootCauseDiagnosis
from app.learning_evidence.models import LearningEvidenceEvent, LearningEvidenceSourceKind
from app.questions.fingerprint import question_content_hash
from app.questions.models import (
    Question,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User


def _setup_curriculum(
    session: Session, prefix: str = "ASG"
) -> tuple[Subject, Chapter, Topic, ProblemType, LearningOutcome, Concept]:
    subject = Subject(code=f"{prefix}-MATH", name=f"{prefix} Toan 12", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{prefix}-CHP1", name=f"{prefix} Giai Tich", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{prefix}-TOP1", name=f"{prefix} Dao Ham", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT-MAXMIN",
        name="Tim gia tri lon nhat nho nhat",
        order_index=0,
        is_active=True,
    )
    lo = LearningOutcome(
        subject_id=subject.id,
        code=f"{prefix}-LO-EXTREMA",
        description="Xac dinh cuc tri ham so",
        grade_level=12,
        order_index=0,
    )
    concept = Concept(
        subject_id=subject.id,
        code=f"{prefix}-CON-DERIV",
        name="Quy tac tinh dao ham",
        order_index=0,
    )
    session.add_all([pt, lo, concept])
    session.flush()

    session.add(ProblemTypeConcept(problem_type_id=pt.id, concept_id=concept.id, weight=1.0, is_primary=True))
    session.flush()
    return subject, chapter, topic, pt, lo, concept


def _create_test_question(
    session: Session,
    subject_id: UUID,
    creator_id: UUID,
    content: str,
    difficulty: float,
    status: QuestionStatus,
    problem_type_id: UUID | None = None,
    learning_outcome_id: UUID | None = None,
    correct_answer: str = "A",
) -> Question:
    q = Question(
        subject_id=subject_id,
        content=content,
        content_hash=question_content_hash(content),
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=difficulty,
        correct_answer=correct_answer,
        explanation=f"Giai thich cho {content}",
        source_type="CURRICULUM",
        exam_weight=1.0,
        status=status,
        created_by=creator_id,
    )
    session.add(q)
    session.flush()

    for idx, label in enumerate(["A", "B", "C", "D"]):
        session.add(
            QuestionOption(
                question_id=q.id,
                label=label,
                content=f"Lua chon {label} cho {content}",
                order_index=idx,
            )
        )

    if problem_type_id:
        session.add(
            QuestionProblemType(
                question_id=q.id,
                problem_type_id=problem_type_id,
                weight=1.0,
                is_primary=True,
            )
        )
    if learning_outcome_id:
        session.add(
            QuestionLearningOutcome(
                question_id=q.id,
                learning_outcome_id=learning_outcome_id,
                weight=1.0,
            )
        )
    session.flush()
    return q


# --------------------------------------------------------------------------
# 1. SAME_SET Assignment: Full Lifecycle & Scoring
# --------------------------------------------------------------------------

def test_same_set_assignment_lifecycle_and_grading(
    db_client: TestClient,
    db_session: Session,
    assignment_user_factory: Callable[[Role, str], User],
    assignment_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher_user = assignment_user_factory(Role.TEACHER, "t_same_set@example.com")
    s1_user = assignment_user_factory(Role.STUDENT, "s1_same_set@example.com")
    s2_user = assignment_user_factory(Role.STUDENT, "s2_same_set@example.com")

    t_prof = teacher_profile(teacher_user)
    s1_prof = student_profile(s1_user)
    s2_prof = student_profile(s2_user)

    subject, _, _, pt, lo, concept = _setup_curriculum(db_session, "SAME")

    classroom = Classroom(
        name="12A1 SameSet Test",
        academic_year="2026-2027",
        grade_level=12,
        created_by=teacher_user.id,
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s1_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))
    db_session.add(StudentEnrollment(student_id=s2_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Create APPROVED questions
    q1 = _create_test_question(
        db_session, subject.id, teacher_user.id, "Cau 1: Dao ham f(x)=x^2", 0.3, QuestionStatus.APPROVED, pt.id, lo.id, "A"
    )
    q2 = _create_test_question(
        db_session, subject.id, teacher_user.id, "Cau 2: Dao ham f(x)=sin(x)", 0.5, QuestionStatus.APPROVED, pt.id, lo.id, "B"
    )
    # Draft question (must not be picked)
    _create_test_question(
        db_session, subject.id, teacher_user.id, "Cau draft AI", 0.4, QuestionStatus.DRAFT, pt.id, lo.id, "C"
    )
    db_session.commit()

    teacher_headers = assignment_bearer(teacher_user)
    s1_headers = assignment_bearer(s1_user)
    s2_headers = assignment_bearer(s2_user)

    # 1. Teacher creates SAME_SET assignment
    create_payload = {
        "classroom_id": str(classroom.id),
        "subject_id": str(subject.id),
        "title": "Bai tap On tap Chuong 1 - SAME_SET",
        "description": "Moi hoc sinh lam cung mot bo de",
        "assignment_type": "SAME_SET",
        "question_count": 2,
        "target_problem_types": [{"problem_type_id": str(pt.id), "weight": 1.0}],
        "learning_outcomes": [{"learning_outcome_id": str(lo.id), "weight": 1.0}],
    }
    create_res = db_client.post(f"/teacher/classes/{classroom.id}/assignments", json=create_payload, headers=teacher_headers)
    assert create_res.status_code == 201, create_res.text
    assignment_data = create_res.json()
    assignment_id = assignment_data["id"]
    assert assignment_data["status"] == "DRAFT"
    assert assignment_data["assignment_type"] == "SAME_SET"

    # 2. Teacher publishes assignment
    pub_res = db_client.post(f"/teacher/assignments/{assignment_id}/publish", headers=teacher_headers)
    assert pub_res.status_code == 200
    assert pub_res.json()["status"] == "PUBLISHED"

    # 3. Students list assignments
    s1_list_res = db_client.get("/students/me/assignments", headers=s1_headers)
    assert s1_list_res.status_code == 200
    assert len(s1_list_res.json()) >= 1
    assert s1_list_res.json()[0]["assignment_id"] == assignment_id

    # 4. Student 1 and Student 2 fetch their assignment details (questions)
    s1_detail_res = db_client.get(f"/students/me/assignments/{assignment_id}", headers=s1_headers)
    assert s1_detail_res.status_code == 200
    s1_questions = s1_detail_res.json()["questions"]

    s2_detail_res = db_client.get(f"/students/me/assignments/{assignment_id}", headers=s2_headers)
    assert s2_detail_res.status_code == 200
    s2_questions = s2_detail_res.json()["questions"]

    # In SAME_SET, both students get the EXACT SAME questions in the same order
    assert len(s1_questions) == 2
    assert len(s2_questions) == 2
    assert [q["question_id"] for q in s1_questions] == [q["question_id"] for q in s2_questions]

    # Security check: before submission, correct_answer & explanation are hidden!
    for q_item in s1_questions:
        assert q_item["correct_answer"] is None
        assert q_item["explanation"] is None
        assert q_item["is_correct"] is None

    # 5. Student 1 submits (100% correct: Q1="A", Q2="B")
    s1_sub_payload = {
        "answers": [
            {"question_id": str(q1.id), "student_answer": "A"},
            {"question_id": str(q2.id), "student_answer": "B"},
        ]
    }
    s1_sub_res = db_client.post(f"/students/me/assignments/{assignment_id}/submit", json=s1_sub_payload, headers=s1_headers)
    assert s1_sub_res.status_code == 200
    s1_result = s1_sub_res.json()
    assert s1_result["score"] == 10.0
    assert s1_result["correct_count"] == 2
    assert s1_result["total_questions"] == 2

    # 6. Student 2 submits (50% correct: Q1="A", Q2="C" - wrong)
    s2_sub_payload = {
        "answers": [
            {"question_id": str(q1.id), "student_answer": "A"},
            {"question_id": str(q2.id), "student_answer": "C"},
        ]
    }
    s2_sub_res = db_client.post(f"/students/me/assignments/{assignment_id}/submit", json=s2_sub_payload, headers=s2_headers)
    assert s2_sub_res.status_code == 200
    s2_result = s2_sub_res.json()
    assert s2_result["score"] == 5.0
    assert s2_result["correct_count"] == 1
    canonical_wrong_event = db_session.scalar(
        select(LearningEvidenceEvent).where(
            LearningEvidenceEvent.student_id == s2_prof.id,
            LearningEvidenceEvent.source_kind
            == LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION,
            LearningEvidenceEvent.is_correct.is_(False),
        )
    )
    assert canonical_wrong_event is not None
    assert db_session.scalar(
        select(RootCauseDiagnosis).where(
            RootCauseDiagnosis.learning_evidence_event_id == canonical_wrong_event.id
        )
    ) is not None

    # 7. Student 1 checks detail after submission -> correct answers and explanations are now revealed
    s1_post_detail = db_client.get(f"/students/me/assignments/{assignment_id}", headers=s1_headers)
    assert s1_post_detail.status_code == 200
    for q_item in s1_post_detail.json()["questions"]:
        assert q_item["correct_answer"] is not None
        assert q_item["explanation"] is not None
        assert q_item["is_correct"] is True

    # 8. Teacher views submissions roster
    roster_res = db_client.get(f"/teacher/assignments/{assignment_id}/submissions", headers=teacher_headers)
    assert roster_res.status_code == 200
    roster_data = roster_res.json()
    assert roster_data["total_students"] == 2
    assert roster_data["submitted_count"] == 2
    assert roster_data["not_started_count"] == 0
    assert roster_data["average_score"] == 7.5  # (10 + 5) / 2


# --------------------------------------------------------------------------
# 2. ADAPTIVE_SET Assignment: Same Objectives, Personalized Questions by Mastery
# --------------------------------------------------------------------------

def test_adaptive_set_assignment_personalization_and_shared_targets(
    db_client: TestClient,
    db_session: Session,
    assignment_user_factory: Callable[[Role, str], User],
    assignment_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher_user = assignment_user_factory(Role.TEACHER, "t_adapt@example.com")
    s_high_user = assignment_user_factory(Role.STUDENT, "s_high_adapt@example.com")
    s_low_user = assignment_user_factory(Role.STUDENT, "s_low_adapt@example.com")

    t_prof = teacher_profile(teacher_user)
    s_high_prof = student_profile(s_high_user)
    s_low_prof = student_profile(s_low_user)

    subject, _, _, pt, lo, concept = _setup_curriculum(db_session, "ADAPT")

    classroom = Classroom(
        name="12A2 Adaptive Test",
        academic_year="2026-2027",
        grade_level=12,
        created_by=teacher_user.id,
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_high_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))
    db_session.add(StudentEnrollment(student_id=s_low_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # High student mastery in pt: 0.90
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_high_prof.id,
            problem_type_id=pt.id,
            mastery_score=0.90,
            confidence=0.85,
            attempt_count=10,
            correct_count=9,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    # Low student mastery in pt: 0.15
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_low_prof.id,
            problem_type_id=pt.id,
            mastery_score=0.15,
            confidence=0.80,
            attempt_count=8,
            correct_count=1,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )

    # Questions pool for the target: 2 easy, 2 hard
    q_easy1 = _create_test_question(
        db_session, subject.id, teacher_user.id, "Easy Q1: Nhan biet cuc tri", 0.20, QuestionStatus.APPROVED, pt.id, lo.id
    )
    q_easy2 = _create_test_question(
        db_session, subject.id, teacher_user.id, "Easy Q2: Thong hieu cuc tri", 0.30, QuestionStatus.APPROVED, pt.id, lo.id
    )
    q_hard1 = _create_test_question(
        db_session, subject.id, teacher_user.id, "Hard Q1: Van dung cuc tri bac 4", 0.80, QuestionStatus.APPROVED, pt.id, lo.id
    )
    q_hard2 = _create_test_question(
        db_session, subject.id, teacher_user.id, "Hard Q2: Van dung cao tham so m", 0.90, QuestionStatus.APPROVED, pt.id, lo.id
    )

    db_session.commit()

    teacher_headers = assignment_bearer(teacher_user)
    s_high_headers = assignment_bearer(s_high_user)
    s_low_headers = assignment_bearer(s_low_user)

    # Teacher creates ADAPTIVE_SET assignment
    create_payload = {
        "classroom_id": str(classroom.id),
        "subject_id": str(subject.id),
        "title": "Bai tap Thich ung (Adaptive Assignment) - Dao ham",
        "description": "He thong tu dong thich ung theo nang luc hoc sinh",
        "assignment_type": "ADAPTIVE_SET",
        "question_count": 2,
        "target_problem_types": [{"problem_type_id": str(pt.id), "weight": 1.0}],
        "learning_outcomes": [{"learning_outcome_id": str(lo.id), "weight": 1.0}],
    }
    create_res = db_client.post(f"/teacher/classes/{classroom.id}/assignments", json=create_payload, headers=teacher_headers)
    assert create_res.status_code == 201
    assignment_id = create_res.json()["id"]

    # Publish assignment
    pub_res = db_client.post(f"/teacher/assignments/{assignment_id}/publish", headers=teacher_headers)
    assert pub_res.status_code == 200

    # Fetch assignment for High Mastery student
    res_high = db_client.get(f"/students/me/assignments/{assignment_id}", headers=s_high_headers)
    assert res_high.status_code == 200
    high_questions = res_high.json()["questions"]
    high_q_ids = {q["question_id"] for q in high_questions}

    # Fetch assignment for Low Mastery student
    res_low = db_client.get(f"/students/me/assignments/{assignment_id}", headers=s_low_headers)
    assert res_low.status_code == 200
    low_questions = res_low.json()["questions"]
    low_q_ids = {q["question_id"] for q in low_questions}

    # 1. Both students received 2 questions
    assert len(high_questions) == 2
    assert len(low_questions) == 2

    # 2. Both received questions from the same configured targets!
    all_q_ids = {str(q_easy1.id), str(q_easy2.id), str(q_hard1.id), str(q_hard2.id)}
    assert high_q_ids.issubset(all_q_ids)
    assert low_q_ids.issubset(all_q_ids)

    # 3. Personalization: High student got harder questions, Low student got easier questions
    high_avg_diff = sum(q["difficulty"] for q in high_questions) / len(high_questions)
    low_avg_diff = sum(q["difficulty"] for q in low_questions) / len(low_questions)
    assert high_avg_diff > low_avg_diff
    assert str(q_hard2.id) in high_q_ids or str(q_hard1.id) in high_q_ids
    assert str(q_easy1.id) in low_q_ids or str(q_easy2.id) in low_q_ids


# --------------------------------------------------------------------------
# 3. Approved Questions Only & Exclusion of Draft/AI Questions
# --------------------------------------------------------------------------

def test_draft_questions_strictly_excluded_from_assignments(
    db_client: TestClient,
    db_session: Session,
    assignment_user_factory: Callable[[Role, str], User],
    assignment_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
) -> None:
    teacher_user = assignment_user_factory(Role.TEACHER, "t_draft_ex@example.com")
    t_prof = teacher_profile(teacher_user)
    subject, _, _, pt, lo, _ = _setup_curriculum(db_session, "DRAFT_EX")

    classroom = Classroom(
        name="12A3 Draft Exclusion", academic_year="2026-2027", grade_level=12, created_by=teacher_user.id
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))

    # Draft AI Question
    q_draft = _create_test_question(
        db_session, subject.id, teacher_user.id, "Draft AI Question", 0.5, QuestionStatus.DRAFT, pt.id, lo.id
    )
    # Review Question
    q_review = _create_test_question(
        db_session, subject.id, teacher_user.id, "Review Question", 0.5, QuestionStatus.REVIEW, pt.id, lo.id
    )
    # Approved Question
    q_approved = _create_test_question(
        db_session, subject.id, teacher_user.id, "Approved Official Question", 0.5, QuestionStatus.APPROVED, pt.id, lo.id
    )
    db_session.commit()

    teacher_headers = assignment_bearer(teacher_user)

    # Attempt 1: Passing draft question explicitly -> must be rejected with 422
    payload_explicit_draft = {
        "classroom_id": str(classroom.id),
        "subject_id": str(subject.id),
        "title": "Bai tap voi cau draft",
        "assignment_type": "SAME_SET",
        "question_ids": [str(q_draft.id)],
        "target_problem_types": [{"problem_type_id": str(pt.id), "weight": 1.0}],
        "learning_outcomes": [{"learning_outcome_id": str(lo.id), "weight": 1.0}],
    }
    res_rejected = db_client.post(
        f"/teacher/classes/{classroom.id}/assignments",
        json=payload_explicit_draft,
        headers=teacher_headers,
    )
    assert res_rejected.status_code == 422
    assert "QUESTION_NOT_APPROVED" in res_rejected.text

    # Attempt 2: Auto selection must ONLY select approved question
    payload_auto = {
        "classroom_id": str(classroom.id),
        "subject_id": str(subject.id),
        "title": "Bai tap Auto Selection",
        "assignment_type": "SAME_SET",
        "question_count": 5,
        "target_problem_types": [{"problem_type_id": str(pt.id), "weight": 1.0}],
        "learning_outcomes": [{"learning_outcome_id": str(lo.id), "weight": 1.0}],
    }
    res_auto = db_client.post(
        f"/teacher/classes/{classroom.id}/assignments",
        json=payload_auto,
        headers=teacher_headers,
    )
    assert res_auto.status_code == 201
    assigned_questions = res_auto.json()["questions"]
    # Only 1 question was approved, so only 1 question should be selected
    assert len(assigned_questions) == 1
    assert assigned_questions[0]["question_id"] == str(q_approved.id)


# --------------------------------------------------------------------------
# 4. Teacher Authorization & Classroom Isolation
# --------------------------------------------------------------------------

def test_teacher_classroom_isolation(
    db_client: TestClient,
    db_session: Session,
    assignment_user_factory: Callable[[Role, str], User],
    assignment_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
) -> None:
    t1_user = assignment_user_factory(Role.TEACHER, "t1_iso@example.com")
    t2_user = assignment_user_factory(Role.TEACHER, "t2_iso@example.com")
    t1_prof = teacher_profile(t1_user)
    _ = teacher_profile(t2_user)

    subject, _, _, pt, lo, _ = _setup_curriculum(db_session, "ISO")

    classroom = Classroom(
        name="12A4 Isolation Class", academic_year="2026-2027", grade_level=12, created_by=t1_user.id
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t1_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.commit()

    t2_headers = assignment_bearer(t2_user)
    payload = {
        "classroom_id": str(classroom.id),
        "subject_id": str(subject.id),
        "title": "Bai tap trai phep",
        "assignment_type": "SAME_SET",
        "question_count": 2,
    }

    # T2 tries to create assignment in T1's class -> 403 Forbidden
    res = db_client.post(f"/teacher/classes/{classroom.id}/assignments", json=payload, headers=t2_headers)
    assert res.status_code == 403
    assert "NOT_ASSIGNED_TO_CLASSROOM" in res.text


# --------------------------------------------------------------------------
# 5. Closed Assignment & Duplicate Submission Prevention
# --------------------------------------------------------------------------

def test_closed_assignment_and_duplicate_submission(
    db_client: TestClient,
    db_session: Session,
    assignment_user_factory: Callable[[Role, str], User],
    assignment_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher_user = assignment_user_factory(Role.TEACHER, "t_close@example.com")
    s_user = assignment_user_factory(Role.STUDENT, "s_close@example.com")
    t_prof = teacher_profile(teacher_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, lo, _ = _setup_curriculum(db_session, "CLOSE")

    classroom = Classroom(
        name="12A5 Close Test", academic_year="2026-2027", grade_level=12, created_by=teacher_user.id
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    q1 = _create_test_question(
        db_session, subject.id, teacher_user.id, "Question 1", 0.5, QuestionStatus.APPROVED, pt.id, lo.id, "A"
    )
    db_session.commit()

    teacher_headers = assignment_bearer(teacher_user)
    student_headers = assignment_bearer(s_user)

    # 1. Create and publish
    create_payload = {
        "classroom_id": str(classroom.id),
        "subject_id": str(subject.id),
        "title": "Bai tap Kiem tra Close",
        "assignment_type": "SAME_SET",
        "question_count": 1,
        "target_problem_types": [{"problem_type_id": str(pt.id), "weight": 1.0}],
    }
    create_res = db_client.post(f"/teacher/classes/{classroom.id}/assignments", json=create_payload, headers=teacher_headers)
    assignment_id = create_res.json()["id"]
    db_client.post(f"/teacher/assignments/{assignment_id}/publish", headers=teacher_headers)

    # 2. Student starts & submits successfully
    sub_payload = {"answers": [{"question_id": str(q1.id), "student_answer": "A"}]}
    first_sub = db_client.post(f"/students/me/assignments/{assignment_id}/submit", json=sub_payload, headers=student_headers)
    assert first_sub.status_code == 200

    # 3. Student attempts duplicate submission -> 409 Conflict
    dup_sub = db_client.post(f"/students/me/assignments/{assignment_id}/submit", json=sub_payload, headers=student_headers)
    assert dup_sub.status_code == 409
    assert "ASSIGNMENT_ALREADY_SUBMITTED" in dup_sub.text

    # 4. Teacher closes assignment
    close_res = db_client.post(f"/teacher/assignments/{assignment_id}/close", headers=teacher_headers)
    assert close_res.status_code == 200
    assert close_res.json()["status"] == "CLOSED"


# --------------------------------------------------------------------------
# 6. Assignment with Explicit Concept Reinforcement (Without Replacing ProblemType)
# --------------------------------------------------------------------------

def test_assignment_with_explicit_concept_reinforcement(
    db_client: TestClient,
    db_session: Session,
    assignment_user_factory: Callable[[Role, str], User],
    assignment_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
) -> None:
    teacher_user = assignment_user_factory(Role.TEACHER, "t_concept_reinforce@example.com")
    t_prof = teacher_profile(teacher_user)
    subject, _, _, pt, lo, concept = _setup_curriculum(db_session, "CONC")

    classroom = Classroom(
        name="12A6 Concept Class", academic_year="2026-2027", grade_level=12, created_by=teacher_user.id
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.commit()

    teacher_headers = assignment_bearer(teacher_user)

    # Teacher creates assignment configuring BOTH ProblemType AND Concept explicitly
    payload = {
        "classroom_id": str(classroom.id),
        "subject_id": str(subject.id),
        "title": "Cung co Khai niem Dao ham va Dang bai Cuc tri",
        "assignment_type": "SAME_SET",
        "question_count": 3,
        "target_problem_types": [{"problem_type_id": str(pt.id), "weight": 1.0}],
        "learning_outcomes": [{"learning_outcome_id": str(lo.id), "weight": 1.0}],
        "target_concepts": [{"concept_id": str(concept.id), "weight": 0.8}],
    }
    res = db_client.post(f"/teacher/classes/{classroom.id}/assignments", json=payload, headers=teacher_headers)
    assert res.status_code == 201
    data = res.json()

    # Verify that ProblemType is NOT replaced by Concept, both are present!
    assert len(data["problem_types"]) == 1
    assert data["problem_types"][0]["problem_type_id"] == str(pt.id)
    assert len(data["concepts"]) == 1
    assert data["concepts"][0]["concept_id"] == str(concept.id)
    assert len(data["learning_objectives"]) == 1
    assert data["learning_objectives"][0]["learning_outcome_id"] == str(lo.id)


# --------------------------------------------------------------------------
# 7. Unenrolled Student Cannot Access Assignment
# --------------------------------------------------------------------------

def test_unenrolled_student_cannot_access_assignment(
    db_client: TestClient,
    db_session: Session,
    assignment_user_factory: Callable[[Role, str], User],
    assignment_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    teacher_user = assignment_user_factory(Role.TEACHER, "t_unenrolled@example.com")
    s_enrolled = assignment_user_factory(Role.STUDENT, "s_enrolled@example.com")
    s_outsider = assignment_user_factory(Role.STUDENT, "s_outsider@example.com")

    t_prof = teacher_profile(teacher_user)
    s_enrolled_prof = student_profile(s_enrolled)
    _ = student_profile(s_outsider)

    subject, _, _, pt, lo, _ = _setup_curriculum(db_session, "UNENR")

    classroom = Classroom(
        name="12A7 Secret Class", academic_year="2026-2027", grade_level=12, created_by=teacher_user.id
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    # Only s_enrolled is enrolled
    db_session.add(StudentEnrollment(student_id=s_enrolled_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))
    _create_test_question(db_session, subject.id, teacher_user.id, "Question Secret", 0.4, QuestionStatus.APPROVED, pt.id, lo.id)
    db_session.commit()

    teacher_headers = assignment_bearer(teacher_user)
    outsider_headers = assignment_bearer(s_outsider)

    create_res = db_client.post(
        f"/teacher/classes/{classroom.id}/assignments",
        json={
            "classroom_id": str(classroom.id),
            "subject_id": str(subject.id),
            "title": "Bai tap Lop 12A7",
            "assignment_type": "SAME_SET",
            "question_count": 1,
            "target_problem_types": [{"problem_type_id": str(pt.id), "weight": 1.0}],
        },
        headers=teacher_headers,
    )
    assignment_id = create_res.json()["id"]
    db_client.post(f"/teacher/assignments/{assignment_id}/publish", headers=teacher_headers)

    # Outsider student tries to get assignment -> 404
    outsider_res = db_client.get(f"/students/me/assignments/{assignment_id}", headers=outsider_headers)
    assert outsider_res.status_code == 404
    assert "ASSIGNMENT_NOT_FOUND" in outsider_res.text

