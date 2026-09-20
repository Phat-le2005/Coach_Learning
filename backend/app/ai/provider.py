from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TypeVar
from pydantic import BaseModel

from app.ai.types import AIMessage, AIResponse

T = TypeVar("T", bound=BaseModel)


class AIProvider(ABC):
    """Abstract interface for external AI model providers (Gemini, OpenAI, etc.).
    
    EduMS does NOT run local models. All provider implementations connect to remote APIs
    or supply deterministic mock responses during testing.
    """

    @abstractmethod
    async def generate(
        self,
        messages: list[AIMessage],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 30.0,
    ) -> AIResponse:
        """Generate a standard text response from the model."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[AIMessage],
        schema: type[T],
        model: str,
        *,
        temperature: float = 0.2,
        timeout: float = 30.0,
    ) -> T:
        """Generate structured output adhering to a Pydantic schema."""
        pass

    @abstractmethod
    async def stream(
        self,
        messages: list[AIMessage],
        model: str,
        *,
        temperature: float = 0.7,
        timeout: float = 30.0,
    ) -> AsyncIterator[str]:
        """Stream response tokens or text chunks asynchronously."""
        pass

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        model: str,
        *,
        timeout: float = 30.0,
    ) -> list[list[float]]:
        """Compute vector embeddings for a list of texts."""
        pass
