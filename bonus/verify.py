"""Validate the submitted bonus benchmark, frozen runs, image evidence and metrics."""
from collections import Counter
from datetime import datetime
import hashlib
import json

import pymupdf

from .run import BENCH, DATA, PDF, ROOT, PROMPT, freeze_hashes, verify_pdf


def validate():
    verify_pdf()
    protocol = json.loads((BENCH / 'protocol.json').read_text())
    for name, expected in protocol['files'].items():
        assert hashlib.sha256((BENCH / name).read_bytes()).hexdigest() == expected, name
    labels = {}
    for split, total in [('dev', 18), ('test', 30)]:
        cases = json.loads((BENCH / f'labels/{split}.json').read_text())
        inputs = json.loads((BENCH / f'{split}.json').read_text())
        assert len(cases) == total and len({c['id'] for c in cases}) == total
        assert inputs == [dict(id=c['id'], question=c['question']) for c in cases]
        counts = Counter(c['group'] for c in cases)
        if split == 'test':
            assert all(counts[k] >= n for k, n in protocol['test_minimum'].items())
        assert sum(c['answerable'] for c in cases) == total - counts['unanswerable']
        for case in cases:
            assert case['answerable'] == (case['group'] != 'unanswerable')
            if case['answerable']:
                assert case['evidence']
            else:
                assert case['absence_check']
            if case['group'] == 'multi_hop':
                assert len({e['pdf_page'] for e in case['evidence']}) >= 2
            for evidence in case['evidence']:
                x0, y0, x1, y1 = evidence['bbox_normalized']
                assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
                assert 1 <= evidence['pdf_page'] <= 291
        labels[split] = {c['id']: c for c in cases}
    pages = json.loads((DATA / 'pages.json').read_text())
    assert [p['pdf_page'] for p in pages] == list(range(1, 292))
    coverage = json.loads((DATA / 'coverage.json').read_text())
    index = json.loads((DATA / 'index.json').read_text())
    assert len(index) == coverage['indexed_pages'] == 284
    included = {c['metadata']['pdf_page'] for c in index}
    excluded = {c['pdf_page'] for c in coverage['excluded_pages']}
    assert not included & excluded and included | excluded == set(range(1, 292))
    assert not coverage['failed_pages']
    assert coverage['index_sha256'] == hashlib.sha256((DATA / 'index.json').read_bytes()).hexdigest()
    regions = {r['id']: (p['pdf_page'], r) for p in pages for r in p['regions']}
    for p in pages:
        width, height = p['image_size']
        for word in p['words']:
            x, y, w, h = word['bbox']
            assert 0 <= x < width and 0 <= y < height and w > 0 and h > 0
    selected = json.loads((ROOT / 'configs/bonus-selected.json').read_text())
    assert selected['hashes'] == freeze_hashes(), 'Pipeline changed after selection'
    image_hashes = {}
    with pymupdf.open(PDF) as document:
        for n, r in regions.values():
            page = document[n - 1]
            x0, y0, x1, y1 = r['bbox_normalized']
            clip = pymupdf.Rect(x0 * page.rect.width, y0 * page.rect.height,
                                x1 * page.rect.width, y1 * page.rect.height)
            image_hashes[r['id']] = hashlib.sha256(page.get_pixmap(dpi=144, clip=clip, alpha=False).tobytes('png')).hexdigest()
    all_ids, all_response_ids = set(), set()
    count = calls = 0
    for run_file in sorted((ROOT / 'results/bonus').glob('*/*/run.json')):
        directory = run_file.parent
        run = json.loads(run_file.read_text())
        traces = [json.loads(line) for line in (directory / 'traces.jsonl').read_text().splitlines()]
        split = run['split']
        assert {t['query_id'] for t in traces} == set(labels[split])
        assert len(traces) == len(labels[split])
        if directory.parts[-2] in ('dev', 'test'):
            assert run['hashes'] == selected['hashes']
        if split == 'test':
            assert datetime.fromisoformat(selected['selected_at']) < datetime.fromisoformat(run['started_at'])
            assert run['configuration'] == selected['configuration'] and run['model'] == selected['model']
        for trace in traces:
            count += 1
            assert trace['question'] == labels[split][trace['query_id']]['question']
            assert trace['llm_calls'] == len(trace['model_calls'])
            total_cost = 0
            for call in trace['model_calls']:
                calls += 1
                assert call.get('request_id') and call['request_id'] not in all_ids
                assert call.get('response_id') and call['response_id'] not in all_response_ids
                all_ids.add(call['request_id']); all_response_ids.add(call['response_id'])
                payload = call['request']
                assert payload['messages'][1] == {'role': 'user', 'content': trace['question']}
                assert payload['temperature'] == 0 and payload['store'] is False
                assert call['elapsed_ms'] > 0 and call['usage']['total_tokens'] > 0
                assert call['estimated_cost_usd'] is not None
                usage = call['usage']; rate = run['pricing']
                detail = usage.get('prompt_tokens_details') or {}
                cached = detail.get('cached_tokens', 0); written = detail.get('cache_write_tokens', 0)
                expected = ((usage['prompt_tokens'] - cached - written) * rate['input_per_million']
                            + cached * rate['cached_input_per_million'] + written * rate['cache_write_per_million']
                            + usage['completion_tokens'] * rate['output_per_million']) / 1_000_000
                assert abs(call['estimated_cost_usd'] - expected) < 1e-10
                total_cost += expected
                last_region = None
                last_page = None
                for message in payload['messages']:
                    if isinstance(message.get('content'), list):
                        for part in message['content']:
                            if part['type'] == 'text':
                                info = json.loads(part['text'])
                                last_page = info['pdf_page']
                                if 'region' in info:
                                    last_region = info['region']['id']
                                    assert info['region'] == regions[last_region][1]
                            elif part['type'] == 'image_url':
                                value = part['image_url']['url']
                                expected_image = image_hashes[last_region] if last_region else pages[last_page - 1]['image_sha256']
                                assert value == 'sha256:' + expected_image, last_region or last_page
                if directory.parts[-2] in ('dev', 'test'):
                    assert payload['messages'][0]['content'] == PROMPT
            assert abs(total_cost - trace['estimated_cost_usd']) < 1e-9
            if trace['status'] != 'error':
                finish = json.loads(trace['model_calls'][-1]['message']['tool_calls'][0]['function']['arguments'])
                assert finish['answer'] == trace['answer'] and finish['citations'] == trace['citations']
                assert set(trace['citations']) <= {r['id'] for n in trace['context_pages'] for r in pages[n - 1]['regions']}
                assert ('abstain' if finish['abstain'] else 'answered') == trace['status']
        reviews = json.loads((directory / 'reviews.json').read_text())
        assert len(reviews) == len(traces) and {r['query_id'] for r in reviews} == set(labels[split])
        assert all(type(r['passed']) is bool and r['reason'] for r in reviews)
        if (directory / 'summary.json').exists():
            summary = json.loads((directory / 'summary.json').read_text())
            assert summary['passed'] == sum(r['passed'] for r in reviews)
            assert summary['total'] == len(traces)
            assert summary['errors'] == sum(t['status'] == 'error' for t in traces)
            assert abs(summary['estimated_cost_usd'] - sum(t['estimated_cost_usd'] for t in traces)) < 1e-9
    for config, files in selected['dev_runs'].items():
        for name, digest in files.items():
            path = ROOT / f'results/bonus/dev/{config}/{name}'
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    print(f'PASS: 291 pages, 284 indexed; 48 benchmark questions; {count} attempts, {calls} real API calls; image hashes, costs, labels and test freeze valid.')


if __name__ == '__main__':
    validate()
