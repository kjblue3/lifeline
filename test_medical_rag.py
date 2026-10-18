"""Offline provenance/contract tests, not assertions of medical validity.

Run with .venv/bin/python -B -m unittest -v test_medical_rag.
All writable database/snapshot fixtures live under the project root. Model
responses are explicit test fixtures; no weights, legacy app, or network needed.
"""
import asyncio
from contextlib import closing, ExitStack, redirect_stdout
import hashlib
import io
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Block network even while importing the router; do not import the legacy app.
NETWORK_TARGETS = ('socket.socket.connect', 'socket.socket.connect_ex',
                   'socket.create_connection', 'socket.getaddrinfo',
                   'socket.gethostbyname', 'socket.gethostbyname_ex',
                   'socket.gethostbyaddr', 'socket.socket.sendto')
with ExitStack() as stack:
    for target in NETWORK_TARGETS:
        stack.enter_context(patch(target, side_effect=AssertionError('Network/DNS forbidden')))
    import chat
    import medical_rag
    from medical_data import install_references as installer
    from inference import Answer, InferenceError, SAFETY_NOTICE, Source

ROOT = Path(__file__).resolve().parent
INSTALLED = ROOT / 'medical_data' / 'lifeline_medical_installed.db'
ORIGINAL = ROOT / 'medical_data' / 'lifeline_medical.db'
SNAPSHOT = ROOT / 'medical_data' / 'official_first_aid.json'


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.network = [self.enterContext(patch(
            target, side_effect=AssertionError('Network/DNS forbidden')))
            for target in NETWORK_TARGETS]
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory(dir=ROOT)))
        self.hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in (ORIGINAL, INSTALLED, SNAPSHOT)}
        self.addCleanup(self.assert_sources_unchanged)
        self.library = medical_rag.MedicalLibrary(INSTALLED, SNAPSHOT)
        self.snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        self.topics = {topic['title']: topic for topic in self.snapshot['topics']}

    def tearDown(self):
        for network in self.network:
            network.assert_not_called()

    def assert_sources_unchanged(self):
        for path, expected in self.hashes.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, str(path))

    def copied_database(self):
        path = self.temp / 'installed.db'
        shutil.copyfile(INSTALLED, path)
        return path

    def assert_provenance(self, row):
        source = self.topics[row['title']]
        self.assertEqual(row['summary'], source['summary'])
        self.assertEqual(row['source_url'], source['url'])
        self.assertEqual(row['medlineplus_id'], source['medlineplus_id'])
        self.assertEqual(row['source_name'], 'MedlinePlus / NLM')
        self.assertEqual(row['published_date'], self.snapshot['feed_date'])
        self.assertEqual(row['imported_at'], self.snapshot['imported_at'])
        self.assertEqual(row['content_status'], 'official_summary')


class RetrievalTests(OfflineTests):
    def test_installed_counts_and_all_ten_source_records(self):
        self.assertEqual(self.library.count(), 10)
        with closing(self.library._connect()) as conn:
            self.assertEqual(dict(conn.execute(
                'SELECT content_status,count(*) FROM cases GROUP BY content_status')),
                {'official_summary': 10, 'catalog_only': 90})
            rows = conn.execute("SELECT * FROM cases WHERE content_status='official_summary'").fetchall()
        self.assertEqual({row['title'] for row in rows}, set(installer.TITLES))
        for row in rows:
            self.assert_provenance(row)

    def test_real_installed_ten_title_queries(self):
        queries = ('bleeding', 'burns', 'choking', 'poisoning', 'heat illness',
                   'hypothermia', 'frostbite', 'dehydration', 'sprains', 'wounds')
        for query, title in zip(queries, installer.TITLES):
            with self.subTest(query=query, title=title):
                rows = self.library.search(query)
                self.assertTrue(rows, f'Installed title {title!r} was not retrieved')
                self.assertEqual(rows[0]['title'], title)
                for row in rows:
                    self.assert_provenance(row)

    def test_real_installed_aliases(self):
        # Burns has no catalog aliases; its literal title is covered above.
        aliases = {'deep wound bleeding': 'Bleeding', 'blocked airway': 'Choking',
                   'swallowed chemicals': 'Poisoning', 'heatstroke': 'Heat Illness',
                   'cold exposure': 'Hypothermia', 'frozen fingers': 'Frostbite',
                   'thirsty': 'Dehydration', 'twisted ankle': 'Sprains and Strains',
                   'lacerations': 'Wounds and Injuries'}
        for query, title in aliases.items():
            with self.subTest(query=query):
                rows = self.library.search(query)
                self.assertTrue(rows, f'Installed alias {query!r} was not retrieved')
                self.assertEqual(rows[0]['title'], title)
                for row in rows:
                    self.assert_provenance(row)

    def test_catalog_only_and_generic_or_unmatched_questions_are_excluded(self):
        for query in ('CPR', 'cardiac arrest', 'chest pain', 'anaphylaxis',
                      'gastrointestinal bleeding', 'foodborne illness',
                      'urinary tract infections', 'first aid', 'help',
                      'please give me advice', '', '!!!', 'zzzxylophoneqqq'):
            with self.subTest(query=query):
                self.assertEqual(self.library.search(query), [])
        self.assertEqual(medical_rag.MedicalLibrary(ORIGINAL, SNAPSHOT).count(), 0)
        self.assertEqual(medical_rag.MedicalLibrary(ORIGINAL, SNAPSHOT).search('choking'), [])

    def test_missing_database_is_not_created(self):
        missing = self.temp / 'missing.db'
        library = medical_rag.MedicalLibrary(missing, SNAPSHOT)
        self.assertEqual(library.count(), 0)
        self.assertEqual(library.search('choking'), [])
        self.assertFalse(missing.exists())

    def test_query_punctuation_and_operators_are_literals(self):
        for query in ('CHOKING!!!', '"choking"', '(choking) OR NOT *',
                      'choking; DROP TABLE cases; --', "choking' UNION SELECT * FROM cases --",
                      'title:choking NEAR(summary, 1)', 'choking\x00'):
            with self.subTest(query=query):
                rows = self.library.search(query)
                self.assertTrue(rows)
                self.assertEqual(rows[0]['title'], 'Choking')
                for row in rows:
                    self.assert_provenance(row)
        for query in ('*', 'OR NOT AND', 'title:*', '" ) OR summary:* --'):
            with self.subTest(query=query):
                self.assertEqual(self.library.search(query), [])
        self.assertEqual(self.library.count(), 10)

    def test_limits_and_duplicate_query_tokens(self):
        for limit in (0, -1, 6):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.library.search('choking', limit=limit)
        self.assertEqual(self.library.search('choking choking'), self.library.search('choking'))
        self.assertEqual(len(self.library.search('hypothermia frostbite', limit=1)), 1)
        self.assertEqual(len(self.library.search('hypothermia frostbite', limit=2)), 2)

    def test_fts_unavailable_falls_back_to_trusted_title_alias_search(self):
        path = self.copied_database()
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute('DROP TABLE cases_fts')
        library = medical_rag.MedicalLibrary(path, SNAPSHOT)
        self.assertEqual(library.search('blocked airway')[0]['title'], 'Choking')
        self.assertEqual(library.search('cardiac arrest'), [])
        self.assertEqual(library.search('burn')[0]['title'], 'Burns')
        self.assertEqual(library.count(), 10)

    def test_natural_phrases_and_unsupported_mixed_questions(self):
        for query, title in (('my friend is bleeding', 'Bleeding'),
                             ('burn on my hand', 'Burns'), ('burned my arm', 'Burns')):
            with self.subTest(query=query):
                self.assertEqual(self.library.search(query)[0]['title'], title)
        for query in ('choking blocked airway cardiac arrest',
                      'deep wound bleeding gastrointestinal bleeding',
                      'burns and anaphylaxis', 'blood'):
            with self.subTest(query=query):
                self.assertEqual(self.library.search(query), [])

    def test_each_tampered_provenance_field_excludes_the_row(self):
        path = self.copied_database()
        fields = {'summary': 'FABRICATED TEST TEXT', 'source_url': 'https://example.invalid/fake',
                  'source_name': 'Fake publisher', 'medlineplus_id': '999999999',
                  'published_date': '01/01/1900 00:00:00',
                  'imported_at': '1900-01-01T00:00:00Z',
                  'content_status': 'catalog_only', 'title': 'Invented Choking Reference'}
        for field, value in fields.items():
            with self.subTest(field=field):
                with closing(sqlite3.connect(path)) as conn, conn:
                    original = conn.execute(f'SELECT {field} FROM cases WHERE id=4').fetchone()[0]
                    conn.execute(f'UPDATE cases SET {field}=? WHERE id=4', (value,))
                library = medical_rag.MedicalLibrary(path, SNAPSHOT)
                self.assertEqual(library.count(), 9)
                self.assertEqual(library.search('choking'), [])
                with closing(sqlite3.connect(path)) as conn, conn:
                    conn.execute(f'UPDATE cases SET {field}=? WHERE id=4', (original,))

    def test_missing_invalid_and_digest_tampered_snapshots_fail_closed(self):
        path = self.temp / 'snapshot.json'
        for contents in (None, '{invalid', '{}', 'null', '[]'):
            with self.subTest(contents=contents):
                if contents is not None:
                    path.write_text(contents, encoding='utf-8')
                library = medical_rag.MedicalLibrary(INSTALLED, path)
                self.assertEqual(library.count(), 0)
                self.assertEqual(library.search('choking'), [])
        tampered = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        tampered['topics'][2]['summary'] += ' FABRICATED TEST TEXT'
        path.write_text(json.dumps(tampered), encoding='utf-8')
        library = medical_rag.MedicalLibrary(INSTALLED, path)
        self.assertEqual(library.count(), 0)
        self.assertEqual(library.search('choking'), [])
        # Recomputing the envelope hash cannot make text differing from XML valid.
        tampered['snapshot_sha256'] = installer.digest(
            {key: value for key, value in tampered.items() if key != 'snapshot_sha256'})
        path.write_text(json.dumps(tampered), encoding='utf-8')
        self.assertEqual(medical_rag.MedicalLibrary(INSTALLED, path).count(), 0)


class GroundingFixtures(OfflineTests):
    def setUp(self):
        super().setUp()
        self.provider = SimpleNamespace(configured=True, ready=True,
                                        model='explicit-test-fixture-no-model', answer=AsyncMock())

    def selector_fixture(self, text):
        self.provider.answer.return_value = Answer(answer=text, notice='TEST FIXTURE ONLY',
            sources=[Source(title='FABRICATED MODEL CITATION', url='https://example.invalid/fake')])


class GroundingTests(GroundingFixtures):
    def test_explicit_selection_quotes_only_chosen_installed_source(self):
        rows = self.library.search('hypothermia frostbite')
        selected = next(row for row in rows if row['title'] == 'Frostbite')
        self.selector_fixture(json.dumps({'source_ids': [str(selected['id'])]}))
        result = asyncio.run(medical_rag.grounded_answer(
            self.provider, self.library, 'hypothermia frostbite'))
        self.assertIn(selected['title'] + '\n' + selected['summary'], result.answer)
        self.assertNotIn(self.topics['Hypothermia']['summary'], result.answer)
        self.assertEqual([source.model_dump() for source in result.sources], [{
            'title': 'Frostbite - MedlinePlus / NLM', 'url': self.topics['Frostbite']['url']}])
        self.assertEqual(result.notice, medical_rag.NOTICE)
        self.assertNotIn('FABRICATED', result.model_dump_json())
        self.assertNotIn('example.invalid', result.model_dump_json())
        self.provider.answer.assert_awaited_once()
        prompt = self.provider.answer.await_args.args[0]
        payload = json.loads(prompt.split('\n', 1)[1])
        self.assertEqual(payload, {'question': 'hypothermia frostbite', 'references': [
            {'id': str(row['id']), 'title': row['title'],
             'text': re.split(r'\n\s*\n', row['summary'])[0],
             'url': row['source_url']} for row in rows]})

    def test_two_explicit_ids_preserve_selection_order(self):
        rows = self.library.search('hypothermia frostbite')
        selected = list(reversed(rows))
        self.selector_fixture(json.dumps({'source_ids': [str(row['id']) for row in selected]}))
        result = asyncio.run(medical_rag.grounded_answer(
            self.provider, self.library, 'hypothermia frostbite'))
        self.assertEqual([source.url for source in result.sources],
                         [row['source_url'] for row in selected])
        for row in selected:
            self.assertIn(row['summary'], result.answer)

    def test_fabricated_prose_citation_ids_and_malformed_selections_fail_closed(self):
        outputs = ('FABRICATED treatment advice [1] https://example.invalid/fake',
                   '```json\n{"source_ids":["4"]}\n```', '{broken', 'null', '[]',
                   '{}', '{"source_ids":[]}', '{"source_ids":["999999"]}',
                   '{"source_ids":["2"]}', '{"source_ids":[4]}',
                   '{"source_ids":"4"}', '{"source_ids":null}',
                   '{"source_ids":["4","4"]}', '{"source_ids":["4","4","4"]}',
                   '{"source_ids":["4"],"answer":"FABRICATED prose"}',
                   '{"source_ids":["4"],"citation":"https://example.invalid/fake"}')
        for output in outputs:
            with self.subTest(output=output):
                self.selector_fixture(output)
                with self.assertRaises(InferenceError) as caught:
                    asyncio.run(medical_rag.grounded_answer(self.provider, self.library, 'choking'))
                self.assertEqual(caught.exception.code, 'medical_grounding_failed')
                self.assertEqual(caught.exception.status_code, 503)
                self.assertNotIn('FABRICATED', str(caught.exception))
                self.assertNotIn('example.invalid', str(caught.exception))

    def test_no_match_never_calls_model(self):
        for question in ('zzzxylophoneqqq', 'help', 'cardiac arrest'):
            with self.subTest(question=question), self.assertRaises(InferenceError) as caught:
                asyncio.run(medical_rag.grounded_answer(self.provider, self.library, question))
            self.assertEqual(caught.exception.code, 'medical_reference_not_found')
        self.provider.answer.assert_not_awaited()

    def test_oversized_unicode_question_rejected_before_inference(self):
        with self.assertRaises(InferenceError) as caught:
            asyncio.run(medical_rag.grounded_answer(
                self.provider, self.library, 'choking ' + '\U0001f600' * 1900))
        self.assertEqual(caught.exception.code, 'medical_question_too_long')
        self.assertEqual(caught.exception.status_code, 422)
        self.provider.answer.assert_not_awaited()

    def test_selector_prompt_is_bounded_for_every_installed_topic(self):
        for title in installer.TITLES:
            row = self.library.search(title)[0]
            self.selector_fixture(json.dumps({'source_ids': [str(row['id'])]}))
            result = asyncio.run(medical_rag.grounded_answer(self.provider, self.library, title))
            self.assertIn(row['summary'], result.answer)
            prompt = self.provider.answer.await_args.args[0]
            self.assertLessEqual(len(prompt.encode('utf-8')), 2400)

    def test_matched_but_unsent_reference_cannot_be_cited(self):
        # Limit the prompt by using a long question, so not every retrieved row
        # fits. A model can only cite IDs actually included in its context.
        rows = self.library.search('hypothermia frostbite')
        self.assertEqual(len(rows), 2)
        question = 'hypothermia frostbite ' + 'x' * 1100
        self.selector_fixture(json.dumps({'source_ids': [str(rows[-1]['id'])]}))
        with self.assertRaises(InferenceError):
            asyncio.run(medical_rag.grounded_answer(self.provider, self.library, question))

    def test_model_unavailable_error_is_not_replaced_by_reference_text(self):
        self.provider.answer.side_effect = InferenceError('local_not_ready', 'TEST unavailable')
        with self.assertRaises(InferenceError) as caught:
            asyncio.run(medical_rag.grounded_answer(self.provider, self.library, 'choking'))
        self.assertEqual(caught.exception.code, 'local_not_ready')


class RouterTests(GroundingFixtures):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.object(chat, 'library', self.library))
        self.enterContext(patch.object(chat, 'provider', self.provider))
        self.enterContext(patch.dict(os.environ, {'LIFELINE_RAG': '1'}))
        isolated = FastAPI()
        isolated.include_router(chat.router)
        self.client = self.enterContext(TestClient(isolated))

    def test_readiness_count_ten_but_not_complete_offline_readiness(self):
        response = self.client.get('/api/status')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['references'], {'installed': True, 'count': 10})
        self.assertEqual(data['mode'], 'local')
        self.assertTrue(data['local']['ready'])
        self.assertFalse(data['offline_ready'])
        self.assertEqual(data['cloud'], {'enabled': False, 'configured': False, 'ready': False})
        self.provider.answer.assert_not_awaited()

    def test_only_exact_environment_opt_in_enables_retrieval(self):
        for value in ('', '0', 'true', 'yes', '01', ' 1'):
            with self.subTest(value=value), patch.dict(os.environ, {'LIFELINE_RAG': value}):
                self.assertFalse(medical_rag.enabled())
                self.assertEqual(self.client.get('/api/status').json()['data']['references'],
                                 {'installed': False, 'count': 0})
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(medical_rag.enabled())
        self.assertTrue(medical_rag.enabled())

    def test_success_preserves_answer_shape_and_source_attribution(self):
        row = self.library.search('choking')[0]
        self.selector_fixture(json.dumps({'source_ids': [str(row['id'])]}))
        response = self.client.post('/api/ask', json={'question': '  choking  '})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {'ok', 'data'})
        self.assertTrue(body['ok'])
        data = body['data']
        self.assertEqual(set(data), {'id', 'answer', 'mode', 'simulated', 'sources', 'notice'})
        UUID(data['id'])
        self.assertEqual(data['mode'], 'local')
        self.assertIs(data['simulated'], False)
        self.assertIn(row['summary'], data['answer'])
        self.assertEqual(data['sources'], [{'title': 'Choking - MedlinePlus / NLM',
                                            'url': self.topics['Choking']['url']}])
        self.assertEqual(data['notice'], medical_rag.NOTICE)
        self.assertNotIn('FABRICATED', response.text)

    def test_api_no_match_and_fabrication_return_structured_failures(self):
        response = self.client.post('/api/ask', json={'question': 'zzzxylophoneqqq'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'medical_reference_not_found')
        self.assertNotIn('data', response.json())
        self.provider.answer.assert_not_awaited()
        self.selector_fixture('FABRICATED advice https://example.invalid/fake')
        response = self.client.post('/api/ask', json={'question': 'choking'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'medical_grounding_failed')
        self.assertNotIn('FABRICATED', response.text)

    def test_opt_out_keeps_original_provider_boundary_without_database(self):
        self.provider.answer.return_value = Answer(answer='EXPLICIT TEST FIXTURE ONLY', notice=SAFETY_NOTICE)
        with patch.dict(os.environ, {'LIFELINE_RAG': '0'}), \
                patch.object(self.library, '_connect', side_effect=AssertionError('Database forbidden')):
            response = self.client.post('/api/ask', json={'question': '  Test fixture  '})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['data']['answer'], 'EXPLICIT TEST FIXTURE ONLY')
            self.assertEqual(response.json()['data']['sources'], [])
            self.assertEqual(self.client.get('/api/status').json()['data']['references']['count'], 0)
        self.provider.answer.assert_awaited_once_with('Test fixture')


class InstallerTests(OfflineTests):
    def test_default_installer_is_offline_and_never_overwrites(self):
        output = self.temp / 'fresh-install.db'
        with patch.object(installer, 'OUTPUT', output), \
                patch.object(sys, 'argv', ['install_references.py']), \
                patch.object(installer, 'download', side_effect=AssertionError('Download forbidden')) as download, \
                redirect_stdout(io.StringIO()):
            installer.main()
            self.assertTrue(output.is_file())
            fresh = medical_rag.MedicalLibrary(output, SNAPSHOT)
            self.assertEqual(fresh.count(), 10)
            with closing(fresh._connect()) as conn, closing(self.library._connect()) as installed:
                self.assertEqual(dict(conn.execute(
                    'SELECT content_status,count(*) FROM cases GROUP BY content_status')),
                    {'catalog_only': 90, 'official_summary': 10})
                self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM cases ORDER BY id')],
                                 [tuple(row) for row in installed.execute('SELECT * FROM cases ORDER BY id')])
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            before = hashlib.sha256(output.read_bytes()).hexdigest()
            with self.assertRaises(FileExistsError):
                installer.main()
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), before)
            download.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
