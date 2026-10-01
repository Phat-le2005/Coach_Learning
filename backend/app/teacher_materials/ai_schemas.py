from pydantic import BaseModel, Field

class ProposedTaxonomyMapping(BaseModel):
    code: str = Field(min_length=1)
    weight: float = Field(gt=0, le=1)
    confidence: float = Field(ge=0, le=1)
    is_primary: bool = False
    rationale: str | None = None

class TeacherMaterialMappingAIOutput(BaseModel):
    problem_types: list[ProposedTaxonomyMapping] = Field(default_factory=list)
    concepts: list[ProposedTaxonomyMapping] = Field(default_factory=list)
    learning_outcomes: list[ProposedTaxonomyMapping] = Field(default_factory=list)
