"""
Base data source interface for the Overture data ingestion layer.

All data source connectors inherit from BaseDataSource and produce
standardized DataItem objects that flow through the pipeline.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DataItem:
    """Standardized data item from any source.

    Every connector normalizes its output into DataItem instances so that
    downstream consumers (agents, pipeline, cache) can work with a single
    uniform schema regardless of where the data originated.

    Attributes:
        source: Human-readable name of the data source (e.g. "yahoo_finance").
        source_type: Category tag -- one of "news", "price", "social",
                     "research", or "screen".
        title: Short headline or label for the item.
        content: Full body / payload text.
        url: Optional link back to the original resource.
        tickers: List of ticker symbols relevant to this item.
        asset_classes: List of asset class tags (e.g. "equity", "commodity").
        sentiment: Pre-computed sentiment score in [-1, 1], or None.
        relevance_score: Relevance weight in [0, 1].
        metadata: Arbitrary extra fields specific to the source.
        published_at: When the original content was published.
        fetched_at: When the item was ingested by Overture.
    """

    source: str
    source_type: str  # "news", "price", "social", "research", "screen"
    title: str
    content: str
    url: str = ""
    tickers: list[str] = field(default_factory=list)
    asset_classes: list[str] = field(default_factory=list)
    sentiment: float | None = None  # -1 to 1
    relevance_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    published_at: datetime | None = None
    fetched_at: datetime = field(default_factory=datetime.utcnow)


class BaseDataSource(ABC):
    """Abstract base class for all Overture data source connectors.

    Sub-classes must implement ``fetch`` (primary data retrieval) and
    ``health_check`` (connectivity / readiness probe).
    """

    def __init__(self, name: str, source_type: str):
        self.name = name
        self.source_type = source_type
        self._enabled = True

    @abstractmethod
    async def fetch(self, **kwargs) -> list[DataItem]:
        """Retrieve data items from this source.

        Keyword arguments are source-specific and allow callers to customise
        the scope of the fetch (e.g. tickers, time ranges, limits).
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return ``True`` if the source is reachable and functional."""
        ...
