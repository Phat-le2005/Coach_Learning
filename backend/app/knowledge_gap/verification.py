"""Root Cause Verification Service: orchestrates frozen probe sessions, deterministic scoring, and evidence publishing."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import ProblemType
from app.knowledge_gap.models import (
    RootCauseDiagnosis,
    RootCauseVerification,
    RootCauseVerificationItem,
    RootCauseVerificationOutcome,
    RootCauseVerificationStatus,
    RootCauseVerificationTarget,
)
from app.knowledge_gap.schemas import (
    RootCauseVerificationAnswerResult,
    RootCauseVerificationAnswerSubmit,
    RootCauseVerificationItemOptionRead,
    RootCauseVerificationItemRead,
    RootCauseVerificationRead,
    RootCauseVerificationTargetRead,
)
from app.knowledge_gap.verification_policy import (
    RootCauseVerificationPolicy,
    TargetResolutionSpec,
)
from app.mastery.evidence import MasteryAttemptEvidencePublisher
from app.practice.evaluation import AnswerEvaluationService
from app.practice.evidence import AttemptEvaluatedEvidence, AttemptEvidencePublisher
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionConcept,
    PracticeSessionProblemType,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.questions.exposure import QuestionExposureService
from app.questions.models import Question
from app.students.models import StudentProfile


class RootCauseVerificationService:
    """Manages empirical verification of root cause hypotheses."""

    def __init__(
        self,
        session: Session,
        evaluator: AnswerEvaluationService | None = None,
        publisher: AttemptEvidencePublisher | None = None,
    ) -> None:
        self.session = session
        self.evaluator = evaluator or AnswerEvaluationService()
        self.publisher = publisher or MasteryAttemptEvidencePublisher()

    def start_verification(
        self,
        student_id: UUID,
        diagnosis_id: UUID,
    ) -> RootCauseVerificationRead:
        """Start or retrieve an idempotent root cause verification session.

        - Frozen probe selection from canonical APPROVED Question Bank.
        - Excludes recent exposures, diagnosis source questions, and cross-target duplicates.
        - If no questions are available in the question bank, marks status UNAVAILABLE.
        - Creates a dedicated PracticeSession of type ROOT_CAUSE_VERIFICATION.
        """
        student = self.session.get(StudentProfile, student_id)
        if student is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile not found.")

        diagnosis = self._get_diagnosis_with_candidates(diagnosis_id)
        if diagnosis is None:
            raise ApplicationError(404, "DIAGNOSIS_NOT_FOUND", "Diagnosis not found.")
        if diagnosis.student_id != student_id:
            raise ApplicationError(403, "DIAGNOSIS_ACCESS_DENIED", "Access denied to diagnosis.")

        # Idempotency: return existing verification if already created
        existing_verification = self._find_existing_verification(diagnosis_id)
        if existing_verification is not None:
            return self._build_verification_read(existing_verification)

        # Resolve targets from policy
        target_specs = RootCauseVerificationPolicy.resolve_targets(diagnosis)
        if not target_specs:
            raise ApplicationError(
                422,
                "NO_VERIFICATION_TARGETS",
                "Diagnosis cannot be resolved into verification targets.",
            )

        # Build exclusion set: recent exposures + diagnosis source question
        exposure_service = QuestionExposureService(self.session)
        excluded_qids = exposure_service.get_recent_exposed_question_ids(student_id)
        diag_source_qid = exposure_service.get_diagnosis_source_question_id(diagnosis)
        if diag_source_qid is not None:
            excluded_qids.add(diag_source_qid)

        # Select probe questions per target spec
        target_questions_map: dict[int, list[tuple[Question, float]]] = {}
        for spec in target_specs:
            probes = RootCauseVerificationPolicy.select_probe_questions(
                session=self.session,
                subject_id=diagnosis.subject_id,
                target_spec=spec,
                excluded_question_ids=excluded_qids,
            )
            target_questions_map[spec.priority_order] = probes
            for q, _ in probes:
                excluded_qids.add(q.id)

        total_probes_count = sum(len(probes) for probes in target_questions_map.values())

        # If 0 questions available in bank across all targets -> UNAVAILABLE
        if total_probes_count == 0:
            now = datetime.now(timezone.utc)
            practice_session = PracticeSession(
                student_id=student_id,
                subject_id=diagnosis.subject_id,
                session_type=PracticeSessionType.ROOT_CAUSE_VERIFICATION,
                status=PracticeSessionStatus.COMPLETED,
                completed_at=now,
            )
            self.session.add(practice_session)
            self.session.flush()

            verification = RootCauseVerification(
                diagnosis_id=diagnosis.id,
                practice_session_id=practice_session.id,
                status=RootCauseVerificationStatus.UNAVAILABLE,
                required_probe_count=0,
                completed_probe_count=0,
                completed_at=now,
            )
            self.session.add(verification)
            self.session.flush()

            for spec in target_specs:
                target_row = RootCauseVerificationTarget(
                    verification_id=verification.id,
                    root_cause_candidate_id=spec.candidate_id,
                    target_type=spec.target_type,
                    target_concept_id=spec.target_concept_id,
                    target_problem_type_id=spec.target_problem_type_id,
                    misconception_definition_id=spec.misconception_definition_id,
                    priority_order=spec.priority_order,
                    outcome=RootCauseVerificationOutcome.UNAVAILABLE,
                    probe_count=0,
                    correct_count=0,
                    completed_at=now,
                )
                self.session.add(target_row)

            self.session.commit()
            return self._build_verification_read(verification)

        # Create active PracticeSession
        practice_session = PracticeSession(
            student_id=student_id,
            subject_id=diagnosis.subject_id,
            session_type=PracticeSessionType.ROOT_CAUSE_VERIFICATION,
            status=PracticeSessionStatus.ACTIVE,
        )
        self.session.add(practice_session)
        self.session.flush()

        # Link practice session targets
        for spec in target_specs:
            if spec.target_concept_id is not None:
                self.session.add(
                    PracticeSessionConcept(
                        practice_session_id=practice_session.id,
                        concept_id=spec.target_concept_id,
                    )
                )
            if spec.target_problem_type_id is not None:
                self.session.add(
                    PracticeSessionProblemType(
                        practice_session_id=practice_session.id,
                        problem_type_id=spec.target_problem_type_id,
                    )
                )

        verification = RootCauseVerification(
            diagnosis_id=diagnosis.id,
            practice_session_id=practice_session.id,
            status=RootCauseVerificationStatus.ACTIVE,
            required_probe_count=total_probes_count,
            completed_probe_count=0,
        )
        self.session.add(verification)
        self.session.flush()

        global_order = 1
        for spec in target_specs:
            probes = target_questions_map.get(spec.priority_order, [])
            target_row = RootCauseVerificationTarget(
                verification_id=verification.id,
                root_cause_candidate_id=spec.candidate_id,
                target_type=spec.target_type,
                target_concept_id=spec.target_concept_id,
                target_problem_type_id=spec.target_problem_type_id,
                misconception_definition_id=spec.misconception_definition_id,
                priority_order=spec.priority_order,
                outcome=(
                    RootCauseVerificationOutcome.PENDING
                    if probes
                    else RootCauseVerificationOutcome.UNAVAILABLE
                ),
                probe_count=0,
                correct_count=0,
            )
            self.session.add(target_row)
            self.session.flush()

            for q, sel_score in probes:
                item = RootCauseVerificationItem(
                    verification_target_id=target_row.id,
                    question_id=q.id,
                    order_index=global_order,
                    desired_difficulty=spec.desired_difficulty,
                    selection_score=sel_score,
                )
                self.session.add(item)
                global_order += 1

        self.session.commit()
        return self._build_verification_read(verification)

    def get_verification(
        self,
        student_id: UUID,
        diagnosis_id: UUID,
    ) -> RootCauseVerificationRead:
        """Fetch verification details for a diagnosis. Hides answers prior to student attempt."""
        diagnosis = self._get_diagnosis_with_candidates(diagnosis_id)
        if diagnosis is None:
            raise ApplicationError(404, "DIAGNOSIS_NOT_FOUND", "Diagnosis not found.")
        if diagnosis.student_id != student_id:
            raise ApplicationError(403, "DIAGNOSIS_ACCESS_DENIED", "Access denied to diagnosis.")

        verification = self._find_existing_verification(diagnosis_id)
        if verification is None:
            raise ApplicationError(
                404,
                "VERIFICATION_NOT_FOUND",
                "Verification session has not been started for this diagnosis.",
            )

        return self._build_verification_read(verification)

    def submit_verification_answer(
        self,
        student_id: UUID,
        diagnosis_id: UUID,
        item_id: UUID,
        data: RootCauseVerificationAnswerSubmit,
    ) -> RootCauseVerificationAnswerResult:
        """Submit student answer for a verification probe item.

        - Prevents duplicate attempts on the same probe item (409).
        - Evaluates answer via deterministic AnswerEvaluationService.
        - Records QuestionAttempt.
        - Publishes evidence through AttemptEvidencePublisher -> LearningEvidencePublisher -> Mastery.
        - Recomputes target outcome deterministically.
        - Automatically completes session when all items are attempted.
        """
        item = self.session.get(RootCauseVerificationItem, item_id)
        if item is None:
            raise ApplicationError(404, "ITEM_NOT_FOUND", "Verification item not found.")

        target = self.session.get(RootCauseVerificationTarget, item.verification_target_id)
        if target is None:
            raise ApplicationError(404, "TARGET_NOT_FOUND", "Verification target not found.")

        verification = self.session.get(RootCauseVerification, target.verification_id)
        if verification is None:
            raise ApplicationError(404, "VERIFICATION_NOT_FOUND", "Verification session not found.")

        if verification.diagnosis_id != diagnosis_id:
            raise ApplicationError(
                400, "ITEM_DIAGNOSIS_MISMATCH", "Item does not belong to specified diagnosis."
            )

        diagnosis = self._get_diagnosis_with_candidates(diagnosis_id)
        if diagnosis is None or diagnosis.student_id != student_id:
            raise ApplicationError(403, "DIAGNOSIS_ACCESS_DENIED", "Access denied to diagnosis.")

        if item.attempt_id is not None:
            raise ApplicationError(
                409, "ITEM_ALREADY_ATTEMPTED", "This verification probe has already been attempted."
            )

        if verification.status != RootCauseVerificationStatus.ACTIVE:
            raise ApplicationError(
                400,
                "VERIFICATION_NOT_ACTIVE",
                f"Verification session is not active (status: {verification.status}).",
            )

        question = self.session.get(Question, item.question_id)
        if question is None:
            raise ApplicationError(404, "QUESTION_NOT_FOUND", "Probe question not found.")

        practice_session = self.session.get(PracticeSession, verification.practice_session_id)
        if practice_session is None:
            raise ApplicationError(
                500, "PRACTICE_SESSION_MISSING", "Associated practice session missing."
            )

        # 1. Deterministic evaluation
        evaluation = self.evaluator.evaluate(question, data.student_answer)

        # 2. Record QuestionAttempt
        attempt_number = verification.completed_probe_count + 1
        now = datetime.now(timezone.utc)
        attempt = QuestionAttempt(
            practice_session_id=practice_session.id,
            student_id=student_id,
            question_id=question.id,
            student_answer=data.student_answer,
            is_correct=evaluation.is_correct,
            score=evaluation.score,
            response_time_seconds=data.response_time_seconds,
            hint_count=data.hint_count,
            attempt_number=attempt_number,
            evaluation_status=evaluation.status,
        )
        self.session.add(attempt)
        self.session.flush()

        item.attempt_id = attempt.id

        # 3. Publish evidence through standard pipeline -> Mastery
        if (
            attempt.evaluation_status
            in {EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED}
            and attempt.is_correct is not None
            and attempt.score is not None
        ):
            evidence = AttemptEvaluatedEvidence(
                attempt_id=attempt.id,
                practice_session_id=practice_session.id,
                student_id=student_id,
                question_id=question.id,
                subject_id=diagnosis.subject_id,
                is_correct=bool(attempt.is_correct),
                score=float(attempt.score),
                problem_type_ids=tuple(
                    sorted(link.problem_type_id for link in question.problem_type_links)
                ),
                concept_ids=tuple(sorted(link.concept_id for link in question.concept_links)),
                learning_outcome_ids=tuple(
                    sorted(link.learning_outcome_id for link in question.learning_outcome_links)
                ),
                occurred_at=attempt.created_at or now,
            )
            self.publisher.publish(evidence, self.session)

        # 4. Re-evaluate target outcome
        target_items = list(
            self.session.scalars(
                select(RootCauseVerificationItem)
                .where(RootCauseVerificationItem.verification_target_id == target.id)
                .order_by(RootCauseVerificationItem.order_index)
            )
        )
        attempts_map = {
            att.id: att
            for att in self.session.scalars(
                select(QuestionAttempt).where(
                    QuestionAttempt.id.in_(
                        [it.attempt_id for it in target_items if it.attempt_id is not None]
                    )
                )
            )
        }

        outcome, probe_count, correct_count, avg_score = (
            RootCauseVerificationPolicy.evaluate_target_outcome(target_items, attempts_map)
        )
        target.outcome = outcome
        target.probe_count = probe_count
        target.correct_count = correct_count
        target.average_score = avg_score

        if probe_count == len(target_items) and target_items:
            target.completed_at = now

        # 5. Update overall verification session
        all_items = list(
            self.session.scalars(
                select(RootCauseVerificationItem)
                .join(
                    RootCauseVerificationTarget,
                    RootCauseVerificationTarget.id
                    == RootCauseVerificationItem.verification_target_id,
                )
                .where(RootCauseVerificationTarget.verification_id == verification.id)
            )
        )
        completed_count = sum(1 for it in all_items if it.attempt_id is not None)
        verification.completed_probe_count = completed_count

        if completed_count >= verification.required_probe_count:
            verification.status = RootCauseVerificationStatus.COMPLETED
            verification.completed_at = now
            practice_session.status = PracticeSessionStatus.COMPLETED
            practice_session.completed_at = now

        self.session.commit()

        return RootCauseVerificationAnswerResult(
            item_id=item.id,
            question_id=question.id,
            is_correct=attempt.is_correct,
            score=attempt.score,
            explanation=question.explanation,
            target_outcome=target.outcome,
            verification_status=verification.status,
        )

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _get_diagnosis_with_candidates(self, diagnosis_id: UUID) -> RootCauseDiagnosis | None:
        return self.session.scalar(
            select(RootCauseDiagnosis)
            .options(selectinload(RootCauseDiagnosis.candidates))
            .where(RootCauseDiagnosis.id == diagnosis_id)
        )

    def _find_existing_verification(
        self, diagnosis_id: UUID
    ) -> RootCauseVerification | None:
        return self.session.scalar(
            select(RootCauseVerification)
            .options(
                selectinload(RootCauseVerification.targets).selectinload(
                    RootCauseVerificationTarget.items
                )
            )
            .where(RootCauseVerification.diagnosis_id == diagnosis_id)
            .order_by(RootCauseVerification.created_at.desc())
        )

    def _build_verification_read(
        self, verification: RootCauseVerification
    ) -> RootCauseVerificationRead:
        targets_read: list[RootCauseVerificationTargetRead] = []

        # Pre-fetch all attempts and questions
        item_ids = [
            it.id
            for t in verification.targets
            for it in t.items
        ]
        attempt_ids = [
            it.attempt_id
            for t in verification.targets
            for it in t.items
            if it.attempt_id is not None
        ]
        question_ids = [
            it.question_id
            for t in verification.targets
            for it in t.items
        ]

        attempts_by_id: dict[UUID, QuestionAttempt] = {}
        if attempt_ids:
            attempts = self.session.scalars(
                select(QuestionAttempt).where(QuestionAttempt.id.in_(attempt_ids))
            ).all()
            attempts_by_id = {att.id: att for att in attempts}

        questions_by_id: dict[UUID, Question] = {}
        if question_ids:
            questions = self.session.scalars(
                select(Question)
                .options(selectinload(Question.options))
                .where(Question.id.in_(question_ids))
            ).all()
            questions_by_id = {q.id: q for q in questions}

        for target in sorted(verification.targets, key=lambda t: t.priority_order):
            items_read: list[RootCauseVerificationItemRead] = []
            for item in sorted(target.items, key=lambda it: it.order_index):
                q = questions_by_id.get(item.question_id)
                options_read: list[RootCauseVerificationItemOptionRead] = []
                if q is not None and q.options:
                    for opt in sorted(q.options, key=lambda o: o.order_index):
                        options_read.append(
                            RootCauseVerificationItemOptionRead(
                                id=opt.id,
                                label=opt.label,
                                content=opt.content,
                                order_index=opt.order_index,
                            )
                        )

                att = attempts_by_id.get(item.attempt_id) if item.attempt_id else None
                is_attempted = att is not None

                items_read.append(
                    RootCauseVerificationItemRead(
                        id=item.id,
                        verification_target_id=target.id,
                        question_id=item.question_id,
                        order_index=item.order_index,
                        desired_difficulty=item.desired_difficulty,
                        selection_score=item.selection_score,
                        attempt_id=item.attempt_id,
                        is_attempted=is_attempted,
                        content=q.content if q else "",
                        question_type=q.question_type.value if q else "MULTIPLE_CHOICE",
                        options=options_read,
                        # Hide answer details before attempt to prevent test leakage!
                        student_answer=att.student_answer if is_attempted else None,
                        is_correct=att.is_correct if is_attempted else None,
                        score=att.score if is_attempted else None,
                        explanation=q.explanation if (is_attempted and q) else None,
                    )
                )

            targets_read.append(
                RootCauseVerificationTargetRead(
                    id=target.id,
                    verification_id=target.verification_id,
                    root_cause_candidate_id=target.root_cause_candidate_id,
                    target_type=target.target_type,
                    target_concept_id=target.target_concept_id,
                    target_problem_type_id=target.target_problem_type_id,
                    misconception_definition_id=target.misconception_definition_id,
                    priority_order=target.priority_order,
                    outcome=target.outcome,
                    probe_count=target.probe_count,
                    correct_count=target.correct_count,
                    average_score=target.average_score,
                    items=items_read,
                )
            )

        return RootCauseVerificationRead(
            id=verification.id,
            diagnosis_id=verification.diagnosis_id,
            practice_session_id=verification.practice_session_id,
            status=verification.status,
            required_probe_count=verification.required_probe_count,
            completed_probe_count=verification.completed_probe_count,
            created_at=verification.created_at,
            completed_at=verification.completed_at,
            targets=targets_read,
        )
