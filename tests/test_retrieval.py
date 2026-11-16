"""Filtering and rank fusion behavior on controlled evidence fixtures."""
import unittest

from src.retrieval import BM25Retriever, HybridRetriever


def chunk(id, text, year=2020):
    return dict(id=id, text=text, source_id='doc', source='doc.pdf', page=1,
                metadata={'publication_year': year, 'document_type': 'booklet', 'topic': 'stroke'})


class RetrievalTests(unittest.TestCase):
    def test_bm25_ranks_evidence_and_enforces_filters(self):
        rows = [chunk('old', 'stroke rehabilitation equipment'),
                chunk('new', 'stroke rehabilitation equipment', 2024),
                chunk('other', 'cholesterol medication')]
        retriever = BM25Retriever(rows)
        self.assertEqual([c['id'] for c in retriever.search('rehabilitation equipment', filters={'publication_year': 2024})], ['new'])
        self.assertEqual(retriever.search('nonexistentword'), [])
        self.assertEqual(retriever.search('cholesterol')[0]['id'], 'other')
        with self.assertRaises(ValueError):
            retriever.search('stroke', filters={'gold_page': 1})

    def test_rrf_rewards_agreement_without_comparing_raw_scores(self):
        a, b, shared = chunk('a', 'a'), chunk('b', 'b'), chunk('shared', 'shared')
        class Ranked:
            def __init__(self, rows): self.rows = rows; self.filters = None
            def search(self, query, *, filters, top_k):
                self.filters = filters
                return self.rows[:top_k]
        dense = Ranked([dict(a, score=.9), dict(shared, score=.8)])
        lexical = Ranked([dict(b, score=1000000), dict(shared, score=.01)])
        result = HybridRetriever(dense, lexical).search('q', filters={'publication_year': 2020})
        self.assertEqual(result[0]['id'], 'shared')
        self.assertEqual(set(result[0]['components']), {'dense', 'bm25'})
        self.assertEqual(dense.filters, lexical.filters)
        self.assertEqual(dense.filters, {'publication_year': 2020})


if __name__ == '__main__': unittest.main()
