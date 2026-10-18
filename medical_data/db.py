"""Local SQLite storage for LifeLine's source-attributed health-topic reference library."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name('lifeline_medical.db')

SCHEMA = '''
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS cases (
 id INTEGER PRIMARY KEY,
 title TEXT NOT NULL UNIQUE COLLATE NOCASE,
 category TEXT NOT NULL,
 aliases TEXT NOT NULL DEFAULT '',
 summary TEXT NOT NULL DEFAULT '',
 source_name TEXT NOT NULL DEFAULT 'MedlinePlus / NLM',
 source_url TEXT NOT NULL DEFAULT '',
 medlineplus_id TEXT NOT NULL DEFAULT '',
 published_date TEXT NOT NULL DEFAULT '',
 imported_at TEXT NOT NULL DEFAULT '',
 content_status TEXT NOT NULL DEFAULT 'catalog_only'
   CHECK(content_status IN ('catalog_only','official_summary'))
);
CREATE TABLE IF NOT EXISTS source_links (
 id INTEGER PRIMARY KEY,
 case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
 organization TEXT NOT NULL,
 url TEXT NOT NULL,
 content_copied INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS emergency_cards (
 id INTEGER PRIMARY KEY,
 heading TEXT NOT NULL UNIQUE,
 description TEXT NOT NULL,
 response TEXT NOT NULL,
 source_name TEXT NOT NULL,
 source_url TEXT NOT NULL,
 content_status TEXT NOT NULL DEFAULT 'source_checked_demo_note'
);
CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
 title, aliases, summary, content='cases', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS cases_ai AFTER INSERT ON cases BEGIN
 INSERT INTO cases_fts(rowid,title,aliases,summary)
 VALUES(new.id,new.title,new.aliases,new.summary);
END;
CREATE TRIGGER IF NOT EXISTS cases_ad AFTER DELETE ON cases BEGIN
 INSERT INTO cases_fts(cases_fts,rowid,title,aliases,summary)
 VALUES('delete',old.id,old.title,old.aliases,old.summary);
END;
CREATE TRIGGER IF NOT EXISTS cases_au AFTER UPDATE ON cases BEGIN
 INSERT INTO cases_fts(cases_fts,rowid,title,aliases,summary)
 VALUES('delete',old.id,old.title,old.aliases,old.summary);
 INSERT INTO cases_fts(rowid,title,aliases,summary)
 VALUES(new.id,new.title,new.aliases,new.summary);
END;
'''

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def init(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def search(conn, query: str, limit: int = 5):
    """Search exact medical terms and lay-language aliases, no cloud service."""
    import re
    tokens = re.findall(r'[a-zA-Z0-9]+', query.lower())[:12]
    if not tokens:
        return []
    fts = ' OR '.join(f'"{t}"' for t in tokens if len(t) > 1)
    if not fts:
        return []
    try:
        rows = conn.execute('''
            SELECT c.*, bm25(cases_fts, 8.0, 4.0, 1.0) AS rank
            FROM cases_fts JOIN cases c ON c.id = cases_fts.rowid
            WHERE cases_fts MATCH ?
            ORDER BY (CASE WHEN lower(c.title)=lower(?) THEN -999 ELSE bm25(cases_fts, 8.0,4.0,1.0) END)
            LIMIT ?
        ''', (fts, query.strip(), limit)).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.OperationalError:
        # Unexpectedly missing FTS5 on a Python install: slower but still offline.
        q = '%' + query[:100].replace('%','') + '%'
        rows = conn.execute('SELECT * FROM cases WHERE title LIKE ? OR aliases LIKE ? LIMIT ?', (q,q,limit)).fetchall()
        return [dict(row) for row in rows]
