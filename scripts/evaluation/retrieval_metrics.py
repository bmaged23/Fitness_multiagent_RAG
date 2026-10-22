"""Reference-based retrieval metrics; unlabelled cases are not scored."""
from __future__ import annotations


def score_retrieval(retrieved: list[dict], relevance_labels: list[dict], k: int = 3):
    """Use (collection, chunk_id), not ambiguous IDs or model similarity scores.

    Labels must enumerate a reviewed positive reference set. Recall is relative
    to that set, not every potentially relevant document in the corpus.
    Duplicate results do not earn additional credit and occupy a rank position.
    """
    if k < 1:
        raise ValueError('k must be positive')
    if not relevance_labels:
        return {'status': 'unscored_missing_labels', 'precision_at_k': None,
                'recall_at_k': None, 'mrr_at_k': None}
    relevant = {(r['collection'], str(r['chunk_id'])) for r in relevance_labels if r['relevant']}
    if not relevant:
        return {'status': 'unscored_no_positive_reference', 'precision_at_k': None,
                'recall_at_k': None, 'mrr_at_k': None}
    seen = set()
    hits = []
    for rank, doc in enumerate(retrieved[:k], 1):
        key = (doc['collection'], str(doc['chunk_id']))
        if key in relevant and key not in seen:
            hits.append(rank)
        seen.add(key)
    return {'status': 'scored', 'precision_at_k': len(hits) / k,
            'recall_at_k': len(hits) / len(relevant),
            'mrr_at_k': 1 / hits[0] if hits else 0.0}
