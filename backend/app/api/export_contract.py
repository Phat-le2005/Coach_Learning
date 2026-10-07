import hashlib
import json
from pathlib import Path
from typing import Any

from app.application import create_app
from app.core.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = BACKEND_DIR / "contracts"
OPENAPI_JSON_PATH = CONTRACTS_DIR / "openapi-v1.json"
OPENAPI_SHA256_PATH = CONTRACTS_DIR / "openapi-v1.sha256"


def get_deterministic_schema() -> dict[str, Any]:
    settings = Settings(
        app_env="test",
        database_name="edums_test",
        database_user="edums_test",
        jwt_secret_key="01234567890123456789012345678901",
    )
    app = create_app(settings)
    return app.openapi()


def compute_compact_sha256(schema: dict[str, Any]) -> str:
    compact_bytes = json.dumps(
        schema,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(compact_bytes).hexdigest()


def export_contract() -> None:
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    schema = get_deterministic_schema()

    serialized = (
        json.dumps(
            schema,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )

    OPENAPI_JSON_PATH.write_text(serialized, encoding="utf-8", newline="\n")

    digest = compute_compact_sha256(schema)
    OPENAPI_SHA256_PATH.write_text(f"{digest}\n", encoding="utf-8", newline="\n")

    print(f"Exported contract to {OPENAPI_JSON_PATH}")
    print(f"Generated SHA-256 ({digest}) to {OPENAPI_SHA256_PATH}")


if __name__ == "__main__":
    export_contract()
