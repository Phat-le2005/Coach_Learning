from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.ai.dependencies import get_ai_gateway_singleton
from app.ai.gateway import AIGateway
from app.ai.prompt_registry import PromptRegistry
from app.ai.types import AIMessage, AIRole, AITaskType
from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import ProblemType, Topic
from app.questions.models import Question
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.tutor.memory_validator import MemoryValidator
from app.tutor.models import (
    LearningMemoryType,
    StudentLearningMemory,
    TutorSession,
    TutorSessionStatus,
    TutorSessionSummary,
)
from app.tutor.schemas import (
    MemoryExtractionAIOutput,
    ProposedMemoryItem,
    TutorSessionCreate,
    TutorSessionEndRequest,
)
from app.users.models import User

logger = logging.getLogger(__name__)

_PROMPT_NAME = "memory_extractor"
_PROMPT_VERSION = "v1"


class MemoryService:
    """Service responsible for extracting, validating, persisting, and querying student learning memories."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._registry = PromptRegistry()

    def get_relevant_memories(
        self,
        student_id: UUID,
        *,
        subject_id: UUID | None = None,
        problem_type_id: UUID | None = None,
        concept_ids: list[UUID] | None = None,
        limit: int = 5,
    ) -> list[StudentLearningMemory]:
        """Fetch strictly relevant long-term memories for a tutoring prompt.
        
        Rules:
        - Includes general learning and tutoring preferences (LEARNING_PREFERENCE, TUTORING_PREFERENCE, IMPORTANT_ACADEMIC_GOAL).
        - Includes difficulties/misconceptions ONLY if linked to the current problem type or concepts.
        - Never leaks difficulties from completely unrelated subjects.
        """
        all_active_stmt = (
            select(StudentLearningMemory)
            .where(
                StudentLearningMemory.student_id == student_id,
                StudentLearningMemory.is_active.is_(True),
            )
            .order_by(StudentLearningMemory.confidence.desc(), StudentLearningMemory.last_confirmed_at.desc())
        )
        candidates = self.session.scalars(all_active_stmt).all()

        relevant: list[StudentLearningMemory] = []
        pref_count = 0
        diff_count = 0

        target_concept_ids = set(concept_ids or [])

        for m in candidates:
            if m.type in (
                LearningMemoryType.LEARNING_PREFERENCE,
                LearningMemoryType.TUTORING_PREFERENCE,
                LearningMemoryType.IMPORTANT_ACADEMIC_GOAL,
            ):
                if pref_count < 3:
                    relevant.append(m)
                    pref_count += 1
            elif m.type in (
                LearningMemoryType.PERSISTENT_DIFFICULTY,
                LearningMemoryType.PERSISTENT_MISCONCEPTION,
            ):
                # Only include if specifically matching current problem type or current concepts
                is_match = False
                if problem_type_id is not None and m.problem_type_id == problem_type_id:
                    is_match = True
                elif m.concept_id is not None and m.concept_id in target_concept_ids:
                    is_match = True

                if is_match and diff_count < 2:
                    relevant.append(m)
                    diff_count += 1

            if len(relevant) >= limit:
                break

        return relevant

    def list_memories(
        self,
        student_id: UUID,
        *,
        memory_type: LearningMemoryType | None = None,
    ) -> list[StudentLearningMemory]:
        """List active memories for a student."""
        stmt = (
            select(StudentLearningMemory)
            .where(
                StudentLearningMemory.student_id == student_id,
                StudentLearningMemory.is_active.is_(True),
            )
            .order_by(StudentLearningMemory.last_confirmed_at.desc())
        )
        if memory_type:
            stmt = stmt.where(StudentLearningMemory.type == memory_type)
        return list(self.session.scalars(stmt).all())

    def delete_memory(self, student_id: UUID, memory_id: UUID) -> bool:
        """Soft-delete / deactivate a memory item by the student."""
        m = self.session.get(StudentLearningMemory, memory_id)
        if not m or m.student_id != student_id:
            return False
        m.is_active = False
        self.session.commit()
        return True

    async def extract_and_persist_async(
        self,
        tutor_session: TutorSession,
        summary_text: str | None = None,
        gateway: AIGateway | None = None,
    ) -> tuple[str, list[str], list[StudentLearningMemory]]:
        """Extract and persist memories using AI Gateway, with strict backend validation and fallback."""
        gw = gateway or get_ai_gateway_singleton()

        # Build context for memory extractor prompt
        student_prof = self.session.get(StudentProfile, tutor_session.student_id)
        student_user = self.session.get(User, student_prof.user_id) if (student_prof and student_prof.user_id) else None
        student_name = student_user.full_name if student_user else "Học sinh"
        grade_level = str(student_prof.grade_level) if student_prof else "12"

        subject_obj = self.session.get(Subject, tutor_session.subject_id) if tutor_session.subject_id else None
        pt_obj = self.session.get(ProblemType, tutor_session.problem_type_id) if tutor_session.problem_type_id else None
        concept_obj = self.session.get(Concept, tutor_session.concept_id) if tutor_session.concept_id else None
        topic_obj = self.session.get(Topic, pt_obj.topic_id) if (pt_obj and pt_obj.topic_id) else None

        subj_name = subject_obj.name if subject_obj else "Tổng quát"
        topic_name = topic_obj.name if topic_obj else (concept_obj.name if concept_obj else "Tổng quát")
        pt_name = pt_obj.name if pt_obj else (concept_obj.name if concept_obj else "Tổng quát")

        session_turns_summary = (
            summary_text
            or f"Phiên học diễn ra với {tutor_session.turn_count} lượt trao đổi về dạng bài '{pt_name}' môn {subj_name}."
        )

        prompt = self._registry.get_prompt(
            name=_PROMPT_NAME,
            version=_PROMPT_VERSION,
            variables={
                "student_name": student_name,
                "grade_level": grade_level,
                "subject_name": subj_name,
                "topic_name": topic_name,
                "problem_type_name": pt_name,
                "session_turns_summary": session_turns_summary,
            },
        )

        ai_output: MemoryExtractionAIOutput | None = None
        if gw:
            try:
                structured_res = await gw.generate_structured(
                    task_type=AITaskType.MEMORY_EXTRACTION,
                    schema=MemoryExtractionAIOutput,
                    messages=[AIMessage(role=AIRole.USER, content=prompt)],
                    temperature=0.3,
                    prompt_name=_PROMPT_NAME,
                    prompt_version=_PROMPT_VERSION,
                    user_id=student_prof.user_id if student_prof else None,
                )
                ai_output = structured_res.data
            except Exception as exc:  # noqa: BLE001
                logger.warning("AI Memory Extractor failed: %s; falling back to deterministic synthesis.", exc)

        if not ai_output:
            ai_output = self._deterministic_fallback_extraction(
                tutor_session, subj_name, pt_name, session_turns_summary
            )

        # Strictly validate each proposed memory item
        saved_memories: list[StudentLearningMemory] = []
        now_dt = datetime.now(timezone.utc)

        for prop in ai_output.proposed_memories:
            # Pass default session IDs if absent
            if not prop.problem_type_id and tutor_session.problem_type_id:
                prop.problem_type_id = tutor_session.problem_type_id
            if not prop.concept_id and tutor_session.concept_id:
                prop.concept_id = tutor_session.concept_id

            v_res = MemoryValidator.validate(prop, self.session)
            if not v_res.is_valid:
                logger.info(
                    "Rejected proposed memory for student=%s: %s (Reason: %s)",
                    tutor_session.student_id,
                    prop.value,
                    v_res.reason,
                )
                continue

            # Deduplication & Update check
            existing = self._find_existing_memory(tutor_session.student_id, prop)
            if existing:
                existing.last_confirmed_at = now_dt
                existing.confidence = max(existing.confidence, prop.confidence)
                if len(prop.value) > len(existing.value):
                    existing.value = prop.value
                saved_memories.append(existing)
            else:
                new_mem = StudentLearningMemory(
                    student_id=tutor_session.student_id,
                    type=prop.type,
                    value=prop.value.strip(),
                    confidence=prop.confidence,
                    problem_type_id=prop.problem_type_id,
                    concept_id=prop.concept_id,
                    source_session_id=tutor_session.id,
                    created_at=now_dt,
                    last_confirmed_at=now_dt,
                    is_active=True,
                )
                self.session.add(new_mem)
                saved_memories.append(new_mem)

        self.session.commit()
        return ai_output.session_summary, ai_output.key_takeaways, saved_memories

    def _find_existing_memory(
        self, student_id: UUID, item: ProposedMemoryItem
    ) -> StudentLearningMemory | None:
        """Find an existing active memory for the student with matching type and topic."""
        stmt = select(StudentLearningMemory).where(
            StudentLearningMemory.student_id == student_id,
            StudentLearningMemory.type == item.type,
            StudentLearningMemory.is_active.is_(True),
        )
        candidates = self.session.scalars(stmt).all()

        val_lower = item.value.strip().lower()

        for c in candidates:
            # Match by identical foreign keys
            if (
                item.problem_type_id and c.problem_type_id == item.problem_type_id
            ) or (
                item.concept_id and c.concept_id == item.concept_id
            ):
                return c

            # Match by high semantic text overlap
            c_val_lower = c.value.strip().lower()
            if val_lower == c_val_lower or val_lower in c_val_lower or c_val_lower in val_lower:
                return c

        return None

    def _deterministic_fallback_extraction(
        self,
        tutor_session: TutorSession,
        subject_name: str,
        problem_type_name: str,
        session_summary: str,
    ) -> MemoryExtractionAIOutput:
        """High-reliability fallback when AI Gateway is offline."""
        summary = (
            f"Phiên gia sư môn {subject_name} về chủ đề '{problem_type_name}'. "
            f"Học sinh đã hoàn thành {tutor_session.turn_count} lượt trao đổi định hướng Socratic."
        )
        takeaways = [
            f"Củng cố phương pháp tiếp cận cho {problem_type_name}",
            f"Rèn luyện tư duy tự giải quyết vấn đề theo hướng dẫn của gia sư",
        ]
        proposed: list[ProposedMemoryItem] = []

        # If turn count is significant, record a tutoring preference
        if tutor_session.turn_count >= 3:
            proposed.append(
                ProposedMemoryItem(
                    type=LearningMemoryType.TUTORING_PREFERENCE,
                    value="Ưa thích phương pháp gợi ý từng bước qua câu hỏi dẫn dắt Socratic",
                    confidence=0.85,
                    reasoning="Tương tác tích cực qua nhiều lượt hội thoại Socratic",
                )
            )

        return MemoryExtractionAIOutput(
            session_summary=summary,
            key_takeaways=takeaways,
            proposed_memories=proposed,
        )


class TutorSessionService:
    """Manages the full lifecycle of AI Tutoring sessions."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.memory_service = MemoryService(session)

    def create_session(
        self,
        student_id: UUID,
        payload: TutorSessionCreate,
    ) -> TutorSession:
        """Create a new active tutoring session."""
        now_dt = datetime.now(timezone.utc)
        t_session = TutorSession(
            student_id=student_id,
            subject_id=payload.subject_id,
            problem_type_id=payload.problem_type_id,
            concept_id=payload.concept_id,
            question_id=payload.question_id,
            started_at=now_dt,
            turn_count=0,
            status=TutorSessionStatus.ACTIVE,
        )
        self.session.add(t_session)
        self.session.commit()
        self.session.refresh(t_session)
        return t_session

    def record_turn(self, session_id: UUID) -> TutorSession | None:
        """Increment interaction turn counter for an ongoing session."""
        t_session = self.session.get(TutorSession, session_id)
        if not t_session or t_session.status != TutorSessionStatus.ACTIVE:
            return None
        t_session.turn_count += 1
        t_session.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        return t_session

    async def end_session_async(
        self,
        session_id: UUID,
        student_id: UUID,
        req: TutorSessionEndRequest | None = None,
        gateway: AIGateway | None = None,
    ) -> tuple[TutorSession, TutorSessionSummary, list[StudentLearningMemory]]:
        """End tutoring session, synthesize academic summary, and extract long-term memories."""
        t_session = self.session.get(TutorSession, session_id)
        if not t_session:
            raise ApplicationError(f"TutorSession {session_id} không tồn tại.")
        if t_session.student_id != student_id:
            raise ApplicationError("Bạn không có quyền thao tác trên phiên học này.")

        now_dt = datetime.now(timezone.utc)
        t_session.ended_at = now_dt
        t_session.status = TutorSessionStatus.COMPLETED

        resolved_count = req.resolved_questions_count if req else 0
        manual_summary = req.summary_text if req else None

        # Extract memories and generate summary
        summary_text, takeaways, saved_memories = await self.memory_service.extract_and_persist_async(
            t_session, summary_text=manual_summary, gateway=gateway
        )

        # Create or update summary record
        existing_summary = self.session.execute(
            select(TutorSessionSummary).where(TutorSessionSummary.session_id == session_id)
        ).scalar_one_or_none()

        if existing_summary:
            existing_summary.summary_text = summary_text
            existing_summary.key_takeaways = takeaways
            existing_summary.resolved_questions_count = resolved_count
            session_summary = existing_summary
        else:
            session_summary = TutorSessionSummary(
                session_id=session_id,
                student_id=student_id,
                summary_text=summary_text,
                key_takeaways=takeaways,
                resolved_questions_count=resolved_count,
                created_at=now_dt,
            )
            self.session.add(session_summary)

        self.session.commit()
        self.session.refresh(t_session)
        self.session.refresh(session_summary)
        return t_session, session_summary, saved_memories
