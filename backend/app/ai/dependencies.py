from functools import lru_cache
from fastapi import Depends

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.ai.provider import AIProvider
from app.core.config import Settings, get_settings


def create_ai_provider(settings: Settings) -> AIProvider:
    """Factory creating AIProvider based on AI_PROVIDER environment setting."""
    provider_name = settings.ai_provider.lower().strip()
    if provider_name == "mock":
        return MockAIProvider()
    # EduMS does NOT run local models. Other providers (Gemini, OpenAI) can be registered here.
    # By default, falls back to MockAIProvider if provider is unrecognized.
    return MockAIProvider()


_GATEWAY_CACHE: dict[int, AIGateway] = {}


def get_ai_gateway_singleton(settings: Settings) -> AIGateway:
    """Cached gateway instance for the application lifecycle."""
    cache_key = id(settings)
    if cache_key not in _GATEWAY_CACHE:
        provider = create_ai_provider(settings)
        _GATEWAY_CACHE[cache_key] = AIGateway(provider=provider, settings=settings)
    return _GATEWAY_CACHE[cache_key]


def get_ai_gateway(settings: Settings = Depends(get_settings)) -> AIGateway:
    """FastAPI dependency for accessing AIGateway."""
    return get_ai_gateway_singleton(settings)
