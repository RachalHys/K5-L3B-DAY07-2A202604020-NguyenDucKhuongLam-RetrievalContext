"""Day 6 BGE-M3 encoding and exact pgvector retrieval, adapted for Day 7 chunks."""
import argparse
from collections import Counter
import json
import math
import os
import re
import time
import unicodedata

from dotenv import load_dotenv
import psycopg
from psycopg.types.json import Jsonb

from .day6 import CORPUS, ROOT, load_snapshot, sha256


FILTER_TYPES = {'publication_year': int, 'document_type': str, 'topic': str}


def validate_filters(filters: dict | None) -> dict:
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise ValueError('Filters must be an object.')
    for key, value in filters.items():
        if key not in FILTER_TYPES or type(value) is not FILTER_TYPES[key]:
            raise ValueError(f'Unsupported filter or value type: {key}')
    return filters


def vector_literal(vector, dimensions: int) -> str:
    values = [float(x) for x in vector]
    if len(values) != dimensions or not all(math.isfinite(x) for x in values) or not any(values):
        raise ValueError('Vector has wrong dimensions, non-finite values, or zero norm.')
    return '[' + ','.join(map(str, values)) + ']'


class QueryEmbedder:
    """Match Day 6's CPU/FP32, encode(), max length and L2 normalization."""

    def __init__(self, config: dict, *, offline: bool = False):
        if offline:
            os.environ['HF_HUB_OFFLINE'] = '1'
        import torch
        from sentence_transformers import SentenceTransformer
        torch.set_num_threads(4)
        self.model = SentenceTransformer(config['name'], revision=config['revision'], device='cpu',
                                         local_files_only=offline, model_kwargs={'torch_dtype': torch.float32})
        self.model.max_seq_length = config['max_tokens']
        if self.model.get_embedding_dimension() != config['dimensions']:
            raise ValueError('Query embedding dimension differs from Day 6.')

    def embed_query(self, query: str):
        if not isinstance(query, str) or not query.strip():
            raise ValueError('Query must be nonempty text.')
        length = len(self.model.tokenizer(query, truncation=False)['input_ids'])
        if length > self.model.max_seq_length:
            raise ValueError('Query exceeds the embedding token limit; refusing silent truncation.')
        return self.model.encode([query], normalize_embeddings=True, show_progress_bar=False,
                                 convert_to_numpy=True)[0]


class PgVectorStore:
    """An isolated Day 7 snapshot; JSON payload retains original citation metadata."""

    def __init__(self, database_url: str, provenance: dict):
        self.database_url = database_url
        self.model = provenance['model']
        self.dimensions = self.model['dimensions']
        self.snapshot = sha256(CORPUS / 'provenance.json')
        self.scope = provenance['scope']

    def load(self, chunks, vectors):
        if len(chunks) != len(vectors) or len({c['id'] for c in chunks}) != len(chunks):
            raise ValueError('Chunk/vector count mismatch or duplicate chunk IDs.')
        rows = [(self.scope, c['id'], Jsonb(c), vector_literal(v, self.dimensions))
                for c, v in zip(chunks, vectors)]
        with psycopg.connect(self.database_url, connect_timeout=10) as connection:
            connection.execute('CREATE EXTENSION IF NOT EXISTS vector')
            connection.execute('''CREATE TABLE IF NOT EXISTS day7_corpora (
                scope text PRIMARY KEY, snapshot text NOT NULL, model jsonb NOT NULL)''')
            connection.execute('''CREATE TABLE IF NOT EXISTS day7_chunks (
                scope text NOT NULL REFERENCES day7_corpora(scope),
                chunk_id text NOT NULL, payload jsonb NOT NULL,
                embedding vector(1024) NOT NULL, PRIMARY KEY (scope, chunk_id))''')
            connection.execute('''INSERT INTO day7_corpora VALUES (%s,%s,%s)
                ON CONFLICT (scope) DO UPDATE SET snapshot=EXCLUDED.snapshot, model=EXCLUDED.model''',
                               (self.scope, self.snapshot, Jsonb(self.model)))
            connection.execute('DELETE FROM day7_chunks WHERE scope=%s', (self.scope,))
            with connection.cursor() as cursor:
                cursor.executemany('INSERT INTO day7_chunks VALUES (%s,%s,%s,%s::vector)', rows)

    def check(self):
        with psycopg.connect(self.database_url, connect_timeout=10) as connection:
            row = connection.execute('SELECT snapshot,model FROM day7_corpora WHERE scope=%s',
                                     (self.scope,)).fetchone()
            if row != (self.snapshot, self.model):
                raise ValueError('Stored corpus/model differs from this snapshot; reload the Day 7 index.')
            ids = connection.execute('SELECT chunk_id FROM day7_chunks WHERE scope=%s ORDER BY chunk_id',
                                     (self.scope,)).fetchall()
        return [row[0] for row in ids]

    def search(self, query_vector, *, filters: dict | None = None, top_k: int = 3):
        if top_k < 1:
            raise ValueError('top_k must be positive.')
        filters = validate_filters(filters)
        vector = vector_literal(query_vector, self.dimensions)
        with psycopg.connect(self.database_url, connect_timeout=10) as connection:
            # Scope is fixed by the chosen corpus, never inferred from evaluation gold.
            rows = connection.execute('''SELECT payload, 1-(embedding <=> %s::vector) AS score
                FROM day7_chunks WHERE scope=%s AND payload->'metadata' @> %s::jsonb
                ORDER BY embedding <=> %s::vector,chunk_id LIMIT %s''',
                                      (vector, self.scope, Jsonb(filters), vector, top_k)).fetchall()
        return [dict(payload, score=score, strategy='dense') for payload, score in rows]


class DenseRetriever:
    def __init__(self, store: PgVectorStore, embedder: QueryEmbedder):
        store.check()
        self.store, self.embedder = store, embedder

    def search(self, query: str, *, filters: dict | None = None, top_k: int = 3):
        validate_filters(filters)
        return self.store.search(self.embedder.embed_query(query), filters=filters, top_k=top_k)


class BM25Retriever:
    """Okapi BM25 with corpus-wide document frequencies and explicit metadata filters."""

    def __init__(self, chunks: list[dict], *, k1: float = 1.2, b: float = 0.75):
        if k1 <= 0 or not 0 <= b <= 1 or not chunks:
            raise ValueError('Invalid BM25 parameters or empty corpus.')
        self.chunks, self.k1, self.b = chunks, k1, b
        self.counts = [Counter(self.tokenize(c['text'])) for c in chunks]
        self.lengths = [sum(row.values()) for row in self.counts]
        self.average_length = sum(self.lengths) / len(chunks)
        frequency = Counter(term for row in self.counts for term in row)
        self.idf = {term: math.log(1 + (len(chunks) - count + 0.5) / (count + 0.5))
                    for term, count in frequency.items()}

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return re.findall(r'\w+', unicodedata.normalize('NFC', text).casefold())

    def search(self, query: str, *, filters: dict | None = None, top_k: int = 3):
        filters = validate_filters(filters)
        if not isinstance(query, str) or not query.strip() or top_k < 1:
            raise ValueError('Query and top_k must be valid.')
        terms = set(self.tokenize(query))
        results = []
        for chunk, counts, length in zip(self.chunks, self.counts, self.lengths):
            if any(chunk['metadata'].get(key) != value for key, value in filters.items()):
                continue
            normalization = self.k1 * (1 - self.b + self.b * length / self.average_length)
            score = sum(self.idf[term] * counts[term] * (self.k1 + 1) / (counts[term] + normalization)
                        for term in terms if counts[term])
            if score > 0:
                results.append(dict(chunk, score=score, strategy='bm25'))
        return sorted(results, key=lambda c: (-c['score'], c['id']))[:top_k]


class HybridRetriever:
    """Fuse ranks, not incomparable dense/BM25 raw scores, using reciprocal rank fusion."""

    def __init__(self, dense: DenseRetriever, lexical: BM25Retriever, *, candidates: int = 20, rrf_k: int = 60):
        if candidates < 3 or rrf_k < 1:
            raise ValueError('Invalid hybrid candidate count or RRF constant.')
        self.dense, self.lexical, self.candidates, self.rrf_k = dense, lexical, candidates, rrf_k

    def search(self, query: str, *, filters: dict | None = None, top_k: int = 3):
        if top_k < 1:
            raise ValueError('top_k must be positive.')
        candidates = max(self.candidates, top_k)
        merged = {}
        for method, retriever in (('dense', self.dense), ('bm25', self.lexical)):
            for rank, chunk in enumerate(retriever.search(query, filters=filters, top_k=candidates), 1):
                row = merged.setdefault(chunk['id'], dict(chunk, score=0.0, strategy='hybrid', components={}))
                row['score'] += 1 / (self.rrf_k + rank)
                row['components'][method] = dict(rank=rank, score=chunk['score'])
        return sorted(merged.values(), key=lambda c: (-c['score'], c['id']))[:top_k]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    subparsers.add_parser('load', help='Load the verified Day 6 snapshot into the separate Day 7 store')
    search = subparsers.add_parser('search', help='Run a real query; this is not a benchmark')
    search.add_argument('--query', required=True)
    search.add_argument('--top-k', type=int, default=3)
    search.add_argument('--filter', type=json.loads, default=None, help='Explicit user metadata filter as JSON')
    search.add_argument('--offline', action='store_true', help='Require the existing model cache')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env', override=False)
    chunks, vectors, provenance = load_snapshot()
    store = PgVectorStore(os.environ['DATABASE_URL'], provenance)
    if args.command == 'load':
        store.load(chunks, vectors)
        if store.check() != sorted(c['id'] for c in chunks):
            raise ValueError('Database snapshot IDs differ from the exported corpus.')
        print(json.dumps(dict(scope=store.scope, chunks=len(chunks), dimensions=store.dimensions)))
    else:
        started = time.perf_counter()
        embedder = QueryEmbedder(provenance['model'], offline=args.offline)
        results = DenseRetriever(store, embedder).search(args.query, filters=args.filter, top_k=args.top_k)
        print(json.dumps(dict(query=args.query, filter=args.filter, results=results,
                              elapsed_seconds_including_model_load=time.perf_counter() - started),
                         ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
