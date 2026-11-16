"""Benchmark integrity, source grounding and separation of agent inputs from gold."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from src.benchmark import BASIC, INPUT_FIELDS, load_cases, load_inputs, validate_benchmark
from src.day6 import load_snapshot, sha256, write_json
from starter.baseline import validate


class BenchmarkTests(unittest.TestCase):
    def test_counts_and_all_alternative_evidence_meet_the_lab_contract(self):
        result = validate_benchmark()
        self.assertEqual(result['counts'], {
            'dev': {'answerable': 20, 'unanswerable': 2, 'total': 22},
            'test': {'answerable': 5, 'unanswerable': 2, 'total': 7},
        })
        chunks, _, _ = load_snapshot()
        for split in ('dev', 'test'):
            validate(chunks, [q for q in load_cases(split) if q['answerable']])

    def test_agent_loader_needs_neither_labels_nor_the_other_split(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            shutil.copyfile(BASIC / 'dev.json', directory / 'dev.json')
            inputs = load_inputs('dev', directory)
            self.assertEqual(len(inputs), 22)
            self.assertTrue(all(set(q) == INPUT_FIELDS for q in inputs))
            self.assertFalse((directory / 'labels').exists())
            self.assertFalse((directory / 'test.json').exists())

    def test_dev_validation_does_not_inspect_test_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'basic'
            shutil.copytree(BASIC, directory)
            (directory / 'test.json').unlink()
            (directory / 'labels/test.json').unlink()
            self.assertEqual(validate_benchmark(split='dev', directory=directory)['counts']['dev']['total'], 22)

    def test_gold_and_unmentioned_filters_are_rejected_from_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows = load_inputs('dev')
            leaked = copy.deepcopy(rows)
            leaked[0]['gold'] = [{'evidence': 'Do not send this to the agent.'}]
            write_json(directory / 'dev.json', leaked)
            with self.assertRaisesRegex(ValueError, 'input may contain only'):
                load_inputs('dev', directory)
            filtered = copy.deepcopy(rows)
            filtered[0]['filter'] = {'publication_year': 2020}
            write_json(directory / 'dev.json', filtered)
            with self.assertRaisesRegex(ValueError, 'explicitly stated'):
                load_inputs('dev', directory)

    def test_q17_equipment_evidence_keeps_home_context_in_one_chunk(self):
        case = next(q for q in load_cases('dev') if q['id'] == 'q17')
        self.assertEqual(len(case['gold']), 1)
        self.assertIn('Home-based rehabilitation', case['gold'][0]['evidence'])
        self.assertIn('specialized equipment', case['gold'][0]['evidence'])
        chunks, _, _ = load_snapshot()
        validate(chunks, [case])

    def test_absence_review_must_cover_every_source_within_filter(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'basic'
            shutil.copytree(BASIC, directory)
            path = directory / 'labels/dev.json'
            labels = json.loads(path.read_text())
            case = next(q for q in labels if not q['answerable'])
            case['absence_check']['checked_source_ids'].pop()
            write_json(path, labels)
            protocol = json.loads((directory / 'protocol.json').read_text())
            protocol['files_sha256']['labels/dev.json'] = sha256(path)
            write_json(directory / 'protocol.json', protocol)
            with self.assertRaisesRegex(ValueError, 'complete filtered corpus'):
                validate_benchmark(split='dev', directory=directory)

    def test_changed_frozen_test_labels_are_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'basic'
            shutil.copytree(BASIC, directory)
            path = directory / 'labels/test.json'
            path.write_text(path.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'Frozen benchmark changed: labels/test.json'):
                validate_benchmark(split='test', directory=directory)

    def test_input_label_id_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'basic'
            shutil.copytree(BASIC, directory)
            path = directory / 'labels/dev.json'
            labels = json.loads(path.read_text())
            labels[0]['id'] = 'wrong-case'
            write_json(path, labels)
            with self.assertRaisesRegex(ValueError, 'exactly the same IDs'):
                load_cases('dev', directory)

    def test_invalid_absence_labels_are_rejected(self):
        mutations = {
            'blank_reason': lambda case: case.update(absence_reason='   '),
            'string_terms': lambda case: case['absence_check'].update(search_terms='TRANSPORT'),
            'blank_term': lambda case: case['absence_check'].update(search_terms=[' ']),
            'answer_requirements': lambda case: case.update(answer_requirements=['An unsupported answer.']),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary) / 'basic'
                shutil.copytree(BASIC, directory)
                path = directory / 'labels/dev.json'
                labels = json.loads(path.read_text())
                mutate(next(q for q in labels if not q['answerable']))
                write_json(path, labels)
                protocol = json.loads((directory / 'protocol.json').read_text())
                protocol['files_sha256']['labels/dev.json'] = sha256(path)
                write_json(directory / 'protocol.json', protocol)
                with self.assertRaises(ValueError):
                    validate_benchmark(split='dev', directory=directory)

    def test_corpus_fingerprint_cannot_omit_artifacts(self):
        for missing in ('all', 'chunks.json'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary) / 'basic'
                shutil.copytree(BASIC, directory)
                protocol = json.loads((directory / 'protocol.json').read_text())
                if missing == 'all':
                    protocol['corpus_sha256'] = {}
                else:
                    protocol['corpus_sha256'].pop(missing)
                write_json(directory / 'protocol.json', protocol)
                with self.assertRaisesRegex(ValueError, 'Corpus fingerprint must cover'):
                    validate_benchmark(split='dev', directory=directory)


if __name__ == '__main__':
    unittest.main()
