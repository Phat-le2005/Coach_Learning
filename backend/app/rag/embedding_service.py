from app.ai.gateway import AIGateway
from app.ai.provider import AIProvider


class EmbeddingService:
    """Service for computing vector embeddings using the configured cloud AI provider."""

    def __init__(self, gateway_or_provider: AIGateway | AIProvider) -> None:
        self.client = gateway_or_provider

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for a list of text strings."""
        if not texts:
            return []

        if isinstance(self.client, AIGateway):
            response = await self.client.embed(texts)
            return response.embeddings
        elif isinstance(self.client, AIProvider):
            # Direct provider fallback
            return await self.client.embed(texts, model="text-embedding-004")
        raise TypeError("client must be an instance of AIGateway or AIProvider")
