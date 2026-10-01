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
from app.learning_evidence.models import LearningEvidenceSourceKind
from app.learning_evidence.publisher import LearningEvidencePayload, LearningEvidencePublisher
from app.practice.evaluation import AnswerEvaluationService
from app.practice.models import EvaluationStatus
from app.questions.eligibility import standalone_question_only
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.planning.models import TeachingPlan
from app.teacher_materials.models import MaterialItemExtractionStatus, MaterialMappingStatus, TeacherMaterialItem
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
            if item.extraction_status != MaterialItemExtractionStatus.READY:
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

    def list_for_classroom(self, teacher_user_id: UUID, classroom_id: UUID) -> list[AssignmentSummaryRead]:
        teacher = self._teacher_for_user(teacher_user_id)
        self._require_teacher_in_classroom(teacher.id, classroom_id)

        assignments = self.session.scalars(
            select(Assignment)
            .where(Assignment.classroom_id == classroom_id)
            .order_by(Assignment.created_at.desc(), Assignment.id)
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
        material_items = [
            AssignmentMaterialItemRead(
                id=link.id, assignment_id=link.assignment_id,
                teacher_material_item_id=link.teacher_material_item_id,
                order_index=link.order_index, content=link.teacher_material_item.content,
                question_type=link.teacher_material_item.question_type.value if link.teacher_material_item.question_type else None,
                difficulty=link.teacher_material_item.difficulty,
                correct_answer=link.teacher_material_item.correct_answer,
                explanation=link.teacher_material_item.explanation,
                options=[AssignmentQuestionOptionRead(id=x.id,label=x.label,content=x.content,order_index=x.order_index) for x in link.teacher_material_item.options],
            ) for link in assignment.material_items
        ]

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
                                order_index=item_link.order_index,
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

    def list_for_student(self, student_user_id: UUID) -> list[StudentAssignmentRead]:
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
                .selectinload(StudentAssignmentMaterialItem.teacher_material_item)
                .selectinload(TeacherMaterialItem.options),
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
                    self.session.add(StudentAssignmentMaterialItem(student_assignment_id=sa.id, teacher_material_item_id=link.teacher_material_item_id, order_index=link.order_index, evaluation_status=EvaluationStatus.NEEDS_EVALUATION))
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
            item = sm.teacher_material_item
            question_items.append(StudentQuestionItemRead(
                source_kind="TEACHER_MATERIAL_ITEM", teacher_material_item_id=item.id,
                order_index=sm.order_index, content=item.content,
                question_type=item.question_type.value if item.question_type else item.evaluation_mode.value,
                difficulty=item.difficulty,
                options=[StudentQuestionOptionRead(id=x.id,label=x.label,content=x.content,order_index=x.order_index) for x in item.options],
                student_answer=sm.student_answer,
                is_correct=sm.is_correct if is_submitted else None,
                correct_answer=item.correct_answer if is_submitted else None,
                explanation=item.explanation if is_submitted else None,
            ))
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
                selectinload(StudentAssignment.student_material_items).selectinload(StudentAssignmentMaterialItem.teacher_material_item).selectinload(TeacherMaterialItem.options),
                selectinload(StudentAssignment.student_material_items).selectinload(StudentAssignmentMaterialItem.teacher_material_item).selectinload(TeacherMaterialItem.concept_mappings),
                selectinload(StudentAssignment.student_material_items).selectinload(StudentAssignmentMaterialItem.teacher_material_item).selectinload(TeacherMaterialItem.problem_type_mappings),
            )
            .where(
                StudentAssignment.assignment_id == assignment_id,
                StudentAssignment.student_id == student.id,
            )
        )
        if sa is None:
            raise ApplicationError(404, "ASSIGNMENT_NOT_FOUND", "Assignment was not found.")

        if sa.assignment.status == AssignmentStatus.CLOSED:
            raise ApplicationError(400, "ASSIGNMENT_CLOSED", "Assignment is closed and no longer accepts submissions.")

        if sa.status in (StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED):
            raise ApplicationError(409, "ASSIGNMENT_ALREADY_SUBMITTED", "Assignment has already been submitted.")

        canonical_answers = {ans.question_id: ans for ans in submission.answers if ans.question_id is not None}
        material_answers = {ans.teacher_material_item_id: ans for ans in submission.answers if ans.teacher_material_item_id is not None}

        results: list[QuestionResultItem] = []
        correct_count = 0
        total_questions = len(sa.student_questions) + len(sa.student_material_items)
        scored_count = 0
        score_sum = 0.0

        now = datetime.now(timezone.utc)

        for sq in sa.student_questions:
            q = sq.question
            submitted = canonical_answers.get(q.id)
            user_ans = submitted.student_answer if submitted else ""
            evaluation = self.evaluator.evaluate(q, user_ans)
            is_correct, item_score = evaluation.is_correct, evaluation.score
            if is_correct is True: correct_count += 1
            if item_score is not None: scored_count += 1; score_sum += item_score

            sq.student_answer = user_ans
            sq.is_correct = is_correct
            sq.score = item_score
            sq.answered_at = now

            results.append(
                QuestionResultItem(
                    question_id=q.id,
                    student_answer=user_ans,
                    correct_answer=q.correct_answer,
                    is_correct=is_correct,
                    score=item_score,
                    explanation=q.explanation,
                )
            )
            if item_score is not None and is_correct is not None:
                self.evidence_publisher.publish(LearningEvidencePayload(
                    student_id=student.id, subject_id=sa.assignment.subject_id,
                    classroom_id=sa.assignment.classroom_id, teaching_plan_id=sa.assignment.teaching_plan_id,
                    assignment_id=sa.assignment.id, source_kind=LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION,
                    source_entity_id=sq.id, is_correct=is_correct, score=item_score, difficulty=q.difficulty,
                    response_time_seconds=submitted.response_time_seconds if submitted else None,
                    hint_count=submitted.hint_count if submitted else 0, evaluation_status=evaluation.status, occurred_at=now,
                    concepts=tuple(WeightedConceptEvidence(x.concept_id,x.weight) for x in q.concept_links),
                    problem_types=tuple(WeightedProblemTypeEvidence(x.problem_type_id,x.weight or 1.0) for x in q.problem_type_links),
                    metadata={"question_id":str(q.id)},
                ),self.session)

        for sm in sa.student_material_items:
            item=sm.teacher_material_item; submitted=material_answers.get(item.id); user_ans=submitted.student_answer if submitted else ""
            if item.evaluation_mode.value == "OBJECTIVE_AUTO" and item.question_type is not None:
                evaluation=self.evaluator.evaluate_values(item.question_type,item.correct_answer,user_ans,option_labels=[x.label for x in item.options])
            else:
                from app.practice.evaluation import AnswerEvaluation
                evaluation=AnswerEvaluation(None,None,EvaluationStatus.NEEDS_TEACHER_REVIEW if item.evaluation_mode.value=="TEACHER_REVIEW" else EvaluationStatus.NEEDS_EVALUATION)
            sm.student_answer=user_ans; sm.is_correct=evaluation.is_correct; sm.score=evaluation.score
            sm.response_time_seconds=submitted.response_time_seconds if submitted else None; sm.hint_count=submitted.hint_count if submitted else 0
            sm.evaluation_status=evaluation.status; sm.evaluation_details={"evaluation":"deterministic" if evaluation.score is not None else "pending_teacher_or_ai"}; sm.answered_at=now
            if evaluation.is_correct is True: correct_count+=1
            if evaluation.score is not None: scored_count+=1; score_sum+=evaluation.score
            results.append(QuestionResultItem(source_kind="TEACHER_MATERIAL_ITEM",teacher_material_item_id=item.id,student_answer=user_ans,correct_answer=item.correct_answer,is_correct=evaluation.is_correct,score=evaluation.score,explanation=item.explanation))
            if evaluation.score is not None and evaluation.is_correct is not None:
                concepts=tuple(WeightedConceptEvidence(x.concept_id,x.weight) for x in item.concept_mappings if x.status==MaterialMappingStatus.CONFIRMED)
                pts=tuple(WeightedProblemTypeEvidence(x.problem_type_id,x.weight,x.is_primary) for x in item.problem_type_mappings if x.status==MaterialMappingStatus.CONFIRMED)
                self.evidence_publisher.publish(LearningEvidencePayload(student_id=student.id,subject_id=sa.assignment.subject_id,classroom_id=sa.assignment.classroom_id,teaching_plan_id=sa.assignment.teaching_plan_id,assignment_id=sa.assignment.id,source_kind=LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM,source_entity_id=sm.id,is_correct=evaluation.is_correct,score=evaluation.score,difficulty=item.difficulty if item.difficulty is not None else .5,response_time_seconds=sm.response_time_seconds,hint_count=sm.hint_count,evaluation_status=evaluation.status,occurred_at=now,concepts=concepts,problem_types=pts,metadata={"teacher_material_item_id":str(item.id),"teacher_material_id":str(item.teacher_material_id)}),self.session)

        overall_score = round((score_sum / scored_count) * 10.0, 2) if scored_count > 0 else 0.0

        sa.status = StudentAssignmentStatus.SUBMITTED
        sa.submitted_at = now
        sa.score = overall_score

        self.session.commit()
        logger.info(
            "Student %s submitted assignment %s with score %.2f (%d/%d)",
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
