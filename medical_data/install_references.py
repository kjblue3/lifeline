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


def validate(snapshot):
    payload = dict(snapshot)
    expected = payload.pop('snapshot_sha256')
    if digest(payload) != expected:
        raise ValueError('Snapshot SHA256 mismatch')
    if snapshot['schema_version'] != 1 or snapshot['notice'] != NOTICE:
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
    topics = snapshot['topics']
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
        node = ET.fromstring(topic['full_summary_xml'])
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
        'snapshot_hash_format': 'SHA256 of UTF-8 JSON excluding snapshot_sha256; sort_keys=True, ensure_ascii=True, separators=(comma,colon)',
        'topics': topics,
    }
    snapshot['snapshot_sha256'] = digest(snapshot)
    validate(snapshot)
    # Automated source-data import, not hand-authored medical content.
    SNAPSHOT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    print('Saved:', SNAPSHOT)


def install():
    snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    validate(snapshot)
    with closing(sqlite3.connect(ORIGINAL.as_uri() + '?mode=ro', uri=True)) as source:
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
                source.backup(target)
                for topic in snapshot['topics']:
                    result = target.execute('''UPDATE cases SET summary=?,
                        source_name='MedlinePlus / NLM', source_url=?, medlineplus_id=?,
                        published_date=?, imported_at=?, content_status='official_summary'
                        WHERE title COLLATE BINARY=?''',
                        (topic['summary'], topic['url'], topic['medlineplus_id'],
                         snapshot['feed_date'], snapshot['imported_at'], topic['title']))
                    if result.rowcount != 1:
                        raise ValueError('Exact catalog title not unique: ' + topic['title'])
                after = target.execute('SELECT * FROM cases ORDER BY id').fetchall()
                for old, new in zip(before, after):
                    if old[columns.index('title')] not in TITLES and old != new:
                        raise ValueError('Non-target catalog row changed')
                counts = dict(target.execute('SELECT content_status,count(*) FROM cases GROUP BY content_status'))
                if counts != {'catalog_only': 90, 'official_summary': 10}:
                    raise ValueError('Unexpected installed counts: ' + str(counts))
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Installed database integrity check failed')
        except Exception:
            OUTPUT.unlink()
            raise
    print('Installed:', OUTPUT)
    print('100 topics: 10 official_summary, 90 catalog_only. Original unchanged.')
    print(NOTICE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Download snapshot only; requires internet')
    args = parser.parse_args()
    if args.download:
        download()
    else:
        install()


if __name__ == '__main__':
    main()
