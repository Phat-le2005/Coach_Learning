from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.misconceptions.models import MisconceptionDefinition
from app.seed_service import SeedService
from data.seed.identifiers import stable_id
from data.seed.misconceptions import MISCONCEPTIONS


def test_grade_12_misconception_taxonomy_has_stable_ids_and_is_idempotent(
    db_session: Session, seed_settings: Settings
) -> None:
    first = SeedService(db_session, seed_settings).seed().to_dict()
    definitions = list(
        db_session.scalars(
            select(MisconceptionDefinition).order_by(MisconceptionDefinition.code)
        )
    )

    assert first["misconception_definitions"]["created"] == len(MISCONCEPTIONS)
    assert len(definitions) == len(MISCONCEPTIONS)
    assert {item.code for item in definitions} == {
        item.code for item in MISCONCEPTIONS
    }
    assert all(
        item.id == stable_id("misconception-definition", item.code)
        for item in definitions
    )
    assert any(item.problem_type_id is None for item in definitions)
    assert any(item.problem_type_id is not None for item in definitions)

    second = SeedService(db_session, seed_settings).seed().to_dict()
    assert second["misconception_definitions"] == {
        "unchanged": len(MISCONCEPTIONS)
    }
