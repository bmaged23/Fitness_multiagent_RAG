"""Rank-aware reference metrics for authoritative source-record QA."""
from __future__ import annotations
import math


def identity(doc):return doc['collection'],str(doc['chunk_id'])


def ranking_metrics(retrieved,qrels,k=5):
    if k<1:raise ValueError('k must be positive')
    grades={identity(r):r['relevance_grade'] for r in qrels}
    if not grades or any(not isinstance(g,int) or g<0 for g in grades.values()):
        raise ValueError('Nonempty nonnegative integer relevance grades are required.')
    positives={key for key,grade in grades.items() if grade>0}
    if not positives:raise ValueError('This answerable QA scorer needs at least one positive source.')
    gains=[];seen=set();hits=0;first=None;ap=0.0
    for rank,doc in enumerate(retrieved[:k],1):
        key=identity(doc);grade=grades.get(key,0) if key not in seen else 0;seen.add(key)
        gains.append((2**grade-1)/math.log2(rank+1))
        if grade>0:
            hits+=1;first=first or rank;ap+=hits/rank
    ideal=sorted(grades.values(),reverse=True)[:k]
    idcg=sum((2**g-1)/math.log2(rank+1) for rank,g in enumerate(ideal,1))
    return {f'ndcg_at_{k}':sum(gains)/idcg,
            f'precision_at_{k}':hits/k,f'recall_at_{k}':hits/len(positives),
            f'mrr_at_{k}':1/first if first else 0.0,
            f'average_precision_at_{k}':ap/min(k,len(positives)),
            f'hit_at_{k}':float(hits>0),'all_required_sources_found':float(hits==len(positives)),
            'required_sources':len(positives),'matched_sources':hits,
            'precision_ceiling':min(k,len(positives))/k}
