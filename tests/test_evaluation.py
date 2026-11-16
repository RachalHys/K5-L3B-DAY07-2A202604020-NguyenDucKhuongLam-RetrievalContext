"""Errors and missing cases must not improve a configuration's selection score."""
import unittest

from src.evaluation import summarize
from src.experiment import run_configuration


class EvaluationTests(unittest.TestCase):
    def test_reviewed_refusal_is_counted_when_model_declares_an_answer(self):
        cases = [dict(id='a', answerable=True, gold=[]), dict(id='u', answerable=False)]
        base = dict(events=[], citations=[], original_ranking=[], original_ranking_ms=1,
                    elapsed_ms=1, estimated_cost_usd=0, cost_complete=True)
        traces = [dict(base, query_id='a', status='answered'), dict(base, query_id='u', status='abstain')]
        reviews = [dict(query_id='a', answer_grade=0, context_grade=0, answer_refused=True,
                        reason='Declines the requested fact despite finish.abstain=false.', citation_support=[]),
                   dict(query_id='u', context_grade=0, answer_refused=True,
                        reason='Correct refusal.', citation_support=[], abstention_correct=True)]
        result = summarize(cases, traces, reviews)
        self.assertEqual(result['agent']['false_abstention'], {'n': 1, 'N': 1})
        self.assertEqual(result['declared_status_disagreements'], ['a'])

    def test_test_execution_requires_selection_before_any_api_or_output(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'must-not-exist'
            with self.assertRaisesRegex(ValueError, 'frozen baseline/selected'):
                run_configuration({'id': 'dense_baseline'}, {}, 'test', output, None)
            self.assertFalse(output.exists())

    def test_error_is_excluded_from_official_mean_but_not_selection_denominator(self):
        cases = [dict(id='a', answerable=True, gold=[]), dict(id='b', answerable=True, gold=[]),
                 dict(id='u', answerable=False)]
        base = dict(events=[], citations=[], original_ranking=[], original_ranking_ms=1,
                    elapsed_ms=1, estimated_cost_usd=0, cost_complete=True)
        traces = [dict(base, query_id='a', status='answered'), dict(base, query_id='b', status='error'),
                  dict(base, query_id='u', status='abstain')]
        reviews = [dict(query_id='a', answer_grade=2, context_grade=2, answer_refused=False, reason='supported', citation_support=[]),
                   dict(query_id='b', reason='provider error'),
                   dict(query_id='u', context_grade=0, answer_refused=True, reason='not in corpus', citation_support=[], abstention_correct=True)]
        result = summarize(cases, traces, reviews)
        self.assertEqual(result['agent']['grounded_answer']['mean'], 2)
        self.assertEqual(result['selection_scores']['grounded_points_per_answerable_attempt'], 1)
        self.assertEqual(result['selection_scores']['correct_abstentions_per_unanswerable_attempt'], 1)
        self.assertEqual(result['errors'], 1)
        with self.assertRaises(ValueError): summarize(cases, traces[:1])


if __name__ == '__main__': unittest.main()
