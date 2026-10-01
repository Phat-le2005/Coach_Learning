import json
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.ai.gateway import AIGateway
from app.ai.prompt_registry import default_prompt_registry
from app.ai.tool_policy import AIToolPolicy
from app.ai.types import AITaskType
from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.teacher_materials.ai_schemas import TeacherMaterialMappingAIOutput
from app.teacher_materials.models import MaterialMappingSource, MaterialMappingStatus, TeacherMaterialItem, TeacherMaterialItemConcept, TeacherMaterialItemLearningOutcome, TeacherMaterialItemProblemType

class TeacherMaterialMappingService:
    def __init__(self, session: Session) -> None: self.session = session

    async def propose(self, item: TeacherMaterialItem, gateway: AIGateway, user_id: UUID) -> TeacherMaterialMappingAIOutput:
        subject_id = item.material.subject_id
        pts = list(self.session.scalars(select(ProblemType).join(Topic).join(Chapter).where(Chapter.subject_id == subject_id, ProblemType.is_active.is_(True))))
        concepts = list(self.session.scalars(select(Concept).where(Concept.subject_id == subject_id)))
        outcomes = list(self.session.scalars(select(LearningOutcome).where(LearningOutcome.subject_id == subject_id)))
        catalogs = {"problem_types": [{"id": str(x.id), "code": x.code, "name": x.name} for x in pts], "concepts": [{"id": str(x.id), "code": x.code, "name": x.name} for x in concepts], "learning_outcomes": [{"id": str(x.id), "code": x.code, "description": x.description} for x in outcomes]}
        passive = AIToolPolicy.format_rag_data([{"title": "Uploaded teacher material", "content": AIToolPolicy.sanitize_prompt(item.content, strict=False)}])
        prompt = default_prompt_registry.get_prompt("teacher_material_mapper", variables={"untrusted_item": passive, "question_type": item.question_type.value if item.question_type else "UNKNOWN", "candidate_catalog": json.dumps(catalogs, ensure_ascii=False)})
        response = await gateway.generate_structured(AITaskType.TEACHER_MATERIAL_MAPPING, TeacherMaterialMappingAIOutput, prompt, prompt_name="teacher_material_mapper", user_id=user_id, check_injection=False)
        self.persist_suggestions(item, response.data, pts, concepts, outcomes)
        return response.data

    def persist_suggestions(self, item: TeacherMaterialItem, output: TeacherMaterialMappingAIOutput, pts: list[ProblemType], concepts: list[Concept], outcomes: list[LearningOutcome]) -> None:
        catalogs = [(output.problem_types, {x.code: x for x in pts}, TeacherMaterialItemProblemType, "problem_type_id"), (output.concepts, {x.code: x for x in concepts}, TeacherMaterialItemConcept, "concept_id"), (output.learning_outcomes, {x.code: x for x in outcomes}, TeacherMaterialItemLearningOutcome, "learning_outcome_id")]
        for proposals, allowed, model, field in catalogs:
            for proposal in proposals:
                target = allowed.get(proposal.code)
                if target is None: raise ApplicationError(422, "AI_MAPPING_UNKNOWN_CODE", f"AI returned an unprovided canonical code: {proposal.code}")
                values = {"item_id": item.id, field: target.id, "weight": proposal.weight, "confidence": proposal.confidence, "is_primary": proposal.is_primary, "source": MaterialMappingSource.AI, "status": MaterialMappingStatus.SUGGESTED, "rationale": proposal.rationale}
                existing = self.session.scalar(select(model).where(model.item_id == item.id, getattr(model, field) == target.id))
                if existing is None: self.session.add(model(**values))
        self.session.flush()
