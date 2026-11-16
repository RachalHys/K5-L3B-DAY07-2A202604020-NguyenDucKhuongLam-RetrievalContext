"""Evidence metrics and aggregation of source-reviewed answer/citation labels."""
import statistics

from starter.agent_metrics import aggregate
from starter.baseline import hit


def ratio(n: int, total: int):
    return dict(n=n, N=total, rate=n / total if total else None)


def evidence_metrics(case: dict, trace: dict) -> dict:
    if not case['answerable']:
        return {}
    ranking = trace.get('original_ranking', [])
    candidates = {c['id']: c for event in trace.get('events', []) if event['event'] == 'search'
                  for c in event.get('results', [])}
    context_ids = set(trace.get('context_ids', []))
    return dict(hit1=bool(ranking and hit(ranking[0], case['gold'])),
                hit3=any(hit(c, case['gold']) for c in ranking[:3]),
                context_hit=any(hit(c, case['gold']) for cid, c in candidates.items() if cid in context_ids))


def summarize(cases: list[dict], traces: list[dict], reviews: list[dict] | None = None) -> dict:
    by_id = {t['query_id']: t for t in traces}
    if len(by_id) != len(traces) or set(by_id) != {c['id'] for c in cases}:
        raise ValueError('One trace per case is required, including errors.')
    answerable = [c for c in cases if c['answerable']]
    metrics = [evidence_metrics(case, by_id[case['id']]) for case in answerable]
    summary = dict(cases=len(cases), answerable=len(answerable), unanswerable=len(cases) - len(answerable),
                   hit1=ratio(sum(m['hit1'] for m in metrics), len(metrics)),
                   hit3=ratio(sum(m['hit3'] for m in metrics), len(metrics)),
                   context_evidence=ratio(sum(m['context_hit'] for m in metrics), len(metrics)),
                   errors=sum(t['status'] == 'error' for t in traces),
                   median_end_to_end_ms=statistics.median(t['elapsed_ms'] for t in traces),
                   original_ranking_median_ms=statistics.median(t['original_ranking_ms'] for t in traces),
                   estimated_cost_usd=sum(t.get('estimated_cost_usd', 0) for t in traces),
                   cost_complete=all(t.get('cost_complete', False) for t in traces),
                   llm_calls=sum(t.get('llm_calls', 0) for t in traces),
                   search_calls=sum(t.get('search_calls', 0) for t in traces),
                   search_call_distribution={str(k): sum(t.get('search_calls', 0) == k for t in traces)
                                             for k in sorted({t.get('search_calls', 0) for t in traces})},
                   prompt_tokens=sum(call.get('usage', {}).get('prompt_tokens', 0) for t in traces for call in t.get('model_calls', [])),
                   completion_tokens=sum(call.get('usage', {}).get('completion_tokens', 0) for t in traces for call in t.get('model_calls', [])))
    if reviews is not None:
        if {r['query_id'] for r in reviews} != set(by_id) or len(reviews) != len(cases):
            raise ValueError('One review per case is required for a completed evaluation.')
        audited_traces, disagreements = [], []
        for review in reviews:
            trace = by_id[review['query_id']]
            if trace['status'] != 'error':
                if review.get('context_grade') not in (0, 1, 2) or not review.get('reason'):
                    raise ValueError('Review needs context_grade 0/1/2 and a source-based reason.')
                if type(review.get('answer_refused')) is not bool:
                    raise ValueError('Review must classify actual refusal, independently of the model flag.')
                status = 'abstain' if review['answer_refused'] else 'answered'
                if status != trace['status']:
                    disagreements.append(trace['query_id'])
                audited_traces.append(dict(trace, status=status))
            else:
                audited_traces.append(trace)
        summary['declared_status_disagreements'] = sorted(disagreements)
        summary['agent'] = aggregate(cases, audited_traces, reviews)
        by_review = {r['query_id']: r for r in reviews}
        summary['reviewed_context_grades'] = {str(k): sum(by_review[c['id']].get('context_grade') == k
                                                        for c in answerable) for k in (0, 1, 2)}
        summary['selection_scores'] = dict(
            grounded_points_per_answerable_attempt=sum(by_review[c['id']].get('answer_grade', 0)
                                                        for c in answerable if by_id[c['id']]['status'] != 'error') / len(answerable),
            correct_abstentions_per_unanswerable_attempt=sum(bool(by_review[c['id']].get('abstention_correct'))
                                                            for c in cases if not c['answerable'] and by_id[c['id']]['status'] != 'error') / (len(cases) - len(answerable)))
    return summary
