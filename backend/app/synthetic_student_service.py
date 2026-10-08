import logging
import secrets
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.attempts.models import StudentAttempt, StudySession
from app.auth.security import hash_password
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment
from app.concepts.graph_service import ConceptGraphService
from app.concepts.models import Concept, RelationType
from app.core.config import Settings
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.parents.models import ParentStudentRelationship  # noqa: F401; registers mapper target
from app.questions.eligibility import standalone_question_only
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionStatus,
)
from app.students.models import StudentProfile, SyntheticProfile
from app.subjects.models import Subject
from app.users.models import Role, User
from data.seed.identifiers import stable_id
from data.synthetic.student_behavior import (
    SeededStudentBehaviorGenerator,
    SyntheticBehaviorTarget,
)

logger = logging.getLogger(__name__)


class SyntheticGenerationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class SyntheticGenerationSummary:
    students_created: int = 0
    students_updated: int = 0
    attempts_created: int = 0
    study_sessions_created: int = 0
    enrollments_created: int = 0
    profiles: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, object]:
        return {
            "students_created": self.students_created,
            "students_updated": self.students_updated,
            "attempts_created": self.attempts_created,
            "study_sessions_created": self.study_sessions_created,
            "enrollments_created": self.enrollments_created,
            "profiles": dict(sorted(self.profiles.items())),
        }


class SyntheticStudentService:
    ATTEMPTS_PER_STUDENT = 48
    ATTEMPTS_PER_SESSION = 6
    MAX_STUDENTS = 500

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.behavior = SeededStudentBehaviorGenerator()
        self.summary = SyntheticGenerationSummary()
        self._disabled_password_hash: str | None = None

    def generate(
        self,
        *,
        count: int,
        seed: int,
        profile: SyntheticProfile | None = None,
        include_study_history: bool = True,
        anchor_time: datetime | None = None,
        gap_problem_type_code: str | None = None,
        gap_concept_code: str | None = None,
        gap_prerequisite_concept_code: str | None = None,
        gap_topic_code: str | None = None,
        gap_chapter_code: str | None = None,
        gap_subject_code: str | None = None,
    ) -> SyntheticGenerationSummary:
        self._validate(count)
        self.summary = SyntheticGenerationSummary()
        self._lock()
        concepts = list(
            self.session.scalars(
                select(Concept)
                .join(Subject, Subject.id == Concept.subject_id)
                .where(Subject.grade_level == 12)
                .order_by(Concept.order_index, Concept.code, Concept.id)
            )
        )
        if not concepts:
            raise SyntheticGenerationError(
                "SYNTHETIC_CONCEPTS_REQUIRED",
                "Grade 12 concepts must be seeded before generating synthetic students.",
            )
        classrooms = list(
            self.session.scalars(
                select(Classroom)
                .where(Classroom.grade_level == 12)
                .order_by(Classroom.created_at, Classroom.id)
            )
        )
        targets, problem_types_by_target, concepts_by_target = self._behavior_targets(concepts)
        gap_keys = self._gap_keys(
            profile,
            targets,
            problem_type_code=gap_problem_type_code,
            concept_code=gap_concept_code,
            prerequisite_concept_code=gap_prerequisite_concept_code,
            topic_code=gap_topic_code,
            chapter_code=gap_chapter_code,
            subject_code=gap_subject_code,
        )
        questions_by_concept = self._approved_questions_by_concept()
        questions_by_problem_type = self._approved_questions_by_problem_type()
        anchor = (anchor_time or datetime.now(UTC)).astimezone(UTC).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        patterns = list(SyntheticProfile)
        try:
            for index in range(1, count + 1):
                selected = profile or patterns[(index - 1) % len(patterns)]
                mode = profile.value if profile is not None else "MIXED"
                student_key = f"{seed}:{mode}:{index:04d}"
                student = self._upsert_student(student_key, seed, index, selected)
                self._replace_history(
                    student,
                    student_key,
                    seed,
                    selected,
                    targets,
                    problem_types_by_target,
                    concepts_by_target,
                    questions_by_concept,
                    questions_by_problem_type,
                    gap_keys,
                    anchor,
                    include_study_history,
                )
                if classrooms:
                    self._enroll(student, classrooms[(index - 1) % len(classrooms)])
                self.summary.profiles[selected.value] += 1
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info(
            "Synthetic students generated (count=%s, seed=%s, profile=%s)",
            count,
            seed,
            profile.value if profile else "MIXED",
        )
        return self.summary

    def _validate(self, count: int) -> None:
        if self.settings.app_env == "production":
            raise SyntheticGenerationError(
                "SYNTHETIC_GENERATION_FORBIDDEN",
                "Synthetic student generation is forbidden in production.",
            )
        if not 1 <= count <= self.MAX_STUDENTS:
            raise SyntheticGenerationError(
                "INVALID_SYNTHETIC_COUNT",
                f"count must be between 1 and {self.MAX_STUDENTS}.",
            )

    def _lock(self) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(
                select(func.pg_advisory_xact_lock(func.hashtext("edums:synthetic-students")))
            )

    def _upsert_student(
        self,
        student_key: str,
        seed: int,
        index: int,
        profile: SyntheticProfile,
    ) -> StudentProfile:
        user_id = stable_id("synthetic-user", student_key)
        profile_id = stable_id("synthetic-student-profile", student_key)
        mode = student_key.split(":")[1].lower()
        email = f"synthetic.{seed}.{mode}.{index:04d}@example.com"
        full_name = f"Synthetic {profile.value.replace('_', ' ').title()} Student {index:04d}"
        user = self.session.get(User, user_id)
        email_collision = self.session.scalar(select(User).where(User.email == email))
        if email_collision is not None and email_collision.id != user_id:
            raise SyntheticGenerationError(
                "SYNTHETIC_IDENTITY_CONFLICT", f"Synthetic email conflict: {email}."
            )
        if user is None:
            if self._disabled_password_hash is None:
                self._disabled_password_hash = hash_password(secrets.token_urlsafe(32))
            user = User(
                id=user_id,
                email=email,
                password_hash=self._disabled_password_hash,
                full_name=full_name,
                role=Role.STUDENT,
                is_active=False,
            )
            self.session.add(user)
            self.session.flush()
            student = StudentProfile(
                id=profile_id,
                user_id=user.id,
                grade_level=12,
                school_name="EduMS Synthetic School",
                is_synthetic=True,
                synthetic_profile=profile,
            )
            self.session.add(student)
            self.session.flush()
            self.summary.students_created += 1
            return student
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user.id)
        )
        if (
            user.role != Role.STUDENT
            or student is None
            or student.id != profile_id
            or not student.is_synthetic
        ):
            raise SyntheticGenerationError(
                "SYNTHETIC_IDENTITY_CONFLICT",
                f"Stable synthetic identity collides with non-synthetic data: {email}.",
            )
        user.email = email
        user.full_name = full_name
        user.is_active = False
        student.grade_level = 12
        student.school_name = "EduMS Synthetic School"
        student.synthetic_profile = profile
        self.summary.students_updated += 1
        return student

    def _replace_history(
        self,
        student: StudentProfile,
        student_key: str,
        seed: int,
        profile: SyntheticProfile,
        targets: list[SyntheticBehaviorTarget],
        problem_types_by_target: dict[str, ProblemType],
        concepts_by_target: dict[str, Concept],
        questions_by_concept: dict[UUID, list[UUID]],
        questions_by_problem_type: dict[UUID, list[UUID]],
        gap_keys: set[str] | None,
        anchor: datetime,
        include_study_history: bool,
    ) -> None:
        self.session.execute(
            delete(StudentAttempt).where(
                StudentAttempt.student_id == student.id,
                StudentAttempt.is_synthetic.is_(True),
            )
        )
        self.session.execute(
            delete(StudySession).where(
                StudySession.student_id == student.id,
                StudySession.is_synthetic.is_(True),
            )
        )
        self.session.flush()
        samples = self.behavior.generate(
            seed=seed,
            student_key=student_key,
            profile=profile,
            targets=targets,
            gap_keys=gap_keys,
            attempt_count=self.ATTEMPTS_PER_STUDENT,
            attempts_per_session=self.ATTEMPTS_PER_SESSION,
        )
        session_count = ceil(len(samples) / self.ATTEMPTS_PER_SESSION)
        sessions: dict[int, StudySession] = {}
        if include_study_history:
            for session_index in range(session_count):
                started = anchor - timedelta(days=(session_count - 1 - session_index) * 4)
                study_session = StudySession(
                    id=stable_id("synthetic-study-session", f"{student_key}:{session_index}"),
                    student_id=student.id,
                    started_at=started,
                    ended_at=started + timedelta(minutes=45),
                    is_synthetic=True,
                )
                self.session.add(study_session)
                sessions[session_index] = study_session
                self.summary.study_sessions_created += 1
        for sample in samples:
            concept = concepts_by_target[sample.target_key]
            problem_type = problem_types_by_target.get(sample.target_key)
            started = anchor - timedelta(days=(session_count - 1 - sample.session_index) * 4)
            question_ids = (
                questions_by_problem_type.get(problem_type.id, [])
                if problem_type is not None
                else []
            ) or questions_by_concept.get(concept.id, [])
            question_id = (
                question_ids[sample.attempt_index % len(question_ids)] if question_ids else None
            )
            self.session.add(
                StudentAttempt(
                    id=stable_id(
                        "synthetic-student-attempt", f"{student_key}:{sample.attempt_index}"
                    ),
                    student_id=student.id,
                    concept_id=concept.id,
                    problem_type_id=problem_type.id if problem_type is not None else None,
                    question_id=question_id,
                    study_session_id=(
                        sessions[sample.session_index].id if include_study_history else None
                    ),
                    is_correct=sample.is_correct,
                    response_time_ms=sample.response_time_ms,
                    attempted_at=started + timedelta(minutes=sample.minute_offset),
                    is_synthetic=True,
                )
            )
            self.summary.attempts_created += 1

    def _approved_questions_by_concept(self) -> dict[UUID, list[UUID]]:
        mapping: dict[UUID, list[UUID]] = {}
        rows = self.session.execute(
            select(QuestionConcept.concept_id, Question.id)
            .join(Question, Question.id == QuestionConcept.question_id)
            .where(
                Question.status == QuestionStatus.APPROVED,
                standalone_question_only(),
            )
            .order_by(QuestionConcept.concept_id, Question.id)
        )
        for concept_id, question_id in rows:
            mapping.setdefault(concept_id, []).append(question_id)
        return mapping

    def _approved_questions_by_problem_type(self) -> dict[UUID, list[UUID]]:
        mapping: dict[UUID, list[UUID]] = {}
        rows = self.session.execute(
            select(QuestionProblemType.problem_type_id, Question.id)
            .join(Question, Question.id == QuestionProblemType.question_id)
            .where(
                Question.status == QuestionStatus.APPROVED,
                standalone_question_only(),
            )
            .order_by(QuestionProblemType.problem_type_id, Question.id)
        )
        for problem_type_id, question_id in rows:
            mapping.setdefault(problem_type_id, []).append(question_id)
        return mapping

    def _behavior_targets(
        self, concepts: list[Concept]
    ) -> tuple[
        list[SyntheticBehaviorTarget], dict[str, ProblemType], dict[str, Concept]
    ]:
        rows = list(self.session.execute(
            select(
                ProblemType,
                Concept,
                Topic.code,
                Chapter.code,
                Subject.code,
                ProblemTypeConcept.is_primary,
                ProblemTypeConcept.weight,
            )
            .join(Topic, Topic.id == ProblemType.topic_id)
            .join(Chapter, Chapter.id == Topic.chapter_id)
            .join(Subject, Subject.id == Chapter.subject_id)
            .join(ProblemTypeConcept, ProblemTypeConcept.problem_type_id == ProblemType.id)
            .join(Concept, Concept.id == ProblemTypeConcept.concept_id)
            .where(ProblemType.is_active.is_(True), Subject.grade_level == 12)
            .order_by(
                ProblemType.code,
                ProblemTypeConcept.is_primary.desc(),
                ProblemTypeConcept.weight.desc(),
                Concept.code,
            )
        ))
        targets: list[SyntheticBehaviorTarget] = []
        problem_types: dict[str, ProblemType] = {}
        concepts_by_target: dict[str, Concept] = {}
        for (
            problem_type,
            concept,
            topic_code,
            chapter_code,
            subject_code,
            is_primary,
            _,
        ) in rows:
            target = SyntheticBehaviorTarget(
                key=f"PROBLEM_TYPE:{problem_type.id}:CONCEPT:{concept.id}",
                concept_code=concept.code,
                problem_type_code=problem_type.code,
                topic_code=topic_code,
                chapter_code=chapter_code,
                subject_code=subject_code,
                is_primary_concept=is_primary,
            )
            targets.append(target)
            problem_types[target.key] = problem_type
            concepts_by_target[target.key] = concept
        if targets:
            return targets, problem_types, concepts_by_target
        subject_codes = dict(self.session.execute(
            select(Subject.id, Subject.code).where(
                Subject.id.in_({concept.subject_id for concept in concepts})
            )
        ).all())
        fallback = [
            SyntheticBehaviorTarget(
                key=f"CONCEPT:{concept.id}",
                concept_code=concept.code,
                subject_code=subject_codes[concept.subject_id],
            )
            for concept in concepts
        ]
        return fallback, {}, {
            target.key: concept for target, concept in zip(fallback, concepts, strict=True)
        }

    def _gap_keys(
        self,
        profile: SyntheticProfile | None,
        targets: list[SyntheticBehaviorTarget],
        *,
        problem_type_code: str | None,
        concept_code: str | None,
        prerequisite_concept_code: str | None,
        topic_code: str | None,
        chapter_code: str | None,
        subject_code: str | None,
    ) -> set[str] | None:
        if concept_code is not None and prerequisite_concept_code is not None:
            raise SyntheticGenerationError(
                "CONFLICTING_SYNTHETIC_CONCEPT_GAPS",
                "Choose either a concept gap or a prerequisite concept gap.",
            )
        selectors = {
            "subject": subject_code,
            "chapter": chapter_code,
            "topic": topic_code,
            "problem_type": problem_type_code,
            "concept": concept_code,
            "prerequisite_concept": prerequisite_concept_code,
        }
        normalized = {
            name: value.strip().upper()
            for name, value in selectors.items()
            if value is not None
        }
        if not normalized:
            return None
        if profile != SyntheticProfile.SPECIFIC_GAP:
            raise SyntheticGenerationError(
                "SYNTHETIC_GAP_PROFILE_REQUIRED",
                "A targeted gap requires --profile SPECIFIC_GAP.",
            )
        matches = set(item.key for item in targets)
        attributes = {
            "subject": "subject_code",
            "chapter": "chapter_code",
            "topic": "topic_code",
            "problem_type": "problem_type_code",
            "concept": "concept_code",
        }
        for selector, attribute in attributes.items():
            value = normalized.get(selector)
            if value is not None:
                matches &= {
                    item.key for item in targets if getattr(item, attribute) == value
                }
        prerequisite = normalized.get("prerequisite_concept")
        if prerequisite is not None:
            affected = self._prerequisite_affected_concepts(
                prerequisite, normalized.get("subject")
            )
            matches &= {
                item.key
                for item in targets
                if (item.subject_code, item.concept_code) in affected
            }
        if not matches:
            description = ", ".join(
                f"{name}={value}" for name, value in sorted(normalized.items())
            )
            raise SyntheticGenerationError(
                "SYNTHETIC_GAP_TARGET_NOT_FOUND",
                f"Synthetic gap target was not found: {description}.",
            )
        return matches

    def _prerequisite_affected_concepts(
        self, concept_code: str, subject_code: str | None
    ) -> set[tuple[str | None, str]]:
        statement = (
            select(Concept, Subject.code)
            .join(Subject, Subject.id == Concept.subject_id)
            .where(Concept.code == concept_code)
        )
        if subject_code is not None:
            statement = statement.where(Subject.code == subject_code)
        roots = list(self.session.execute(statement.order_by(Subject.code, Concept.id)))
        if not roots:
            return set()
        graph = ConceptGraphService(self.session)
        affected_concepts: dict[UUID, Concept] = {}
        for root, _ in roots:
            affected_concepts[root.id] = root
            for dependent in graph.get_descendants(
                root.id, relation_type=RelationType.PREREQUISITE
            ):
                affected_concepts[dependent.id] = dependent
        subject_codes = dict(self.session.execute(
            select(Subject.id, Subject.code).where(
                Subject.id.in_({item.subject_id for item in affected_concepts.values()})
            )
        ).all())
        return {
            (subject_codes[item.subject_id], item.code)
            for item in affected_concepts.values()
        }

    def _enroll(self, student: StudentProfile, classroom: Classroom) -> None:
        enrollment = self.session.get(StudentEnrollment, (student.id, classroom.id))
        if enrollment is None:
            self.session.add(
                StudentEnrollment(
                    student_id=student.id,
                    classroom_id=classroom.id,
                    status=EnrollmentStatus.ACTIVE,
                )
            )
            self.summary.enrollments_created += 1
        else:
            enrollment.status = EnrollmentStatus.ACTIVE
