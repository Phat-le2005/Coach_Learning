from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.curriculum.models import ProblemType
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.schemas import PracticeAnswerCreate, PracticeSessionCreate
from app.practice.service import PracticeService
from app.questions.models import QuestionConcept, QuestionProblemType
from app.users.models import User
from tests.practice.conftest import PracticeContent


def answer_mcq(
    db_session: Session, student: User, content: PracticeContent
) -> None:
    service = PracticeService(db_session)
    practice = service.create_session(
        student,
        PracticeSessionCreate(
            subject_id=content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=[content.problem_type.id],
            concept_ids=[content.concept.id],
        ),
    )
    service.answer(
        student,
        practice.id,
        PracticeAnswerCreate(
            question_id=content.mcq.id,
            student_answer="B",
            hint_count=0,
        ),
    )


def test_attempt_updates_concept_and_problem_type_mastery(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    answer_mcq(db_session, student, practice_content)
    student_id = db_session.scalar(
        select(StudentConceptMastery.student_id).where(
            StudentConceptMastery.concept_id == practice_content.concept.id
        )
    )
    concept = db_session.get(
        StudentConceptMastery, (student_id, practice_content.concept.id)
    )
    problem = db_session.get(
        StudentProblemTypeMastery, (student_id, practice_content.problem_type.id)
    )
    assert concept is not None and problem is not None
    assert concept.attempt_count == problem.attempt_count == 1
    assert concept.correct_count == problem.correct_count == 1
    assert 0.0 < concept.mastery_score <= 0.3
    assert 0.0 < problem.confidence <= 1.0


def test_mapping_weights_apply_independently_to_multiple_concepts_and_problem_types(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    second_concept = Concept(
        subject_id=practice_content.subject.id,
        code="SECOND-MASTERY-CONCEPT",
        name="Second mastery concept",
        description="Lower weight concept",
        grade_level=12,
        order_index=10,
    )
    second_problem = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code="SECOND_MASTERY_PROBLEM",
        name="Second mastery problem",
        description="Lower weight problem type",
        order_index=10,
    )
    db_session.add_all([second_concept, second_problem])
    db_session.flush()
    practice_content.mcq.concept_links[0].weight = 0.7
    practice_content.mcq.problem_type_links[0].weight = 0.7
    practice_content.mcq.concept_links.append(
        QuestionConcept(concept_id=second_concept.id, weight=0.3)
    )
    practice_content.mcq.problem_type_links.append(
        QuestionProblemType(
            problem_type_id=second_problem.id, weight=0.3, is_primary=False
        )
    )
    db_session.commit()

    answer_mcq(db_session, student, practice_content)
    concept_rows = list(
        db_session.scalars(
            select(StudentConceptMastery).order_by(
                StudentConceptMastery.mastery_score.desc()
            )
        )
    )
    problem_rows = list(
        db_session.scalars(
            select(StudentProblemTypeMastery).order_by(
                StudentProblemTypeMastery.mastery_score.desc()
            )
        )
    )
    assert len(concept_rows) == len(problem_rows) == 2
    assert concept_rows[0].concept_id == practice_content.concept.id
    assert problem_rows[0].problem_type_id == practice_content.problem_type.id
    assert concept_rows[0].mastery_score > concept_rows[1].mastery_score
    assert problem_rows[0].confidence > problem_rows[1].confidence
