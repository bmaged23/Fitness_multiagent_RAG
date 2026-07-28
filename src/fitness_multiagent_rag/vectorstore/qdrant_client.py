from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny, SearchParams

from config.settings import (
    QDRANT_URL, QDRANT_API_KEY,
    QDRANT_EXACT_SEARCH, QDRANT_MAX_TOP_K,
    P_GOAL, P_LEVEL, P_EQUIPMENT,
)
from .schema import SearchResult

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30)
    return _client


def search(
    collection: str,
    query_vector: list[float],
    top_k: int = 5,
    goal: Optional[list[str]] = None,
    level: Optional[list[str]] = None,
    equipment: Optional[list[str]] = None,
) -> list[SearchResult]:
    top_k = min(top_k, QDRANT_MAX_TOP_K)

    conditions = []
    if goal:
        conditions.append(FieldCondition(key=P_GOAL, match=MatchAny(any=goal)))
    if level:
        conditions.append(FieldCondition(key=P_LEVEL, match=MatchAny(any=level)))
    if equipment:
        conditions.append(FieldCondition(key=P_EQUIPMENT, match=MatchAny(any=equipment)))

    filt = Filter(must=conditions) if conditions else None

    response = _get_client().query_points(
        collection_name=collection,
        query=query_vector,
        limit=top_k,
        query_filter=filt,
        search_params=SearchParams(exact=QDRANT_EXACT_SEARCH),
        with_payload=True,
    )

    return [
        SearchResult(score=hit.score, collection=collection, **hit.payload)
        for hit in response.points
    ]
