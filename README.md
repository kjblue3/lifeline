# LastLine starter

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --reload
```

Open `http://127.0.0.1:8000/docs` to inspect API. In a second PowerShell window from this folder, serve the dashboard:

```powershell
py -3.11 -m http.server 5500
```

Open `http://127.0.0.1:5500/dashboard.html`. If the dashboard is served from port 5500, add CORS to FastAPI (see below), or instead serve dashboard from the backend itself by adding:

```python
from fastapi.responses import FileResponse
@app.get('/')
def dashboard():
    return FileResponse(Path(__file__).with_name('dashboard.html'))
```

Then open `http://127.0.0.1:8000/` (recommended). This avoids CORS.

**Important:** This is a working *scaffold*, not yet the promised AI system. The classifier uses keyword rules, the cloud mode is a manual simulation, and `cloud_reports` is another SQLite table, not a remote cloud service. Replace all three honestly before the final demo.
