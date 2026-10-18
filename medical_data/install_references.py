"""Download ten official references once; install them offline without altering the catalog.

python -B medical_data/install_references.py --download  # network, snapshot only
python -B medical_data/install_references.py             # offline, new database only
Summaries are source-extracted reference material, not clinically reviewed first-aid protocols.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
ORIGINAL = BASE / 'lifeline_medical.db'
OUTPUT = BASE / 'lifeline_medical_installed.db'
SNAPSHOT = BASE / 'official_first_aid.json'
INSTALLATION_VERSION = 2
SNAPSHOT_DIGEST = '6adb725b911c5afc4d9d6c85ae6d0be8e31436525e122878682d1fdc34c7094f'
CATALOG_DIGEST = '72616156a6d7b12a97836670223306e1a64e0a14c3cd9ea556100665fda6df61'
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
HASH_FORMAT = 'SHA256 of UTF-8 JSON excluding snapshot_sha256; sort_keys=True, ensure_ascii=True, separators=(comma,colon)'
TITLES = (
    'Bleeding', 'Burns', 'Choking', 'Poisoning', 'Heat Illness',
    'Hypothermia', 'Frostbite', 'Dehydration', 'Sprains and Strains',
    'Wounds and Injuries',
)
SOURCE_INDEX = 'https://medlineplus.gov/xml.html'
NOTICE = 'Source-extracted MedlinePlus health-topic summaries; not clinical review or complete first-aid protocols.'


def helper():
    # The existing helper uses sibling imports. Never run its all-catalog main.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(BASE))
    try:
        import refresh_medlineplus
        return refresh_medlineplus
    finally:
        sys.path.pop(0)


def trusted_url(url):
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or parsed.hostname not in
            ('medlineplus.gov', 'www.medlineplus.gov') or
            parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError('Untrusted official source URL: ' + url)
    return url


def digest(payload):
    """Hash the canonical UTF-8 JSON payload, excluding its own digest field."""
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(',', ':')
    ).encode('utf-8')).hexdigest()


def load_snapshot(path):
    """Read bounded JSON without accepting ambiguous duplicate object keys."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate snapshot JSON key: ' + key)
            result[key] = value
        return result

    with Path(path).open('rb') as stream:
        data = stream.read(MAX_SNAPSHOT_BYTES + 1)
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise ValueError('Snapshot exceeds the 2 MiB size limit')
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Invalid snapshot JSON') from exc


def validate(snapshot, require_approved=True):
    string_fields = {
        'notice', 'source_index', 'feed_url', 'feed_date', 'imported_at',
        'xml_sha256', 'snapshot_hash_format', 'snapshot_sha256',
    }
    if (not isinstance(snapshot, dict) or
            set(snapshot) != string_fields | {'schema_version', 'topics'} or
            any(not isinstance(snapshot[key], str) for key in string_fields) or
            type(snapshot['schema_version']) is not int or
            snapshot['schema_version'] != 1 or
            not isinstance(snapshot['topics'], list)):
        raise ValueError('Invalid snapshot schema or field types')
    topic_fields = {
        'title', 'url', 'medlineplus_id', 'date_created', 'summary',
        'full_summary_xml', 'content_status',
    }
    topics = snapshot['topics']
    if (len(topics) != len(TITLES) or any(
            not isinstance(topic, dict) or set(topic) != topic_fields or
            any(not isinstance(topic[key], str) for key in topic_fields)
            for topic in topics)):
        raise ValueError('Invalid topic schema or field types')
    payload = dict(snapshot)
    expected = payload.pop('snapshot_sha256')
    if not re.fullmatch(r'[0-9a-f]{64}', expected) or digest(payload) != expected:
        raise ValueError('Snapshot SHA256 mismatch')
    if require_approved and expected != SNAPSHOT_DIGEST:
        raise ValueError('Snapshot is not the pinned approved snapshot')
    if snapshot['notice'] != NOTICE or snapshot['snapshot_hash_format'] != HASH_FORMAT:
        raise ValueError('Unsupported snapshot format or missing source-extraction notice')
    if snapshot['source_index'] != SOURCE_INDEX:
        raise ValueError('Unexpected feed index')
    trusted_url(snapshot['feed_url'])
    if not re.fullmatch(r'[0-9a-f]{64}', snapshot['xml_sha256']):
        raise ValueError('Missing XML provenance digest')
    datetime.strptime(snapshot['feed_date'], '%m/%d/%Y %H:%M:%S')
    timestamp = snapshot['imported_at']
    if not timestamp.endswith('Z'):
        raise ValueError('Import time must be UTC')
    datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
    if [topic['title'] for topic in topics] != list(TITLES):
        raise ValueError('Snapshot must contain exactly the ten requested titles, in order')
    extract = helper()
    ids = set()
    for topic in topics:
        trusted_url(topic['url'])
        if (topic['content_status'] != 'official_summary' or
                not re.fullmatch(r'[0-9]+', topic['medlineplus_id']) or
                topic['medlineplus_id'] in ids or len(topic['summary']) < 75):
            raise ValueError('Invalid official topic metadata: ' + topic['title'])
        ids.add(topic['medlineplus_id'])
        datetime.strptime(topic['date_created'], '%m/%d/%Y')
        try:
            node = ET.fromstring(topic['full_summary_xml'])
        except ET.ParseError as exc:
            raise ValueError('Invalid summary XML: ' + topic['title']) from exc
        if node.tag != 'full-summary' or extract.cleaned_summary(node) != topic['summary']:
            raise ValueError('Summary differs from extracted source: ' + topic['title'])


def download():
    extract = helper()
    original_urlopen = extract.urlopen
    requested = []

    def checked_urlopen(request, **kwargs):
        url = trusted_url(request.full_url)
        response = original_urlopen(request, **kwargs)
        try:
            trusted_url(response.geturl())
        except Exception:
            response.close()
            raise
        requested.append(url)
        return response

    extract.urlopen = checked_urlopen
    try:
        archive = extract.official_download()
    finally:
        extract.urlopen = original_urlopen
    xml_bytes = extract.raw_xml_bytes(archive)
    records, _, generated = extract.parse_official_topics(xml_bytes)
    nodes = {node.get('id'): node for node in ET.fromstring(xml_bytes).findall('health-topic')
             if node.get('language', '').lower() == 'english'}
    topics = []
    for title in TITLES:
        rec = records.get(extract.norm(title))
        if not rec or rec['title'] != title:
            raise ValueError('Exact official topic missing; no substitutions made: ' + title)
        topics.append({
            'title': title, 'url': rec['url'], 'medlineplus_id': rec['medlineplus_id'],
            'date_created': rec['date'], 'summary': rec['summary'],
            'full_summary_xml': ET.tostring(
                nodes[rec['medlineplus_id']].find('full-summary'), encoding='unicode'),
            'content_status': 'official_summary',
        })
    snapshot = {
        'schema_version': 1, 'notice': NOTICE, 'source_index': SOURCE_INDEX,
        'feed_url': requested[-1], 'feed_date': generated,
        'imported_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'xml_sha256': hashlib.sha256(xml_bytes).hexdigest(),
        'snapshot_hash_format': HASH_FORMAT,
        'topics': topics,
    }
    snapshot['snapshot_sha256'] = digest(snapshot)
    validate(snapshot, require_approved=False)
    # Automated source-data import, not hand-authored medical content.
    SNAPSHOT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    print('Saved:', SNAPSHOT)


def install():
    snapshot = load_snapshot(SNAPSHOT)
    validate(snapshot)
    with closing(sqlite3.connect(':memory:')) as probe:
        try:
            probe.execute("CREATE VIRTUAL TABLE fts_probe USING fts5(text, tokenize='porter unicode61')")
        except sqlite3.OperationalError as exc:
            raise RuntimeError('Installation requires SQLite FTS5; use a Python/SQLite build with FTS5 enabled.') from exc
    with ORIGINAL.open('rb') as stream:
        catalog_hash = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            catalog_hash.update(chunk)
    if catalog_hash.hexdigest() != CATALOG_DIGEST:
        raise ValueError('Original catalog SHA256 does not match the committed catalog')
    with closing(sqlite3.connect(ORIGINAL.as_uri() + '?mode=ro', uri=True)) as source:
        source.execute('PRAGMA foreign_keys=ON')
        before = source.execute('SELECT * FROM cases ORDER BY id').fetchall()
        columns = [row[1] for row in source.execute('PRAGMA table_info(cases)')]
        rows = [dict(zip(columns, row)) for row in before]
        if (len(rows) != 100 or any(row['content_status'] != 'catalog_only' or row['summary']
                                    for row in rows)):
            raise ValueError('Expected original catalog: 100 catalog_only rows, no summaries')
        if not set(TITLES).issubset({row['title'] for row in rows}):
            raise ValueError('Original catalog is missing exact target titles')
        # Exclusive creation is intentional: never truncate or replace an existing output.
        with OUTPUT.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(OUTPUT)) as target, target:
                target.execute('PRAGMA foreign_keys=ON')
                source.backup(target)
                target.execute("ALTER TABLE cases ADD COLUMN feed_generated_at TEXT NOT NULL DEFAULT ''")
                target.execute("ALTER TABLE cases ADD COLUMN source_created_date TEXT NOT NULL DEFAULT ''")
                for topic in snapshot['topics']:
                    result = target.execute('''UPDATE cases SET summary=?,
                        source_name='MedlinePlus / NLM', source_url=?, medlineplus_id=?,
                        published_date='', feed_generated_at=?, source_created_date=?,
                        imported_at=?, content_status='official_summary'
                        WHERE title COLLATE BINARY=?''',
                        (topic['summary'], topic['url'], topic['medlineplus_id'],
                         snapshot['feed_date'], topic['date_created'],
                         snapshot['imported_at'], topic['title']))
                    if result.rowcount != 1:
                        raise ValueError('Exact catalog title not unique: ' + topic['title'])
                after = target.execute('SELECT ' + ','.join('"' + col + '"' for col in columns) +
                                       ' FROM cases ORDER BY id').fetchall()
                for old, new in zip(before, after):
                    if old[columns.index('title')] not in TITLES and old != new:
                        raise ValueError('Non-target catalog row changed')
                counts = dict(target.execute('SELECT content_status,count(*) FROM cases GROUP BY content_status'))
                if counts != {'catalog_only': 90, 'official_summary': 10}:
                    raise ValueError('Unexpected installed counts: ' + str(counts))
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Installed database integrity check failed')
                if target.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('Installed database foreign key check failed')
                target.execute(f'PRAGMA user_version={INSTALLATION_VERSION}')
        except Exception:
            OUTPUT.unlink()
            raise
    print('Installed:', OUTPUT)
    print('100 topics: 10 official_summary, 90 catalog_only. Original unchanged.')
    print(NOTICE)


def check_installation(path=None):
    """Verify generated schema/content offline and read-only, not just row count.

    Never upgrades or replaces the database. Incompatible output must be backed
    up and regenerated explicitly; the committed catalog is not modified.
    """
    snapshot = load_snapshot(SNAPSHOT)
    validate(snapshot)
    path = Path(path) if path is not None else OUTPUT
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        if conn.execute('PRAGMA user_version').fetchone()[0] != INSTALLATION_VERSION:
            raise ValueError('Installed schema version mismatch; back up the generated DB and reinstall')
        rows = conn.execute('SELECT * FROM cases').fetchall()
        counts = dict(conn.execute('SELECT content_status,count(*) FROM cases GROUP BY content_status'))
        if len(rows) != 100 or counts != {'catalog_only': 90, 'official_summary': 10}:
            raise ValueError('Installed reference/catalog counts differ from the approved installation')
        by_title = {row['title']: row for row in rows}
        for topic in snapshot['topics']:
            row = by_title.get(topic['title'])
            expected = {
                'summary': topic['summary'], 'source_url': topic['url'],
                'source_name': 'MedlinePlus / NLM', 'medlineplus_id': topic['medlineplus_id'],
                'content_status': 'official_summary', 'published_date': '',
                'feed_generated_at': snapshot['feed_date'], 'source_created_date': topic['date_created'],
                'imported_at': snapshot['imported_at'],
            }
            if row is None or any(key not in row.keys() or row[key] != value
                                  for key, value in expected.items()):
                raise ValueError('Installed content/provenance mismatch: ' + topic['title'])
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Installed database integrity check failed')
    return INSTALLATION_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--download', action='store_true', help='Download snapshot only; requires internet')
    mode.add_argument('--check', action='store_true', help='Check installed schema/content/provenance offline, without writing')
    args = parser.parse_args()
    if args.check:
        try:
            version = check_installation()
        except (OSError, ValueError, sqlite3.Error) as exc:
            parser.exit(1, 'Installation is missing or incompatible: ' + str(exc) + '\n'
                        'Stop FastAPI, back up only the generated DB, and rerun the offline installer.\n')
        print(f'Current offline installation: schema version {version}, 10 approved reference topics.')
    elif args.download:
        download()
    else:
        install()


if __name__ == '__main__':
    main()
