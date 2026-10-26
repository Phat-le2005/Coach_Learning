from collections import Counter
from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.assignments.models import (
    Assignment,
    AssignmentConcept,
    AssignmentLearningObjective,
    AssignmentMaterialItem,
    AssignmentProblemType,
    AssignmentQuestion,
    AssignmentStatus,
    AssignmentStudentQuestion,
    AssignmentType,
    StudentAssignmentMaterialItem,
    StudentAssignment,
    StudentAssignmentStatus,
)
from app.assignments.schemas import (
    AnswerSubmitItem,
    AssignmentConceptRead,
    AssignmentCreate,
    AssignmentLearningObjectiveRead,
    AssignmentMaterialItemRead,
    AssignmentProblemTypeRead,
    AssignmentQuestionOptionRead,
    AssignmentQuestionRead,
    AssignmentRead,
    AssignmentSubmissionRequest,
    AssignmentSubmissionResultRead,
    MaterialItemGradeRequest,
    MaterialItemGradeRead,
    AssignmentSummaryRead,
    AssignmentUpdate,
    QuestionResultItem,
    StudentAssignmentRead,
    StudentQuestionItemRead,
    StudentQuestionOptionRead,
    StudentRosterStatusItem,
    TeacherAssignmentRosterRead,
)
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import LearningOutcome, ProblemType
from app.mastery.models import StudentProblemTypeMastery
from app.mastery.evidence import WeightedConceptEvidence, WeightedProblemTypeEvidence
from app.learning_evidence.models import LearningEvidenceEvent, LearningEvidenceSourceKind
from app.learning_evidence.publisher import LearningEvidencePayload, LearningEvidencePublisher
from app.practice.evaluation import AnswerEvaluation, AnswerEvaluationService
from app.practice.models import EvaluationStatus
from app.questions.eligibility import standalone_question_only
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.planning.models import TeachingPlan
from app.teacher_materials.models import MaterialItemExtractionStatus, MaterialMappingStatus, TeacherMaterialItem, TeacherMaterialStatus
from app.assignments.material_snapshot import snapshot_material_item
from app.assignments.scoring import recalculate_student_assignment_score
from app.assignments.teacher_grading_schemas import (
    CanonicalQuestionGradeRead, CanonicalQuestionGradeRequest,
)
from app.users.models import User

logger = logging.getLogger(__name__)


class AssignmentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.evaluator = AnswerEvaluationService()
        self.evidence_publisher = LearningEvidencePublisher()

    # -------------------------------------------------------------------------
    # Teacher Operations
    # -------------------------------------------------------------------------

    def create_assignment(self, teacher_user_id: UUID, data: AssignmentCreate) -> AssignmentRead:
        teacher = self._teacher_for_user(teacher_user_id)
        self._require_teacher_in_classroom(teacher.id, data.classroom_id)

        subject = self.session.get(Subject, data.subject_id)
        if subject is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        if data.teaching_plan_id is not None:
            plan = self.session.get(TeachingPlan, data.teaching_plan_id)
            if plan is None:
                raise ApplicationError(404, "TEACHING_PLAN_NOT_FOUND", "Teaching plan was not found.")
            if plan.classroom_id != data.classroom_id or plan.subject_id != data.subject_id:
                raise ApplicationError(422, "TEACHING_PLAN_SCOPE_MISMATCH", "Teaching plan must match assignment classroom and subject.")
        material_ids = list(dict.fromkeys(data.teacher_material_item_ids or []))
        if material_ids and data.assignment_type != AssignmentType.SAME_SET:
            raise ApplicationError(422, "MATERIAL_ITEMS_REQUIRE_SAME_SET", "Teacher material items are allowed only in SAME_SET assignments.")
        material_items = list(self.session.scalars(select(TeacherMaterialItem).options(selectinload(TeacherMaterialItem.material), selectinload(TeacherMaterialItem.problem_type_mappings), selectinload(TeacherMaterialItem.concept_mappings)).where(TeacherMaterialItem.id.in_(material_ids)))) if material_ids else []
        if {x.id for x in material_items} != set(material_ids):
            raise ApplicationError(404, "MATERIAL_ITEM_NOT_FOUND", "One or more teacher material items were not found.")
        for item in material_items:
            if item.material.classroom_id != data.classroom_id or item.material.subject_id != data.subject_id:
                raise ApplicationError(422, "MATERIAL_ITEM_SCOPE_MISMATCH", "Material item must match assignment classroom and subject.")
            if (
                item.extraction_status != MaterialItemExtractionStatus.READY
                or item.material.status != TeacherMaterialStatus.READY
            ):
                raise ApplicationError(422, "MATERIAL_ITEM_NOT_READY", "Material item must be READY.")
            if not any(x.status == MaterialMappingStatus.CONFIRMED for x in item.problem_type_mappings) or not any(x.status == MaterialMappingStatus.CONFIRMED for x in item.concept_mappings):
                raise ApplicationError(422, "MATERIAL_ITEM_MAPPING_REQUIRED", "Material item requires confirmed mappings.")

        # Validate target problem types
        for pt_item in data.target_problem_types:
            pt = self.session.get(ProblemType, pt_item.problem_type_id)
            if pt is None:
                raise ApplicationError(
                    404, "PROBLEM_TYPE_NOT_FOUND", f"Problem type {pt_item.problem_type_id} was not found."
                )

        # Validate target learning outcomes
        for lo_item in data.learning_outcomes:
            lo = self.session.get(LearningOutcome, lo_item.learning_outcome_id)
            if lo is None:
                raise ApplicationError(
                    404, "LEARNING_OUTCOME_NOT_FOUND", f"Learning outcome {lo_item.learning_outcome_id} was not found."
                )

        # Validate target concepts
        for c_item in data.target_concepts:
            c = self.session.get(Concept, c_item.concept_id)
            if c is None:
                raise ApplicationError(
                    404, "CONCEPT_NOT_FOUND", f"Concept {c_item.concept_id} was not found."
                )

        now = datetime.now(timezone.utc)
        start_at = data.start_at or now

        assignment = Assignment(
            classroom_id=data.classroom_id,
            subject_id=data.subject_id,
            teaching_plan_id=data.teaching_plan_id,
            title=data.title,
            description=data.description,
            assignment_type=data.assignment_type,
            status=AssignmentStatus.DRAFT,
            question_count=data.question_count,
            difficulty_distribution=data.difficulty_distribution,
            start_at=start_at,
            due_at=data.due_at,
            created_by=teacher_user_id,
        )
        self.session.add(assignment)
        self.session.flush()
        for idx, item in enumerate(material_items):
            self.session.add(AssignmentMaterialItem(assignment_id=assignment.id, teacher_material_item_id=item.id, order_index=idx))

        # Link learning outcomes
        for lo_item in data.learning_outcomes:
            self.session.add(
                AssignmentLearningObjective(
                    assignment_id=assignment.id,
                    learning_outcome_id=lo_item.learning_outcome_id,
                    weight=lo_item.weight,
                )
            )

        # Link problem types
        for pt_item in data.target_problem_types:
            self.session.add(
                AssignmentProblemType(
                    assignment_id=assignment.id,
                    problem_type_id=pt_item.problem_type_id,
                    weight=pt_item.weight,
                )
            )

        # Link concepts
        for c_item in data.target_concepts:
            self.session.add(
                AssignmentConcept(
                    assignment_id=assignment.id,
                    concept_id=c_item.concept_id,
                    weight=c_item.weight,
                )
            )

        # If SAME_SET: select or assign fixed questions
        if data.assignment_type == AssignmentType.SAME_SET:
            if data.question_ids:
                # Validate provided questions
                for idx, qid in enumerate(data.question_ids):
                    question = self.session.scalar(
                        select(Question).where(
                            Question.id == qid,
                            standalone_question_only(),
                        )
                    )
                    if question is None:
                        if self.session.get(Question, qid) is not None:
                            raise ApplicationError(
                                422,
                                "QUESTION_NOT_ELIGIBLE",
                                f"Question {qid} is an internal QuestionGroup child.",
                            )
                        raise ApplicationError(404, "QUESTION_NOT_FOUND", f"Question {qid} not found.")
                    if question.status != QuestionStatus.APPROVED:
                        raise ApplicationError(
                            422,
                            "QUESTION_NOT_APPROVED",
                            f"Question {qid} is not approved. Only APPROVED questions are allowed.",
                        )
                    if question.subject_id != data.subject_id:
                        raise ApplicationError(
                            422,
                            "QUESTION_SUBJECT_MISMATCH",
                            f"Question {qid} does not belong to subject {data.subject_id}.",
                        )
                    self.session.add(
                        AssignmentQuestion(
                            assignment_id=assignment.id,
                            question_id=qid,
                            order_index=idx,
                        )
                    )
            elif not material_items:
                # Automatically pick approved questions matching targets
                selected_questions = self._query_approved_candidate_questions(
                    subject_id=data.subject_id,
                    target_pt_ids=[pt.problem_type_id for pt in data.target_problem_types],
                    target_lo_ids=[lo.learning_outcome_id for lo in data.learning_outcomes],
                    limit=data.question_count,
                )
                for idx, q in enumerate(selected_questions):
                    self.session.add(
                        AssignmentQuestion(
                            assignment_id=assignment.id,
                            question_id=q.id,
                            order_index=idx,
                        )
                    )
        if data.question_ids or material_items:
            assignment.question_count = len(data.question_ids or []) + len(material_items)

        self.session.commit()
        logger.info("Created assignment %s (type=%s)", assignment.id, assignment.assignment_type)
        return self.get_for_teacher(teacher_user_id, assignment.id)

    def list_for_classroom(
        self, teacher_user_id: UUID, classroom_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[AssignmentSummaryRead]:
        teacher = self._teacher_for_user(teacher_user_id)
        self._require_teacher_in_classroom(teacher.id, classroom_id)

        assignments = self.session.scalars(
            select(Assignment)
            .where(Assignment.classroom_id == classroom_id)
            .order_by(Assignment.created_at.desc(), Assignment.id)
            .offset(offset)
            .limit(limit)
        ).all()

        return [
            AssignmentSummaryRead(
                id=a.id,
                classroom_id=a.classroom_id,
                subject_id=a.subject_id,
                teaching_plan_id=a.teaching_plan_id,
                title=a.title,
                description=a.description,
                assignment_type=a.assignment_type,
                status=a.status,
                question_count=a.question_count,
                start_at=a.start_at,
                due_at=a.due_at,
                created_by=a.created_by,
                created_at=a.created_at,
            )
            for a in assignments
        ]

    def get_for_teacher(self, teacher_user_id: UUID, assignment_id: UUID) -> AssignmentRead:
        teacher = self._teacher_for_user(teacher_user_id)
        assignment = self.session.scalar(
            select(Assignment)
            .options(
                selectinload(Assignment.learning_objectives).selectinload(AssignmentLearningObjective.learning_outcome),
                selectinload(Assignment.problem_types).selectinload(AssignmentProblemType.problem_type),
                selectinload(Assignment.concepts).selectinload(AssignmentConcept.concept),
                selectinload(Assignment.questions).selectinload(AssignmentQuestion.question).selectinload(Question.options),
                selectinload(Assignment.material_items).selectinload(AssignmentMaterialItem.teacher_material_item).selectinload(TeacherMaterialItem.options),
                selectinload(Assignment.material_items).selectinload(AssignmentMaterialItem.options),
                selectinload(Assignment.student_assignments),
            )
            .where(Assignment.id == assignment_id)
        )
        if assignment is None:
            raise ApplicationError(404, "ASSIGNMENT_NOT_FOUND", "Assignment was not found.")
        self._require_teacher_in_classroom(teacher.id, assignment.classroom_id)

        # Build responses
        los = [
            AssignmentLearningObjectiveRead(
                id=lo.id,
                learning_outcome_id=lo.learning_outcome_id,
                weight=lo.weight,
                name=lo.learning_outcome.description if lo.learning_outcome else None,
                description=lo.learning_outcome.description if lo.learning_outcome else None,
                code=lo.learning_outcome.code if lo.learning_outcome else None,
            )
            for lo in assignment.learning_objectives
        ]
        pts = [
            AssignmentProblemTypeRead(
                id=pt.id,
                problem_type_id=pt.problem_type_id,
                weight=pt.weight,
                name=pt.problem_type.name if pt.problem_type else None,
                code=pt.problem_type.code if pt.problem_type else None,
            )
            for pt in assignment.problem_types
        ]
        concepts = [
            AssignmentConceptRead(
                id=c.id,
                concept_id=c.concept_id,
                weight=c.weight,
                name=c.concept.name if c.concept else None,
                code=c.concept.code if c.concept else None,
            )
            for c in assignment.concepts
        ]
        questions = [
            AssignmentQuestionRead(
                id=q.id,
                assignment_id=q.assignment_id,
                question_id=q.question_id,
                order_index=q.order_index,
                content=q.question.content if q.question else None,
                question_type=q.question.question_type.value if q.question else None,
                difficulty=q.question.difficulty if q.question else None,
                correct_answer=q.question.correct_answer if q.question else None,
                explanation=q.question.explanation if q.question else None,
                options=[
                    AssignmentQuestionOptionRead(
                        id=opt.id,
                        label=opt.label,
                        content=opt.content,
                        order_index=opt.order_index,
                    )
                    for opt in (q.question.options if q.question else [])
                ],
            )
            for q in assignment.questions
        ]
        material_items = []
        for link in assignment.material_items:
            source = link.teacher_material_item
            snapshot_ready = link.snapshotted_at is not None
            material_items.append(
                AssignmentMaterialItemRead(
                    id=link.id,
                    assignment_id=link.assignment_id,
                    teacher_material_item_id=link.teacher_material_item_id,
                    assignment_material_item_id=link.id if snapshot_ready else None,
                    source_content_hash=link.source_content_hash,
                    snapshotted_at=link.snapshotted_at,
                    order_index=len(assignment.questions) + link.order_index,
                    content=link.content if snapshot_ready else source.content,
                    question_type=(
                        link.question_type.value if link.question_type else None
                    ) if snapshot_ready else (
                        source.question_type.value if source.question_type else None
                    ),
                    difficulty=link.difficulty if snapshot_ready else source.difficulty,
                    correct_answer=link.correct_answer if snapshot_ready else source.correct_answer,
                    explanation=link.explanation if snapshot_ready else source.explanation,
                    options=[
                        AssignmentQuestionOptionRead(
                            id=option.id,
                            label=option.label,
                            content=option.content,
                            order_index=option.order_index,
                        )
                        for option in (link.options if snapshot_ready else source.options)
                    ],
                )
            )

        total_students = len(assignment.student_assignments)
        submitted_count = sum(
            1 for sa in assignment.student_assignments if sa.status in (StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED)
        )

        return AssignmentRead(
            id=assignment.id,
            classroom_id=assignment.classroom_id,
            subject_id=assignment.subject_id,
            teaching_plan_id=assignment.teaching_plan_id,
            title=assignment.title,
            description=assignment.description,
            assignment_type=assignment.assignment_type,
            status=assignment.status,
            question_count=assignment.question_count,
            difficulty_distribution=assignment.difficulty_distribution,
            start_at=assignment.start_at,
            due_at=assignment.due_at,
            created_by=assignment.created_by,
            created_at=assignment.created_at,
            learning_objectives=los,
            problem_types=pts,
            concepts=concepts,
            questions=questions,
            material_items=material_items,
            total_assigned_students=total_students,
            submitted_count=submitted_count,
        )

    def update_assignment(self, teacher_user_id: UUID, assignment_id: UUID, data: AssignmentUpdate) -> AssignmentRead:
        teacher = self._teacher_for_user(teacher_user_id)
        assignment = self.session.get(Assignment, assignment_id)
        if assignment is None:
            raise ApplicationError(404, "ASSIGNMENT_NOT_FOUND", "Assignment was not found.")
        self._require_teacher_in_classroom(teacher.id, assignment.classroom_id)

        if data.title is not None:
            assignment.title = data.title
        if data.description is not None:
            assignment.description = data.description
        if data.due_at is not None:
            assignment.due_at = data.due_at

        self.session.commit()
        return self.get_for_teacher(teacher_user_id, assignment_id)

    def publish_assignment(self, teacher_user_id: UUID, assignment_id: UUID) -> AssignmentRead:
        teacher = self._teacher_for_user(teacher_user_id)
        assignment = self.session.scalar(
            select(Assignment)
            .options(
                selectinload(Assignment.questions),
                selectinload(Assignment.material_items),
                selectinload(Assignment.problem_types),
                selectinload(Assignment.learning_objectives),
                selectinload(Assignment.concepts),
            )
            .where(Assignment.id == assignment_id)
        )
        if assignment is None:
            raise ApplicationError(404, "ASSIGNMENT_NOT_FOUND", "Assignment was not found.")
        self._require_teacher_in_classroom(teacher.id, assignment.classroom_id)

        if assignment.status != AssignmentStatus.DRAFT:
            raise ApplicationError(
                400, "INVALID_STATUS", f"Cannot publish assignment with status {assignment.status}."
            )

        # Ensure SAME_SET has questions
        if assignment.assignment_type == AssignmentType.SAME_SET and not assignment.questions and not assignment.material_items:
            selected_questions = self._query_approved_candidate_questions(
                subject_id=assignment.subject_id,
                target_pt_ids=[pt.problem_type_id for pt in assignment.problem_types],
                target_lo_ids=[lo.learning_outcome_id for lo in assignment.learning_objectives],
                limit=assignment.question_count,
            )
            for idx, q in enumerate(selected_questions):
                self.session.add(
                    AssignmentQuestion(
                        assignment_id=assignment.id,
                        question_id=q.id,
                        order_index=idx,
                    )
                )
            self.session.flush()

        for link in assignment.material_items:
            source = self.session.get(TeacherMaterialItem, link.teacher_material_item_id)
            if source is None:
                raise ApplicationError(404, "MATERIAL_ITEM_NOT_FOUND", "Material source was not found.")
            if source.material.classroom_id != assignment.classroom_id or source.material.subject_id != assignment.subject_id:
                raise ApplicationError(422, "MATERIAL_ITEM_SCOPE_MISMATCH", "Material item must match assignment scope.")
            if source.material.status != TeacherMaterialStatus.READY:
                raise ApplicationError(422, "MATERIAL_ITEM_NOT_READY", "Material must be READY at publish.")
            snapshot_material_item(self.session, link, source)

        assignment.status = AssignmentStatus.PUBLISHED

        # Enrolled active students
        enrollments = self.session.scalars(
            select(StudentEnrollment).where(
                StudentEnrollment.classroom_id == assignment.classroom_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        ).all()

        for enrollment in enrollments:
            existing_sa = self.session.scalar(
                select(StudentAssignment).where(
                    StudentAssignment.assignment_id == assignment.id,
                    StudentAssignment.student_id == enrollment.student_id,
                )
            )
            if existing_sa is None:
                sa = StudentAssignment(
                    assignment_id=assignment.id,
                    student_id=enrollment.student_id,
                    status=StudentAssignmentStatus.NOT_STARTED,
                    assigned_at=datetime.now(timezone.utc),
                )
                self.session.add(sa)
                self.session.flush()

                if assignment.assignment_type == AssignmentType.SAME_SET:
                    for idx, q in enumerate(assignment.questions):
                        self.session.add(
                            AssignmentStudentQuestion(
                                student_assignment_id=sa.id,
                                question_id=q.question_id,
                                order_index=idx,
                            )
                        )
                    for item_link in assignment.material_items:
                        self.session.add(
                            StudentAssignmentMaterialItem(
                                student_assignment_id=sa.id,
                                teacher_material_item_id=item_link.teacher_material_item_id,
                                assignment_material_item_id=item_link.id,
                                order_index=len(assignment.questions) + item_link.order_index,
                                evaluation_status=EvaluationStatus.NEEDS_EVALUATION,
                            )
                        )
                elif assignment.assignment_type == AssignmentType.ADAPTIVE_SET:
                    adaptive_questions = self._select_adaptive_questions_for_student(
                        student_id=enrollment.student_id,
                        assignment=assignment,
                    )
                    for idx, q in enumerate(adaptive_questions):
                        self.session.add(
                            AssignmentStudentQuestion(
                                student_assignment_id=sa.id,
                                question_id=q.id,
                                order_index=idx,
                            )
                        )

        self.session.commit()
        logger.info("Published assignment %s to %d students", assignment.id, len(enrollments))
        return self.get_for_teacher(teacher_user_id, assignment_id)

    def close_assignment(self, teacher_user_id: UUID, assignment_id: UUID) -> AssignmentRead:
        teacher = self._teacher_for_user(teacher_user_id)
        assignment = self.session.get(Assignment, assignment_id)
        if assignment is None:
            raise ApplicationError(404, "ASSIGNMENT_NOT_FOUND", "Assignment was not found.")
        self._require_teacher_in_classroom(teacher.id, assignment.classroom_id)

        assignment.status = AssignmentStatus.CLOSED
        self.session.commit()
        return self.get_for_teacher(teacher_user_id, assignment_id)

    def get_assignment_roster(self, teacher_user_id: UUID, assignment_id: UUID) -> TeacherAssignmentRosterRead:
        teacher = self._teacher_for_user(teacher_user_id)
        assignment = self.session.scalar(
            select(Assignment)
            .options(
                selectinload(Assignment.student_assignments)
                .selectinload(StudentAssignment.student)
            )
            .where(Assignment.id == assignment_id)
        )
        if assignment is None:
            raise ApplicationError(404, "ASSIGNMENT_NOT_FOUND", "Assignment was not found.")
        self._require_teacher_in_classroom(teacher.id, assignment.classroom_id)

        user_ids = [sa.student.user_id for sa in assignment.student_assignments if sa.student]
        users = self.session.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
        user_map = {u.id: u.full_name for u in users}

        roster_items = []
        scores = []
        not_started = 0
        in_progress = 0
        submitted = 0
        graded = 0

        for sa in assignment.student_assignments:
            student_name = user_map.get(sa.student.user_id, "Unknown") if sa.student else "Unknown"
            if sa.status == StudentAssignmentStatus.NOT_STARTED:
                not_started += 1
            elif sa.status == StudentAssignmentStatus.IN_PROGRESS:
                in_progress += 1
            elif sa.status == StudentAssignmentStatus.SUBMITTED:
                submitted += 1
            elif sa.status == StudentAssignmentStatus.GRADED:
                graded += 1

            if sa.score is not None:
                scores.append(sa.score)

            roster_items.append(
                StudentRosterStatusItem(
                    student_id=sa.student_id,
                    student_name=student_name,
                    status=sa.status,
                    assigned_at=sa.assigned_at,
                    started_at=sa.started_at,
                    submitted_at=sa.submitted_at,
                    score=sa.score,
                )
            )

        avg_score = round(sum(scores) / len(scores), 2) if scores else None

        return TeacherAssignmentRosterRead(
            assignment_id=assignment.id,
            title=assignment.title,
            total_students=len(assignment.student_assignments),
            not_started_count=not_started,
            in_progress_count=in_progress,
            submitted_count=submitted,
            graded_count=graded,
            average_score=avg_score,
            roster=roster_items,
        )

    # -------------------------------------------------------------------------
    # Student Operations
    # -------------------------------------------------------------------------

    def list_for_student(
        self, student_user_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[StudentAssignmentRead]:
        student = self._student_for_user(student_user_id)
        records = self.session.scalars(
            select(StudentAssignment)
            .options(selectinload(StudentAssignment.assignment))
            .join(Assignment, StudentAssignment.assignment_id == Assignment.id)
            .where(
                StudentAssignment.student_id == student.id,
                Assignment.status != AssignmentStatus.DRAFT,
            )
            .order_by(Assignment.start_at.desc(), StudentAssignment.id)
            .offset(offset)
            .limit(limit)
        ).all()

        results = []
        for sa in records:
            a = sa.assignment
            results.append(
                StudentAssignmentRead(
                    id=sa.id,
                    assignment_id=a.id,
                    classroom_id=a.classroom_id,
                    subject_id=a.subject_id,
                    teaching_plan_id=a.teaching_plan_id,
                    title=a.title,
                    description=a.description,
                    assignment_type=a.assignment_type,
                    status=sa.status,
                    question_count=a.question_count,
                    start_at=a.start_at,
                    due_at=a.due_at,
                    assigned_at=sa.assigned_at,
                    started_at=sa.started_at,
                    submitted_at=sa.submitted_at,
                    score=sa.score,
                    questions=[],
                )
            )
        return results

    def get_student_assignment(self, student_user_id: UUID, assignment_id: UUID) -> StudentAssignmentRead:
        student = self._student_for_user(student_user_id)
        sa = self.session.scalar(
            select(StudentAssignment)
            .options(
                selectinload(StudentAssignment.assignment).selectinload(Assignment.problem_types),
                selectinload(StudentAssignment.assignment).selectinload(Assignment.learning_objectives),
                selectinload(StudentAssignment.student_questions)
                .selectinload(AssignmentStudentQuestion.question)
                .selectinload(Question.options),
                selectinload(StudentAssignment.student_material_items)
                .selectinload(StudentAssignmentMaterialItem.assignment_material_item)
                .selectinload(AssignmentMaterialItem.options),
            )
            .where(
                StudentAssignment.assignment_id == assignment_id,
                StudentAssignment.student_id == student.id,
            )
        )
        if sa is None:
            raise ApplicationError(404, "ASSIGNMENT_NOT_FOUND", "Assignment was not assigned to this student.")

        assignment = sa.assignment
        if assignment.status == AssignmentStatus.DRAFT:
            raise ApplicationError(403, "ASSIGNMENT_NOT_PUBLISHED", "Assignment is not published yet.")

        # If not started, mark in progress
        if sa.status == StudentAssignmentStatus.NOT_STARTED:
            sa.status = StudentAssignmentStatus.IN_PROGRESS
            sa.started_at = datetime.now(timezone.utc)
            self.session.commit()

        # If questions not yet populated, generate them now
        if not sa.student_questions and not sa.student_material_items:
            if assignment.assignment_type == AssignmentType.SAME_SET:
                assign_qs = self.session.scalars(
                    select(AssignmentQuestion)
                    .where(AssignmentQuestion.assignment_id == assignment.id)
                    .order_by(AssignmentQuestion.order_index)
                ).all()
                for idx, aq in enumerate(assign_qs):
                    self.session.add(
                        AssignmentStudentQuestion(
                            student_assignment_id=sa.id,
                            question_id=aq.question_id,
                            order_index=idx,
                        )
                    )
                assign_items = self.session.scalars(select(AssignmentMaterialItem).where(AssignmentMaterialItem.assignment_id == assignment.id).order_by(AssignmentMaterialItem.order_index)).all()
                for link in assign_items:
                    self.session.add(StudentAssignmentMaterialItem(
                        student_assignment_id=sa.id,
                        teacher_material_item_id=link.teacher_material_item_id,
                        assignment_material_item_id=link.id,
                        order_index=len(assign_qs) + link.order_index,
                        evaluation_status=EvaluationStatus.NEEDS_EVALUATION,
                    ))
            elif assignment.assignment_type == AssignmentType.ADAPTIVE_SET:
                adaptive_qs = self._select_adaptive_questions_for_student(student.id, assignment)
                for idx, q in enumerate(adaptive_qs):
                    self.session.add(
                        AssignmentStudentQuestion(
                            student_assignment_id=sa.id,
                            question_id=q.id,
                            order_index=idx,
                        )
                    )
            self.session.commit()
            self.session.refresh(sa)

        is_submitted = sa.status in (StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED)

        question_items = []
        for sq in sa.student_questions:
            q = sq.question
            options = [
                StudentQuestionOptionRead(
                    id=opt.id,
                    label=opt.label,
                    content=opt.content,
                    order_index=opt.order_index,
                )
                for opt in q.options
            ]
            question_items.append(
                StudentQuestionItemRead(
                    question_id=q.id,
                    order_index=sq.order_index,
                    content=q.content,
                    question_type=q.question_type.value,
                    difficulty=q.difficulty,
                    options=options,
                    student_answer=sq.student_answer,
                    is_correct=sq.is_correct if is_submitted else None,
                    correct_answer=q.correct_answer if is_submitted else None,
                    explanation=q.explanation if is_submitted else None,
                )
            )
        for sm in sa.student_material_items:
            item = sm.assignment_material_item
            if item is None or item.snapshotted_at is None:
                raise ApplicationError(409, "MATERIAL_SNAPSHOT_MISSING", "Published material snapshot is missing.")
            question_items.append(
                StudentQuestionItemRead(
                    source_kind="TEACHER_MATERIAL_ITEM",
                    teacher_material_item_id=item.teacher_material_item_id,
                    assignment_material_item_id=item.id,
                    student_material_item_id=sm.id,
                    order_index=sm.order_index,
                    content=item.content,
                    question_type=item.question_type.value if item.question_type else item.evaluation_mode.value,
                    difficulty=item.difficulty,
                    options=[
                        StudentQuestionOptionRead(
                            id=option.id,
                            label=option.label,
                            content=option.content,
                            order_index=option.order_index,
                        )
                        for option in item.options
                    ],
                    student_answer=sm.student_answer,
                    is_correct=sm.is_correct if is_submitted else None,
                    correct_answer=item.correct_answer if is_submitted else None,
                    explanation=item.explanation if is_submitted else None,
                )
            )
        question_items.sort(key=lambda x: (x.order_index, x.source_kind))

        return StudentAssignmentRead(
            id=sa.id,
            assignment_id=assignment.id,
            classroom_id=assignment.classroom_id,
            subject_id=assignment.subject_id,
            teaching_plan_id=assignment.teaching_plan_id,
            title=assignment.title,
            description=assignment.description,
            assignment_type=assignment.assignment_type,
            status=sa.status,
            question_count=assignment.question_count,
            start_at=assignment.start_at,
            due_at=assignment.due_at,
            assigned_at=sa.assigned_at,
            started_at=sa.started_at,
            submitted_at=sa.submitted_at,
            score=sa.score,
            questions=question_items,
        )

    def submit_assignment(
        self,
        student_user_id: UUID,
        assignment_id: UUID,
        submission: AssignmentSubmissionRequest,
    ) -> AssignmentSubmissionResultRead:
        student = self._student_for_user(student_user_id)
        sa = self.session.scalar(
            select(StudentAssignment)
            .options(
                selectinload(StudentAssignment.assignment),
                selectinload(StudentAssignment.student_questions).selectinload(AssignmentStudentQuestion.question).selectinload(Question.options),
                selectinload(StudentAssignment.student_questions).selectinload(AssignmentStudentQuestion.question).selectinload(Question.concept_links),
                selectinload(StudentAssignment.student_questions).selectinload(AssignmentStudentQuestion.question).selectinload(Question.problem_type_links),
                selectinload(StudentAssignment.student_material_items).selectinload(StudentAssignmentMaterialItem.assignment_material_item).selectinload(AssignmentMaterialItem.options),
                selectinload(StudentAssignment.student_material_items).selectinload(StudentAssignmentMaterialItem.assignment_material_item).selectinload(AssignmentMaterialItem.concept_mappings),
                selectinload(StudentAssignment.student_material_items).selectinload(StudentAssignmentMaterialItem.assignment_material_item).selectinload(AssignmentMaterialItem.problem_type_mappings),
                selectinload(StudentAssignment.student_material_items).selectinload(StudentAssignmentMaterialItem.assignment_material_item).selectinload(AssignmentMaterialItem.learning_outcome_mappings),
            )
            .where(
                StudentAssignment.assignment_id == assignment_id,
                StudentAssignment.student_id == student.id,
            )
            .with_for_update()
        )
        if sa is None:
            raise ApplicationError(404, "ASSIGNMENT_NOT_FOUND", "Assignment was not found.")

        if sa.assignment.status == AssignmentStatus.CLOSED:
            raise ApplicationError(400, "ASSIGNMENT_CLOSED", "Assignment is closed and no longer accepts submissions.")

        if sa.status in (StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED):
            raise ApplicationError(409, "ASSIGNMENT_ALREADY_SUBMITTED", "Assignment has already been submitted.")

        from app.math_solutions.models import SolutionAttempt

        submitted_solutions = list(self.session.scalars(
            select(SolutionAttempt).where(
                SolutionAttempt.student_assignment_id == sa.id,
                SolutionAttempt.status == "SUBMITTED",
            )
        ).all())
        submitted_question_items = {
            attempt.assignment_student_question_id
            for attempt in submitted_solutions
            if attempt.source_kind == "CANONICAL"
        }
        submitted_material_items = {
            attempt.student_assignment_material_item_id
            for attempt in submitted_solutions
            if attempt.source_kind == "TEACHER_MATERIAL"
        }
        canonical_answers = {ans.question_id: ans for ans in submission.answers if ans.question_id is not None}
        material_answers = {ans.teacher_material_item_id: ans for ans in submission.answers if ans.teacher_material_item_id is not None}

        results: list[QuestionResultItem] = []
        correct_count = 0
        total_questions = len(sa.student_questions) + len(sa.student_material_items)
        now = datetime.now(timezone.utc)

        for sq in sa.student_questions:
            question = sq.question
            submitted = canonical_answers.get(question.id)
            answer = submitted.student_answer if submitted else ""
            if (
                question.question_type == QuestionType.OPEN_RESPONSE
                and sq.id in submitted_question_items
            ):
                # A second text answer would make the graded submission ambiguous.
                if answer.strip():
                    raise ApplicationError(
                        409, "ASSIGNMENT_ANSWER_SOURCE_CONFLICT",
                        "Submit either the confirmed step solution or a text answer.",
                    )
                evaluation = AnswerEvaluation(None, None, EvaluationStatus.NEEDS_EVALUATION)
            else:
                evaluation = self.evaluator.evaluate(question, answer)
            sq.student_answer = answer
            sq.is_correct = evaluation.is_correct
            sq.score = evaluation.score
            sq.answered_at = now
            if evaluation.is_correct is True:
                correct_count += 1
            results.append(
                QuestionResultItem(
                    question_id=question.id,
                    student_answer=answer,
                    correct_answer=question.correct_answer,
                    is_correct=evaluation.is_correct,
                    score=evaluation.score,
                    explanation=question.explanation,
                )
            )
            from app.math_solutions.models import EvaluationDecision, SolutionAttempt

            has_solution_eval = self.session.scalar(
                select(SolutionAttempt.id)
                .join(EvaluationDecision, EvaluationDecision.attempt_id == SolutionAttempt.id)
                .where(
                    SolutionAttempt.assignment_student_question_id == sq.id,
                    SolutionAttempt.status == "EVALUATED",
                    EvaluationDecision.learning_evidence_event_id.is_not(None),
                )
                .limit(1)
            )
            if not has_solution_eval and evaluation.score is not None and evaluation.is_correct is not None:
                self.evidence_publisher.publish(
                    LearningEvidencePayload(
                        student_id=student.id,
                        subject_id=sa.assignment.subject_id,
                        classroom_id=sa.assignment.classroom_id,
                        teaching_plan_id=sa.assignment.teaching_plan_id,
                        assignment_id=sa.assignment.id,
                        source_kind=LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION,
                        source_entity_id=sq.id,
                        is_correct=evaluation.is_correct,
                        score=evaluation.score,
                        difficulty=question.difficulty,
                        response_time_seconds=submitted.response_time_seconds if submitted else None,
                        hint_count=submitted.hint_count if submitted else 0,
                        evaluation_status=evaluation.status,
                        occurred_at=now,
                        concepts=tuple(
                            WeightedConceptEvidence(mapping.concept_id, mapping.weight)
                            for mapping in question.concept_links
                        ),
                        problem_types=tuple(
                            WeightedProblemTypeEvidence(mapping.problem_type_id, mapping.weight or 1.0)
                            for mapping in question.problem_type_links
                        ),
                        metadata={"question_id": str(question.id)},
                    ),
                    self.session,
                )

        for sm in sa.student_material_items:
            snapshot = sm.assignment_material_item
            if snapshot is None or snapshot.snapshotted_at is None:
                raise ApplicationError(409, "MATERIAL_SNAPSHOT_MISSING", "Published material snapshot is missing.")
            submitted = material_answers.get(snapshot.teacher_material_item_id)
            answer = submitted.student_answer if submitted else ""
            if sm.id in submitted_material_items and answer.strip():
                raise ApplicationError(
                    409, "ASSIGNMENT_ANSWER_SOURCE_CONFLICT",
                    "Submit either the confirmed step solution or a text answer.",
                )
            if snapshot.evaluation_mode.value == "OBJECTIVE_AUTO" and snapshot.question_type is not None:
                evaluation = self.evaluator.evaluate_values(
                    snapshot.question_type,
                    snapshot.correct_answer,
                    answer,
                    option_labels=[option.label for option in snapshot.options],
                )
            else:
                status = (
                    EvaluationStatus.NEEDS_TEACHER_REVIEW
                    if snapshot.evaluation_mode.value == "TEACHER_REVIEW"
                    else EvaluationStatus.NEEDS_EVALUATION
                )
                evaluation = AnswerEvaluation(None, None, status)
            sm.student_answer = answer
            sm.is_correct = evaluation.is_correct
            sm.score = evaluation.score
            sm.response_time_seconds = submitted.response_time_seconds if submitted else None
            sm.hint_count = submitted.hint_count if submitted else 0
            sm.evaluation_status = evaluation.status
            sm.evaluation_details = {
                "evaluation": "deterministic" if evaluation.score is not None else "pending_teacher_review"
            }
            sm.answered_at = now
            if evaluation.is_correct is True:
                correct_count += 1
            results.append(
                QuestionResultItem(
                    source_kind="TEACHER_MATERIAL_ITEM",
                    teacher_material_item_id=snapshot.teacher_material_item_id,
                    student_answer=answer,
                    correct_answer=snapshot.correct_answer,
                    is_correct=evaluation.is_correct,
                    score=evaluation.score,
                    explanation=snapshot.explanation,
                )
            )
            if evaluation.score is not None and evaluation.is_correct is not None:
                self._publish_material_evidence(sa, sm, now, "AUTO")

        sa.status = StudentAssignmentStatus.SUBMITTED
        sa.submitted_at = now
        try:
            self._grade_submitted_solutions(sa, results)
            overall_score = recalculate_student_assignment_score(sa, finalize=False)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        correct_count = sum(item.is_correct is True for item in results)
        logger.info(
            "Student %s submitted assignment %s with score %s (%d/%d correct)",
            student.id,
            assignment_id,
            overall_score,
            correct_count,
            total_questions,
        )
        return AssignmentSubmissionResultRead(
            student_assignment_id=sa.id,
            assignment_id=sa.assignment_id,
            status=sa.status,
            score=overall_score,
            total_questions=total_questions,
            correct_count=correct_count,
            submitted_at=now,
            results=results,
        )

    def _grade_submitted_solutions(
        self,
        assigned: StudentAssignment,
        results: list[QuestionResultItem],
    ) -> None:
        """Score submitted step work in the same transaction as Assignment submit.

        Missing rubrics and unverified mathematics remain pending for teacher review.
        Duplicate solution attempts for one item are never picked arbitrarily.
        """
        from app.math_solutions.evaluator_service import MathEvaluatorService
        from app.math_solutions.models import SolutionAttempt

        attempts = list(self.session.scalars(
            select(SolutionAttempt).where(
                SolutionAttempt.student_assignment_id == assigned.id,
                SolutionAttempt.status == "SUBMITTED",
            ).order_by(SolutionAttempt.id)
        ))
        targets = Counter(
            attempt.assignment_student_question_id or attempt.student_assignment_material_item_id
            for attempt in attempts
        )
        pending_codes = {
            "GRADING_RUBRIC_REQUIRED",
            "GRADING_RUBRIC_UNAVAILABLE",
            "GRADING_RUBRIC_UNSUPPORTED",
            "GRADING_SOURCE_MISMATCH",
            "GRADING_SOURCE_UNAVAILABLE",
            "GRADING_TARGET_UNSUPPORTED",
            "GRADING_REVIEW_REQUIRED",
        }
        evaluator = MathEvaluatorService(self.session)
        for attempt in attempts:
            target_id = (
                attempt.assignment_student_question_id
                or attempt.student_assignment_material_item_id
            )
            if targets[target_id] != 1 or attempt.rubric_id is None:
                continue
            try:
                decision = evaluator.evaluate_attempt(attempt.id, commit=False)
            except ApplicationError as exc:
                if exc.code not in pending_codes:
                    raise
                logger.info(
                    "Assigned math solution remains pending teacher review "
                    "(attempt_id=%s, reason=%s)",
                    attempt.id, exc.code,
                )
                continue

            for result in results:
                if (
                    attempt.source_kind == "CANONICAL"
                    and result.question_id == attempt.question_id
                ) or (
                    attempt.source_kind == "TEACHER_MATERIAL"
                    and result.teacher_material_item_id is not None
                    and any(
                        item.id == attempt.student_assignment_material_item_id
                        and item.teacher_material_item_id == result.teacher_material_item_id
                        for item in assigned.student_material_items
                    )
                ):
                    result.score = decision.final_score
                    result.is_correct = decision.is_correct
                    break

    def grade_canonical_item(
        self,
        teacher_user_id: UUID,
        assignment_id: UUID,
        student_id: UUID,
        student_question_item_id: UUID,
        data: CanonicalQuestionGradeRequest,
    ) -> CanonicalQuestionGradeRead:
        """Teacher resolves a pending assigned open response without a step score."""
        teacher = self._teacher_for_user(teacher_user_id)
        assigned = self.session.scalar(
            select(StudentAssignment)
            .where(
                StudentAssignment.assignment_id == assignment_id,
                StudentAssignment.student_id == student_id,
            )
            .with_for_update()
        )
        if assigned is None:
            raise ApplicationError(404, "STUDENT_ASSIGNMENT_NOT_FOUND", "Student assignment was not found.")
        self._require_teacher_in_classroom(teacher.id, assigned.assignment.classroom_id)
        item = self.session.scalar(
            select(AssignmentStudentQuestion)
            .options(
                selectinload(AssignmentStudentQuestion.question).selectinload(Question.concept_links),
                selectinload(AssignmentStudentQuestion.question).selectinload(Question.problem_type_links),
            )
            .where(
                AssignmentStudentQuestion.id == student_question_item_id,
                AssignmentStudentQuestion.student_assignment_id == assigned.id,
            )
        )
        if item is None:
            raise ApplicationError(404, "ASSIGNMENT_QUESTION_NOT_FOUND", "Assigned question was not found.")
        if item.question.question_type != QuestionType.OPEN_RESPONSE:
            raise ApplicationError(409, "QUESTION_NOT_OPEN_RESPONSE", "Only open responses use teacher review here.")
        if assigned.status != StudentAssignmentStatus.SUBMITTED or item.answered_at is None:
            raise ApplicationError(409, "QUESTION_NOT_PENDING", "The question is not submitted for review.")
        previous = self.session.scalar(
            select(LearningEvidenceEvent.id).where(
                LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION,
                LearningEvidenceEvent.source_entity_id == item.id,
            )
        )
        if item.score is not None or item.is_correct is not None or previous is not None:
            raise ApplicationError(409, "QUESTION_ALREADY_EVALUATED", "The question has already been evaluated.")

        now = datetime.now(timezone.utc)
        item.score = data.score
        item.is_correct = data.is_correct
        question = item.question
        try:
            self.evidence_publisher.publish(
                LearningEvidencePayload(
                    student_id=assigned.student_id,
                    subject_id=assigned.assignment.subject_id,
                    classroom_id=assigned.assignment.classroom_id,
                    teaching_plan_id=assigned.assignment.teaching_plan_id,
                    assignment_id=assigned.assignment_id,
                    source_kind=LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION,
                    source_entity_id=item.id,
                    is_correct=data.is_correct,
                    score=data.score,
                    difficulty=question.difficulty if question.difficulty is not None else 0.5,
                    response_time_seconds=None,
                    hint_count=0,
                    evaluation_status=EvaluationStatus.EVALUATED,
                    occurred_at=now,
                    concepts=tuple(
                        WeightedConceptEvidence(mapping.concept_id, mapping.weight)
                        for mapping in question.concept_links
                    ),
                    problem_types=tuple(
                        WeightedProblemTypeEvidence(
                            mapping.problem_type_id, mapping.weight or 1.0,
                            is_primary=mapping.is_primary,
                        )
                        for mapping in question.problem_type_links
                    ),
                    metadata={
                        "question_id": str(question.id),
                        "grading_source": "TEACHER",
                        "graded_by": str(teacher_user_id),
                        "feedback": data.feedback,
                    },
                ),
                self.session,
            )
            assignment_score = recalculate_student_assignment_score(assigned, finalize=True)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return CanonicalQuestionGradeRead(
            item_id=item.id,
            question_id=question.id,
            score=data.score,
            is_correct=data.is_correct,
            feedback=data.feedback,
            graded_by=teacher_user_id,
            graded_at=now,
            assignment_score=assignment_score,
            assignment_status=assigned.status,
        )

    def grade_material_item(
        self,
        teacher_user_id: UUID,
        assignment_id: UUID,
        student_id: UUID,
        student_material_item_id: UUID,
        data: MaterialItemGradeRequest,
    ) -> MaterialItemGradeRead:
        teacher = self._teacher_for_user(teacher_user_id)
        sa = self.session.scalar(
            select(StudentAssignment)
            .where(
                StudentAssignment.assignment_id == assignment_id,
                StudentAssignment.student_id == student_id,
            )
            .with_for_update()
        )
        if sa is None:
            raise ApplicationError(404, "STUDENT_ASSIGNMENT_NOT_FOUND", "Student assignment was not found.")
        self._require_teacher_in_classroom(teacher.id, sa.assignment.classroom_id)
        sm = self.session.scalar(
            select(StudentAssignmentMaterialItem)
            .options(
                selectinload(StudentAssignmentMaterialItem.assignment_material_item).selectinload(AssignmentMaterialItem.concept_mappings),
                selectinload(StudentAssignmentMaterialItem.assignment_material_item).selectinload(AssignmentMaterialItem.problem_type_mappings),
                selectinload(StudentAssignmentMaterialItem.assignment_material_item).selectinload(AssignmentMaterialItem.learning_outcome_mappings),
            )
            .where(
                StudentAssignmentMaterialItem.id == student_material_item_id,
                StudentAssignmentMaterialItem.student_assignment_id == sa.id,
            )
        )
        if sm is None:
            raise ApplicationError(404, "MATERIAL_SUBMISSION_NOT_FOUND", "Material submission was not found.")
        existing = self.session.scalar(
            select(LearningEvidenceEvent.id).where(
                LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM,
                LearningEvidenceEvent.source_entity_id == sm.id,
            )
        )
        if existing is not None or sm.evaluation_status == EvaluationStatus.EVALUATED:
            raise ApplicationError(409, "MATERIAL_ITEM_ALREADY_EVALUATED", "Material item has already been evaluated.")
        if sa.status != StudentAssignmentStatus.SUBMITTED or sm.answered_at is None:
            raise ApplicationError(409, "MATERIAL_ITEM_NOT_PENDING", "Material item is not pending teacher grading.")
        if sm.evaluation_status not in {
            EvaluationStatus.NEEDS_EVALUATION,
            EvaluationStatus.NEEDS_TEACHER_REVIEW,
        }:
            raise ApplicationError(409, "MATERIAL_ITEM_NOT_PENDING", "Material item is not pending teacher grading.")
        now = datetime.now(timezone.utc)
        sm.score = data.score
        sm.is_correct = data.is_correct
        sm.teacher_feedback = data.feedback
        sm.graded_by = teacher_user_id
        sm.graded_at = now
        sm.evaluation_status = EvaluationStatus.EVALUATED
        sm.evaluation_details = {"evaluation": "teacher"}
        try:
            self._publish_material_evidence(sa, sm, now, "TEACHER")
            assignment_score = recalculate_student_assignment_score(sa, finalize=True)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return MaterialItemGradeRead(
            item_id=sm.id,
            evaluation_status=sm.evaluation_status.value,
            score=sm.score,
            is_correct=sm.is_correct,
            feedback=sm.teacher_feedback,
            graded_at=sm.graded_at,
            graded_by=sm.graded_by,
            assignment_score=assignment_score,
            assignment_status=sa.status,
        )

    def _publish_material_evidence(
        self,
        sa: StudentAssignment,
        sm: StudentAssignmentMaterialItem,
        occurred_at: datetime,
        grading_source: str,
    ) -> None:
        snapshot = sm.assignment_material_item
        if snapshot is None or snapshot.snapshotted_at is None:
            raise ApplicationError(409, "MATERIAL_SNAPSHOT_MISSING", "Published material snapshot is missing.")

        from app.math_solutions.models import EvaluationDecision, SolutionAttempt

        has_solution_eval = self.session.scalar(
            select(SolutionAttempt.id)
            .join(EvaluationDecision, EvaluationDecision.attempt_id == SolutionAttempt.id)
            .where(
                SolutionAttempt.student_assignment_material_item_id == sm.id,
                SolutionAttempt.status == "EVALUATED",
                EvaluationDecision.learning_evidence_event_id.is_not(None),
            )
            .limit(1)
        )
        if has_solution_eval:
            return

        self.evidence_publisher.publish(
            LearningEvidencePayload(
                student_id=sa.student_id,
                subject_id=sa.assignment.subject_id,
                classroom_id=sa.assignment.classroom_id,
                teaching_plan_id=sa.assignment.teaching_plan_id,
                assignment_id=sa.assignment.id,
                source_kind=LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM,
                source_entity_id=sm.id,
                is_correct=sm.is_correct,
                score=sm.score,
                difficulty=snapshot.difficulty if snapshot.difficulty is not None else 0.5,
                response_time_seconds=sm.response_time_seconds,
                hint_count=sm.hint_count,
                evaluation_status=sm.evaluation_status,
                occurred_at=occurred_at,
                concepts=tuple(
                    WeightedConceptEvidence(mapping.concept_id, mapping.weight)
                    for mapping in snapshot.concept_mappings
                ),
                problem_types=tuple(
                    WeightedProblemTypeEvidence(
                        mapping.problem_type_id, mapping.weight, mapping.is_primary
                    )
                    for mapping in snapshot.problem_type_mappings
                ),
                metadata={
                    "assignment_material_item_id": str(snapshot.id),
                    "teacher_material_item_id": str(snapshot.teacher_material_item_id),
                    "teacher_material_id": str(snapshot.teacher_material_id),
                    "original_teacher_material_item_id": str(snapshot.teacher_material_item_id),
                    "original_teacher_material_id": str(snapshot.teacher_material_id),
                    "snapshot_content_hash": snapshot.source_content_hash,
                    "evaluation_mode": snapshot.evaluation_mode.value,
                    "grading_source": grading_source,
                    "learning_outcome_ids": [
                        str(mapping.learning_outcome_id)
                        for mapping in snapshot.learning_outcome_mappings
                    ],
                },
            ),
            self.session,
        )

    # -------------------------------------------------------------------------
    # Recommendation & Adaptive Question Selection
    # -------------------------------------------------------------------------

    def _query_approved_candidate_questions(
        self,
        subject_id: UUID,
        target_pt_ids: list[UUID],
        target_lo_ids: list[UUID],
        limit: int,
    ) -> list[Question]:
        """Query APPROVED questions matching target problem types and learning outcomes."""
        stmt = (
            select(Question)
            .options(
                selectinload(Question.options),
                selectinload(Question.problem_type_links),
                selectinload(Question.learning_outcome_links),
            )
            .where(
                Question.subject_id == subject_id,
                Question.status == QuestionStatus.APPROVED,
                standalone_question_only(),
            )
        )
        if target_pt_ids:
            stmt = stmt.where(
                Question.problem_type_links.any(
                    QuestionProblemType.problem_type_id.in_(target_pt_ids)
                )
            )
        if target_lo_ids:
            stmt = stmt.where(
                Question.learning_outcome_links.any(
                    QuestionLearningOutcome.learning_outcome_id.in_(target_lo_ids)
                )
            )

        stmt = stmt.order_by(Question.difficulty.asc(), Question.id.asc()).limit(limit)
        return list(self.session.scalars(stmt))

    def _select_adaptive_questions_for_student(
        self,
        student_id: UUID,
        assignment: Assignment,
    ) -> list[Question]:
        """Adaptive question selection for a student using Recommendation Engine principles.

        Mỗi học sinh nhận câu hỏi khác nhau nhưng BẮT BUỘC PHẢI CÙNG:
        - Target LearningOutcomes
        - Target ProblemTypes
        - APPROVED questions ONLY
        - Thích ứng theo năng lực học sinh (Mastery) và difficulty_distribution.
        """
        target_pt_ids = [pt.problem_type_id for pt in assignment.problem_types]
        target_lo_ids = [lo.learning_outcome_id for lo in assignment.learning_objectives]

        # 1. Query all APPROVED candidate questions meeting targets
        stmt = (
            select(Question)
            .options(
                selectinload(Question.options),
                selectinload(Question.problem_type_links),
                selectinload(Question.learning_outcome_links),
                selectinload(Question.concept_links),
            )
            .where(
                Question.subject_id == assignment.subject_id,
                Question.status == QuestionStatus.APPROVED,
                standalone_question_only(),
            )
        )
        if target_pt_ids:
            stmt = stmt.where(
                Question.problem_type_links.any(
                    QuestionProblemType.problem_type_id.in_(target_pt_ids)
                )
            )
        if target_lo_ids:
            stmt = stmt.where(
                Question.learning_outcome_links.any(
                    QuestionLearningOutcome.learning_outcome_id.in_(target_lo_ids)
                )
            )

        candidates = list(self.session.scalars(stmt))
        if not candidates:
            # Fallback to any approved questions in the subject matching problem types
            fallback_stmt = (
                select(Question)
                .options(selectinload(Question.options))
                .where(
                    Question.subject_id == assignment.subject_id,
                    Question.status == QuestionStatus.APPROVED,
                    standalone_question_only(),
                )
                .limit(assignment.question_count)
            )
            return list(self.session.scalars(fallback_stmt))

        # 2. Get student's current mastery in target problem types
        mastery_map: dict[UUID, float] = {}
        if target_pt_ids:
            mastery_rows = self.session.scalars(
                select(StudentProblemTypeMastery).where(
                    StudentProblemTypeMastery.student_id == student_id,
                    StudentProblemTypeMastery.problem_type_id.in_(target_pt_ids),
                )
            ).all()
            for m in mastery_rows:
                mastery_map[m.problem_type_id] = m.mastery_score

        # Average mastery of the student across target problem types
        if mastery_map:
            avg_mastery = sum(mastery_map.values()) / len(mastery_map)
        else:
            avg_mastery = 0.5  # Neutral default for unassessed students

        # 3. Determine target difficulty
        # Student with low mastery gets easier questions (ZPD scaffold)
        # Student with high mastery gets harder questions
        if avg_mastery < 0.4:
            student_target_difficulty = 0.35
        elif avg_mastery >= 0.7:
            student_target_difficulty = 0.75
        else:
            student_target_difficulty = 0.55

        # If teacher configured difficulty distribution, e.g. {"easy": 0.4, "medium": 0.4, "hard": 0.2}
        dist = assignment.difficulty_distribution or {}
        if dist:
            # Bucket candidates
            easy_pool = [q for q in candidates if q.difficulty < 0.4]
            med_pool = [q for q in candidates if 0.4 <= q.difficulty < 0.7]
            hard_pool = [q for q in candidates if q.difficulty >= 0.7]

            total_needed = assignment.question_count
            easy_needed = int(round(dist.get("easy", 0.33) * total_needed))
            hard_needed = int(round(dist.get("hard", 0.33) * total_needed))
            med_needed = max(0, total_needed - easy_needed - hard_needed)

            # Sort pools by fit to student mastery
            def _score_q(q: Question) -> float:
                return -abs(q.difficulty - student_target_difficulty)

            easy_pool.sort(key=_score_q, reverse=True)
            med_pool.sort(key=_score_q, reverse=True)
            hard_pool.sort(key=_score_q, reverse=True)

            chosen: list[Question] = []
            chosen.extend(easy_pool[:easy_needed])
            chosen.extend(med_pool[:med_needed])
            chosen.extend(hard_pool[:hard_needed])

            # If not enough, fill from remaining
            if len(chosen) < total_needed:
                chosen_ids = {q.id for q in chosen}
                remaining = [q for q in candidates if q.id not in chosen_ids]
                remaining.sort(key=_score_q, reverse=True)
                chosen.extend(remaining[: total_needed - len(chosen)])

            return chosen[:total_needed]

        # Standard adaptive scoring based on mastery proximity and coverage
        def score_candidate(q: Question) -> tuple[float, float]:
            # Distance from student's target difficulty
            diff_score = 1.0 - abs(q.difficulty - student_target_difficulty)
            # Preference to reinforce lower-mastery problem types
            pt_bonus = 0.0
            for pt_link in q.problem_type_links:
                pt_m = mastery_map.get(pt_link.problem_type_id, 0.5)
                pt_bonus = max(pt_bonus, 1.0 - pt_m)
            total_score = diff_score + 0.3 * pt_bonus
            # Secondary tie-breaker: question id
            return (total_score, -q.difficulty)

        candidates.sort(key=score_candidate, reverse=True)
        return candidates[: assignment.question_count]

    # -------------------------------------------------------------------------
    # Helper / Permission Methods
    # -------------------------------------------------------------------------

    def _teacher_for_user(self, user_id: UUID) -> TeacherProfile:
        teacher = self.session.scalar(
            select(TeacherProfile).where(TeacherProfile.user_id == user_id)
        )
        if teacher is None:
            raise ApplicationError(403, "TEACHER_PROFILE_REQUIRED", "Teacher profile required.")
        return teacher

    def _student_for_user(self, user_id: UUID) -> StudentProfile:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if student is None:
            raise ApplicationError(403, "STUDENT_PROFILE_REQUIRED", "Student profile required.")
        return student

    def _require_teacher_in_classroom(self, teacher_id: UUID, classroom_id: UUID) -> Classroom:
        classroom = self.session.get(Classroom, classroom_id)
        if classroom is None:
            raise ApplicationError(404, "CLASSROOM_NOT_FOUND", "Classroom was not found.")

        assigned = self.session.scalar(
            select(TeacherClassroom).where(
                TeacherClassroom.teacher_id == teacher_id,
                TeacherClassroom.classroom_id == classroom_id,
            )
        )
        if assigned is None:
            raise ApplicationError(
                403, "NOT_ASSIGNED_TO_CLASSROOM", "User is not assigned to this classroom."
            )
        return classroom
