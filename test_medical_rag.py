"""Offline provenance/contract tests, not assertions of medical validity.

Run with .venv/bin/python -B -m unittest -v test_medical_rag.
All writable database/snapshot fixtures live under the project root. Model
responses are explicit test fixtures; no weights, legacy app, or network needed.
"""
import asyncio
import argparse
from contextlib import closing, ExitStack, redirect_stdout
import hashlib
import io
import http.client
import json
import os
import re
from pathlib import Path
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
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
                       for path in (ORIGINAL, SNAPSHOT)}
        self.addCleanup(self.assert_sources_unchanged)
        # A clean clone must not require an ignored, previously generated DB.
        self.installed = self.temp / 'fixture-installed.db'
        with patch.object(installer, 'OUTPUT', self.installed), redirect_stdout(io.StringIO()):
            installer.install()
        self.library = medical_rag.MedicalLibrary(self.installed, SNAPSHOT)
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
        shutil.copyfile(self.installed, path)
        return path

    def assert_provenance(self, row):
        source = self.topics[row['title']]
        self.assertEqual(row['summary'], source['summary'])
        self.assertEqual(row['source_url'], source['url'])
        self.assertEqual(row['medlineplus_id'], source['medlineplus_id'])
        self.assertEqual(row['source_name'], 'MedlinePlus / NLM')
        self.assertEqual(row['published_date'], '')
        self.assertEqual(row['feed_generated_at'], self.snapshot['feed_date'])
        self.assertEqual(row['source_created_date'], source['date_created'])
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
        for query in ('CHOKING!!!', '"choking"',
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

    def test_reviewed_natural_phrases_and_conservative_ambiguity(self):
        for query, title in (("I twisted my ankle", 'Sprains and Strains'),
                             ("I rolled my ankle", 'Sprains and Strains'),
                             ("I'm freezing and shivering", 'Hypothermia'),
                             ("I'm dehydrated", 'Dehydration'),
                             ('heat stroke', 'Heat Illness')):
            with self.subTest(query=query):
                rows = self.library.search(query)
                self.assertEqual([row['title'] for row in rows], [title])
        for query in ("I broke my arm", 'broken arm and bleeding', 'fractured wrist',
                      'help', 'no chest pain', 'not dehydrated', "I don't have burns",
                      "I wasn't dehydrated", "They weren't choking", "I didn't burn my hand",
                      'stroke and heat stroke',
                      'no chest pain but thirsty', 'dizzy and weak',
                      'dehydrated and confused', 'freezing and dizzy',
                      'heat illness and hypothermia', 'burns bleeding choking',
                      'food poisoning', 'blood in vomit', 'burning urination'):
            with self.subTest(query=query):
                self.assertEqual(self.library.search(query), [])
        self.assertEqual({row['title'] for row in self.library.search('hypothermia frostbite')},
                         {'Hypothermia', 'Frostbite'})

    def test_shared_body_parts_and_ftsstemming_are_not_relevance_evidence(self):
        for query in ('arm', 'my arm hurts', 'cold', 'pain', 'blood', 'shivering'):
            with self.subTest(query=query):
                self.assertEqual(self.library.search(query), [])

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
                  'feed_generated_at': '01/01/1900 00:00:00',
                  'source_created_date': '01/01/1900',
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
                library = medical_rag.MedicalLibrary(self.installed, path)
                self.assertEqual(library.count(), 0)
                self.assertEqual(library.search('choking'), [])
        tampered = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        tampered['topics'][2]['summary'] += ' FABRICATED TEST TEXT'
        path.write_text(json.dumps(tampered), encoding='utf-8')
        library = medical_rag.MedicalLibrary(self.installed, path)
        self.assertEqual(library.count(), 0)
        self.assertEqual(library.search('choking'), [])
        # Recomputing the envelope hash cannot make text differing from XML valid.
        tampered['snapshot_sha256'] = installer.digest(
            {key: value for key, value in tampered.items() if key != 'snapshot_sha256'})
        path.write_text(json.dumps(tampered), encoding='utf-8')
        self.assertEqual(medical_rag.MedicalLibrary(self.installed, path).count(), 0)


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
              'text': row['summary'],
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
        for question in ('zzzxylophoneqqq', 'help', 'cardiac arrest', 'I broke my arm',
                         'no chest pain', 'dizzy and weak', 'dehydrated and confused'):
            with self.subTest(question=question), self.assertRaises(InferenceError) as caught:
                asyncio.run(medical_rag.grounded_answer(self.provider, self.library, question))
            self.assertEqual(caught.exception.code, 'medical_reference_not_found')
        self.provider.answer.assert_not_awaited()

    def test_original_question_is_not_rewritten_by_alias_expansion(self):
        question = 'My hiking partner rolled an ankle. What reference is available?'
        row = self.library.search(question)[0]
        self.selector_fixture(json.dumps({'source_ids': [str(row['id'])]}))
        asyncio.run(medical_rag.grounded_answer(self.provider, self.library, question))
        payload = json.loads(self.provider.answer.await_args.args[0].split('\n', 1)[1])
        self.assertEqual(payload['question'], question)
        self.assertEqual(payload['references'][0]['title'], 'Sprains and Strains')

    def test_two_complete_summaries_never_drop_qualifications_to_meet_soft_budget(self):
        question = 'dehydration and heat illness'
        rows = self.library.search(question)
        self.assertEqual(len(rows), 2)
        self.selector_fixture(json.dumps({'source_ids': [str(row['id']) for row in rows]}))
        result = asyncio.run(medical_rag.grounded_answer(self.provider, self.library, question))
        payload = json.loads(self.provider.answer.await_args.args[0].split('\n', 1)[1])
        self.assertEqual([entry['text'] for entry in payload['references']],
                         [row['summary'] for row in rows])
        for row in rows:
            self.assertIn(row['summary'], result.answer)

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
            self.assertLessEqual(len(prompt.encode('utf-8')), 10000)

    def test_full_dehydration_and_frostbite_qualifications_reach_model_and_display(self):
        for query, markers in (('dehydration', ('What are the symptoms', 'Get medical help right away',
                                                'What are the treatments for dehydration')),
                               ('frostbite', ("Don't rub", "Don't use a heating pad", 'seek medical care'))):
            with self.subTest(query=query):
                row = self.library.search(query)[0]
                self.selector_fixture(json.dumps({'source_ids': [str(row['id'])]}))
                result = asyncio.run(medical_rag.grounded_answer(self.provider, self.library, query))
                prompt = self.provider.answer.await_args.args[0]
                payload = json.loads(prompt.split('\n', 1)[1])
                self.assertEqual(payload['question'], query)
                self.assertEqual(payload['references'][0]['text'], row['summary'])
                for marker in markers:
                    self.assertIn(marker, payload['references'][0]['text'])
                    self.assertIn(marker, result.answer)

    def test_matched_but_unsent_reference_cannot_be_cited(self):
        # Library matches and selection context are separate trust boundaries.
        # An installed but unretrieved reference is not eligible for citation.
        frostbite = self.library.search('frostbite')[0]
        self.selector_fixture(json.dumps({'source_ids': [str(frostbite['id'])]}))
        with self.assertRaises(InferenceError):
            asyncio.run(medical_rag.grounded_answer(self.provider, self.library, 'hypothermia'))

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

    def test_missing_references_fail_closed_through_existing_routes(self):
        missing = medical_rag.MedicalLibrary(self.temp / 'absent.db', SNAPSHOT)
        with patch.object(chat, 'library', missing):
            self.assertEqual(self.client.get('/api/status').json()['data']['references'],
                             {'installed': False, 'count': 0})
            response = self.client.post('/api/ask', json={'question': 'I rolled my ankle'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'medical_reference_not_found')
        self.assertNotIn('data', response.json())
        self.provider.answer.assert_not_awaited()
        self.assertFalse(missing.path.exists())

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
    def test_check_requires_schema_version_even_with_ten_populated_topics(self):
        path = self.copied_database()
        self.assertEqual(installer.check_installation(path), installer.INSTALLATION_VERSION)
        with closing(sqlite3.connect(path)) as conn, conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM cases WHERE content_status='official_summary'").fetchone()[0], 10)
            conn.execute('PRAGMA user_version=1')
        with self.assertRaisesRegex(ValueError, 'schema version mismatch'):
            installer.check_installation(path)
        self.assertEqual(medical_rag.MedicalLibrary(path, SNAPSHOT).count(), 0)
        self.assertEqual(medical_rag.MedicalLibrary(path, SNAPSHOT).search('choking'), [])

    def test_check_rejects_stale_dates_or_content_even_with_current_schema_and_count(self):
        path = self.copied_database()
        for field, value in (('published_date', self.snapshot['feed_date']),
                             ('feed_generated_at', '01/01/1900 00:00:00'),
                             ('source_created_date', '01/01/1900'),
                             ('summary', 'UNTRUSTED TEST CONTENT'),
                             ('source_url', 'https://example.invalid/changed')):
            with self.subTest(field=field):
                with closing(sqlite3.connect(path)) as conn, conn:
                    old = conn.execute(f'SELECT {field} FROM cases WHERE id=4').fetchone()[0]
                    conn.execute(f'UPDATE cases SET {field}=? WHERE id=4', (value,))
                    self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], installer.INSTALLATION_VERSION)
                    self.assertEqual(conn.execute(
                        "SELECT count(*) FROM cases WHERE content_status='official_summary'").fetchone()[0], 10)
                with self.assertRaisesRegex(ValueError, 'content/provenance mismatch'):
                    installer.check_installation(path)
                with closing(sqlite3.connect(path)) as conn, conn:
                    conn.execute(f'UPDATE cases SET {field}=? WHERE id=4', (old,))

    def test_check_cli_is_read_only_and_returns_failure_for_outdated_output(self):
        path = self.copied_database()
        with patch.object(installer, 'OUTPUT', path), \
                patch.object(sys, 'argv', ['install_references.py', '--check']), \
                redirect_stdout(io.StringIO()):
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            installer.main()
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute('PRAGMA user_version=0')
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as failure:
                installer.main()
            self.assertEqual(failure.exception.code, 1)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_unapproved_snapshot_and_changed_catalog_rejected_before_output(self):
        snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        snapshot['imported_at'] = '2026-10-19T00:00:00Z'
        snapshot['snapshot_sha256'] = installer.digest(
            {key: value for key, value in snapshot.items() if key != 'snapshot_sha256'})
        tampered = self.temp / 'tampered.json'
        tampered.write_text(json.dumps(snapshot), encoding='utf-8')
        output = self.temp / 'must-not-exist.db'
        with patch.object(installer, 'SNAPSHOT', tampered), patch.object(installer, 'OUTPUT', output):
            with self.assertRaises(ValueError):
                installer.install()
        self.assertFalse(output.exists())
        catalog = self.temp / 'catalog.db'
        shutil.copyfile(ORIGINAL, catalog)
        with closing(sqlite3.connect(catalog)) as conn, conn:
            conn.execute("UPDATE cases SET aliases='unreviewed alias' WHERE id=4")
        with patch.object(installer, 'ORIGINAL', catalog), patch.object(installer, 'OUTPUT', output):
            with self.assertRaises(ValueError):
                installer.install()
        self.assertFalse(output.exists())

    def test_malformed_duplicate_keys_untrusted_urls_and_dates_rejected(self):
        path = self.temp / 'bad.json'
        for value in ('{"topics":[],"topics":[]}', 'null', '[]', '{}', '{broken'):
            with self.subTest(value=value):
                path.write_text(value, encoding='utf-8')
                with self.assertRaises(ValueError):
                    installer.validate(installer.load_snapshot(path))
        for field, value in (('url', 'https://example.invalid/fake'), ('summary', ''),
                             ('medlineplus_id', None), ('date_created', 'not-a-date')):
            snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
            snapshot['topics'][0][field] = value
            snapshot['snapshot_sha256'] = installer.digest(
                {key: val for key, val in snapshot.items() if key != 'snapshot_sha256'})
            with self.subTest(field=field), self.assertRaises(ValueError):
                installer.validate(snapshot, require_approved=False)

    def test_legacy_date_schema_fails_closed_until_explicit_reinstall(self):
        path = self.copied_database()
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("UPDATE cases SET published_date=feed_generated_at")
        self.assertEqual(medical_rag.MedicalLibrary(path, SNAPSHOT).count(), 0)
        self.assertEqual(medical_rag.MedicalLibrary(path, SNAPSHOT).search('choking'), [])
        with self.assertRaisesRegex(ValueError, 'content/provenance mismatch'):
            installer.check_installation(path)

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


class BrowserRAGTests(unittest.TestCase):
    def test_existing_website_displays_only_validated_sources_and_retains_unsupported_draft(self):
        try:
            from playwright.sync_api import expect, sync_playwright
            import uvicorn
        except ImportError:
            self.skipTest('Browser check needs the existing requirements-dev dependencies')
        with tempfile.TemporaryDirectory(dir=ROOT) as directory, ExitStack() as stack:
            path = Path(directory) / 'references.db'
            with patch.object(installer, 'OUTPUT', path), redirect_stdout(io.StringIO()):
                installer.install()
            library = medical_rag.MedicalLibrary(path)
            row = library.search('I rolled my ankle')[0]
            provider = SimpleNamespace(configured=True, ready=True, model='EXPLICIT TEST SELECTOR ONLY',
                answer=AsyncMock(return_value=Answer(answer=json.dumps({'source_ids': [str(row['id'])]}),
                    notice='TEST ONLY', sources=[Source(title='FABRICATED', url='https://example.invalid/fake')])))
            connect = sqlite3.connect
            with patch('sqlite3.connect', side_effect=lambda *a, **kw: connect(':memory:')):
                from app import app
            stack.enter_context(patch.object(chat, 'library', library))
            stack.enter_context(patch.object(chat, 'provider', provider))
            stack.enter_context(patch.dict(os.environ, {'LIFELINE_RAG': '1'}))
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            base = f'http://127.0.0.1:{port}'
            server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
            thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
            thread.start()
            try:
                for _ in range(500):
                    if server.started:
                        break
                    time.sleep(0.01)
                self.assertTrue(server.started)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    try:
                        context = browser.new_context(service_workers='block')
                        external, payloads, errors = [], [], []

                        def guard(route):
                            if not route.request.url.startswith(base + '/'):
                                external.append(route.request.url)
                                route.abort()
                            else:
                                if route.request.url == base + '/api/ask':
                                    payloads.append(route.request.post_data_json)
                                route.continue_()

                        context.route('**/*', guard)
                        page = context.new_page()
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(base)
                        page.locator('#question').fill('  I rolled my ankle  ')
                        expect(page.locator('#send-button')).to_be_enabled()
                        page.locator('#send-button').click()
                        expect(page.locator('.message.assistant')).to_contain_text(row['summary'].strip())
                        expect(page.locator('.message.assistant')).not_to_contain_text('source_ids')
                        expect(page.locator('.message.assistant')).not_to_contain_text('FABRICATED')
                        expect(page.locator('.source-list a')).to_have_attribute('href', row['source_url'])
                        expect(page.locator('.message-notice')).to_have_text(medical_rag.NOTICE)
                        expect(page.locator('#question')).to_have_value('')
                        selector = json.loads(provider.answer.await_args.args[0].split('\n', 1)[1])
                        self.assertEqual(selector['question'], 'I rolled my ankle')
                        page.locator('#question').fill('I broke my arm')
                        page.locator('#send-button').click()
                        expect(page.locator('#error-detail')).to_contain_text('No reliable installed reference')
                        expect(page.locator('#question')).to_have_value('I broke my arm')
                        expect(page.locator('.message.assistant')).to_have_count(1)
                        self.assertEqual(payloads, [{'question': 'I rolled my ankle'}, {'question': 'I broke my arm'}])
                        self.assertEqual(provider.answer.await_count, 1)
                        self.assertEqual(external, [])
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                sock.close()


def live_checks(argv):
    """Opt-in Dell checks using the existing provider and real loopback servers.

    Not a second RAG implementation. No production state/files are changed.
    Raw selection/metrics remain local; automatic provenance checks are not a
    clinical relevance or medical-correctness certification.
    """
    parser = argparse.ArgumentParser(description=live_checks.__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True, help='New local JSONL file')
    args = parser.parse_args(argv)
    library = medical_rag.MedicalLibrary()
    if library.count() != 10:
        parser.error('Install the current pinned references first; expected 10 trusted topics')

    def api(method, path, payload=None, port=8000):
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=150)
        started = time.perf_counter()
        try:
            conn.request(method, path, body=json.dumps(payload).encode() if payload else None,
                         headers={'Content-Type': 'application/json'})
            response = conn.getresponse()
            return response.status, json.loads(response.read()), (time.perf_counter() - started) * 1000
        finally:
            conn.close()

    try:
        status, health, _ = api('GET', '/health', port=8081)
        if status != 200 or health.get('status') != 'ok':
            parser.error('Existing llama-server on 8081 is not healthy')
        status, state, _ = api('GET', '/api/status')
        if status != 200 or state['data']['references'] != {'installed': True, 'count': 10}:
            parser.error('Existing website server must have LIFELINE_RAG=1 and 10 installed references')
    except (OSError, ValueError, KeyError) as exc:
        parser.error('Existing loopback services unavailable: ' + str(exc))

    # Import provider class without creating the legacy application's database.
    connect = sqlite3.connect
    with patch('sqlite3.connect', side_effect=lambda *a, **kw: connect(':memory:')):
        from offline_ai.llama_adapter import LlamaCPUProvider

    class MeasuredProvider(LlamaCPUProvider):
        def __init__(self):
            super().__init__()
            self.metrics = []

        def _request(self, method, path, payload=None):
            started = time.perf_counter()
            result = super()._request(method, path, payload)
            if path == '/v1/chat/completions':
                self.metrics.append({
                    'elapsed_ms': (time.perf_counter() - started) * 1000,
                    'request': payload, 'selection': result.get('choices'),
                    'usage': result.get('usage'), 'timings': result.get('timings'),
                })
            return result

    provider = MeasuredProvider()
    if not provider.configured:
        parser.error('LIFELINE_GGUF_PATH must point at the same existing GGUF as the model server')
    cases = [(title, True) for title in installer.TITLES] + [
        ('I twisted my ankle', True), ('I rolled my ankle', True),
        ("I'm freezing and shivering", True), ("I'm dehydrated", True),
        ('I broke my arm', False), ('help', False), ('no chest pain', False),
        ('dizzy and weak', False), ('dehydrated and confused', False),
    ]

    def check_extract(data, rows):
        available = {row['source_url']: row for row in rows}
        sources = data['sources']
        if not 1 <= len(sources) <= 2 or data['mode'] != 'local' or data['simulated'] is not False:
            return False
        chosen = []
        for source in sources:
            row = available.get(source['url'])
            if row is None or source['title'] != row['title'] + ' - MedlinePlus / NLM':
                return False
            chosen.append(row)
        return (len({row['id'] for row in chosen}) == len(chosen)
                and data['answer'] == 'For immediate danger, contact local emergency services now.\n\n'
                'Installed reference information (not a diagnosis or complete first-aid instructions):\n\n'
                + '\n\n'.join(row['title'] + '\n' + row['summary'] for row in chosen)
                and data['notice'] == medical_rag.NOTICE)

    failures = 0
    with args.output.open('x', encoding='utf-8') as output:
        for question, supported in cases:
            samples = []
            rows = []
            for _ in range(10):
                started = time.perf_counter()
                rows = library.search(question)
                samples.append((time.perf_counter() - started) * 1000)
            provider.metrics = []
            started = time.perf_counter()
            direct_error = None
            try:
                direct = asyncio.run(medical_rag.grounded_answer(provider, library, question))
                direct_valid = supported and check_extract(direct.model_dump(), rows)
            except InferenceError as exc:
                direct_error = exc.code
                direct_valid = not supported and exc.code == 'medical_reference_not_found'
            direct_ms = (time.perf_counter() - started) * 1000
            status, body, api_ms = api('POST', '/api/ask', {'question': question})
            api_valid = (status == 200 and body.get('ok') is True and check_extract(body['data'], rows)
                         if supported else status == 503 and body.get('error', {}).get('code') == 'medical_reference_not_found')
            record = {'question': question, 'expected_supported': supported,
                      'retrieved_titles': [row['title'] for row in rows],
                      'retrieval_median_ms': sorted(samples)[len(samples) // 2],
                      'retrieval_max_ms': max(samples), 'direct_rag_ms': direct_ms,
                      'direct_error': direct_error, 'api_total_ms': api_ms, 'http_status': status,
                      'api_response': body, 'selector_metrics': provider.metrics,
                      'automatic_contract_pass': direct_valid and api_valid,
                      'human_relevance_review': 'REQUIRED',
                      'time_to_first_visible_content': 'Not measured; API/browser buffer final JSON'}
            output.write(json.dumps(record, ensure_ascii=True) + '\n')
            output.flush()
            failures += not record['automatic_contract_pass']
            print(('PASS' if record['automatic_contract_pass'] else 'FAIL'), question,
                  f'retrieval={record["retrieval_median_ms"]:.2f}ms api={api_ms:.1f}ms')
    print('Review all raw selections and final source relevance. This is not clinical validation.')
    return 1 if failures else 0


if __name__ == '__main__':
    if '--live' in sys.argv:
        raise SystemExit(live_checks(sys.argv[1:]))
    unittest.main(verbosity=2)
