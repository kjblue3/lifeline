"""Download the official MedlinePlus topic XML and import 100 real summaries.
Source: https://medlineplus.gov/xml.html
Only <health-topic><full-summary> text is copied, not third-party linked
medical encyclopedia articles, images, medication monographs, or videos.
Run once WITH INTERNET, then LifeLine can search its database offline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import io
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile
from db import connect, init
from seed_data import EXTRA_CANDIDATES, ALIASES

SOURCE_INDEX = 'https://medlineplus.gov/xml.html'

class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower() in ('p','br','li','h2','h3','h4','div'):
            self.chunks.append('\n')
    def handle_data(self, data): self.chunks.append(data)
    def output(self):
        return re.sub(r'\n{3,}','\n\n', re.sub(r'[ \t]+',' ',' '.join(self.chunks))).strip()

def cleaned_summary(node):
    if node is None:
        return ''
    # Handles either HTML escaped as text or actual nested XML elements.
    markup = ''.join(ET.tostring(n,encoding='unicode') for n in node) or (node.text or '')
    h=TextOnly()
    h.feed(markup)
    return h.output()

def official_download():
    req=Request(SOURCE_INDEX, headers={'User-Agent':'LifeLineHackathonDemo/1.0 (student open-source project)'})
    with urlopen(req,timeout=30) as response:
        index = response.read(250_000).decode('utf-8','replace')
    match = re.findall(r'''(?:href\s*=\s*["'])([^"']*mplus_topics_compressed_\d{4}-\d{2}-\d{2}\.zip)''', index, re.I)
    if not match:
        raise RuntimeError('Could not find official MedlinePlus download link. See https://medlineplus.gov/xml.html')
    url=urljoin(SOURCE_INDEX,match[0].replace('&amp;','&'))
    if urlparse(url).hostname not in ('medlineplus.gov','www.medlineplus.gov'):
        raise RuntimeError('Download link was not on the official MedlinePlus domain.')
    print('Downloading:',url)
    with urlopen(Request(url, headers={'User-Agent':'LifeLineHackathonDemo/1.0'}),timeout=90) as r:
        data=r.read(15_000_000)
    print(f'Downloaded {len(data):,} bytes')
    return data

def raw_xml_bytes(content: bytes):
    if zipfile.is_zipfile(io.BytesIO(content)):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            opts=[name for name in z.namelist() if name.endswith('.xml')]
            if not opts: raise RuntimeError('ZIP does not contain an XML file')
            print('Extracting:',opts[0])
            return z.read(opts[0])
    if content.lstrip().startswith(b'<?xml') or content.lstrip().startswith(b'<health-topics'):
        return content
    raise RuntimeError('The input is not a MedlinePlus XML file or ZIP')

def norm(s):
    return re.sub(r'[^a-z0-9]+','',s.casefold())

def parse_official_topics(xml_bytes):
    root=ET.fromstring(xml_bytes)
    if root.tag != 'health-topics': raise RuntimeError('Unexpected XML root: ' + root.tag)
    records={}; synonyms={}
    for node in root.findall('health-topic'):
        if (node.get('language') or '').lower() != 'english': continue
        title=node.get('title','').strip()
        url=node.get('url','')
        if not title or not urlparse(url).hostname in ('medlineplus.gov','www.medlineplus.gov'): continue
        summary=cleaned_summary(node.find('full-summary'))
        if not summary or len(summary) < 75: continue
        aliases=[n.text.strip() for tag in ('also-called','see-reference')
                 for n in node.findall(tag) if n.text and n.text.strip()]
        rec={'title':title,'url':url,'summary':summary,'medlineplus_id':node.get('id',''),
             'date':node.get('date-created',''),'aliases':aliases}
        key=norm(title)
        records[key]=rec
        for alias in aliases:
            synonyms.setdefault(norm(alias), rec)
    print('Valid English records with summaries:',len(records))
    return records, synonyms, root.get('date-generated','')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--file',help='An already downloaded official .zip or .xml. Otherwise download the newest ZIP.')
    args=parser.parse_args()
    archive=Path(args.file).read_bytes() if args.file else official_download()
    records,synonyms,generated=parse_official_topics(raw_xml_bytes(archive))
    con=connect(); init(con)
    seed_rows=con.execute('SELECT id,title,category,aliases FROM cases ORDER BY id').fetchall()
    if not seed_rows:
        raise RuntimeError('No seed catalog. Run python seed_database.py first.')
    now=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    used_ids=set(); updated=0; unresolved=[]; substituted=[]
    def find(title):
        return records.get(norm(title)) or synonyms.get(norm(title))
    with con:
        for row in seed_rows:
            rec=find(row['title'])
            if not rec or rec['medlineplus_id'] in used_ids:
                unresolved.append(dict(row))
                continue
            used_ids.add(rec['medlineplus_id'])
            aliases=' '.join(dict.fromkeys(filter(None,[row['aliases'],*rec['aliases']])))
            con.execute('''UPDATE cases SET summary=?, source_name='MedlinePlus / NLM',
                    source_url=?, medlineplus_id=?, published_date=?, imported_at=?,
                    aliases=?, content_status='official_summary' WHERE id=?''',
                (rec['summary'],rec['url'],rec['medlineplus_id'],generated,now,aliases,row['id']))
            updated+=1
        available=[(cat,name,find(name)) for cat,name in EXTRA_CANDIDATES]
        for row in unresolved:
            # Try fallback MedlinePlus record; never invent an article or clinical claim.
            candidate=next(((cat,name,rec) for cat,name,rec in available
                            if rec and rec['medlineplus_id'] not in used_ids),None)
            if candidate is None:
                continue
            category,name,rec=candidate
            used_ids.add(rec['medlineplus_id'])
            aliases=' '.join(rec['aliases'])
            con.execute('DELETE FROM source_links WHERE case_id=?',(row['id'],))
            con.execute('''UPDATE cases SET title=?,category=?,summary=?,source_name='MedlinePlus / NLM',
                 source_url=?,medlineplus_id=?,published_date=?,imported_at=?,aliases=?,
                 content_status='official_summary' WHERE id=?''',
                (rec['title'],category,rec['summary'],rec['url'],rec['medlineplus_id'],generated,now,aliases,row['id']))
            substituted.append(f"{row['title']} -> {rec['title']}")
            updated+=1
    after=con.execute("SELECT COUNT(*) FROM cases WHERE content_status='official_summary'").fetchone()[0]
    total=con.execute('SELECT COUNT(*) FROM cases').fetchone()[0]
    db_size=Path(__file__).with_name('lifeline_medical.db').stat().st_size
    print(f'Imported official summaries: {after}/{total}. Database size: {db_size:,} bytes.')
    if substituted: print('Replacements:', '; '.join(substituted))
    if after != 100:
        print('WARNING: Some catalog entries do not have source text; they must NOT be treated as medically answered.')
        for row in con.execute("SELECT title FROM cases WHERE content_status='catalog_only'"):
            print('  Missing official summary:',row['title'])
    else:
        print('SUCCESS: all 100 cases now contain official offline MedlinePlus health-topic summaries.')
    con.close()

if __name__ == '__main__': main()
