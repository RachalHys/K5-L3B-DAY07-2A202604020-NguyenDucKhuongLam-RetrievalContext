"""HTTP contract, secret-free errors and accounting from reported token usage."""
import io
import json
import unittest
from unittest.mock import patch
import urllib.error

from src.llm import ChatClient, ProviderError


class LLMTests(unittest.TestCase):
    def test_http_error_does_not_leak_key_or_response_body(self):
        client = ChatClient(model='test', api_key='fake-private-test-key')
        error = urllib.error.HTTPError(client.url, 401, 'denied', {}, io.BytesIO(b'fake-private-test-key'))
        with patch('urllib.request.urlopen', side_effect=error), self.assertRaises(ProviderError) as caught:
            client.complete([], [])
        self.assertEqual(caught.exception.record['http_status'], 401)
        self.assertNotIn('fake-private-test-key', str(caught.exception) + json.dumps(caught.exception.record))

    def test_cached_and_written_tokens_are_accounted_separately(self):
        rates = dict(model='test', input_per_million=1, cached_input_per_million=.1,
                     cache_write_per_million=1.25, output_per_million=5)
        body = dict(id='response', model='test', choices=[dict(finish_reason='tool_calls', message={})],
                    usage=dict(prompt_tokens=100, completion_tokens=4,
                               prompt_tokens_details=dict(cached_tokens=20, cache_write_tokens=10)))
        class Response(io.BytesIO): headers = {'x-request-id': 'request'}
        with patch('urllib.request.urlopen', return_value=Response(json.dumps(body).encode())):
            record = ChatClient(model='test', api_key='fake', rates=rates).complete([], [])
        self.assertAlmostEqual(record['estimated_cost_usd'], .0001045)
        self.assertEqual(record['request_id'], 'request')


if __name__ == '__main__': unittest.main()
