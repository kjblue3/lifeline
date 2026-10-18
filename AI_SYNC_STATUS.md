# Local Qwen Integration Status

## GitHub Comparison

Fetched all configured origin branches without pulling, resetting, merging, or
committing the shared worktree. Latest observed main is Kiran's
`b5505bd7cb1ebfa77d9b9e0d807e60512e18a855`, a diagnostics commit. The newest
production llama.cpp adapter is from `2db01e1`; the PyTorch adapter is from
`576eff0`. The current copies of both adapters, their runtime documentation,
quality probes, and the three latest payload-diagnostic files are byte-for-byte
identical to `origin/main`. No source overwrite was necessary. The diagnostic
files already existed in this worktree; they were not staged or recommitted.

The worktree remains on `medical-rag-integration` and retains its RAG changes.
The fact that main lacks the feature branch's RAG files is not a reason to
replace `chat.py` with main's older version. All unrelated frontend/PWA and
teammates' untracked changes remain in place.

## Running Processes And Blockers

At inspection time:

| Port | Role | State |
| --- | --- | --- |
| 8000 | LifeLine FastAPI | Running `app:app`, the placeholder provider |
| 8081 | Qwen llama.cpp inference | No listener |
| 8010 | Restricted public frontend | Running; preserved |

The intended private inference path already exists:

`web/api.js -> POST /api/ask -> chat.py -> optional medical RAG -> LlamaCPUProvider -> 127.0.0.1:8081/v1/chat/completions`

The actual port-8000 process was launched with `app:app`, not
`offline_ai.llama_adapter:app`. The latter is Kiran's existing entry point that
selects `chat.provider = LlamaCPUProvider()` after importing the shared app.
The RAG branch calls the same selected provider; it does not replace the engine.

This workspace has no model artifacts in the project (`.gguf`, `.safetensors`,
`.bin`, or `.pte`), no `llama-server`/`llama-cli` on PATH, and no installed Torch,
Transformers, or llama-cpp-python in the application environment. Git excludes
weights and model directories; fetching source code cannot supply them. This is
Linux x86_64 with about 7.8 GiB RAM. A suitable Linux CPU runtime and supplied
Qwen GGUF might run here, but performance and compatibility have not been
validated. The Windows Dell binary is not a Linux runtime. No large model
download, runtime installation, or new service was attempted.

The llama.cpp adapter uses Python's standard library HTTP client and does not
need Torch, Transformers, or llama-cpp-python. It does need an independently
running compatible llama-server and the configured local GGUF path. Those are
the immediate blockers for that adapter. The separate PyTorch alternative
requires both its dependencies and its own model files; it is not a fallback
that works simply because the llama.cpp runtime is missing.

`127.0.0.1` means the machine running the process. CoShell's loopback does not
reach the Dell's loopback. No authenticated Dell connection has been configured.

## Read-Only Check

Run in the same Python environment used to run FastAPI:

```powershell
$py = '.\offline_ai\.venv-x64\Scripts\python.exe'
& $py -B check_ai_setup.py
```

Or in this Linux workspace:

```sh
.venv/bin/python -B check_ai_setup.py
```

This checks loopback status endpoints, the configured GGUF header, and installed
references. It never generates text, downloads a model, starts a server, or
imports/reconfigures the application. Exit 2 means prerequisites are not ready.
The tool is a preflight, not proof of real model identity or valid generation.

## Fastest Safe Dell Test

1. Preserve the working Dell checkout and bring over the RAG integration as
   described in `MEDICAL_RAG.md`. Do not overwrite local AI files. The existing
   model server and its known-working flags should remain unchanged.
2. Keep that server listening on `127.0.0.1:8081`. Confirm its health in the
   terminal where the working server is already running; do not start a second
   server. If the server is absent, use Kiran's existing command from
   `offline_ai/LLAMA_CPP.md` and the actual local model path, not guessed paths.
3. In the backend terminal, use the actual environment and existing GGUF path:

```powershell
$py = '.\offline_ai\.venv-x64\Scripts\python.exe'
$env:LIFELINE_GGUF_PATH = 'C:\REPLACE_WITH_EXISTING_PATH\qwen2.5-3b-instruct-q4_k_m.gguf'
$env:LIFELINE_LLAMA_PORT = '8081'
if (!(Test-Path -LiteralPath $env:LIFELINE_GGUF_PATH)) { throw 'Set the actual existing GGUF path first.' }
Invoke-RestMethod http://127.0.0.1:8081/health
```

4. First test the actual provider without RAG so an unsupported nonmedical test
   question does not fail reference retrieval before reaching Qwen. Stop only
   the old Dell FastAPI process on 8000 when ready, keep the model server alive,
   and start one instance using Kiran's unchanged entry point:

```powershell
Remove-Item Env:LIFELINE_RAG -ErrorAction SilentlyContinue
& $py -m uvicorn offline_ai.llama_adapter:app --host 127.0.0.1 --port 8000 --workers 1
```

From another terminal:

```powershell
$body = @{question='Reply with one short sentence explaining what a triangle is.'} | ConvertTo-Json
$reply = Invoke-RestMethod http://127.0.0.1:8000/api/ask -Method Post -ContentType 'application/json' -Body $body
$reply.data.answer
$reply.data.mode
$reply.data.simulated
```

Inspect actual Qwen text, server logs, and the website at
`http://127.0.0.1:8000/`. This test is not an assessment of medical correctness.
Expect real, coherent local output with `mode=local` and `simulated=false`.
This response flag alone is not hardware/model attestation. If output is
corrupted, use Kiran's diagnostics in `offline_ai/LLAMA_PAYLOAD_AB.md`; the
latest diagnostic commit is not evidence that corruption has been fixed.

5. Install the references offline if not already installed, then stop only
   FastAPI and rerun the same command with RAG enabled:

```powershell
if (!(Test-Path 'medical_data\lifeline_medical_installed.db')) {
    & $py -B medical_data/install_references.py
    if ($LASTEXITCODE -ne 0) { throw 'Reference installation failed.' }
}
$env:LIFELINE_RAG = '1'
& $py -m uvicorn offline_ai.llama_adapter:app --host 127.0.0.1 --port 8000 --workers 1
```

From another terminal:

```powershell
(Invoke-RestMethod http://127.0.0.1:8000/api/status).data.references
$body = @{question='My hiking partner twisted an ankle. What reference information is available?'} | ConvertTo-Json
$reply = Invoke-RestMethod http://127.0.0.1:8000/api/ask -Method Post -ContentType 'application/json' -Body $body
$reply.data.answer
$reply.data.sources | Format-Table title,url
```

Expected installed reference count is 10. The model must return valid reference
IDs; the backend publishes exact corresponding reference text and source links,
not unchecked generated treatments. Selection failure produces
`medical_grounding_failed`, not a fabricated answer. This extractive design is
unchanged. Repeat the website test with Dell Wi-Fi disconnected. The tests here
do not establish actual Dell selection quality, generation speed, ExecuTorch,
Qualcomm NPU acceleration, or clinical validation.

## Samsung And Public Preview

The existing Samsung PWA URL and tunnel are preserved. The port-8010 public
server is intentionally frontend-only: it does not proxy port 8000 or 8081.
Its status response and ask-unavailable response are explicit public-preview
notices, not fake inference. Existing installed-interface and public reference
library behavior remain separate from model availability.

The Samsung currently cannot use the Dell model through this CoShell preview:
there is no private authenticated route from this machine to that Dell, and
there is no approved authenticated ask gateway. Adding permissive CORS,
forwarding the entire backend, binding the raw model publicly, or entering
`127.0.0.1:8081` on the phone would not safely solve this.

The fastest currently available working AI path is the Dell's own browser and
its existing loopback services. For phone inference access later, keep Qwen on
loopback and use a private trusted network/VPN plus an authenticated,
rate-limited gateway exposing only approved ask/status routes. A same-origin
gateway can preserve the PWA API URLs; it must explicitly block reports,
databases, docs, raw model APIs and other development routes. Dell reachability
and credentials must be supplied before this can be implemented and tested.
No such access was invented or enabled as part of this task.
