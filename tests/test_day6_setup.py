"""Check inherited evidence integrity and reject incompatible retrieval inputs."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from src.day6 import CORPUS, load_snapshot, sha256, write_json
from src.retrieval import validate_filters, vector_literal


class SnapshotTests(unittest.TestCase):
    def test_inherited_chunks_resolve_to_source_pages(self):
        chunks, vectors, provenance = load_snapshot()
        self.assertEqual(len(chunks), 252)
        self.assertEqual(vectors.shape, (252, 1024))
        self.assertEqual(provenance['counts']['eligible_content_page_count'], 67)
        self.assertEqual(len({(c['source_id'], c['page']) for c in chunks}), 67)
        self.assertTrue(all(c['metadata']['document_id'] == c['source_id'] for c in chunks))

    def test_modified_source_text_fails_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'corpus'
            shutil.copytree(CORPUS, directory)
            with (directory / 'pages.jsonl').open('a', encoding='utf-8') as output:
                output.write('\n')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch: pages.jsonl'):
                load_snapshot(directory)

    def test_reordered_vector_rows_fail_even_with_updated_file_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'corpus'
            shutil.copytree(CORPUS, directory)
            path = directory / 'dense_vectors.npz'
            with np.load(path, allow_pickle=False) as archive:
                ids, vectors = archive['ids'].copy(), archive['vectors'].copy()
            np.savez_compressed(path, ids=ids[::-1], vectors=vectors[::-1])
            provenance = json.loads((directory / 'provenance.json').read_text())
            provenance['files']['dense_vectors.npz'] = sha256(path)
            write_json(directory / 'provenance.json', provenance)
            with self.assertRaisesRegex(ValueError, 'vector rows do not match'):
                load_snapshot(directory)

    def test_query_vectors_and_explicit_filters_are_validated(self):
        for vector in ([0, 0], [1], [float('nan'), 1], [float('inf'), 1]):
            with self.subTest(vector=vector), self.assertRaises(ValueError):
                vector_literal(vector, 2)
        for filters in ({'publication_year': True}, {'gold_source_id': 'source'}, [], {'topic': 2020}):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                validate_filters(filters)
        self.assertEqual(validate_filters({'publication_year': 2024}), {'publication_year': 2024})


if __name__ == '__main__':
    unittest.main()
