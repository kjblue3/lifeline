"""LastLine MVP: persistent local processing and simulated cloud sync."""
import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from threading import Lock
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from classifier import classify

DB = Path(__file__).with_name('lastline.db')
app = FastAPI(title='LifeLine Prototype')
cloud_available = True  # Demo switch, not a real network probe.
lock = Lock()

class ReportIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)

class NetworkIn(BaseModel):
    online: bool


def connect():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

with closing(connect()) as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY, text TEXT NOT NULL, category TEXT NOT NULL,
        urgency TEXT NOT NULL, engine TEXT NOT NULL, created_at REAL NOT NULL,
        synced INTEGER NOT NULL DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cloud_reports (
        id TEXT PRIMARY KEY, payload TEXT NOT NULL)''')
    conn.commit()

@app.get('/status')
def status():
    with closing(connect()) as conn:
        pending = conn.execute('SELECT COUNT(*) FROM reports WHERE synced=0').fetchone()[0]
        total = conn.execute('SELECT COUNT(*) FROM reports').fetchone()[0]
    return {'cloud_available_simulated': cloud_available, 'inference_engine': 'rules-baseline',
            'pending_sync': pending, 'total_reports': total}

@app.get('/reports')
def reports():
    with closing(connect()) as conn:
        rows = conn.execute('SELECT * FROM reports ORDER BY created_at DESC').fetchall()
    return [dict(r) for r in rows]

@app.post('/reports')
def add_report(payload: ReportIn):
    result = classify(payload.text)
    report = {'id': str(uuid.uuid4()), 'text': payload.text, 'created_at': time.time(), **result}
    # Always commit locally before attempting any remote action.
    with lock, closing(connect()) as conn:
        conn.execute('INSERT INTO reports (id,text,category,urgency,engine,created_at,synced) VALUES (?,?,?,?,?,?,0)',
                     (report['id'], report['text'], report['category'], report['urgency'], report['engine'], report['created_at']))
        conn.commit()
    if cloud_available:
        sync()
    return report

@app.post('/demo/network')
def set_network(payload: NetworkIn):
    global cloud_available
    cloud_available = payload.online
    return {'cloud_available_simulated': cloud_available}

@app.post('/sync')
def sync():
    if not cloud_available:
        raise HTTPException(503, 'Simulated cloud unavailable')
    count = 0
    with lock, closing(connect()) as conn:
        pending = conn.execute('SELECT * FROM reports WHERE synced=0').fetchall()
        for row in pending:
            # Simulated remote receiver, stored in a separate table for the demo.
            # Replace with an actual HTTPS endpoint to demonstrate real remote sync.
            conn.execute('INSERT OR IGNORE INTO cloud_reports (id,payload) VALUES (?,?)',
                         (row['id'], json.dumps(dict(row))))
            conn.execute('UPDATE reports SET synced=1 WHERE id=?', (row['id'],))
            count += 1
        conn.commit()
    return {'synced': count, 'destination': 'simulated-cloud-table'}

@app.get('/cloud-reports')
def cloud_reports():
    with closing(connect()) as conn:
        return [json.loads(r['payload']) for r in conn.execute('SELECT payload FROM cloud_reports').fetchall()]

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi import Request
from chat import router as chat_router

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    if request.url.path.startswith('/api/'):
        return JSONResponse(status_code=422, content={
            'ok': False, 'error': {
                'code': 'invalid_request',
                'message': 'Send a JSON object with a question of 1 to 2000 characters.'
            }
        })
    return await request_validation_exception_handler(request, exc)

app.include_router(chat_router)
app.mount('/assets', StaticFiles(directory=Path(__file__).parent / 'web'), name='assets')

@app.get('/')
def dashboard():
    return FileResponse(Path(__file__).parent / 'web' / 'index.html')

@app.get('/legacy')
def legacy_dashboard():
    return FileResponse(Path(__file__).with_name('dashboard.html'))
