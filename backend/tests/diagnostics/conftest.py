from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from tests.practice.conftest import (
    PracticeContent,
    practice_bearer,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)

__all__ = [
    "PracticeContent",
    "practice_bearer",
    "practice_content",
    "practice_students",
    "practice_user_factory",
    "student_profile",
]


@dataclass(frozen=True)
class DiagnosticContent:
    base: PracticeContent
    problem_types: tuple[ProblemType, ProblemType, ProblemType]
    concepts: tuple[Concept, Concept, Concept]
    prerequisite: Concept
    medium_questions: tuple[Question, Question, Question]
    hard_questions: tuple[Question, Question, Question]
    prerequisite_question: Question


@pytest.fixture
def diagnostic_content(
    db_session: Session, practice_content: PracticeContent
) -> DiagnosticContent:
    existing_topic = db_session.get(Topic, practice_content.problem_type.topic_id)
    assert existing_topic is not None
    second_topic = Topic(
        chapter_id=existing_topic.chapter_id,
        code="DIAGNOSTIC_TOPIC_2",
        name="Diagnostic topic 2",
        description="Second topic for diagnostic coverage.",
        order_index=1,
    )
    second_chapter = Chapter(
        subject_id=practice_content.subject.id,
        code="DIAGNOSTIC_CHAPTER_2",
        name="Diagnostic chapter 2",
        description="Second chapter for diagnostic coverage.",
        order_index=1,
    )
    db_session.add_all([second_topic, second_chapter])
    db_session.flush()
    third_topic = Topic(
        chapter_id=second_chapter.id,
        code="DIAGNOSTIC_TOPIC_3",
        name="Diagnostic topic 3",
        description="Third topic for diagnostic coverage.",
        order_index=0,
    )
    db_session.add(third_topic)
    db_session.flush()
    second_problem = ProblemType(
        topic_id=second_topic.id,
        code="DIAGNOSTIC_PT_2",
        name="Diagnostic ProblemType 2",
        description="Second diagnostic ProblemType.",
        order_index=0,
        is_active=True,
    )
    third_problem = ProblemType(
        topic_id=third_topic.id,
        code="DIAGNOSTIC_PT_3",
        name="Diagnostic ProblemType 3",
        description="Third diagnostic ProblemType.",
        order_index=0,
        is_active=True,
    )
    second_concept = Concept(
        subject_id=practice_content.subject.id,
        code="DIAGNOSTIC_CONCEPT_2",
        name="Diagnostic concept 2",
        description="Second diagnostic concept.",
        grade_level=12,
        order_index=10,
    )
    third_concept = Concept(
        subject_id=practice_content.subject.id,
        code="DIAGNOSTIC_CONCEPT_3",
        name="Diagnostic concept 3",
        description="Third diagnostic concept.",
        grade_level=12,
        order_index=11,
    )
    prerequisite = Concept(
        subject_id=practice_content.subject.id,
        code="DIAGNOSTIC_PREREQUISITE",
        name="Diagnostic prerequisite",
        description="Direct prerequisite checked after an incorrect answer.",
        grade_level=12,
        order_index=9,
    )
    db_session.add_all([second_problem, third_problem, second_concept, third_concept, prerequisite])
    db_session.flush()
    db_session.add_all(
        [
            ProblemTypeConcept(
                problem_type_id=practice_content.problem_type.id,
                concept_id=practice_content.concept.id,
                weight=1.0,
                is_primary=True,
            ),
            ProblemTypeConcept(
                problem_type_id=second_problem.id,
                concept_id=second_concept.id,
                weight=1.0,
                is_primary=True,
            ),
            ProblemTypeConcept(
                problem_type_id=third_problem.id,
                concept_id=third_concept.id,
                weight=1.0,
                is_primary=True,
            ),
            ConceptRelation(
                source_concept_id=prerequisite.id,
                target_concept_id=practice_content.concept.id,
                relation_type=RelationType.PREREQUISITE,
            ),
        ]
    )

    def question(
        problem_type: ProblemType,
        concept: Concept,
        difficulty: float,
        label: str,
        *,
        exam_weight: float = 0.7,
    ) -> Question:
        item = Question(
            subject_id=practice_content.subject.id,
            content=f"Diagnostic {label} at difficulty {difficulty}",
            question_type=QuestionType.TRUE_FALSE,
            difficulty=difficulty,
            correct_answer="TRUE",
            explanation="Deterministic diagnostic fixture.",
            source_type="TEST",
            source_reference="diagnostic-suite",
            cognitive_level=(
                CognitiveLevel.UNDERSTAND
                if difficulty < 0.5
                else CognitiveLevel.APPLY
                if difficulty < 0.8
                else CognitiveLevel.ANALYZE
            ),
            exam_weight=exam_weight,
            status=QuestionStatus.APPROVED,
            created_by=practice_content.mcq.created_by,
            problem_type_links=[
                QuestionProblemType(
                    problem_type_id=problem_type.id,
                    weight=1.0,
                    is_primary=True,
                )
            ],
            concept_links=[QuestionConcept(concept_id=concept.id, weight=1.0)],
            learning_outcome_links=[
                QuestionLearningOutcome(
                    learning_outcome_id=practice_content.learning_outcome.id,
                    weight=1.0,
                )
            ],
        )
        db_session.add(item)
        return item

    problem_types = (practice_content.problem_type, second_problem, third_problem)
    concepts = (practice_content.concept, second_concept, third_concept)
    medium = tuple(
        question(problem_type, concept, 0.55, f"medium-{index}")
        for index, (problem_type, concept) in enumerate(zip(problem_types, concepts))
    )
    hard = tuple(
        question(problem_type, concept, 0.85, f"hard-{index}")
        for index, (problem_type, concept) in enumerate(zip(problem_types, concepts))
    )
    for index, (problem_type, concept) in enumerate(zip(problem_types, concepts)):
        question(problem_type, concept, 0.25, f"easy-{index}")
    prerequisite_question = question(
        third_problem,
        prerequisite,
        0.35,
        "prerequisite",
        exam_weight=0.2,
    )
    db_session.commit()
    return DiagnosticContent(
        base=practice_content,
        problem_types=problem_types,
        concepts=concepts,
        prerequisite=prerequisite,
        medium_questions=medium,
        hard_questions=hard,
        prerequisite_question=prerequisite_question,
    )
