import json
from pathlib import Path
from typing import Any

from app.api.export_contract import compute_compact_sha256
from app.api.v2.application import create_v2_app
from app.core.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = BACKEND_DIR / "contracts"
OPENAPI_V2_JSON_PATH = CONTRACTS_DIR / "openapi-v2.json"
OPENAPI_V2_SHA256_PATH = CONTRACTS_DIR / "openapi-v2.sha256"


def get_v2_contract_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_name="EduMS",
        app_env="test",
        debug=False,
        database_name="contract",
        database_user="contract",
        database_password="",
        jwt_secret_key="01234567890123456789012345678901",
        frontend_url="http://localhost:3000",
        ai_provider="mock",
    )


def get_v2_deterministic_schema() -> dict[str, Any]:
    return create_v2_app(get_v2_contract_settings()).openapi()


def export_v2_contract() -> None:
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    schema = get_v2_deterministic_schema()
    serialized = json.dumps(
        schema, indent=2, sort_keys=True, ensure_ascii=False
    ) + "\n"
    OPENAPI_V2_JSON_PATH.write_text(serialized, encoding="utf-8", newline="\n")
    digest = compute_compact_sha256(schema)
    OPENAPI_V2_SHA256_PATH.write_text(f"{digest}\n", encoding="utf-8", newline="\n")
    print(f"Exported API v2 contract to {OPENAPI_V2_JSON_PATH}")
    print(f"Generated API v2 SHA-256 ({digest}) to {OPENAPI_V2_SHA256_PATH}")


if __name__ == "__main__":
    export_v2_contract()