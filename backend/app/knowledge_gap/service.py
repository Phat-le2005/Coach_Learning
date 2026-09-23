from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.dependencies import create_ai_provider
from app.ai.gateway import AIGateway
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.types import AIMessage, AIRole, AITaskType
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.curriculum.models import ProblemType, ProblemTypeConcept
from app.knowledge_gap.schemas import (
    AIGapDiagnosisOutput,
    KnowledgeGapResult,
    KnowledgeGapType,
)
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.deterministic_rules import has_reasoning
from app.misconceptions.models import (
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.practice.models import QuestionAttempt
from app.questions.models import Question, QuestionConcept, QuestionProblemType
from app.students.models import StudentProfile

logger = logging.getLogger(__name__)


class KnowledgeGapService:
    """Diagnoses student knowledge gaps for a ProblemType by synthesizing mastery,

    concept dependencies, prerequisite relations, misconceptions, and attempt reasoning.

    Priority:
        1. Deterministic rules are evaluated first.
        2. AI is only consulted if rule-based signals are inconclusive AND the student
           provided complex reasoning/scratchwork.
        3. The backend always decides the final authoritative classification.
    """

    LOW_MASTERY_THRESHOLD: float = 0.50
    HIGH_MASTERY_THRESHOLD: float = 0.65
    MIN_ATTEMPTS_FOR_CERTAINTY: int = 2

    def __init__(
        self,
        session: Session,
        gateway: AIGateway | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.session = session
        if gateway is not None:
            self.gateway = gateway
        else:
            settings = Settings()
            provider = create_ai_provider(settings)
            self.gateway = AIGateway(provider=provider, settings=settings)
        self.prompt_registry = prompt_registry or default_prompt_registry

    async def analyze_gap(
        self,
        student_id: UUID,
        problem_type_id: UUID,
        *,
        recent_attempt_id: UUID | None = None,
        use_ai: bool = True,
    ) -> KnowledgeGapResult:
        """Analyze and classify a student's knowledge gap for a problem type."""
        # 1. Fetch ProblemType and verify existence
        problem_type = self.session.get(ProblemType, problem_type_id)
        if problem_type is None:
            raise ApplicationError(404, "PROBLEM_TYPE_NOT_FOUND", "Problem type not found.")

        # 2. Fetch StudentProfile
        student_profile = self.session.get(StudentProfile, student_id)
        if student_profile is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile not found.")

        # 3. Retrieve StudentProblemTypeMastery
        pt_mastery = self.session.get(
            StudentProblemTypeMastery, (student_id, problem_type_id)
        )
        pt_score = pt_mastery.mastery_score if pt_mastery else 0.0
        pt_conf = pt_mastery.confidence if pt_mastery else 0.0
        pt_attempts = pt_mastery.attempt_count if pt_mastery else 0
        pt_correct = pt_mastery.correct_count if pt_mastery else 0

        # 4. Retrieve underlying direct Concepts & their mastery
        ptc_concept_ids = set(
            self.session.scalars(
                select(ProblemTypeConcept.concept_id).where(
                    ProblemTypeConcept.problem_type_id == problem_type_id
                )
            ).all()
        )
        # Also include concepts mapped via questions belonging to this problem type
        q_concept_ids = set(
            self.session.scalars(
                select(QuestionConcept.concept_id)
                .join(QuestionProblemType, QuestionProblemType.question_id == QuestionConcept.question_id)
                .where(QuestionProblemType.problem_type_id == problem_type_id)
            ).all()
        )
        direct_concept_ids = list(ptc_concept_ids | q_concept_ids)

        direct_concepts: dict[UUID, Concept] = {}
        if direct_concept_ids:
            c_rows = self.session.scalars(
                select(Concept).where(Concept.id.in_(direct_concept_ids))
            ).all()
            direct_concepts = {c.id: c for c in c_rows}

        direct_masteries: dict[UUID, StudentConceptMastery | None] = {
            cid: self.session.get(StudentConceptMastery, (student_id, cid))
            for cid in direct_concept_ids
        }

        # 5. Retrieve Prerequisite Concepts via ConceptGraph (ConceptRelation) & their mastery
        prereq_relations = []
        if direct_concept_ids:
            prereq_relations = self.session.scalars(
                select(ConceptRelation).where(
                    ConceptRelation.target_concept_id.in_(direct_concept_ids),
                    ConceptRelation.relation_type == RelationType.PREREQUISITE,
                )
            ).all()

        prereq_concept_ids = list(
            {r.source_concept_id for r in prereq_relations if r.source_concept_id not in direct_concept_ids}
        )
        prereq_concepts: dict[UUID, Concept] = {}
        if prereq_concept_ids:
            p_rows = self.session.scalars(
                select(Concept).where(Concept.id.in_(prereq_concept_ids))
            ).all()
            prereq_concepts = {p.id: p for p in p_rows}

        prereq_masteries: dict[UUID, StudentConceptMastery | None] = {
            pid: self.session.get(StudentConceptMastery, (student_id, pid))
            for pid in prereq_concept_ids
        }

        # 6. Retrieve active misconceptions
        all_scoped_concept_ids = set(direct_concept_ids) | set(prereq_concept_ids)
        misconception_conditions = [MisconceptionDefinition.problem_type_id == problem_type_id]
        if all_scoped_concept_ids:
            misconception_conditions.append(
                MisconceptionDefinition.concept_id.in_(all_scoped_concept_ids)
            )

        scoped_misconceptions: list[tuple[StudentMisconception, MisconceptionDefinition]] = []
        stmt = (
            select(StudentMisconception, MisconceptionDefinition)
            .join(
                MisconceptionDefinition,
                StudentMisconception.misconception_definition_id == MisconceptionDefinition.id,
            )
            .where(
                StudentMisconception.student_id == student_id,
                StudentMisconception.status.in_(
                    [
                        StudentMisconceptionStatus.CONFIRMED,
                        StudentMisconceptionStatus.SUSPECTED,
                    ]
                ),
            )
        )
        for sm, md in self.session.execute(stmt).all():
            if md.problem_type_id == problem_type_id or md.concept_id in all_scoped_concept_ids:
                scoped_misconceptions.append((sm, md))

        # 7. Retrieve Recent Attempt
        recent_attempt: QuestionAttempt | None = None
        if recent_attempt_id:
            recent_attempt = self.session.get(QuestionAttempt, recent_attempt_id)
        else:
            recent_attempt = self.session.scalar(
                select(QuestionAttempt)
                .join(QuestionProblemType, QuestionProblemType.question_id == QuestionAttempt.question_id)
                .where(
                    QuestionAttempt.student_id == student_id,
                    QuestionProblemType.problem_type_id == problem_type_id,
                )
                .order_by(QuestionAttempt.created_at.desc())
                .limit(1)
            )

        # 8. Step 1: Evaluate Deterministic Rules
        det_result = self._evaluate_deterministic_rules(
            problem_type=problem_type,
            pt_score=pt_score,
            pt_conf=pt_conf,
            pt_attempts=pt_attempts,
            pt_correct=pt_correct,
            direct_concepts=direct_concepts,
            direct_masteries=direct_masteries,
            prereq_concepts=prereq_concepts,
            prereq_masteries=prereq_masteries,
            misconceptions=scoped_misconceptions,
        )

        # If deterministic rules yield a decisive, confident result, return immediately
        if det_result is not None and det_result.confidence >= 0.75:
            return det_result

        # 9. Step 2: Determine if AI consultation is warranted
        # AI is only called if:
        # - use_ai is True
        # - rule-based is inconclusive / borderline (det_result is None or low confidence)
        # - recent attempt has complex reasoning
        has_complex_reasoning = (
            recent_attempt is not None and has_reasoning(recent_attempt.student_answer)
        )

        if use_ai and has_complex_reasoning and recent_attempt is not None:
            ai_result = await self._consult_ai_diagnosis(
                student_id=student_id,
                problem_type=problem_type,
                pt_score=pt_score,
                direct_concepts=direct_concepts,
                direct_masteries=direct_masteries,
                prereq_concepts=prereq_concepts,
                prereq_masteries=prereq_masteries,
                misconceptions=scoped_misconceptions,
                recent_attempt=recent_attempt,
                fallback_result=det_result,
            )
            if ai_result is not None:
                return ai_result

        # 10. Fallback: Return deterministic result or default INSUFFICIENT_EVIDENCE
        if det_result is not None:
            return det_result

        return KnowledgeGapResult(
            gap_type=KnowledgeGapType.INSUFFICIENT_EVIDENCE,
            target_problem_type_id=problem_type.id,
            target_problem_type_code=problem_type.code,
            evidence=["Not enough practice evidence or mastery confidence to classify a persistent gap."],
            confidence=0.50,
            reason_code="INSUFFICIENT_DATA_FALLBACK",
            metadata={
                "pt_attempts": pt_attempts,
                "pt_mastery": pt_score,
            },
        )

    # --------------------------------------------------------------------------
    # Deterministic Classifier
    # --------------------------------------------------------------------------

    def _evaluate_deterministic_rules(
        self,
        *,
        problem_type: ProblemType,
        pt_score: float,
        pt_conf: float,
        pt_attempts: int,
        pt_correct: int,
        direct_concepts: dict[UUID, Concept],
        direct_masteries: dict[UUID, StudentConceptMastery | None],
        prereq_concepts: dict[UUID, Concept],
        prereq_masteries: dict[UUID, StudentConceptMastery | None],
        misconceptions: list[tuple[StudentMisconception, MisconceptionDefinition]],
    ) -> KnowledgeGapResult | None:
        """Rule-based decision cascade."""
        # --- Rule 1: PERSISTENT_MISCONCEPTION ---
        # If student has a CONFIRMED misconception in scope, or SUSPECTED with confidence >= 0.65
        confirmed_m = [
            (sm, md)
            for sm, md in misconceptions
            if sm.status == StudentMisconceptionStatus.CONFIRMED or (sm.occurrence_count >= 2 and sm.confidence >= 0.65)
        ]
        if confirmed_m:
            # Pick highest confidence
            top_sm, top_md = max(confirmed_m, key=lambda pair: pair[0].confidence)
            target_c = direct_concepts.get(top_md.concept_id) or prereq_concepts.get(top_md.concept_id)
            return KnowledgeGapResult(
                gap_type=KnowledgeGapType.PERSISTENT_MISCONCEPTION,
                target_problem_type_id=problem_type.id,
                target_problem_type_code=problem_type.code,
                target_concept_id=top_md.concept_id,
                target_concept_code=target_c.code if target_c else None,
                evidence=[
                    f"Xác nhận hiểu sai dai dẳng: '{top_md.name}' (mã: {top_md.code}).",
                    f"Độ tin cậy: {top_sm.confidence:.2f}, xuất hiện {top_sm.occurrence_count} lần.",
                ],
                confidence=min(0.95, round(top_sm.confidence, 2)),
                reason_code=f"CONFIRMED_MISCONCEPTION_{top_md.code}",
                metadata={"misconception_code": top_md.code, "status": top_sm.status.value},
            )

        # Calculate direct concept mastery stats
        weak_direct: list[tuple[Concept, float]] = []
        strong_direct: list[tuple[Concept, float]] = []
        for cid, concept in direct_concepts.items():
            cm = direct_masteries.get(cid)
            score = cm.mastery_score if cm else 0.0
            attempts = cm.attempt_count if cm else 0
            if cm is not None and attempts > 0:
                if score < self.LOW_MASTERY_THRESHOLD:
                    weak_direct.append((concept, score))
                elif score >= self.HIGH_MASTERY_THRESHOLD:
                    strong_direct.append((concept, score))

        # Calculate prerequisite mastery stats
        weak_prereqs: list[tuple[Concept, float]] = []
        strong_prereqs: list[tuple[Concept, float]] = []
        for pid, concept in prereq_concepts.items():
            pm = prereq_masteries.get(pid)
            score = pm.mastery_score if pm else 0.0
            attempts = pm.attempt_count if pm else 0
            if pm is not None and attempts > 0:
                if score < self.LOW_MASTERY_THRESHOLD:
                    weak_prereqs.append((concept, score))
                elif score >= self.HIGH_MASTERY_THRESHOLD:
                    strong_prereqs.append((concept, score))

        # Total relevant attempts
        total_attempts = pt_attempts + sum(
            cm.attempt_count for cm in direct_masteries.values() if cm
        )

        # --- Rule: Check INSUFFICIENT_EVIDENCE ---
        if total_attempts < self.MIN_ATTEMPTS_FOR_CERTAINTY and not weak_direct and not weak_prereqs:
            return KnowledgeGapResult(
                gap_type=KnowledgeGapType.INSUFFICIENT_EVIDENCE,
                target_problem_type_id=problem_type.id,
                target_problem_type_code=problem_type.code,
                evidence=[
                    f"Số lượt làm bài dạng [{problem_type.name}] quá ít ({pt_attempts} lượt).",
                    "Chưa đủ dữ liệu quan sát để khẳng định lỗ hổng bền vững.",
                ],
                confidence=0.85,
                reason_code="INSUFFICIENT_ATTEMPTS",
                metadata={"pt_attempts": pt_attempts, "total_attempts": total_attempts},
            )

        # --- Rule 2: MULTI_CONCEPT_GAP ---
        # Multiple direct concepts are weak
        if len(weak_direct) >= 2:
            weak_names = [f"{c.name} ({s:.2f})" for c, s in weak_direct]
            return KnowledgeGapResult(
                gap_type=KnowledgeGapType.MULTI_CONCEPT_GAP,
                target_problem_type_id=problem_type.id,
                target_problem_type_code=problem_type.code,
                evidence=[
                    f"Có {len(weak_direct)} khái niệm trực tiếp của dạng bài đang bị yếu: {', '.join(weak_names)}.",
                    f"Điểm thành thạo dạng bài: {pt_score:.2f}.",
                ],
                confidence=0.88,
                reason_code="MULTI_DIRECT_CONCEPTS_DEFICIT",
                metadata={"weak_concepts": [c.code for c, _ in weak_direct]},
            )

        # --- Rule 3: PREREQUISITE_CONCEPT_GAP ---
        # Student struggles with problem type (pt_score < 0.60 or pt_correct < pt_attempts),
        # direct underlying concepts are strong / not multi-gap,
        # BUT at least one prerequisite concept is weak (< LOW_MASTERY_THRESHOLD)
        pt_struggles = pt_score < self.HIGH_MASTERY_THRESHOLD or (pt_attempts >= 2 and pt_correct < pt_attempts)
        direct_mostly_ok = len(weak_direct) == 0 or len(strong_direct) >= 1

        if pt_struggles and direct_mostly_ok and weak_prereqs:
            # Pick weakest prerequisite concept
            weakest_p, p_score = min(weak_prereqs, key=lambda pair: pair[1])
            strong_names = [f"{c.name} ({s:.2f})" for c, s in strong_direct] or ["khá"]
            return KnowledgeGapResult(
                gap_type=KnowledgeGapType.PREREQUISITE_CONCEPT_GAP,
                target_problem_type_id=problem_type.id,
                target_problem_type_code=problem_type.code,
                target_concept_id=weakest_p.id,
                target_concept_code=weakest_p.code,
                evidence=[
                    f"Dạng bài [{problem_type.name}] có điểm thấp ({pt_score:.2f}).",
                    f"Khái niệm cốt lõi của bài đã vững ({', '.join(strong_names)}).",
                    f"Tuy nhiên kiến thức tiên quyết [{weakest_p.name}] bị hổng ({p_score:.2f} < {self.LOW_MASTERY_THRESHOLD}).",
                ],
                confidence=0.90,
                reason_code=f"PREREQUISITE_GAP_{weakest_p.code}",
                metadata={
                    "prerequisite_concept_id": str(weakest_p.id),
                    "prerequisite_concept_code": weakest_p.code,
                    "prerequisite_score": p_score,
                },
            )

        # --- Rule 4: CURRENT_PROBLEM_TYPE_GAP ---
        # Underlying concepts are strong (>= HIGH_MASTERY_THRESHOLD or no weak),
        # Prerequisite concepts (if any) are not weak,
        # BUT student still fails the problem type itself (pt_score < LOW_MASTERY_THRESHOLD, pt_attempts >= 2)
        prereqs_ok = len(weak_prereqs) == 0
        if direct_mostly_ok and prereqs_ok and pt_attempts >= self.MIN_ATTEMPTS_FOR_CERTAINTY and pt_score < self.LOW_MASTERY_THRESHOLD:
            return KnowledgeGapResult(
                gap_type=KnowledgeGapType.CURRENT_PROBLEM_TYPE_GAP,
                target_problem_type_id=problem_type.id,
                target_problem_type_code=problem_type.code,
                evidence=[
                    f"Khái niệm nền tảng và tiên quyết đều đạt yêu cầu.",
                    f"Học sinh gặp khó khăn ở kỹ năng tổng hợp và quy trình đặc thù của dạng bài [{problem_type.name}] (điểm: {pt_score:.2f}).",
                ],
                confidence=0.85,
                reason_code="PROBLEM_TYPE_SYNTHESIS_DEFICIT",
                metadata={"pt_score": pt_score, "pt_attempts": pt_attempts},
            )

        return None

    # --------------------------------------------------------------------------
    # AI Diagnosis (Advisory consultation for complex reasoning)
    # --------------------------------------------------------------------------

    async def _consult_ai_diagnosis(
        self,
        *,
        student_id: UUID,
        problem_type: ProblemType,
        pt_score: float,
        direct_concepts: dict[UUID, Concept],
        direct_masteries: dict[UUID, StudentConceptMastery | None],
        prereq_concepts: dict[UUID, Concept],
        prereq_masteries: dict[UUID, StudentConceptMastery | None],
        misconceptions: list[tuple[StudentMisconception, MisconceptionDefinition]],
        recent_attempt: QuestionAttempt,
        fallback_result: KnowledgeGapResult | None,
    ) -> KnowledgeGapResult | None:
        """Consult AI structured diagnosis when student scratchwork contains reasoning."""
        question = self.session.get(Question, recent_attempt.question_id)
        if question is None:
            return fallback_result

        # Format context strings
        pt_info = f"- Code: {problem_type.code} | Name: {problem_type.name} | Mastery Score: {pt_score:.2f}"

        direct_lines = []
        for cid, c in direct_concepts.items():
            cm = direct_masteries.get(cid)
            s_txt = f"{cm.mastery_score:.2f}" if cm else "unrated"
            direct_lines.append(f"  * {c.name} ({c.code}, id: {c.id}): mastery={s_txt}")
        direct_info = "\n".join(direct_lines) or "  (None)"

        prereq_lines = []
        for pid, p in prereq_concepts.items():
            pm = prereq_masteries.get(pid)
            s_txt = f"{pm.mastery_score:.2f}" if pm else "unrated"
            prereq_lines.append(f"  * {p.name} ({p.code}, id: {p.id}): mastery={s_txt}")
        prereq_info = "\n".join(prereq_lines) or "  (None)"

        misc_lines = [
            f"  * {md.name} ({md.code}): status={sm.status.value}, conf={sm.confidence:.2f}"
            for sm, md in misconceptions
        ]
        misc_info = "\n".join(misc_lines) or "  (None)"

        prompt_text = self.prompt_registry.get_prompt(
            "knowledge_gap_analyzer",
            "v1",
            variables={
                "problem_type_info": pt_info,
                "underlying_concepts_info": direct_info,
                "prerequisite_concepts_info": prereq_info,
                "active_misconceptions_info": misc_info,
                "recent_attempt_content": f"Question: {question.content}\nSolution: {question.explanation or question.correct_answer or 'None'}",
                "student_reasoning": recent_attempt.student_answer,
            },
        )

        messages = [AIMessage(role=AIRole.USER, content=prompt_text)]

        try:
            response = await self.gateway.generate_structured(
                task_type=AITaskType.MISCONCEPTION_ANALYSIS,
                messages=messages,
                schema=AIGapDiagnosisOutput,
                temperature=0.2,
                prompt_name="knowledge_gap_analyzer",
                prompt_version="v1",
            )
            ai_output: AIGapDiagnosisOutput = response.data
        except Exception as exc:
            logger.warning("KnowledgeGapService: AI consultation failed: %s", exc)
            return fallback_result

        # Backend validates AI output whitelist
        target_concept_id = ai_output.target_concept_id
        target_concept = None
        if target_concept_id:
            target_concept = direct_concepts.get(target_concept_id) or prereq_concepts.get(target_concept_id)
            if target_concept is None:
                target_concept_id = None

        # Build backend authoritative result incorporating AI evidence
        evidence = list(ai_output.observations)
        evidence.append(
            f"Tham vấn AI từ lời giải học sinh (độ tin cậy AI: {ai_output.confidence:.2f})."
        )

        return KnowledgeGapResult(
            gap_type=ai_output.suggested_gap_type,
            target_problem_type_id=problem_type.id,
            target_problem_type_code=problem_type.code,
            target_concept_id=target_concept_id,
            target_concept_code=target_concept.code if target_concept else None,
            evidence=evidence,
            confidence=round(ai_output.confidence, 2),
            reason_code=ai_output.reason_code or "AI_DIAGNOSED_REASONING_GAP",
            metadata={
                "ai_consulted": True,
                "pt_mastery": pt_score,
            },
        )
