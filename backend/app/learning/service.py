from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.learning.models import (
    ConceptSignalLevel,
    QuickCheckQuestion,
    QuickCheckQuestionRole,
    QuickCheckSession,
    QuickCheckVerdict,
)
from app.learning.policy import QuickCheckPolicy
from app.learning.schemas import (
    QuickCheckConceptSignal,
    QuickCheckProblemTypeResult,
    QuickCheckQuestionItemRead,
    QuickCheckQuestionOptionRead,
    QuickCheckResultRead,
    QuickCheckStartRead,
    QuickCheckStartRequest,
)
from app.mastery.models import StudentConceptMastery
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.practice.models import (
    PracticeSession,
    PracticeSessionConcept,
    PracticeSessionProblemType,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.practice.schemas import PracticeAnswerCreate, QuestionAttemptRead
from app.practice.service import PracticeService
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import User

logger = logging.getLogger(__name__)


class QuickCheckService:
    def __init__(self, session: Session, policy: QuickCheckPolicy | None = None) -> None:
        self.session = session
        self.policy = policy or QuickCheckPolicy()

    def start_quick_check(
        self, current_user: User, data: QuickCheckStartRequest
    ) -> QuickCheckStartRead:
        student = self._student_for_user(current_user.id)
        self._subject_or_404(data.subject_id)

        plan = self._find_active_teaching_plan(student.id, data.subject_id, data.classroom_id)
        if not plan.items:
            raise ApplicationError(
                422,
                "EMPTY_TEACHING_PLAN",
                "Active teaching plan contains no problem type items.",
            )

        selected_items = self._select_questions(student.id, plan)

        practice_session = PracticeSession(
            student_id=student.id,
            subject_id=data.subject_id,
            session_type=PracticeSessionType.QUICK_CHECK,
            problem_type_links=[
                PracticeSessionProblemType(problem_type_id=item.problem_type_id)
                for item in plan.items
            ],
            concept_links=[
                PracticeSessionConcept(concept_id=c_id)
                for c_id in self._concepts_for_plan(plan)
            ],
        )
        self.session.add(practice_session)
        self.session.flush()

        quick_check = QuickCheckSession(
            id=practice_session.id,
            teaching_plan_id=plan.id,
            classroom_id=plan.classroom_id,
        )
        for order_idx, item in enumerate(selected_items):
            quick_check.questions.append(
                QuickCheckQuestion(
                    question_id=item["question_id"],
                    target_problem_type_id=item.get("target_problem_type_id"),
                    target_concept_id=item.get("target_concept_id"),
                    target_role=item["target_role"],
                    order_index=order_idx,
                )
            )

        self.session.add(quick_check)
        self.session.commit()
        self.session.refresh(quick_check)

        logger.info(
            "Quick check started (session_id=%s, student_id=%s, questions=%d)",
            quick_check.id,
            student.id,
            len(selected_items),
        )
        return self._to_start_read(quick_check, plan, selected_items)

    def answer_question(
        self,
        current_user: User,
        quick_check_id: UUID,
        data: PracticeAnswerCreate,
    ) -> QuestionAttemptRead:
        student = self._student_for_user(current_user.id)
        qc = self.session.get(QuickCheckSession, quick_check_id)
        if qc is None:
            raise ApplicationError(404, "QUICK_CHECK_NOT_FOUND", "Quick check was not found.")

        attempt = PracticeService(self.session).answer(
            current_user,
            quick_check_id,
            data,
            commit=False,
            complete_if_exhausted=False,
        )

        qc_questions = list(
            self.session.scalars(
                select(QuickCheckQuestion.question_id).where(
                    QuickCheckQuestion.quick_check_id == quick_check_id
                )
            )
        )
        attempted_question_ids = set(
            self.session.scalars(
                select(QuestionAttempt.question_id).where(
                    QuestionAttempt.practice_session_id == quick_check_id
                )
            )
        )
        if set(qc_questions).issubset(attempted_question_ids):
            practice_session = self.session.get(PracticeSession, quick_check_id)
            if practice_session:
                practice_session.status = PracticeSessionStatus.COMPLETED
                practice_session.completed_at = datetime.now(timezone.utc)

        self.session.commit()
        self.session.refresh(attempt)
        return QuestionAttemptRead.model_validate(attempt)

    def get_result(self, current_user: User, quick_check_id: UUID) -> QuickCheckResultRead:
        qc = self.session.scalar(
            select(QuickCheckSession)
            .options(
                selectinload(QuickCheckSession.questions),
                selectinload(QuickCheckSession.practice_session),
                selectinload(QuickCheckSession.teaching_plan).selectinload(TeachingPlan.items),
            )
            .where(QuickCheckSession.id == quick_check_id)
        )
        if qc is None:
            raise ApplicationError(404, "QUICK_CHECK_NOT_FOUND", "Quick check was not found.")

        self._authorize_view_result(current_user, qc)

        attempts = list(
            self.session.scalars(
                select(QuestionAttempt)
                .where(QuestionAttempt.practice_session_id == quick_check_id)
                .order_by(QuestionAttempt.created_at)
            )
        )
        attempts_by_qid = {a.question_id: a for a in attempts}

        max_priority = (
            max(item.priority for item in qc.teaching_plan.items)
            if qc.teaching_plan.items
            else 1
        )
        core_pt_ids = {
            item.problem_type_id
            for item in qc.teaching_plan.items
            if item.priority == max_priority
        }

        # Problem Type results
        pt_stats: dict[UUID, dict] = {}
        for item in qc.teaching_plan.items:
            pt = self.session.get(ProblemType, item.problem_type_id)
            pt_stats[item.problem_type_id] = {
                "problem_type_id": item.problem_type_id,
                "problem_type_code": pt.code if pt else None,
                "problem_type_name": pt.name if pt else None,
                "is_core": item.problem_type_id in core_pt_ids,
                "total_questions": 0,
                "correct_questions": 0,
                "earned_score": 0.0,
            }

        # Concept signals
        concept_stats: dict[UUID, dict] = {}

        for qc_q in qc.questions:
            att = attempts_by_qid.get(qc_q.question_id)
            score = att.score if att and att.score is not None else 0.0
            is_correct = att.is_correct if att and att.is_correct is not None else False

            if qc_q.target_problem_type_id and qc_q.target_problem_type_id in pt_stats:
                st = pt_stats[qc_q.target_problem_type_id]
                st["total_questions"] += 1
                if is_correct:
                    st["correct_questions"] += 1
                st["earned_score"] += score

            if qc_q.target_concept_id:
                cid = qc_q.target_concept_id
                if cid not in concept_stats:
                    concept = self.session.get(Concept, cid)
                    concept_stats[cid] = {
                        "concept_id": cid,
                        "concept_code": concept.code if concept else None,
                        "concept_name": concept.name if concept else None,
                        "is_prerequisite": qc_q.target_role == QuickCheckQuestionRole.PREREQUISITE,
                        "total_questions": 0,
                        "correct_questions": 0,
                        "earned_score": 0.0,
                    }
                c_st = concept_stats[cid]
                c_st["total_questions"] += 1
                if is_correct:
                    c_st["correct_questions"] += 1
                c_st["earned_score"] += score

        problem_type_results = []
        for st in pt_stats.values():
            tot = st["total_questions"]
            avg_score = st["earned_score"] / tot if tot > 0 else 0.0
            status = self.policy.evaluate_problem_type(tot, st["correct_questions"], avg_score)
            problem_type_results.append(
                QuickCheckProblemTypeResult(
                    problem_type_id=st["problem_type_id"],
                    problem_type_code=st["problem_type_code"],
                    problem_type_name=st["problem_type_name"],
                    is_core=st["is_core"],
                    total_questions=tot,
                    correct_questions=st["correct_questions"],
                    score=round(avg_score, 4),
                    status=status,
                )
            )

        concept_signals = []
        for st in concept_stats.values():
            tot = st["total_questions"]
            avg_score = st["earned_score"] / tot if tot > 0 else 0.0
            signal = self.policy.evaluate_concept_signal(tot, st["correct_questions"], avg_score)
            concept_signals.append(
                QuickCheckConceptSignal(
                    concept_id=st["concept_id"],
                    concept_code=st["concept_code"],
                    concept_name=st["concept_name"],
                    is_prerequisite=st["is_prerequisite"],
                    total_questions=tot,
                    correct_questions=st["correct_questions"],
                    score=round(avg_score, 4),
                    signal=signal,
                )
            )

        verdict = self.policy.evaluate_verdict(
            [
                {"problem_type_id": r.problem_type_id, "status": r.status}
                for r in problem_type_results
            ],
            core_pt_ids,
        )

        total_questions = len(qc.questions)
        attempted_questions = len(attempts)
        correct_questions = sum(1 for a in attempts if a.is_correct is True)
        overall_score = (
            sum(a.score for a in attempts if a.score is not None) / total_questions
            if total_questions > 0
            else 0.0
        )

        return QuickCheckResultRead(
            id=qc.id,
            teaching_plan_id=qc.teaching_plan_id,
            classroom_id=qc.classroom_id,
            subject_id=qc.practice_session.subject_id,
            status=qc.practice_session.status,
            verdict=verdict,
            score=round(overall_score, 4),
            total_questions=total_questions,
            attempted_questions=attempted_questions,
            correct_questions=correct_questions,
            problem_type_results=problem_type_results,
            concept_signals=concept_signals,
        )

    def _select_questions(
        self, student_id: UUID, plan: TeachingPlan
    ) -> list[dict]:
        target_pt_ids = [item.problem_type_id for item in plan.items]
        target_concept_ids = set(
            self.session.scalars(
                select(ProblemTypeConcept.concept_id).where(
                    ProblemTypeConcept.problem_type_id.in_(target_pt_ids)
                )
            )
        )

        selected: list[dict] = []
        used_qids: set[UUID] = set()

        # Optional Prerequisite Check
        prereq_concept_ids = set(
            self.session.scalars(
                select(ConceptRelation.source_concept_id).where(
                    ConceptRelation.relation_type == RelationType.PREREQUISITE,
                    ConceptRelation.target_concept_id.in_(target_concept_ids),
                )
            )
        )
        weak_prereqs: list[tuple[float, UUID]] = []
        if prereq_concept_ids:
            masteries = {
                m.concept_id: m
                for m in self.session.scalars(
                    select(StudentConceptMastery).where(
                        StudentConceptMastery.student_id == student_id,
                        StudentConceptMastery.concept_id.in_(prereq_concept_ids),
                    )
                )
            }
            for cid in prereq_concept_ids:
                m = masteries.get(cid)
                score = m.mastery_score if m else 0.0
                if score < 0.6:
                    weak_prereqs.append((score, cid))
            weak_prereqs.sort()

        if weak_prereqs:
            prereq_cid = weak_prereqs[0][1]
            prereq_q = self.session.scalar(
                select(Question)
                .join(QuestionConcept, QuestionConcept.question_id == Question.id)
                .where(
                    Question.subject_id == plan.subject_id,
                    Question.status == QuestionStatus.APPROVED,
                    QuestionConcept.concept_id == prereq_cid,
                )
                .order_by(Question.difficulty.asc(), Question.id)
                .limit(1)
            )
            if prereq_q:
                used_qids.add(prereq_q.id)
                selected.append(
                    {
                        "question": prereq_q,
                        "question_id": prereq_q.id,
                        "target_problem_type_id": None,
                        "target_concept_id": prereq_cid,
                        "target_role": QuickCheckQuestionRole.PREREQUISITE,
                    }
                )

        # Coverage: basic understanding & application for active ProblemTypes
        for item in plan.items:
            pt_id = item.problem_type_id
            primary_cid = self.session.scalar(
                select(ProblemTypeConcept.concept_id).where(
                    ProblemTypeConcept.problem_type_id == pt_id,
                    ProblemTypeConcept.is_primary.is_(True),
                )
            ) or self.session.scalar(
                select(ProblemTypeConcept.concept_id).where(
                    ProblemTypeConcept.problem_type_id == pt_id
                )
            )

            # Understanding question
            q_und = self.session.scalar(
                select(Question)
                .join(QuestionProblemType, QuestionProblemType.question_id == Question.id)
                .where(
                    Question.subject_id == plan.subject_id,
                    Question.status == QuestionStatus.APPROVED,
                    QuestionProblemType.problem_type_id == pt_id,
                    ~Question.id.in_(used_qids) if used_qids else True,
                    (
                        Question.cognitive_level.in_(
                            [CognitiveLevel.REMEMBER, CognitiveLevel.UNDERSTAND]
                        )
                    )
                    | (Question.difficulty <= 0.45),
                )
                .order_by(Question.difficulty.asc(), Question.id)
                .limit(1)
            )
            if q_und:
                used_qids.add(q_und.id)
                selected.append(
                    {
                        "question": q_und,
                        "question_id": q_und.id,
                        "target_problem_type_id": pt_id,
                        "target_concept_id": primary_cid,
                        "target_role": QuickCheckQuestionRole.UNDERSTANDING,
                    }
                )

            # Application question
            q_app = self.session.scalar(
                select(Question)
                .join(QuestionProblemType, QuestionProblemType.question_id == Question.id)
                .where(
                    Question.subject_id == plan.subject_id,
                    Question.status == QuestionStatus.APPROVED,
                    QuestionProblemType.problem_type_id == pt_id,
                    ~Question.id.in_(used_qids) if used_qids else True,
                    (
                        Question.cognitive_level.in_(
                            [CognitiveLevel.APPLY, CognitiveLevel.ANALYZE]
                        )
                    )
                    | (Question.difficulty >= 0.50),
                )
                .order_by(Question.difficulty.desc(), Question.id)
                .limit(1)
            )
            if q_app:
                used_qids.add(q_app.id)
                selected.append(
                    {
                        "question": q_app,
                        "question_id": q_app.id,
                        "target_problem_type_id": pt_id,
                        "target_concept_id": primary_cid,
                        "target_role": QuickCheckQuestionRole.APPLICATION,
                    }
                )

        # Bounding to 3-7 questions
        # If under 3 questions, backfill with any approved questions of target ProblemTypes
        if len(selected) < self.policy.thresholds.min_questions:
            fallback_qs = list(
                self.session.scalars(
                    select(Question)
                    .join(QuestionProblemType, QuestionProblemType.question_id == Question.id)
                    .where(
                        Question.subject_id == plan.subject_id,
                        Question.status == QuestionStatus.APPROVED,
                        QuestionProblemType.problem_type_id.in_(target_pt_ids),
                        ~Question.id.in_(used_qids) if used_qids else True,
                    )
                    .order_by(Question.difficulty.asc(), Question.id)
                    .limit(self.policy.thresholds.min_questions - len(selected))
                )
            )
            for q in fallback_qs:
                used_qids.add(q.id)
                role = (
                    QuickCheckQuestionRole.UNDERSTANDING
                    if q.difficulty < 0.5
                    else QuickCheckQuestionRole.APPLICATION
                )
                pt_id = self.session.scalar(
                    select(QuestionProblemType.problem_type_id).where(
                        QuestionProblemType.question_id == q.id
                    )
                )
                cid = self.session.scalar(
                    select(QuestionConcept.concept_id).where(QuestionConcept.question_id == q.id)
                )
                selected.append(
                    {
                        "question": q,
                        "question_id": q.id,
                        "target_problem_type_id": pt_id,
                        "target_concept_id": cid,
                        "target_role": role,
                    }
                )

        # Cap at max_questions (7)
        if len(selected) > self.policy.thresholds.max_questions:
            selected = selected[: self.policy.thresholds.max_questions]

        return selected

    def _find_active_teaching_plan(
        self, student_id: UUID, subject_id: UUID, classroom_id: UUID | None
    ) -> TeachingPlan:
        if classroom_id is not None:
            enrollment = self.session.scalar(
                select(StudentEnrollment).where(
                    StudentEnrollment.student_id == student_id,
                    StudentEnrollment.classroom_id == classroom_id,
                    StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                )
            )
            if enrollment is None:
                raise ApplicationError(
                    403,
                    "CLASSROOM_ACCESS_DENIED",
                    "Student is not actively enrolled in this classroom.",
                )
            plan = self.session.scalar(
                select(TeachingPlan)
                .options(selectinload(TeachingPlan.items))
                .where(
                    TeachingPlan.classroom_id == classroom_id,
                    TeachingPlan.subject_id == subject_id,
                    TeachingPlan.status == TeachingPlanStatus.ACTIVE,
                )
            )
            if plan is None:
                raise ApplicationError(
                    422,
                    "ACTIVE_TEACHING_PLAN_REQUIRED",
                    "No active teaching plan found for this classroom and subject.",
                )
            return plan

        # When classroom_id is None, look across active classrooms
        classrooms = list(
            self.session.scalars(
                select(StudentEnrollment.classroom_id).where(
                    StudentEnrollment.student_id == student_id,
                    StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                )
            )
        )
        if not classrooms:
            raise ApplicationError(
                422,
                "ACTIVE_TEACHING_PLAN_REQUIRED",
                "Student has no active classroom enrollments.",
            )

        plans = list(
            self.session.scalars(
                select(TeachingPlan)
                .options(selectinload(TeachingPlan.items))
                .where(
                    TeachingPlan.classroom_id.in_(classrooms),
                    TeachingPlan.subject_id == subject_id,
                    TeachingPlan.status == TeachingPlanStatus.ACTIVE,
                )
                .order_by(TeachingPlan.created_at.desc())
            )
        )
        if not plans:
            raise ApplicationError(
                422,
                "ACTIVE_TEACHING_PLAN_REQUIRED",
                "An active teaching plan is required to start a quick check.",
            )
        return plans[0]

    def _concepts_for_plan(self, plan: TeachingPlan) -> set[UUID]:
        pt_ids = [item.problem_type_id for item in plan.items]
        return set(
            self.session.scalars(
                select(ProblemTypeConcept.concept_id).where(
                    ProblemTypeConcept.problem_type_id.in_(pt_ids)
                )
            )
        )

    def _to_start_read(
        self,
        quick_check: QuickCheckSession,
        plan: TeachingPlan,
        selected_items: list[dict],
    ) -> QuickCheckStartRead:
        questions_read = []
        for idx, item in enumerate(selected_items):
            q: Question = item["question"]
            options = list(
                self.session.scalars(
                    select(QuestionOption)
                    .where(QuestionOption.question_id == q.id)
                    .order_by(QuestionOption.order_index)
                )
            )
            questions_read.append(
                QuickCheckQuestionItemRead(
                    question_id=q.id,
                    order_index=idx,
                    content=q.content,
                    question_type=q.question_type,
                    difficulty=q.difficulty,
                    target_problem_type_id=item.get("target_problem_type_id"),
                    target_concept_id=item.get("target_concept_id"),
                    target_role=item["target_role"],
                    options=[
                        QuickCheckQuestionOptionRead(
                            id=opt.id,
                            label=opt.label,
                            content=opt.content,
                            order_index=opt.order_index,
                        )
                        for opt in options
                    ],
                )
            )

        return QuickCheckStartRead(
            id=quick_check.id,
            teaching_plan_id=quick_check.teaching_plan_id,
            classroom_id=quick_check.classroom_id,
            subject_id=plan.subject_id,
            status=PracticeSessionStatus.ACTIVE,
            question_count=len(questions_read),
            target_problem_type_ids=[item.problem_type_id for item in plan.items],
            questions=questions_read,
        )

    def _student_for_user(self, user_id: UUID) -> StudentProfile:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if student is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
        return student

    def _subject_or_404(self, subject_id: UUID) -> Subject:
        subject = self.session.get(Subject, subject_id)
        if subject is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        return subject

    def _authorize_view_result(self, current_user: User, qc: QuickCheckSession) -> None:
        if current_user.role.value == "STUDENT":
            student = self._student_for_user(current_user.id)
            if qc.practice_session.student_id != student.id:
                raise ApplicationError(
                    403, "ACCESS_DENIED", "You cannot view another student's quick check result."
                )
        elif current_user.role.value == "TEACHER":
            teacher = self.session.scalar(
                select(TeacherProfile).where(TeacherProfile.user_id == current_user.id)
            )
            if teacher is None:
                raise ApplicationError(404, "PROFILE_NOT_FOUND", "Teacher profile was not found.")
            assignment = self.session.scalar(
                select(TeacherClassroom).where(
                    TeacherClassroom.teacher_id == teacher.id,
                    TeacherClassroom.classroom_id == qc.classroom_id,
                )
            )
            if assignment is None:
                raise ApplicationError(
                    403, "CLASSROOM_ACCESS_DENIED", "You are not assigned to this classroom."
                )
        else:
            raise ApplicationError(403, "ROLE_FORBIDDEN", "Unauthorized role to view result.")
