"""Minimal Chat Completions client, following the existing Day 4 HTTP adapter."""
import json
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from .day6 import ROOT


class ProviderError(RuntimeError):
    def __init__(self, message: str, record: dict):
        super().__init__(message)
        self.record = record


class ChatClient:
    def __init__(self, *, model: str, api_key: str, base_url: str = 'https://api.openai.com/v1',
                 reasoning_effort: str = 'none', max_completion_tokens: int = 1200,
                 timeout: float = 60, rates: dict | None = None):
        if not model or not api_key:
            raise ValueError('Configure LLM_MODEL and OPENAI_API_KEY in the local .env.')
        self.model, self.api_key = model, api_key
        self.url = base_url.rstrip('/') + '/chat/completions'
        self.reasoning_effort, self.max_completion_tokens = reasoning_effort, max_completion_tokens
        self.timeout, self.rates = timeout, rates

    @classmethod
    def from_env(cls, *, rates: dict | None = None):
        load_dotenv(ROOT / '.env', override=False)
        return cls(model=os.environ.get('LLM_MODEL', ''), api_key=os.environ.get('OPENAI_API_KEY', ''),
                   base_url=os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1'),
                   reasoning_effort=os.environ.get('LLM_REASONING_EFFORT', 'none'), rates=rates)

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        payload = dict(model=self.model, messages=messages, tools=tools, tool_choice='required',
                       parallel_tool_calls=False, reasoning_effort=self.reasoning_effort,
                       max_completion_tokens=self.max_completion_tokens, temperature=0, store=False)
        # Only this request header carries credentials; it is never stored in the trace.
        request = urllib.request.Request(self.url, data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json',
                                                  'Authorization': 'Bearer ' + self.api_key})
        started = time.perf_counter()
        record = dict(request=payload, elapsed_ms=None, estimated_cost_usd=None)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
                record['request_id'] = response.headers.get('x-request-id')
        except urllib.error.HTTPError as error:
            record.update(elapsed_ms=(time.perf_counter() - started) * 1000, http_status=error.code)
            raise ProviderError(f'LLM HTTP {error.code}; check model, key and quota.', record) from None
        except (urllib.error.URLError, TimeoutError):
            record['elapsed_ms'] = (time.perf_counter() - started) * 1000
            raise ProviderError('LLM connection failed or timed out.', record) from None
        record.update(elapsed_ms=(time.perf_counter() - started) * 1000, model=data.get('model'),
                      usage=data.get('usage', {}), response_id=data.get('id'))
        choice = data['choices'][0]
        record.update(message=choice['message'], finish_reason=choice.get('finish_reason'))
        if self.rates and self.rates['model'] == record['model'] and record['usage']:
            usage = record['usage']
            details = usage.get('prompt_tokens_details') or {}
            cached, written = details.get('cached_tokens', 0), details.get('cache_write_tokens', 0)
            uncached = usage['prompt_tokens'] - cached - written
            if uncached < 0:
                raise ProviderError('LLM reported inconsistent usage.', record)
            record['estimated_cost_usd'] = (uncached * self.rates['input_per_million'] +
                                            cached * self.rates['cached_input_per_million'] +
                                            written * self.rates['cache_write_per_million'] +
                                            usage['completion_tokens'] * self.rates['output_per_million']) / 1_000_000
        return record
