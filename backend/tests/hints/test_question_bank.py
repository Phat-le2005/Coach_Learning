from fastapi.testclient import TestClient

from app.users.models import Role
from tests.questions.test_api import multiple_choice_payload


def test_question_bank_stores_predefined_hints_and_blocks_early_answer(
    db_client: TestClient,
    question_user_factory,
    question_bearer,
    math_content,
) -> None:
    teacher = question_user_factory(Role.TEACHER, "hint-author@example.com")
    headers = question_bearer(teacher)
    payload = multiple_choice_payload(*math_content)
    payload["hints"] = [
        {
            "hint_level": "LEVEL_1",
            "content": "Recall the power rule and identify the exponent.",
        },
        {
            "hint_level": "LEVEL_4",
            "content": "The answer is B after applying the power rule.",
        },
    ]
    created = db_client.post("/questions", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    assert [item["hint_level"] for item in created.json()["hints"]] == [
        "LEVEL_1",
        "LEVEL_4",
    ]

    unsafe = multiple_choice_payload(*math_content)
    unsafe["content"] = "A second derivative hint policy question."
    unsafe["hints"] = [
        {"hint_level": "LEVEL_1", "content": "The answer is B."}
    ]
    rejected = db_client.post("/questions", json=unsafe, headers=headers)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "HINT_REVEALS_FINAL_ANSWER"
