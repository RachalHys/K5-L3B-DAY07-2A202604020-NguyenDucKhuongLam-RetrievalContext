"""Load safe query inputs and validate the frozen basic benchmark without retrieval."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import unicodedata

from .day6 import CORPUS, ROOT, load_snapshot, sha256
from .retrieval import validate_filters


BASIC = ROOT / 'benchmark/basic'
CORPUS_FILES = {'manifest.json', 'pages.jsonl', 'chunks.json', 'dense_vectors.npz', 'provenance.json'}
INPUT_FIELDS = {'id', 'split', 'question', 'filter'}
LABEL_FIELDS = {'id', 'answerable', 'expected_behavior', 'expected_answer', 'gold',
                'answer_requirements', 'category', 'origin', 'absence_reason', 'absence_check'}


def read_rows(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f'Expected a nonempty JSON array: {path.name}')
    ids = [row.get('id') if isinstance(row, dict) else None for row in rows]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError(f'Case IDs must be nonempty and unique: {path.name}')
    return rows


def load_inputs(split: str, directory: Path = BASIC) -> list[dict]:
    """Agent-facing loader: never opens labels or inspects answerability/gold."""
    if split not in ('dev', 'test'):
        raise ValueError('Select dev or test explicitly.')
    rows = read_rows(directory / f'{split}.json')
    for row in rows:
        if set(row) != INPUT_FIELDS:
            raise ValueError(f"{row['id']}: input may contain only id/split/question/filter")
        if row['split'] != split or not isinstance(row['question'], str) or not row['question'].strip():
            raise ValueError(f"{row['id']}: invalid split/question")
        if not isinstance(row['filter'], dict):
            raise ValueError(f"{row['id']}: filter must be an object")
        filters = validate_filters(row['filter'])
        # The benchmark provides only years explicitly present in the user query.
        years = re.findall(r'\b(?:19|20)\d{2}\b', row['question'])
        expected = {'publication_year': int(years[0])} if len(set(years)) == 1 else {}
        if filters != expected:
            raise ValueError(f"{row['id']}: filter must match the year explicitly stated in the query")
    return rows


def load_labels(split: str, directory: Path = BASIC) -> dict[str, dict]:
    if split not in ('dev', 'test'):
        raise ValueError('Select dev or test explicitly.')
    rows = read_rows(directory / 'labels' / f'{split}.json')
    for row in rows:
        if set(row) - LABEL_FIELDS or type(row.get('answerable')) is not bool:
            raise ValueError(f"{row['id']}: invalid evaluation label fields/answerability")
    return {row['id']: row for row in rows}


def load_cases(split: str, directory: Path = BASIC) -> list[dict]:
    """Evaluation only: join inputs and labels; do not send these rows to the agent."""
    inputs, labels = load_inputs(split, directory), load_labels(split, directory)
    if {q['id'] for q in inputs} != set(labels):
        raise ValueError(f'{split}: inputs and labels must have exactly the same IDs')
    return [dict(q, **{key: value for key, value in labels[q['id']].items() if key != 'id'}) for q in inputs]


def normalized(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFC', text).split())


def check_evidence(evidence: dict, chunks: list[dict], pages: dict, filters: dict, *, single_chunk=True):
    if not isinstance(evidence, dict):
        raise ValueError('Evidence must be an object.')
    source, page, quote = (evidence.get(key) for key in ('source_id', 'page', 'evidence'))
    if not isinstance(source, str) or type(page) is not int or not isinstance(quote, str) or not quote.strip():
        raise ValueError('Evidence needs source_id, physical page and nonempty quotation.')
    original = pages.get((source, page))
    if original is None or quote not in original['text']:
        raise ValueError(f'Evidence is absent from the source page: {source}:{page}')
    if any(original['metadata'].get(key) != value for key, value in filters.items()):
        raise ValueError(f'Evidence conflicts with the query filter: {source}:{page}')
    if single_chunk and not any(c['source_id'] == source and c['page'] == page and quote in c['text'] for c in chunks):
        raise ValueError(f'Evidence is not whole in one chunk: {source}:{page}')


def verify_pdfs(manifest: dict, pages: dict) -> int:
    from pypdf import PdfReader
    checked = 0
    for document in manifest['documents']:
        path = ROOT / document['source_path_or_url']
        if sha256(path) != document['sha256']:
            raise ValueError(f"Original PDF checksum mismatch: {document['source_id']}")
        reader = PdfReader(path)
        if len(reader.pages) != document['physical_page_count']:
            raise ValueError(f"Original PDF page count mismatch: {document['source_id']}")
        for number in document['selected_pages']:
            extracted = reader.pages[number - 1].extract_text() or ''
            if normalized(extracted) != normalized(pages[(document['source_id'], number)]['text']):
                raise ValueError(f"Indexed page differs from original PDF: {document['source_id']}:{number}")
            checked += 1
    return checked


def validate_benchmark(*, split: str = 'all', directory: Path = BASIC, check_pdfs: bool = False) -> dict:
    if split not in ('dev', 'test', 'all'):
        raise ValueError('Select dev, test or all for static validation.')
    splits = ('dev', 'test') if split == 'all' else (split,)
    chunks, _, _ = load_snapshot()
    pages = {(p['document_id'], p['page']): p for p in
             map(json.loads, (CORPUS / 'pages.jsonl').read_text(encoding='utf-8').splitlines())}
    manifest = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))
    protocol = json.loads((directory / 'protocol.json').read_text(encoding='utf-8'))
    if not isinstance(protocol.get('corpus_sha256'), dict) or set(protocol['corpus_sha256']) != CORPUS_FILES:
        raise ValueError('Corpus fingerprint must cover every frozen corpus artifact.')
    for name, expected in protocol['corpus_sha256'].items():
        if sha256(CORPUS / name) != expected:
            raise ValueError(f'Benchmark corpus changed: {name}')
    summary, all_ids, questions = {}, set(), set()
    for selected in splits:
        for name in (f'{selected}.json', f'labels/{selected}.json'):
            if sha256(directory / name) != protocol['files_sha256'][name]:
                raise ValueError(f'Frozen benchmark changed: {name}')
        cases = load_cases(selected, directory)
        counts = Counter()
        for case in cases:
            question = normalized(case['question']).casefold()
            if case['id'] in all_ids or question in questions:
                raise ValueError('Duplicate case ID or question across splits.')
            all_ids.add(case['id'])
            questions.add(question)
            if not case.get('origin') or not case.get('category'):
                raise ValueError(f"{case['id']}: missing origin/category")
            if case['answerable']:
                if case.get('expected_behavior') != 'search_and_answer':
                    raise ValueError(f"{case['id']}: answerable case needs search_and_answer")
                if not isinstance(case.get('expected_answer'), str) or not case['expected_answer'].strip():
                    raise ValueError(f"{case['id']}: missing expected answer")
                requirements = case.get('answer_requirements')
                if not isinstance(requirements, list) or not requirements or any(not isinstance(r, str) or not r.strip() for r in requirements):
                    raise ValueError(f"{case['id']}: missing grading requirements")
                if not isinstance(case.get('gold'), list) or not case['gold'] or 'absence_check' in case or 'absence_reason' in case:
                    raise ValueError(f"{case['id']}: missing grading requirements/gold or conflicting absence label")
                for evidence in case['gold']:
                    check_evidence(evidence, chunks, pages, case['filter'])
            else:
                reason = case.get('absence_reason')
                if case.get('expected_behavior') != 'search_and_abstain' or not isinstance(reason, str) or not reason.strip():
                    raise ValueError(f"{case['id']}: missing abstention behavior/reason")
                if any(key in case for key in ('gold', 'expected_answer', 'answer_requirements')):
                    raise ValueError(f"{case['id']}: unanswerable case must not carry answer/gold requirements")
                review = case.get('absence_check', {})
                if not isinstance(review, dict):
                    raise ValueError(f"{case['id']}: absence_check must be an object")
                source_ids = {d['source_id'] for d in manifest['documents']
                              if all(d.get(key) == value for key, value in case['filter'].items())}
                checked = review.get('checked_source_ids')
                if not isinstance(checked, list) or any(not isinstance(s, str) for s in checked):
                    raise ValueError(f"{case['id']}: checked_source_ids must be a list of source IDs")
                if set(checked) != source_ids or len(checked) != len(source_ids):
                    raise ValueError(f"{case['id']}: absence review must cover the complete filtered corpus")
                terms, related = review.get('search_terms'), review.get('related_evidence')
                if not isinstance(terms, list) or not terms or any(not isinstance(t, str) or not t.strip() for t in terms):
                    raise ValueError(f"{case['id']}: search_terms must be a nonempty list of nonblank strings")
                if not isinstance(related, list) or not related:
                    raise ValueError(f"{case['id']}: absence review needs search terms and relevant source passages")
                for evidence in related:
                    check_evidence(evidence, chunks, pages, case['filter'], single_chunk=False)
            counts['answerable' if case['answerable'] else 'unanswerable'] += 1
        if counts['answerable'] < (15 if selected == 'dev' else 5) or counts['unanswerable'] < 2:
            raise ValueError(f'{selected}: fewer cases than required by BENCHMARK.md')
        summary[selected] = dict(answerable=counts['answerable'], unanswerable=counts['unanswerable'], total=len(cases))
        if summary[selected] != protocol['counts'][selected]:
            raise ValueError(f'{selected}: protocol counts differ from the actual cases')
    return dict(benchmark_id=protocol['benchmark_id'], counts=summary,
                original_pdf_pages_checked=verify_pdfs(manifest, pages) if check_pdfs else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', required=True, choices=('dev', 'test', 'all'))
    parser.add_argument('--check-pdfs', action='store_true', help='Verify all 67 indexed pages against original PDFs')
    args = parser.parse_args()
    print(json.dumps(validate_benchmark(split=args.split, check_pdfs=args.check_pdfs), indent=2))


if __name__ == '__main__':
    main()
