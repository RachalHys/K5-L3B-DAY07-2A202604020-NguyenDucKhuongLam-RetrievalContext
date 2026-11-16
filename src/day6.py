"""Export and verify the selected Day 6 corpus without changing its repository."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'data/basic'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_snapshot(directory: Path = CORPUS):
    provenance = json.loads((directory / 'provenance.json').read_text(encoding='utf-8'))
    for name, expected in provenance['files'].items():
        if sha256(directory / name) != expected:
            raise ValueError(f'Corpus checksum mismatch: {name}')
    chunks = json.loads((directory / 'chunks.json').read_text(encoding='utf-8'))
    with np.load(directory / 'dense_vectors.npz', allow_pickle=False) as archive:
        ids, vectors = archive['ids'].tolist(), archive['vectors'].copy()
    if ids != [c['id'] for c in chunks] or len(set(ids)) != len(ids):
        raise ValueError('Chunk IDs and vector rows do not match uniquely and in order.')
    if vectors.shape != (len(chunks), provenance['model']['dimensions']):
        raise ValueError('Vector count or embedding dimensions do not match the corpus.')
    if vectors.dtype != np.float32 or not np.isfinite(vectors).all():
        raise ValueError('Expected finite float32 embeddings.')
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5):
        raise ValueError('Expected L2-normalized Day 6 embeddings.')
    pages = [json.loads(line) for line in (directory / 'pages.jsonl').read_text(encoding='utf-8').splitlines()]
    page_map = {(p['document_id'], p['page']): p for p in pages}
    for chunk in chunks:
        page = page_map[(chunk['source_id'], chunk['page'])]
        start, end = chunk['metadata']['start_char'], chunk['metadata']['end_char']
        if page['text'][start:end] != chunk['text'] or page['source'] != chunk['source']:
            raise ValueError(f"Chunk does not match its original page/offsets: {chunk['id']}")
    return chunks, vectors, provenance


def export_day6(repo: Path) -> dict:
    repo = repo.resolve()
    pointer = json.loads((repo / 'artifacts/current_prepared.json').read_text(encoding='utf-8'))
    prepared = repo / pointer['path']
    prepared_info = json.loads((prepared / 'prepared.json').read_text(encoding='utf-8'))
    embedding_info = json.loads((repo / 'artifacts/embeddings/embedding_run.json').read_text(encoding='utf-8'))
    vectors_path = repo / 'artifacts/embeddings/vectors.npz'
    if sha256(vectors_path) != embedding_info['vectors_sha256']:
        raise ValueError('Day 6 vector archive checksum mismatch.')
    if embedding_info['prepared_id'] != pointer['prepared_id']:
        raise ValueError('Day 6 embeddings refer to a different prepared snapshot.')
    if embedding_info['model'] != prepared_info['config']['model']:
        raise ValueError('Day 6 preprocessing and embedding model configurations differ.')
    for name in ('chunks_B.jsonl', 'pages.jsonl'):
        if sha256(prepared / name) != prepared_info['files'][name]:
            raise ValueError(f'Day 6 prepared file checksum mismatch: {name}')
    manifest_path = repo / 'data/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if sha256(manifest_path) != prepared_info['input_hashes']['data/manifest.json']:
        raise ValueError('Day 6 source manifest changed after preprocessing.')
    for document in manifest['documents']:
        if sha256(repo / document['source_path_or_url']) != document['sha256']:
            raise ValueError(f"Source PDF checksum mismatch: {document['source_id']}")

    raw = [json.loads(line) for line in (prepared / 'chunks_B.jsonl').read_text(encoding='utf-8').splitlines()]
    chunks = [dict(id=c['chunk_id'], source_id=c['document_id'], source=c['source'],
                   page=c['page'], text=c['text'], metadata=c['metadata']) for c in raw]
    with np.load(vectors_path, allow_pickle=False) as archive:
        ids, vectors = archive['ids_B'].copy(), archive['B'].copy()
    if ids.tolist() != [c['id'] for c in chunks]:
        raise ValueError('Day 6 B chunk/vector order mismatch.')
    CORPUS.mkdir(parents=True, exist_ok=True)
    write_json(CORPUS / 'chunks.json', chunks)
    np.savez_compressed(CORPUS / 'dense_vectors.npz', ids=ids, vectors=vectors)
    shutil.copyfile(prepared / 'pages.jsonl', CORPUS / 'pages.jsonl')
    shutil.copyfile(manifest_path, CORPUS / 'manifest.json')
    for document in manifest['documents']:
        relative = document['source_path_or_url']
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / relative, target)

    provenance = dict(
        upstream_repository='https://github.com/RachalHys/K5-L3B-DAY06-NguyenDucKhuongLam-2A202604020-DataIngestion',
        upstream_commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
        prepared_id=pointer['prepared_id'], chunk_strategy='B',
        chunking=prepared_info['config']['strategies']['B'],
        model=embedding_info['model'], embedding_device=embedding_info['device'],
        embedding_packages=embedding_info['packages'],
        upstream_vectors_sha256=embedding_info['vectors_sha256'],
        upstream_chunks_sha256=prepared_info['files']['chunks_B.jsonl'],
        upstream_questions_sha256=prepared_info['input_hashes']['benchmark/questions.json'],
        scope=manifest['corpus_id'], counts=dict(manifest['summary'], chunk_count=len(chunks)),
        files={name: sha256(CORPUS / name) for name in
               ('chunks.json', 'dense_vectors.npz', 'pages.jsonl', 'manifest.json')},
    )
    write_json(CORPUS / 'provenance.json', provenance)
    load_snapshot()
    return provenance['counts']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True, help='Read-only source Day 6 checkout')
    args = parser.parse_args()
    print(json.dumps(export_day6(args.repo), indent=2))


if __name__ == '__main__':
    main()
