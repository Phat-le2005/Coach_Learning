"""StudentTutorService — orchestrates context building and AI call for the Socratic AI Tutor.

GUARDRAILS:
- NEVER writes to the database (read-only).
- NEVER updates mastery, study plan, or teaching plan.
- NEVER invents student facts.
- Falls back gracefully if AI is unavailable (returns placeholder message).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.prompt_registry import PromptRegistry
from app.ai.tutor_context_builder import TutorContextBuilder
from app.ai.tutor_schemas import TutorContextData, TutorRequest, TutorResponse
from app.ai.types import AITaskType
from app.users.models import User

logger = logging.getLogger(__name__)

_PROMPT_NAME = "student_tutor"
_PROMPT_VERSION = "v1"

_FALLBACK_MESSAGE = (
    "Xin lỗi em, gia sư AI hiện không khả dụng. "
    "Em hãy hỏi thầy/cô giáo để được hỗ trợ nhé!"
)


class StudentTutorService:
    """Builds context, renders prompt, calls AI, and returns tutor reply.

    This service is completely read-only with respect to the database.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self._context_builder = TutorContextBuilder(session)
        self._registry = PromptRegistry()

    async def tutor(
        self,
        *,
        student_user: User,
        gateway: AIGateway,
        request: TutorRequest,
    ) -> TutorResponse:
        """Non-streaming tutor response."""
        context = await self._context_builder.build_context(
            student_user, request, gateway=gateway
        )
        prompt = self._render_prompt(context)
        metadata = self._build_metadata(context, request)

        try:
            response = await gateway.generate(
                task_type=AITaskType.TUTOR,
                messages=prompt,
                temperature=0.7,
                prompt_name=_PROMPT_NAME,
                prompt_version=_PROMPT_VERSION,
                user_id=student_user.id,
            )
            reply = response.content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "StudentTutorService.tutor: AI call failed for user=%s: %s",
                student_user.id,
                exc,
            )
            reply = _FALLBACK_MESSAGE

        return TutorResponse(reply=reply, metadata=metadata)

    async def tutor_stream(
        self,
        *,
        student_user: User,
        gateway: AIGateway,
        request: TutorRequest,
    ) -> AsyncIterator[str]:
        """Streaming tutor response — yields text chunks."""
        context = await self._context_builder.build_context(
            student_user, request, gateway=gateway
        )
        prompt = self._render_prompt(context)

        try:
            async for chunk in gateway.stream(
                task_type=AITaskType.TUTOR,
                messages=prompt,
                temperature=0.7,
            ):
                yield chunk
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "StudentTutorService.tutor_stream: stream failed for user=%s: %s",
                student_user.id,
                exc,
            )
            yield _FALLBACK_MESSAGE

    # ------------------------------------------------------------------ helpers

    def _render_prompt(self, context: TutorContextData) -> str:
        """Render the versioned prompt template with validated variables."""
        variables = context.to_prompt_variables()
        return self._registry.get_prompt(
            name=_PROMPT_NAME,
            version=_PROMPT_VERSION,
            variables=variables,
        )

    def _build_metadata(self, context: TutorContextData, request: TutorRequest) -> dict:
        """Non-sensitive metadata included in non-streaming response."""
        return {
            "subject": context.subject_name,
            "topic": context.topic_name,
            "problem_type": context.problem_type_name,
            "prompt_name": _PROMPT_NAME,
            "prompt_version": _PROMPT_VERSION,
            "has_rag": context.rag_context not in (
                "(Không có tài liệu tham khảo liên quan)",
                "(Không thể tải tài liệu tham khảo)",
                "(Không tìm thấy tài liệu tham khảo liên quan)",
            ),
            "stream": request.stream,
        }
