import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.models import AuthSession
from app.auth.security import hash_password
from app.classes.models import Classroom, StudentEnrollment, TeacherClassroom
from app.core.config import Settings
from app.curriculum.import_service import CurriculumImportService
from app.parents.models import ParentProfile, ParentStudentRelationship
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from data.fixtures import CLASSROOMS, PARENT_LINKS
from data.curriculum import DEFAULT_CURRICULUM_DATASET
from data.seed.demo_users import USERS
from data.seed.identifiers import stable_id
from data.seed.records import UserSeed

logger = logging.getLogger(__name__)

RESET_CONFIRMATION = "RESET-DEVELOPMENT-SEED"


class SeedOperationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class SeedSummary:
    counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def mark(self, entity: str, state: str, amount: int = 1) -> None:
        states = self.counts.setdefault(entity, {})
        states[state] = states.get(state, 0) + amount

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {entity: dict(sorted(states.items())) for entity, states in sorted(self.counts.items())}


class SeedService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.summary = SeedSummary()

    def seed(self) -> SeedSummary:
        self._validate_environment()
        self._lock()
        try:
            self._seed_all()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info("Development seed completed")
        return self.summary

    def reset(self, confirmation: str) -> SeedSummary:
        if self.settings.app_env == "production":
            raise SeedOperationError("SEED_RESET_FORBIDDEN", "Seed reset is forbidden in production.")
        if confirmation != RESET_CONFIRMATION:
            raise SeedOperationError(
                "SEED_RESET_CONFIRMATION_REQUIRED",
                f"Reset requires --confirm {RESET_CONFIRMATION}.",
            )
        self._validate_environment()
        self._lock()
        try:
            self._delete_seed_records()
            self.session.flush()
            self._seed_all()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info("Development seed reset completed")
        return self.summary

    def _validate_environment(self) -> None:
        if self.settings.app_env == "production":
            raise SeedOperationError(
                "DEMO_SEED_FORBIDDEN", "Demo seed data cannot be applied in production."
            )
        password = self.settings.seed_demo_password.get_secret_value()
        if len(password) < 12:
            raise SeedOperationError(
                "SEED_PASSWORD_REQUIRED",
                "Set SEED_DEMO_PASSWORD to at least 12 characters before running the seed command.",
            )

    def _lock(self) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext("edums:data-seed"))))

    def _seed_all(self) -> None:
        curriculum = CurriculumImportService(self.session).import_dataset(
            DEFAULT_CURRICULUM_DATASET, commit=False
        )
        for state in ("created", "updated", "unchanged"):
            for entity, amount in getattr(curriculum, state).items():
                self.summary.mark(entity, state, amount)
        identities = {record.code: self._seed_user(record) for record in USERS}
        self._seed_parent_links(identities)
        self._seed_classrooms(identities)

    def _seed_user(self, record: UserSeed) -> tuple[User, StudentProfile | TeacherProfile | ParentProfile | None]:
        user_id = stable_id("user", record.code)
        existing = self.session.get(User, user_id)
        collision = self.session.scalar(select(User).where(User.email == record.email))
        if collision is not None and collision.id != user_id:
            raise self._conflict("user email", record.email)
        if existing is not None and (existing.email != record.email or existing.role != record.role):
            raise self._conflict("user identity", record.code)
        if existing is None:
            existing = User(
                id=user_id,
                email=record.email,
                password_hash=hash_password(self.settings.seed_demo_password.get_secret_value()),
                full_name=record.full_name,
                role=record.role,
                is_active=True,
            )
            self.session.add(existing)
            self.summary.mark("users", "created")
        else:
            self._reconcile("users", existing, {"full_name": record.full_name, "is_active": True})
        self.session.flush()
        profile = self._seed_profile(existing, record)
        self.session.flush()
        return existing, profile

    def _seed_profile(
        self, user: User, record: UserSeed
    ) -> StudentProfile | TeacherProfile | ParentProfile | None:
        definitions: dict[Role, tuple[type, dict[str, object]]] = {
            Role.STUDENT: (StudentProfile, {"grade_level": 12}),
            Role.TEACHER: (TeacherProfile, {"specialization": "Mathematics"}),
            Role.PARENT: (ParentProfile, {}),
        }
        definition = definitions.get(record.role)
        if definition is None:
            return None
        model, extra = definition
        profile_id = stable_id("profile", record.code)
        by_id = self.session.get(model, profile_id)
        by_user = self.session.scalar(select(model).where(model.user_id == user.id))
        if by_id is not None and by_id.user_id != user.id:
            raise self._conflict("profile identity", record.code)
        if by_user is not None and by_user.id != profile_id:
            raise self._conflict("profile user", record.code)
        profile = by_id or by_user
        entity = f"{record.role.value.lower()}_profiles"
        values = {"user_id": user.id, **extra}
        if profile is None:
            profile = model(id=profile_id, **values)
            self.session.add(profile)
            self.summary.mark(entity, "created")
        else:
            self._reconcile(entity, profile, values)
        return profile

    def _seed_parent_links(
        self, identities: dict[str, tuple[User, StudentProfile | TeacherProfile | ParentProfile | None]]
    ) -> None:
        for fixture in PARENT_LINKS:
            parent = identities[fixture.parent_code][1]
            student = identities[fixture.student_code][1]
            if not isinstance(parent, ParentProfile) or not isinstance(student, StudentProfile):
                raise SeedOperationError("SEED_DATA_INVALID", "Parent fixture references an invalid profile.")
            existing = self.session.get(ParentStudentRelationship, (parent.id, student.id))
            values = {"relationship_type": fixture.relationship_type, "is_active": True}
            if existing is None:
                self.session.add(ParentStudentRelationship(parent_id=parent.id, student_id=student.id, **values))
                self.summary.mark("parent_student_relationships", "created")
            else:
                self._reconcile("parent_student_relationships", existing, values)
            self.session.flush()

    def _seed_classrooms(
        self, identities: dict[str, tuple[User, StudentProfile | TeacherProfile | ParentProfile | None]]
    ) -> None:
        for fixture in CLASSROOMS:
            teacher_user, teacher_profile = identities[fixture.teacher_code]
            if not isinstance(teacher_profile, TeacherProfile):
                raise SeedOperationError("SEED_DATA_INVALID", "Classroom fixture references an invalid teacher.")
            classroom_id = stable_id("classroom", fixture.code)
            classroom = self.session.get(Classroom, classroom_id)
            values = {
                "name": fixture.name,
                "academic_year": fixture.academic_year,
                "grade_level": fixture.grade_level,
                "created_by": teacher_user.id,
            }
            if classroom is None:
                classroom = Classroom(id=classroom_id, **values)
                self.session.add(classroom)
                self.summary.mark("classrooms", "created")
            else:
                self._reconcile("classrooms", classroom, values)
            self.session.flush()
            assignment = self.session.get(TeacherClassroom, (teacher_profile.id, classroom.id))
            if assignment is None:
                self.session.add(TeacherClassroom(
                    teacher_id=teacher_profile.id, classroom_id=classroom.id, role="OWNER"
                ))
                self.summary.mark("teacher_classrooms", "created")
            else:
                self._reconcile("teacher_classrooms", assignment, {"role": "OWNER"})
            self.session.flush()
            for student_code, status in fixture.enrollments:
                student = identities[student_code][1]
                if not isinstance(student, StudentProfile):
                    raise SeedOperationError("SEED_DATA_INVALID", "Classroom fixture references an invalid student.")
                enrollment = self.session.get(StudentEnrollment, (student.id, classroom.id))
                if enrollment is None:
                    self.session.add(StudentEnrollment(
                        student_id=student.id, classroom_id=classroom.id, status=status
                    ))
                    self.summary.mark("student_enrollments", "created")
                else:
                    self._reconcile("student_enrollments", enrollment, {"status": status})
                self.session.flush()

    def _delete_seed_records(self) -> None:
        classroom_ids = [stable_id("classroom", fixture.code) for fixture in CLASSROOMS]
        user_ids = [stable_id("user", record.code) for record in USERS]
        operations = (
            ("student_enrollments", delete(StudentEnrollment).where(StudentEnrollment.classroom_id.in_(classroom_ids))),
            ("teacher_classrooms", delete(TeacherClassroom).where(TeacherClassroom.classroom_id.in_(classroom_ids))),
            ("classrooms", delete(Classroom).where(Classroom.id.in_(classroom_ids))),
            ("parent_student_relationships", delete(ParentStudentRelationship).where(
                ParentStudentRelationship.parent_id.in_([stable_id("profile", record.code) for record in USERS if record.role == Role.PARENT])
            )),
            ("auth_sessions", delete(AuthSession).where(AuthSession.user_id.in_(user_ids))),
            ("users", delete(User).where(User.id.in_(user_ids))),
        )
        for entity, statement in operations:
            result = self.session.execute(statement.execution_options(synchronize_session=False))
            if result.rowcount:
                self.summary.mark(entity, "deleted", result.rowcount)

    def _reconcile(self, entity: str, record: object, values: dict[str, object]) -> None:
        changed = False
        for field_name, value in values.items():
            if getattr(record, field_name) != value:
                setattr(record, field_name, value)
                changed = True
        self.summary.mark(entity, "updated" if changed else "unchanged")

    @staticmethod
    def _conflict(entity: str, key: str) -> SeedOperationError:
        return SeedOperationError(
            "SEED_IDENTITY_CONFLICT",
            f"Existing {entity} conflicts with stable seed key {key}.",
        )
