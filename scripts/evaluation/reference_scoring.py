"""Score reference contracts without treating unjudged documents as proven negatives."""
from __future__ import annotations
from scripts.evaluation.retrieval_metrics import score_retrieval


def score_reference_case(case,documents,k=3):
    if k<1:raise ValueError('k must be positive')
    expected=case['expected'];scope=expected.get('reference_scope')
    if scope=='exhaustive_exact_title_absence':
        return {'scope':scope,'status':'scored_exact_title_absence',
                'abstained':not bool(documents),'reference_title':expected['reference_rule']['exact_title_casefold']}
    if scope not in {'exhaustive_recorded_metadata','curated_partial_pool'}:
        return {'scope':scope,'status':'requires_behavior_or_context_evaluator'}
    scores={}
    for collection in expected['collections']:
        ranked=[d for d in documents if d.get('collection')==collection][:k]
        refs=[r for r in expected['relevance_labels'] if r['collection']==collection]
        if scope=='exhaustive_recorded_metadata':
            result=score_retrieval(ranked,refs,k)
            positive_count=sum(r['relevant'] for r in refs)
            result.update({'scope':'recorded_metadata_only','reference_positive_count':positive_count,
                           'recall_at_k_ceiling':min(k,positive_count)/positive_count if positive_count else None})
            scores[collection]=result
            continue
        labels={r['chunk_id']:r['relevant'] for r in refs}
        positives={id for id,relevant in labels.items() if relevant}
        judged=0;hits=[];seen=set()
        for rank,doc in enumerate(ranked,1):
            id=doc.get('chunk_id')
            if id in labels:judged+=1
            if labels.get(id) is True and id not in seen:hits.append(rank)
            seen.add(id)
        scores[collection]={'status':'partial_pool_not_full_semantic_ground_truth',
            'known_positive_hits':len(hits),'reference_positive_count':len(positives),
            'reference_coverage_at_k':len(hits)/len(positives) if positives else None,
            'precision_at_k_lower_bound':len(hits)/k,
            'mrr_known_positive_lower_bound':1/hits[0] if hits else 0.0,
            'judged_returned_count':judged,'returned_count':len(ranked),
            'judgment_coverage':judged/len(ranked) if ranked else 0.0,
            'precision_among_judged':len(hits)/judged if judged else None,
            'unjudged_returned_count':len(ranked)-judged}
    return {'scope':scope,'collections':scores}
