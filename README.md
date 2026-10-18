# LifeLine

A fully local emergency-information **prototype** for the Qualcomm hackathon.
The existing FastAPI application serves both the website and `/api/ask` on port
8000. Qwen2.5-3B-Instruct Q4_K_M runs in a separate loopback llama-server on port
8081, using the currently validated **b11490 Windows ARM64 CPU** build on Kiran's
Snapdragon X Elite Dell. This is not ExecuTorch or verified NPU inference.

No cloud AI service or Gemini key is used by the current application. No model,
runtime binary or virtual environment is included in Git. Use fictional scenarios
for the prototype, not real personal/health information. Keep services bound to
`127.0.0.1`, not the public internet; this demo has no authentication.

## Offline Medical RAG

Follow **[MEDICAL_RAG.md](MEDICAL_RAG.md)** for the complete setup, generated-DB
backup/reinstallation steps, live acceptance commands and current limitations.
The installer runs without internet and creates a new generated database; it
does not replace the committed 100-topic catalog. Only ten MedlinePlus topic
summaries are populated: Bleeding, Burns, Choking, Poisoning, Heat Illness,
Hypothermia, Frostbite, Dehydration, Sprains and Strains, and Wounds and Injuries.
The other 90 entries, including Fractures, are catalog-only, not usable articles.

After installing references, keep the existing validated b11490 CPU-only model
server running on port 8081. In another PowerShell terminal at the project root:

```powershell
$python = '.\offline_ai\.venv-x64\Scripts\python.exe'
$env:LIFELINE_GGUF_PATH = 'C:\REPLACE\actual-qwen2.5-3b-instruct-q4_k_m.gguf'
$env:LIFELINE_LLAMA_PORT = '8081'
$env:LIFELINE_RAG = '1'
& $python -m uvicorn offline_ai.llama_adapter:app --host 127.0.0.1 --port 8000 --workers 1
```

Open **http://127.0.0.1:8000/**. No separate frontend server, build step or CORS
configuration is needed. Use the working installed environment; do not copy a
Linux virtual environment onto Windows. On macOS use the corresponding working
local environment and runtime; installation uses standard Python/SQLite FTS5.

Qwen selects IDs from trusted retrieved references; final medical text and
citations are extracted from pinned installed records, not generated treatments.
Ambiguous, unsupported, negated or ungrounded selections fail explicitly. The
reference library is not a complete first-aid protocol collection or clinical
validation. For immediate danger, contact local emergency services and follow
dispatcher instructions; do not wait for this chat.

## API And Verification

- `GET /api/health`: backend health.
- `GET /api/status`: local provider and reference availability; `offline_ready`
  remains false because this is not a complete emergency system.
- `POST /api/ask`: `{"question":"A fictional scenario"}`. Only the current
  question is sent, not profile/history. RAG has a documented 1200 UTF-8-byte limit.
- Success: `{"ok":true,"data":{id,answer,mode,simulated,sources,notice}}`.
- Failures: `{"ok":false,"error":{code,message}}`; missing references or unsafe
  model selections fail closed with HTTP 503.
- `/docs`: existing API documentation.

Without `LIFELINE_RAG=1`, the pre-existing provider-only mode returns ungrounded
model text; do not use that mode to demonstrate reference-backed medical answers.
Launching only `app:app` selects the disconnected placeholder in a fresh process.

```powershell
& $python -B -m unittest -v test_medical_rag test_chat test_llama_adapter
$results = Join-Path $env:TEMP ('lifeline-rag-live-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.jsonl')
& $python -B test_medical_rag.py --live --output $results
```

Unit/browser tests use clearly labeled model fixtures, not real Qwen inference.
The opt-in live mode needs both existing services, the local GGUF, and installed
references. Review relevance/citations manually, then repeat with Wi-Fi off.
The browser regression uses the existing Playwright development dependencies.
See [offline_ai/LLAMA_CPP.md](offline_ai/LLAMA_CPP.md) and
[runtime validation](offline_ai/LLAMA_RUNTIME_VALIDATION.md) for runtime setup.

The preserved report demo at `/legacy` stores reports in SQLite; its cloud switch
and sync are simulations, separate from local chat. Never enter real medical data
there. The standalone browser library and packing checklist are separate from
backend RAG/reference status; see [FRONTEND_FEATURES.md](FRONTEND_FEATURES.md).
