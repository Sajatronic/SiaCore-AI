from abc import ABC, abstractmethod

from models.schemas import RawArticle


class BaseNewsProvider(ABC):
    """Abstract adapter for external news/event sources."""

    provider_name: str
    reliability_tier: int = 3

    @abstractmethod
    async def fetch(self, **kwargs) -> list[RawArticle]:
        """Fetch and normalize records from the provider."""
