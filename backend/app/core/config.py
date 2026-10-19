from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    app_name: str = "EduMS"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False

    database_host: str = "localhost"
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(min_length=1)
    database_user: str = Field(min_length=1)
    database_password: SecretStr = SecretStr("")

    backend_host: str = "127.0.0.1"
    backend_port: int = Field(default=8000, ge=1, le=65535)
    frontend_url: AnyHttpUrl = AnyHttpUrl("http://localhost:3000")

    jwt_secret_key: SecretStr = SecretStr("")
    jwt_issuer: str = Field(default="edums", min_length=1)
    jwt_audience: str = Field(default="edums-api", min_length=1)
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30)
    seed_demo_password: SecretStr = SecretStr("")

    # OCR is disabled by default; no mock output is ever served automatically.
    math_ocr_provider: Literal["disabled", "mathpix", "local_rapid", "local_pix2tex", "mock"] = "disabled"
    mathpix_app_id: str = ""
    mathpix_app_key: SecretStr = SecretStr("")
    math_ocr_timeout_seconds: float = Field(default=12.0, ge=1.0, le=30.0)

    ai_provider: str = Field(default="mock", min_length=1)
    ai_api_key: SecretStr = SecretStr("")
    ai_model_fast: str = Field(default="gemini-2.5-flash", min_length=1)
    ai_model_standard: str = Field(default="gemini-2.5-standard", min_length=1)
    ai_model_reasoning: str = Field(default="gemini-2.5-pro", min_length=1)
    ai_embedding_model: str = Field(default="text-embedding-004", min_length=1)
    ai_timeout_seconds: float = Field(default=30.0, ge=0.5, le=300.0)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    ai_rate_limit_per_minute: int = Field(default=20, ge=1, le=600)
    ai_daily_requests_limit_per_student: int = Field(default=100, ge=1, le=10000)
    ai_rag_top_k: int = Field(default=3, ge=1, le=10)
    ai_max_context_chars: int = Field(default=3000, ge=200, le=50000)
    teacher_material_storage_dir: Path = BACKEND_DIR / "var" / "teacher_materials"
    teacher_material_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    question_acquisition_allowed_domains: str = ""
    question_acquisition_storage_dir: Path = BACKEND_DIR / "var" / "question_acquisition"
    question_acquisition_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1)

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if secret and len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes")
        return value

    @field_validator("seed_demo_password")
    @classmethod
    def validate_seed_demo_password(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if secret and len(secret) < 12:
            raise ValueError("SEED_DEMO_PASSWORD must contain at least 12 characters")
        return value

    @field_validator("frontend_url")
    @classmethod
    def validate_frontend_origin(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if (
            value.username is not None
            or value.password is not None
            or value.path not in (None, "/")
            or value.query is not None
            or value.fragment is not None
        ):
            raise ValueError("FRONTEND_URL must be an HTTP(S) origin without credentials or a path")
        return value

    @model_validator(mode="after")
    def validate_production_config(self) -> "Settings":
        if self.app_env == "production":
            jwt_secret = self.jwt_secret_key.get_secret_value()
            if not jwt_secret or len(jwt_secret.encode("utf-8")) < 32:
                raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes in production")
            if self.debug:
                raise ValueError("DEBUG must be false in production")
        return self

    @property
    def frontend_origin(self) -> str:
        return str(self.frontend_url).rstrip("/")

    @property
    def database_url(self) -> URL:
        # URL.create handles reserved characters in credentials without string interpolation.
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
