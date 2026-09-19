from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.classes.models import Classroom, TeacherClassroom
from app.concepts.models import Concept
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture
def synthetic_catalog(db_session: Session) -> Iterator[dict[str, object]]:
    teacher = UserService(db_session).create_user(UserCreate(
        email="synthetic-teacher@example.com",
        password="Synthetic-Generator-Test-Password-2026!",
        full_name="Synthetic Teacher",
        role=Role.TEACHER,
    ))
    teacher_profile = db_session.query(TeacherProfile).filter_by(user_id=teacher.id).one()
    subject = Subject(code="SYNTH_MATH12", name="Synthetic Mathematics", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    concepts = [
        Concept(
            subject_id=subject.id,
            code=code,
            name=name,
            description=f"Synthetic {name}",
            grade_level=12,
            order_index=index,
        )
        for index, (code, name) in enumerate(
            [("FUNCTION", "Function"), ("DERIVATIVE", "Derivative"), ("OXYZ", "Oxyz")]
        )
    ]
    classroom = Classroom(
        name="Synthetic Dashboard Class",
        academic_year="2026-2027",
        grade_level=12,
        created_by=teacher.id,
    )
    db_session.add_all([*concepts, classroom])
    db_session.flush()
    chapter = Chapter(
        subject_id=subject.id,
        code="OXYZ_CHAPTER",
        name="Oxyz Chapter",
        order_index=1,
    )
    db_session.add(chapter)
    db_session.flush()
    topic = Topic(
        chapter_id=chapter.id,
        code="OXYZ_TOPIC",
        name="Oxyz Topic",
        order_index=1,
    )
    db_session.add(topic)
    db_session.flush()
    problem_type = ProblemType(
        topic_id=topic.id,
        code="OXYZ_LINE_PLANE_INTERSECTION",
        name="Oxyz line-plane intersection",
        order_index=1,
        is_active=True,
    )
    db_session.add(problem_type)
    db_session.flush()
    db_session.add(ProblemTypeConcept(
        problem_type_id=problem_type.id,
        concept_id=concepts[-1].id,
        weight=1.0,
        is_primary=True,
    ))
    db_session.add(TeacherClassroom(
        teacher_id=teacher_profile.id, classroom_id=classroom.id, role="OWNER"
    ))
    question = Question(
        subject_id=subject.id,
        content="Synthetic approved Oxyz question",
        question_type=QuestionType.TRUE_FALSE,
        difficulty=0.5,
        correct_answer="TRUE",
        source_type="TEST",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        created_by=teacher.id,
    )
    question.concept_links.append(QuestionConcept(concept_id=concepts[-1].id, weight=1.0))
    question.problem_type_links.append(QuestionProblemType(
        problem_type_id=problem_type.id, weight=1.0, is_primary=True
    ))
    db_session.add(question)
    db_session.commit()
    yield {
        "teacher": teacher,
        "subject": subject,
        "concepts": concepts,
        "classroom": classroom,
        "question": question,
        "problem_type": problem_type,
    }
