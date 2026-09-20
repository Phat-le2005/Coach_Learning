import asyncio
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.ai.models import AIRequestLog
from app.ai.prompt_exceptions import PromptNotFoundError, PromptVariableMissingError
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.types import AITaskType
from app.ai.usage_service import AIUsageService
from app.core.config import Settings

EXPECTED_PROMPT_NAMES = [
    "admission_assistant",
    "exam_analyzer",
    "hint_generator",
    "misconception_detector",
    "open_response_evaluator",
    "parent_summary",
    "rag_assistant",
    "student_tutor",
    "study_plan_explainer",
    "teacher_copilot",
]


# --------------------------------------------------------------------------
# 1. Prompt Discovery and Versioning Tests
# --------------------------------------------------------------------------

def test_all_ten_prompts_exist_and_versioned():
    prompts = default_prompt_registry.list_prompts()
    for expected in EXPECTED_PROMPT_NAMES:
        assert expected in prompts, f"Expected prompt directory '{expected}' missing."

    for name in EXPECTED_PROMPT_NAMES:
        versions = default_prompt_registry.list_versions(name)
        assert "v1" in versions, f"Prompt '{name}' must have version 'v1'."


def test_prompt_not_found_raises_exception():
    with pytest.raises(PromptNotFoundError) as exc_info:
        default_prompt_registry.get_prompt("non_existent_prompt", "v1")
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "PROMPT_NOT_FOUND"

    with pytest.raises(PromptNotFoundError) as exc_info_v:
        default_prompt_registry.get_prompt("student_tutor", "v999")
    assert exc_info_v.value.status_code == 404


# --------------------------------------------------------------------------
# 2. Strict Variable Validation Tests
# --------------------------------------------------------------------------

def test_missing_variable_raises_explicit_error():
    required = default_prompt_registry.get_required_variables("student_tutor", "v1")
    assert len(required) > 0

    # Calling with empty variables
    with pytest.raises(PromptVariableMissingError) as exc_info:
        default_prompt_registry.get_prompt("student_tutor", "v1", variables={})
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "MISSING_PROMPT_VARIABLE"
    assert set(exc_info.value.missing_variables) == required

    # Calling with partial variables (missing only one)
    partial = {var: "dummy_value" for var in required}
    missing_one = list(required)[0]
    del partial[missing_one]

    with pytest.raises(PromptVariableMissingError) as exc_partial:
        default_prompt_registry.get_prompt("student_tutor", "v1", variables=partial)
    assert exc_partial.value.missing_variables == [missing_one]


# --------------------------------------------------------------------------
# 3. Successful Rendering Tests
# --------------------------------------------------------------------------

def test_render_all_prompts_with_valid_variables():
    for name in EXPECTED_PROMPT_NAMES:
        required_vars = default_prompt_registry.get_required_variables(name, "v1")
        mock_vars = {var: f"value_for_{var}" for var in required_vars}

        rendered = default_prompt_registry.get_prompt(name, "v1", mock_vars)
        assert rendered is not None
        assert len(rendered) > 50

        # Assert all variable values are present
        for var in required_vars:
            assert f"value_for_{var}" in rendered

        # Assert no dangling unrendered variables
        assert "{" not in rendered, f"Dangling unrendered variable placeholder in {name}"
        assert "}" not in rendered, f"Dangling unrendered variable placeholder in {name}"


# --------------------------------------------------------------------------
# 4. Anti-Hardcoding Curriculum Fact Verification
# --------------------------------------------------------------------------

def test_no_hardcoded_curriculum_facts_in_templates():
    """Verify that templates do not hardcode fixed solutions or static exam questions."""
    for name in EXPECTED_PROMPT_NAMES:
        template_text, _ = default_prompt_registry._load_template(name, "v1")

        # Must not have hard-coded answers
        assert "x = 5" not in template_text
        assert "The answer is" not in template_text
        assert "Đáp án đúng là" not in template_text

        # Must explicitly reference academic context from variables
        assert "{" in template_text and "}" in template_text


# --------------------------------------------------------------------------
# 5. Integration with AIRequestLog Metadata Tracking
# --------------------------------------------------------------------------

def test_gateway_records_prompt_name_and_version(db_session: Session):
    async def _run():
        settings = Settings(
            database_name="test_edums",
            database_user="postgres",
            ai_provider="mock",
        )
        provider = MockAIProvider(default_text="Gợi ý phương trình bậc 2")
        gateway = AIGateway(provider=provider, settings=settings)
        usage_service = AIUsageService(db_session)

        # Render prompt via registry
        prompt_name = "hint_generator"
        prompt_version = "v1"
        required_vars = default_prompt_registry.get_required_variables(prompt_name, prompt_version)
        variables = {
            "question_content": "Giải phương trình 2x^2 + 5x - 3 = 0",
            "problem_type_name": "Phương trình bậc hai",
            "learning_outcome_descriptions": "Biết cách tính delta",
            "hint_level": "1",
            "previous_hints": "Chưa có",
            "student_attempt_answer": "x = 1",
        }
        rendered_prompt = default_prompt_registry.get_prompt(prompt_name, prompt_version, variables)

        # Call AI gateway with prompt metadata and usage service
        resp = await gateway.generate(
            task_type=AITaskType.HINT,
            messages=rendered_prompt,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            usage_service=usage_service,
        )
        db_session.commit()

        assert resp.content == "Gợi ý phương trình bậc 2"

        # Verify AIRequestLog recorded prompt_name and prompt_version
        logs = usage_service.get_logs(task="HINT")
        assert logs.total >= 1
        latest_log = logs.items[0]
        assert latest_log.prompt_name == "hint_generator"
        assert latest_log.prompt_version == "v1"

    asyncio.run(_run())
