# LifeLine

A local-first emergency-assistance **prototype** for the Qualcomm ExecuTorch
Hackathon 2026. Chat connects the browser to FastAPI and Google's Gemini API.
A server-side Gemini API key is required; without it requests fail explicitly,
never with a fake answer. Verified medical retrieval is not connected.
Use fictional scenarios only, never real health information.

## Run On The Dell

From the project folder in Windows PowerShell, with native Windows ARM64 Python
3.11 or newer installed:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/**. The backend serves the frontend too; no second
server, Node.js, or CORS setup is needed. Keep the terminal running.
Configure the API key below before starting the server. Cloud chat requires
internet access; offline AI and automatic offline switching are not enabled.
Windows ARM64 dependency installation and inference still need testing on the Dell.
Transfer the source through GitHub, not the cloud machine's `.venv` directory.

Linux/macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

## Cloud Configuration

Create a Gemini Developer API key at **https://aistudio.google.com/apikey**
for a project authorized to use the Gemini API, with sufficient quota/billing.
LifeLine reads **`GEMINI_API_KEY`** from the backend process environment.
CoShell subscriptions/internal tokens do not grant this application API access.
Do not put the key in frontend code, Git, screenshots, or chat messages.

PowerShell, before the Uvicorn command:

```powershell
$env:GEMINI_API_KEY = Read-Host 'Gemini API key' -MaskInput
```

Linux/macOS Bash, before the Uvicorn command:

```bash
read -rs -p 'Gemini API key: ' GEMINI_API_KEY
export GEMINI_API_KEY
```

Restart the backend after setting the environment. The default model is
`gemini-2.5-flash`; optionally set `GEMINI_MODEL` to another available Gemini
model ID. No `.env` file is loaded automatically. Status reports configured
when a key exists, and ready only after successful inference. It is not a
continuous network probe. Requests have a bounded 25-second cloud deadline.

## Try It

1. Open the homepage and confirm cloud AI is configured.
2. Enter a fictional question, such as “My fictional hiking partner injured an ankle.”
3. Press Enter or the send arrow. A real Gemini answer appears with a **CLOUD AI** badge, or an explicit configuration/provider error appears and your question is retained.
4. Check offline readiness: local model/references remain uninstalled; cloud readiness updates after a successful call.
5. Try an optional fictional profile. It stays in page memory and is never sent to the API.

Only the current question is sent to Google, not the profile or chat history;
Google's API data-handling terms apply. Questions are not stored by LifeLine's
chat API. Reloading clears the conversation
and profile. Frontend assets have no external font, script, or CDN dependencies.
The preserved **legacy report demo** at `/legacy` does store reports in SQLite;
its cloud switch and sync remain simulations. Do not enter real medical data there.
There is no authentication; keep the prototype bound to localhost, not the public internet.

## API

- `GET /api/health`: backend health.
- `GET /api/status`: configured cloud provider/model and last-inference readiness; local/reference readiness remains false.
- `POST /api/ask`: JSON `{"question":"A fictional scenario"}`, 1-2000 characters.
- `/docs`: interactive API documentation.

Successful API responses use `{"ok":true,"data":{...}}`. Invalid chat requests
return HTTP 422 with `{"ok":false,"error":{"code":"invalid_request","message":"..."}}`.
Answers contain `id`, `answer`, `mode`, `simulated`, `sources`, and `notice`.
Sources are empty deliberately: none are installed, and citations are not invented.
Provider failures use the same error envelope with HTTP 503 (missing key),
504 (timeout), or 502 (upstream failure, rejected credentials/quota, blocked,
incomplete, or malformed answer). There is no mock or offline fallback.

## Integration Boundaries

- Aryan: `web/`, `chat.py`, and FastAPI assembly in `app.py`.
- Kiran: implement the async `InferenceProvider.answer(question) -> Answer` boundary in a separate local-model adapter after confirming ExecuTorch text inference on the Dell. No ExecuTorch implementation has been changed here.
- Kanishk: prepare verified references with source metadata in a separate knowledge collection. No reference collection has been changed here.

`inference.py` defines the shared `InferenceProvider.answer(question) -> Answer`
contract; `cloud_ai.py` implements Gemini separately from the API and database.
`chat.py` selects this cloud adapter only. Kiran can implement the same contract
later without changing the cloud transport. Automatic offline switching is not
implemented. No local model or medical database files were changed.

The system instruction identifies LifeLine as a first-aid information assistant,
not a doctor. Because verified references are unavailable, it requires disclosing
that limitation, prohibits fabricated treatments/citations and step-by-step
treatment instructions, and prioritizes emergency services for serious situations.
The UI also displays a fixed limitation notice. These safeguards are not medical
validation; generated text can still be wrong. LifeLine is not a replacement for
emergency services or medical professionals.

## Tests

```sh
python -m pip install -r requirements-dev.txt
python -m unittest -v test_chat
python -m playwright install chromium
python browser_check.py
```

Unit tests use mock HTTP transport, not live inference. The browser check needs
a running server without a configured API key (default port 8000, override with
`--base-url`). It verifies the real missing-key failure, then explicitly mocks
API answers for rendering checks; it does not prove live Gemini inference.
Screenshots go under the system temporary directory's `lifeline-browser/` (override with
`--artifacts-dir`). Playwright is a development tool, not a runtime
dependency required on the Dell. On Linux, Chromium may also need system
libraries installed with `python -m playwright install-deps chromium`.
