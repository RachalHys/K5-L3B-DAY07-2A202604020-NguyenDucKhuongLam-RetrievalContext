"""Offline tests for the production loop; these do not measure LLM quality."""
import json
import unittest

from src.agent import run_agent
from src.llm import ProviderError


CONFIG = dict(top_k=3, budget_chars=60, max_searches=2, context_policy='recent')
CHUNK = dict(id='c1', text='Evidence one.', source='doc.pdf', source_id='doc', page=1, metadata={})


def action(name, **arguments):
    return dict(id='call_' + name, type='function', function=dict(name=name, arguments=json.dumps(arguments)))


class Client:
    def __init__(self, actions): self.actions = iter(actions); self.prompts = []; self.tools = []
    def complete(self, messages, tools):
        self.prompts.append(messages)
        self.tools.append(tools)
        return dict(message=dict(role='assistant', content=None, tool_calls=[next(self.actions)]),
                    finish_reason='tool_calls', estimated_cost_usd=0, usage={})


class Retriever:
    def __init__(self, rows): self.rows = iter(rows); self.calls = []
    def search(self, query, *, filters, top_k):
        self.calls.append((query, filters, top_k))
        return next(self.rows)


class LiveAgentTests(unittest.TestCase):
    def test_citation_schema_allows_only_exact_ids_from_visible_context(self):
        full_id = 'bd79e3d322f21588b017ea4d'
        row = dict(CHUNK, id=full_id)
        client = Client([action('search', query='q'),
                         action('finish', answer=f'Evidence [{full_id}]', citations=[full_id], abstain=False)])
        result = run_agent('q', client, Retriever([[row]]), filters=None, config=dict(CONFIG, budget_chars=150))
        self.assertEqual(result['status'], 'answered')
        schema = next(t['function'] for t in client.tools[1] if t['function']['name'] == 'finish')
        self.assertEqual(schema['parameters']['properties']['citations']['items'].get('enum'), [full_id])

    def test_model_controls_search_and_cites_only_current_context(self):
        other = dict(CHUNK, id='c2', text='Evidence two.')
        client = Client([action('search', query='first'), action('search', query='second'),
                         action('finish', answer='Supported answer [c2]', citations=['c2'], abstain=False)])
        result = run_agent('q', client, Retriever([[CHUNK], [other]]), filters={'publication_year': 2020}, config=CONFIG)
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['context_ids'], ['c2'])
        self.assertEqual(result['search_calls'], 2)
        final_prompt = json.dumps(client.prompts[-1])
        self.assertIn('Evidence two.', final_prompt)
        self.assertNotIn('Evidence one.', final_prompt)
        self.assertTrue(all(len(e['context']) <= CONFIG['budget_chars'] for e in result['events'] if e['event'] == 'search'))

    def test_missing_search_or_invalid_citation_gets_feedback_not_a_fake_answer(self):
        client = Client([action('finish', answer='Guess [c1]', citations=['c1'], abstain=False),
                         action('search', query='q'),
                         action('finish', answer='Wrong ID [missing]', citations=['missing'], abstain=False),
                         action('finish', answer='Not enough evidence in the documents.', citations=[], abstain=True)])
        result = run_agent('q', client, Retriever([[CHUNK]]), filters=None, config=CONFIG)
        self.assertEqual(result['status'], 'abstain')
        self.assertEqual(sum(e['event'] == 'invalid_action' for e in result['events']), 2)
        self.assertEqual(result['citations'], [])

    def test_retrieval_failure_retains_attempt_and_prior_model_usage(self):
        class Broken:
            def search(self, query, *, filters, top_k): raise ConnectionError('database unavailable')
        result = run_agent('q', Client([action('search', query='q')]), Broken(), filters=None, config=CONFIG)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['search_calls'], 1)
        self.assertEqual(len(result['model_calls']), 1)
        self.assertEqual(result['events'][0]['error'], 'database unavailable')

    def test_provider_errors_are_preserved_without_mock_fallback(self):
        class Broken:
            def complete(self, messages, tools):
                raise ProviderError('LLM HTTP 429', dict(elapsed_ms=1, http_status=429, estimated_cost_usd=None))
        result = run_agent('q', Broken(), Retriever([]), filters=None, config=CONFIG)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_type'], 'provider')
        self.assertFalse(result['cost_complete'])
        self.assertEqual(result['llm_calls'], 1)


if __name__ == '__main__': unittest.main()
