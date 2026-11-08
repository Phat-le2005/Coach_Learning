"""Logical steps and original ink are preserved before any scoring call."""
from uuid import uuid4
import pytest
import json
from unittest.mock import MagicMock, patch
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkPoint, InkStroke
from app.math_ocr.gemini_adapter import GeminiMathOCRAdapter
from app.math_ocr.step_proposals import map_step_proposals
from app.ai.gemini_provider import _sanitize_schema_for_gemini


def ink(y):
    return InkStroke(id=uuid4(),tool="PEN",color="#000000",width=2,
                     points=[InkPoint(x=.2,y=y),InkPoint(x=.3,y=y+.02)])


def proposal(title, latex, type_, box):
    return {"title":title,"content_kind":"MATH","latex":latex,"explanation_text":None,"suggested_step_type":type_,"box_2d":box}


def examples():
    strokes=[ink(.1),ink(.12),ink(.35),ink(.4),ink(.65),ink(.75)]
    steps=[proposal("Đạo hàm","y'=3x^2-3","DERIVATIVE_CALCULATION",[50,100,200,500]),
           proposal("Tìm nghiệm",r"y'=0 \Leftrightarrow \begin{cases}x=1\\x=-1\end{cases}","ROOT_FINDING",[300,100,500,500]),
           proposal("Bảng biến thiên",r"\begin{array}{c|ccc}x&-1&1&+\infty\\y'&0&0&+\end{array}","VARIATION_TABLE",[600,100,850,600])]
    return strokes,steps


def test_three_logical_steps_keep_root_cases_and_table_together():
    strokes,steps=examples()
    result=map_step_proposals(steps,strokes,(0,0,794,1123))
    assert [step.suggested_step_type for step in result]==["DERIVATIVE_CALCULATION","ROOT_FINDING","VARIATION_TABLE"]
    assert [step.source_stroke_ids for step in result]==[[s.id for s in strokes[i:i+2]] for i in (0,2,4)]
    assert "begin{cases}" in result[1].latex and "begin{array}" in result[2].latex
    assert len({id for step in result for id in step.source_stroke_ids})==len(strokes)


def test_cropped_image_coordinates_are_mapped_back_to_original_page():
    strokes=[ink(.3),ink(.7)]
    steps=[proposal("Một","2+2=5","CUSTOM",[0,0,300,1000]),proposal("Hai","x=1","ROOT_FINDING",[700,0,1000,1000])]
    result=map_step_proposals(steps,strokes,(100,250,400,600))
    assert result[0].source_stroke_ids==[strokes[0].id]
    assert result[1].source_stroke_ids==[strokes[1].id]
    assert result[0].latex=="2+2=5"  # OCR does not repair mathematics.


@pytest.mark.parametrize("invalid",[[],[{"title":"bad"}],None])
def test_invalid_proposals_keep_ocr_text_with_an_explicit_warning(invalid):
    strokes,_=examples()
    result=GeminiMathOCRAdapter._to_response({"latex":"y'=3x^2-3","steps":invalid},strokes,crop_box=(0,0,794,1123))
    assert result.latex=="y'=3x^2-3"
    assert not result.steps and result.segmentation_warning


def test_empty_hallucinated_region_cannot_become_a_grading_step():
    strokes,steps=examples()
    steps.append(proposal("Không có nét", "x=100", "CONCLUSION",[900,900,1000,1000]))
    with pytest.raises(ValueError,match="no supporting"):
        map_step_proposals(steps,strokes,(0,0,794,1123))


def test_nearby_unboxed_ink_is_retained_in_exactly_one_proposal():
    strokes,steps=examples()
    between=ink(.27)
    strokes.append(between)
    result=map_step_proposals(steps,strokes,(0,0,794,1123))
    ids=[id for step in result for id in step.source_stroke_ids]
    assert len(ids)==len(set(ids))==len(strokes)
    assert between.id in ids


def test_generated_schema_preserves_required_data_named_title():
    from app.math_ocr.gemini_adapter import GeminiOCRJsonOutput
    schema=_sanitize_schema_for_gemini(GeminiOCRJsonOutput.model_json_schema())
    step=schema["properties"]["steps"]["items"]
    assert "title" in step["properties"] and "title" in step["required"]
    assert set(step["required"])<=set(step["properties"])


def test_busy_primary_uses_configured_gemini_fallback_with_same_step_schema():
    settings=Settings(_env_file=None,database_name="test",database_user="test",ai_api_key="fixture-key",
                      gemini_ocr_model="configured-primary",ai_model_fast="configured-fallback")
    adapter=GeminiMathOCRAdapter(settings=settings)
    strokes,_=examples()
    class Busy(RuntimeError): code=503
    client=MagicMock()
    client.models.generate_content.side_effect=[Busy("Busy"),MagicMock(text=json.dumps({"latex":"x=1","steps":[proposal("Tìm nghiệm","x=1","ROOT_FINDING",[0,0,1000,1000])]}))]
    with patch("app.math_ocr.gemini_adapter._get_genai_client",return_value=client):
        response=adapter.recognize(strokes)
    calls=client.models.generate_content.call_args_list
    assert [call.kwargs["model"] for call in calls]==["configured-primary","configured-fallback"]
    assert "title" in calls[0].kwargs["config"].response_json_schema["properties"]["steps"]["items"]["properties"]
    assert response.steps and set(response.steps[0].source_stroke_ids)=={s.id for s in strokes}


def test_quota_error_stops_without_multiplying_requests_across_models():
    settings=Settings(_env_file=None,database_name="test",database_user="test",ai_api_key="fixture-key")
    adapter=GeminiMathOCRAdapter(settings=settings)
    class Quota(RuntimeError): code=429
    client=MagicMock();client.models.generate_content.side_effect=Quota("Quota")
    with patch("app.math_ocr.gemini_adapter._get_genai_client",return_value=client):
        with pytest.raises(ApplicationError) as error:
            adapter.recognize(examples()[0])
    assert error.value.code=="OCR_RATE_LIMITED"
    assert client.models.generate_content.call_count==1
