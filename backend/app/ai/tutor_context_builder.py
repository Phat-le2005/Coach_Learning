"""TutorContextBuilder — assembles lean, targeted academic context for the AI Tutor prompt.

STRICT BOUNDARIES:
- Does NOT send full Digital Twin.
- Does NOT send full chat history.
- Does NOT invent or modify student data.
- All curriculum facts come from database, never from LLM.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.tutor_schemas import TutorContextData, TutorRequest
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.curriculum.models import Chapter, ProblemType, Topic
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.models import EvaluationStatus, QuestionAttempt
from app.questions.models import Question, QuestionConcept, QuestionProblemType
from app.rag.embedding_service import EmbeddingService
from app.rag.search_service import SemanticSearchService
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import User

logger = logging.getLogger(__name__)

# Mastery thresholds for narrative generation
_MASTERY_LOW = 0.4
_MASTERY_HIGH = 0.7

# How many recent attempts to include in context
_RECENT_ATTEMPTS_LIMIT = 3

# How many RAG chunks to retrieve
_RAG_TOP_K = 2


def _mastery_label(score: float) -> str:
    if score < _MASTERY_LOW:
        return "Yếu"
    if score < _MASTERY_HIGH:
        return "Trung bình"
    return "Tốt"


class TutorContextBuilder:
    """Builds a lean TutorContextData by querying only relevant academic data.

    This class is read-only; it never writes to the database.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    async def build_context(
        self,
        student_user: User,
        request: TutorRequest,
        *,
        gateway=None,  # AIGateway | None — injected to enable RAG embeddings
    ) -> TutorContextData:
        """Assemble context for the tutor prompt.

        Gracefully falls back to placeholder text when optional data is absent.
        """
        s = self.session

        # --- Student profile ---
        profile: StudentProfile | None = s.execute(
            select(StudentProfile).where(StudentProfile.user_id == student_user.id)
        ).scalar_one_or_none()

        student_name: str = student_user.full_name or "Học sinh"
        grade_level: int = profile.grade_level if profile else 12
        student_id: UUID | None = profile.id if profile else None

        # --- Resolve question, problem type, concept, subject ---
        question: Question | None = None
        if request.question_id:
            question = s.get(Question, request.question_id)

        # Determine subject from question → concept → problem_type fallback chain
        subject: Subject | None = None
        topic: Topic | None = None
        chapter: Chapter | None = None
        primary_problem_type: ProblemType | None = None
        primary_concept: Concept | None = None
        concept_ids_for_question: list[UUID] = []
        problem_type_ids_for_question: list[UUID] = []

        if question:
            subject = s.get(Subject, question.subject_id)

            # Concept links on the question
            qc_rows = s.execute(
                select(QuestionConcept).where(QuestionConcept.question_id == question.id)
            ).scalars().all()
            concept_ids_for_question = [qc.concept_id for qc in qc_rows]

            # Problem type links on the question
            qpt_rows = s.execute(
                select(QuestionProblemType).where(QuestionProblemType.question_id == question.id)
            ).scalars().all()
            problem_type_ids_for_question = [qpt.problem_type_id for qpt in qpt_rows]

            # Primary problem type from question
            primary_qpt = next((q for q in qpt_rows if q.is_primary), next(iter(qpt_rows), None))
            if primary_qpt:
                primary_problem_type = s.get(ProblemType, primary_qpt.problem_type_id)
            # Primary concept from question (highest-weight)
            best_qc = max(qc_rows, key=lambda q: q.weight, default=None)
            if best_qc:
                primary_concept = s.get(Concept, best_qc.concept_id)

        # Override with explicit IDs if caller provided them
        if request.problem_type_id and not primary_problem_type:
            primary_problem_type = s.get(ProblemType, request.problem_type_id)
        if request.concept_id and not primary_concept:
            primary_concept = s.get(Concept, request.concept_id)

        # Resolve topic → chapter → subject from problem_type if still unknown
        if primary_problem_type:
            topic = s.get(Topic, primary_problem_type.topic_id)
        if topic:
            chapter = s.get(Chapter, topic.chapter_id)
        if chapter and not subject:
            subject = s.get(Subject, chapter.subject_id)
        if primary_concept and not subject:
            subject = s.get(Subject, primary_concept.subject_id)

        subject_name = subject.name if subject else "(Môn học không xác định)"
        topic_name = topic.name if topic else (chapter.name if chapter else "(Chủ đề không xác định)")
        problem_type_name = primary_problem_type.name if primary_problem_type else "(Dạng bài không xác định)"

        # --- Concept context ---
        concept_context = self._build_concept_context(primary_concept)

        # --- Mastery context ---
        mastery_context = "(Không có dữ liệu mastery)"
        if student_id:
            mastery_context = await self._build_mastery_context(
                student_id,
                primary_problem_type,
                primary_concept,
                concept_ids_for_question,
                problem_type_ids_for_question,
            )

        # --- Question context ---
        question_context = self._build_question_context(question)

        # --- Recent attempts context ---
        recent_attempts_context = "(Không có lịch sử làm bài gần đây)"
        if student_id and question:
            recent_attempts_context = self._build_recent_attempts_context(student_id, question.id)

        # --- RAG context ---
        rag_context = "(Không có tài liệu tham khảo liên quan)"
        if gateway:
            rag_context = await self._build_rag_context(
                query=request.message,
                subject=subject,
                gateway=gateway,
            )

        # --- Misconceptions context ---
        # Currently derived from recent low-confidence attempts; future: dedicated misconception table
        misconceptions_context = self._build_misconceptions_context(
            student_id, concept_ids_for_question
        )

        return TutorContextData(
            student_name=student_name,
            grade_level=grade_level,
            subject_name=subject_name,
            topic_name=topic_name,
            problem_type_name=problem_type_name,
            concept_context=concept_context,
            mastery_context=mastery_context,
            misconceptions_context=misconceptions_context,
            question_context=question_context,
            recent_attempts_context=recent_attempts_context,
            rag_context=rag_context,
            session_summary=request.session_summary or "(Không có tóm tắt phiên học)",
            student_query=request.message,
        )

    # ------------------------------------------------------------------ helpers

    def _build_concept_context(self, concept: Concept | None) -> str:
        if not concept:
            return "(Không có thông tin khái niệm cụ thể)"
        lines = [f"- Khái niệm: {concept.name} (mã: {concept.code})"]
        if concept.description:
            lines.append(f"  Mô tả: {concept.description}")

        # Prerequisite concepts
        prereq_relations = self.session.execute(
            select(ConceptRelation).where(
                ConceptRelation.target_concept_id == concept.id,
                ConceptRelation.relation_type == RelationType.PREREQUISITE,
            )
        ).scalars().all()
        if prereq_relations:
            prereq_concepts = [
                self.session.get(Concept, r.source_concept_id) for r in prereq_relations
            ]
            prereq_names = [f"{c.name} ({c.code})" for c in prereq_concepts if c]
            if prereq_names:
                lines.append(f"  Kiến thức tiên quyết: {', '.join(prereq_names)}")

        return "\n".join(lines)

    async def _build_mastery_context(
        self,
        student_id: UUID,
        primary_problem_type: ProblemType | None,
        primary_concept: Concept | None,
        concept_ids: list[UUID],
        problem_type_ids: list[UUID],
    ) -> str:
        lines: list[str] = []

        # Problem type mastery
        if primary_problem_type:
            ptm = self.session.get(
                StudentProblemTypeMastery, (student_id, primary_problem_type.id)
            )
            if ptm:
                label = _mastery_label(ptm.mastery_score)
                lines.append(
                    f"- Dạng bài [{primary_problem_type.name}]: "
                    f"{label} (điểm={ptm.mastery_score:.2f}, độ tin cậy={ptm.confidence:.2f}, "
                    f"{ptm.correct_count}/{ptm.attempt_count} đúng)"
                )
            else:
                lines.append(f"- Dạng bài [{primary_problem_type.name}]: Chưa có dữ liệu")

        # Concept mastery + prerequisite gap detection
        all_concept_ids = list(dict.fromkeys(concept_ids))  # dedup, preserve order
        if primary_concept and primary_concept.id not in all_concept_ids:
            all_concept_ids.insert(0, primary_concept.id)

        # Also fetch prerequisite concept mastery
        prereq_concept_ids: list[UUID] = []
        if primary_concept:
            prereq_relations = self.session.execute(
                select(ConceptRelation).where(
                    ConceptRelation.target_concept_id == primary_concept.id,
                    ConceptRelation.relation_type == RelationType.PREREQUISITE,
                )
            ).scalars().all()
            prereq_concept_ids = [r.source_concept_id for r in prereq_relations]

        for cid in all_concept_ids + [p for p in prereq_concept_ids if p not in all_concept_ids]:
            concept_obj = self.session.get(Concept, cid)
            if not concept_obj:
                continue
            scm = self.session.get(StudentConceptMastery, (student_id, cid))
            is_prereq = cid in prereq_concept_ids
            tag = " [TIÊN QUYẾT]" if is_prereq else ""
            if scm:
                label = _mastery_label(scm.mastery_score)
                gap_warn = " ⚠️ CẦN CỦNG CỐ" if is_prereq and scm.mastery_score < _MASTERY_LOW else ""
                lines.append(
                    f"- Khái niệm [{concept_obj.name}]{tag}: "
                    f"{label} (điểm={scm.mastery_score:.2f}{gap_warn})"
                )
            else:
                lines.append(f"- Khái niệm [{concept_obj.name}]{tag}: Chưa có dữ liệu")

        return "\n".join(lines) if lines else "(Chưa có dữ liệu mastery)"

    def _build_question_context(self, question: Question | None) -> str:
        if not question:
            return "(Không có câu hỏi cụ thể)"
        lines = [
            f"- Nội dung câu hỏi: {question.content}",
            f"- Dạng câu hỏi: {question.question_type}",
            f"- Độ khó: {question.difficulty:.2f}",
        ]
        if question.explanation:
            lines.append(f"- Gợi ý giải thích (dành cho gia sư): {question.explanation}")
        return "\n".join(lines)

    def _build_recent_attempts_context(self, student_id: UUID, question_id: UUID) -> str:
        attempts = self.session.execute(
            select(QuestionAttempt)
            .where(
                QuestionAttempt.student_id == student_id,
                QuestionAttempt.question_id == question_id,
            )
            .order_by(QuestionAttempt.created_at.desc())
            .limit(_RECENT_ATTEMPTS_LIMIT)
        ).scalars().all()

        if not attempts:
            return "(Chưa có lần làm bài nào cho câu hỏi này)"

        lines: list[str] = []
        for i, attempt in enumerate(attempts, 1):
            result = "✅ Đúng" if attempt.is_correct else "❌ Sai"
            score_txt = f", điểm={attempt.score:.2f}" if attempt.score is not None else ""
            answer_txt = attempt.student_answer[:100] if attempt.student_answer else "(không có)"
            line = f"  Lần {i}: {result}{score_txt} | Câu trả lời: {answer_txt}"
            # Include AI evaluation reason if available
            if attempt.evaluation_details and isinstance(attempt.evaluation_details, dict):
                reason = attempt.evaluation_details.get("reason", "")
                if reason:
                    line += f"\n    → Nhận xét AI: {reason[:200]}"
            lines.append(line)

        return "\n".join(lines)

    def _build_misconceptions_context(
        self, student_id: UUID | None, concept_ids: list[UUID]
    ) -> str:
        """Derive misconceptions from low-mastery concepts.

        Future: can be upgraded to query a dedicated misconception table.
        """
        if not student_id or not concept_ids:
            return "(Không có thông tin về hiểu nhầm)"

        lines: list[str] = []
        for cid in concept_ids:
            scm = self.session.get(StudentConceptMastery, (student_id, cid))
            if scm and scm.mastery_score < _MASTERY_LOW and scm.attempt_count >= 3:
                concept_obj = self.session.get(Concept, cid)
                if concept_obj:
                    lines.append(
                        f"- [{concept_obj.name}]: điểm thấp liên tục "
                        f"({scm.mastery_score:.2f}), có thể có hiểu nhầm cơ bản."
                    )

        return "\n".join(lines) if lines else "(Không phát hiện hiểu nhầm rõ ràng)"

    async def _build_rag_context(
        self,
        query: str,
        subject: Subject | None,
        gateway,  # AIGateway
    ) -> str:
        try:
            from app.rag.embedding_service import EmbeddingService
            from app.rag.search_service import SemanticSearchService

            embedding_svc = EmbeddingService(gateway)
            search_svc = SemanticSearchService(self.session, embedding_svc)
            results = await search_svc.semantic_search(
                query=query,
                subject_id=subject.id if subject else None,
                top_k=_RAG_TOP_K,
            )
            if not results:
                return "(Không tìm thấy tài liệu tham khảo liên quan)"

            lines: list[str] = []
            for i, item in enumerate(results, 1):
                safe_content = item.content[:400].strip()
                lines.append(f"[{i}] {safe_content}")
            return "\n\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RAG context build failed: %s", exc)
            return "(Không thể tải tài liệu tham khảo)"
