from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from app.database.base import Base
from app.attempts.models import StudentAttempt, StudySession  # noqa: F401
from app.curriculum.models import (  # noqa: F401
    Chapter, Curriculum, CurriculumImportHistory, CurriculumVersion,
    LearningOutcome, ProblemType, ProblemTypeConcept, ProblemTypeLearningOutcome, Topic,
)
from app.questions.models import QuestionLearningOutcome, QuestionProblemType  # noqa: F401
from tests.migrations import downgrade_test_schema


def test_migration_chain_matches_models_and_can_downgrade(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        assert set(inspect(connection).get_table_names()) == {
            "users", "auth_sessions", "auth_refresh_tokens", "student_profiles",
            "teacher_profiles", "parent_profiles", "parent_student_relationships",
            "subjects", "concepts", "concept_relations",
            "classrooms", "teacher_classrooms", "student_enrollments",
            "questions", "question_options", "question_concepts",
            "question_groups", "question_group_items",
            "question_import_batches", "question_import_rows",
            "study_sessions", "student_attempts",
            "curricula", "curriculum_versions", "chapters", "topics",
            "problem_types", "learning_outcomes", "problem_type_concepts",
            "problem_type_learning_outcomes", "curriculum_import_history",
            "question_problem_types", "question_learning_outcomes",
            "practice_sessions", "practice_session_problem_types",
            "practice_session_concepts", "question_attempts",
            "question_group_attempts", "question_group_attempt_items",
            "student_concept_mastery", "student_problem_type_mastery",
            "diagnostic_assessments", "diagnostic_blueprint_items",
            "diagnostic_attempt_contexts",
            "academic_goals", "subject_goals",
            "teaching_plans", "teaching_plan_items",
            "quick_check_sessions", "quick_check_questions",
            "review_schedules",
            "study_plans", "study_tasks",
            "ai_request_logs",
            "documents", "document_chunks",
            "question_hints", "practice_question_hints",
            "misconception_definitions", "student_misconceptions",
            "assignments", "assignment_learning_objectives",
            "assignment_problem_types", "assignment_concepts",
            "assignment_questions", "student_assignments",
            "assignment_student_questions",
            "exams", "exam_sections", "exam_questions",
            "exam_attempts", "exam_responses",
            "universities", "majors", "admission_methods",
            "admission_data_sources", "admission_rules",
            "student_admission_targets", "admission_import_histories",
            "tutor_sessions", "tutor_session_summaries", "student_learning_memories",
        }
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []
        downgrade_test_schema(connection)
        assert inspect(connection).get_table_names() == []
