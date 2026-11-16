"""Run dev experiments, freeze a dev-selected configuration, then evaluate held-out test."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import time

from dotenv import load_dotenv

from .agent import run_agent, SYSTEM_PROMPT
from .benchmark import BASIC, load_cases, load_inputs, validate_benchmark
from .day6 import CORPUS, ROOT, load_snapshot, sha256, write_json
from .evaluation import summarize
from .llm import ChatClient
from .retrieval import BM25Retriever, DenseRetriever, HybridRetriever, PgVectorStore, QueryEmbedder


CONFIG_PATH = ROOT / 'configs/experiments.json'


def code_hashes():
    paths = sorted((ROOT / 'src').glob('*.py')) + [ROOT / 'starter/baseline.py', ROOT / 'starter/agent_metrics.py']
    return {str(p.relative_to(ROOT)): sha256(p) for p in paths}


def make_retriever(config: dict, settings: dict):
    load_dotenv(ROOT / '.env', override=False)
    chunks, _, provenance = load_snapshot()
    lexical = BM25Retriever(chunks, **settings['bm25'])
    if config['method'] == 'bm25':
        return lexical
    store = PgVectorStore(os.environ['DATABASE_URL'], provenance)
    dense = DenseRetriever(store, QueryEmbedder(provenance['model'], offline=True))
    if config['method'] == 'dense':
        return dense
    if config['method'] == 'hybrid':
        return HybridRetriever(dense, lexical, **settings['hybrid'])
    raise ValueError('Unknown retrieval method.')


def read_traces(directory: Path):
    return [json.loads(line) for line in (directory / 'traces.jsonl').read_text(encoding='utf-8').splitlines()]


def model_settings(client):
    return dict(model=client.model, endpoint=client.url, reasoning_effort=client.reasoning_effort,
                max_completion_tokens=client.max_completion_tokens, temperature=0)


def run_configuration(config: dict, settings: dict, split: str, output: Path, selection: dict | None):
    if split == 'test':
        if selection is None or config['id'] not in (selection['baseline']['id'], selection['selected']['id']):
            raise ValueError('Test requires a frozen baseline/selected configuration.')
        if selection['config_file_sha256'] != sha256(CONFIG_PATH) or selection['code_sha256'] != code_hashes():
            raise ValueError('Configuration/code changed after selection; test is blocked.')
        if selection['benchmark_protocol_sha256'] != sha256(BASIC / 'protocol.json'):
            raise ValueError('Benchmark changed after selection.')
        if config not in settings['configurations']:
            raise ValueError('Frozen configuration parameters differ from the experiment registry.')
    validate_benchmark(split=split)
    inputs = load_inputs(split)
    client = ChatClient.from_env(rates=settings['pricing'])
    if selection is not None and split == 'test' and model_settings(client) != selection['model_settings']:
        raise ValueError('LLM settings changed after selection; test is blocked.')
    output.mkdir(parents=True, exist_ok=False)
    setup_started = time.perf_counter()
    retriever = make_retriever(config, settings)
    manifest = dict(config=config, split=split, model=client.model, reasoning_effort=client.reasoning_effort,
                    endpoint=client.url, max_completion_tokens=client.max_completion_tokens, temperature=0,
                    started_at=datetime.now(timezone.utc).isoformat(),
                    python=platform.python_version(), requirements_sha256=sha256(ROOT / 'requirements.lock'),
                    embedding_model=json.loads((CORPUS / 'provenance.json').read_text())['model'],
                    packages={name: importlib.metadata.version(name) for name in ('torch', 'sentence-transformers', 'numpy', 'psycopg')},
                    benchmark_protocol_sha256=sha256(BASIC / 'protocol.json'),
                    input_sha256=sha256(BASIC / f'{split}.json'), config_file_sha256=sha256(CONFIG_PATH),
                    code_sha256=code_hashes(), system_prompt_sha256=hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
                    git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    setup_seconds=time.perf_counter() - setup_started, pricing=settings['pricing'])
    manifest['model_settings'] = model_settings(client)
    write_json(output / 'run.json', manifest)
    traces = []
    with (output / 'traces.jsonl').open('w', encoding='utf-8') as stream:
        for q in inputs:
            started = time.perf_counter()
            ranking_started = time.perf_counter()
            try:
                ranking = retriever.search(q['question'], filters=q['filter'], top_k=3)
                ranking_ms = (time.perf_counter() - ranking_started) * 1000
                result = run_agent(q['question'], client, retriever, filters=q['filter'], config=config)
            except Exception as error:
                ranking, ranking_ms = [], (time.perf_counter() - ranking_started) * 1000
                result = dict(status='error', answer='', citations=[], events=[], model_calls=[],
                              context='', context_ids=[], search_calls=0, llm_calls=0,
                              estimated_cost_usd=0, cost_complete=True, error=str(error))
            result.update(query_id=q['id'], split=split, question=q['question'], filter=q['filter'],
                          configuration=config['id'], original_ranking=ranking, original_ranking_ms=ranking_ms,
                          elapsed_ms=(time.perf_counter() - started) * 1000)
            traces.append(result)
            stream.write(json.dumps(result, ensure_ascii=False) + '\n')
            stream.flush()
            print(f"{config['id']} {split} {q['id']}: {result['status']}", flush=True)
    # Gold is opened only for evaluation, never supplied to run_agent or a retriever.
    write_json(output / 'summary.json', summarize(load_cases(split), traces))


def review_run(directory: Path):
    manifest = json.loads((directory / 'run.json').read_text())
    if manifest['benchmark_protocol_sha256'] != sha256(BASIC / 'protocol.json'):
        raise ValueError('Cannot review against a changed benchmark protocol.')
    reviews = json.loads((directory / 'reviews.json').read_text())
    summary = summarize(load_cases(manifest['split']), read_traces(directory), reviews)
    write_json(directory / 'summary.json', summary)
    return summary


def selection_key(summary: dict):
    scores = summary['selection_scores']
    agent = summary['agent']
    citation = agent['citation_validity']
    supported_rate = citation['n'] / citation['N'] if citation['N'] else -1
    return (scores['grounded_points_per_answerable_attempt'], scores['correct_abstentions_per_unanswerable_attempt'],
            -summary['errors'], supported_rate, summary['context_evidence']['rate'],
            -summary['median_end_to_end_ms'], -summary['estimated_cost_usd'] if summary['cost_complete'] else -1e99)


def freeze_selection(dev_root: Path, output: Path, settings: dict):
    if output.exists():
        raise ValueError('Selection file already exists; preserve the previous selection.')
    candidates, models = [], None
    for config in settings['configurations']:
        directory = dev_root / config['id']
        manifest = json.loads((directory / 'run.json').read_text())
        if manifest['split'] != 'dev' or manifest['config'] != config:
            raise ValueError('Selection requires matching complete dev runs.')
        if manifest['code_sha256'] != code_hashes() or manifest['config_file_sha256'] != sha256(CONFIG_PATH):
            raise ValueError('Dev runs are stale after code/config changes; rerun the affected experiment.')
        if manifest['benchmark_protocol_sha256'] != sha256(BASIC / 'protocol.json'):
            raise ValueError('Benchmark differs from the reviewed dev run.')
        if models is None:
            models = manifest['model_settings']
        elif models != manifest['model_settings']:
            raise ValueError('Dev comparison must use the same LLM settings.')
        summary = review_run(directory)
        candidates.append((selection_key(summary), config, directory))
    _, selected, _ = max(candidates, key=lambda item: item[0])
    baseline = next(c for c in settings['configurations'] if c['id'] == 'dense_baseline')
    write_json(output, dict(selected=selected, baseline=baseline, frozen_at=datetime.now(timezone.utc).isoformat(),
                            model_settings=models,
                            config_file_sha256=sha256(CONFIG_PATH), code_sha256=code_hashes(),
                            benchmark_protocol_sha256=sha256(BASIC / 'protocol.json'),
                            rule=json.loads((BASIC / 'protocol.json').read_text())['selection_rule'],
                            dev_runs=[dict(path=str(p.relative_to(ROOT)), selection_key=list(key),
                                           reviews_sha256=sha256(p / 'reviews.json'), traces_sha256=sha256(p / 'traces.jsonl'))
                                      for key, _, p in candidates]))
    print(json.dumps(dict(selected=selected['id'], baseline=baseline['id'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('--split', required=True, choices=('dev', 'test'))
    run.add_argument('--config', required=True, help='Configuration ID, all (dev), or comparison (test)')
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--selection', type=Path)
    review = commands.add_parser('review')
    review.add_argument('--run', type=Path, required=True)
    select = commands.add_parser('select')
    select.add_argument('--dev-root', type=Path, required=True)
    select.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    settings = json.loads(CONFIG_PATH.read_text())
    if args.command == 'review':
        print(json.dumps(review_run(args.run), indent=2))
    elif args.command == 'select':
        freeze_selection(args.dev_root.resolve(), args.output, settings)
    else:
        selection = json.loads(args.selection.read_text()) if args.selection else None
        if args.config == 'comparison' and args.split == 'test' and selection:
            configs = [selection['baseline']]
            if selection['selected']['id'] != selection['baseline']['id']:
                configs.append(selection['selected'])
        elif args.config == 'all' and args.split == 'dev':
            configs = settings['configurations']
        else:
            configs = [c for c in settings['configurations'] if c['id'] == args.config]
        if not configs:
            raise ValueError('Unknown configuration.')
        for config in configs:
            run_configuration(config, settings, args.split, args.output / config['id'], selection)


if __name__ == '__main__':
    main()
