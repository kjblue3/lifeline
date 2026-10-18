# Local Qwen With llama.cpp

This uses Qwen2.5-3B-Instruct Q4_K_M on CPU, not ExecuTorch or NPU inference.
The adapter connects to an externally managed persistent llama-server. It does
not launch or reconfigure that process: the CPU settings below are mandatory.
No Python dependency changes are required beyond the existing FastAPI environment.

## Validated Dell Runtime

Use the **official b11490 Windows ARM64 CPU build** for the current demo.
Kiran reports coherent short/long CLI output and server output with the full
unchanged LifeLine system instruction using the same Qwen2.5-3B-Instruct Q4_K_M
GGUF. The b11680 Windows ARM64 CPU build produced gibberish on long prompts.
This is a validated-build choice on this Dell, not a proven upstream root cause.
CLI measurements and the regression/website checklist are recorded in
[LLAMA_RUNTIME_VALIDATION.md](LLAMA_RUNTIME_VALIDATION.md).

Select b11490 by explicit executable path; do not let PATH/WinGet silently select
b11680 or mix DLLs from different bundles. Keep the exact tested launch command
and inspect b11490's own `--help` before using flags from older investigations.
Website end-to-end testing on port 8000 is still in progress.

## Find Existing Model And Server

Run from the LifeLine repository root in PowerShell. Search the llama.cpp cache
and common Hugging Face/local model locations; nothing is downloaded:

```powershell
$roots = @(
  "$env:LOCALAPPDATA\llama.cpp",
  "$env:USERPROFILE\AppData\Local\llama.cpp",
  "$env:USERPROFILE\.cache\llama.cpp",
  "$env:USERPROFILE\.cache\huggingface",
  "$PWD\offline_ai\models"
)
if ($env:LLAMA_CACHE) { $roots += $env:LLAMA_CACHE }
if ($env:HF_HOME) { $roots += $env:HF_HOME }
$roots | Select-Object -Unique | Where-Object { Test-Path $_ } |
  ForEach-Object { Get-ChildItem -LiteralPath $_ -Recurse -File -Filter '*q4_k_m*.gguf' -ErrorAction SilentlyContinue } |
  Select-Object FullName, Length

Get-Command llama-server.exe -ErrorAction SilentlyContinue
$cli = Get-Command llama-cli.exe -ErrorAction Stop
Get-ChildItem -LiteralPath (Split-Path $cli.Source) -Filter 'llama-server*'
```

Select the official Qwen2.5-3B-Instruct Q4_K_M file, not a different model.
If missing from these locations, search the directory used when running the
working CLI, or use `llama-cli --cache-list` if supported by your build.
For split GGUFs choose the first shard and keep every shard alongside it.
If llama-server is absent, this build cannot serve the HTTP API; obtain/build
the matching server binary separately before the offline demo. No CLI fallback
is silently substituted. Verify `llama-server --help` supports the flags below.

## Terminal 1: Keep Model Server Running

Replace the following two paths with the actual local paths just found:

```powershell
$server = 'C:\path\to\b11490-cpu-arm64\llama-server.exe'
$gguf = 'C:\path\to\qwen2.5-3b-instruct-q4_k_m.gguf'
if (!(Test-Path -LiteralPath $server)) { throw 'llama-server.exe is missing' }
if (!(Test-Path -LiteralPath $gguf)) { throw 'GGUF file is missing' }
& $server --version
& $server --help
& $server -m $gguf --host 127.0.0.1 --port 8081 --alias lifeline-qwen --n-gpu-layers 0 --device none --no-kv-offload --no-op-offload --temp 0 --chat-template chatml --check-tensors --ctx-size 4096 --parallel 1 --offline
```

Use `-m`, not `-hf`: launches use the existing file without hub resolution.
ChatML is applied by llama-server to the system/user messages. No prompt text
is assembled by the adapter. Check server logs for zero GPU-offloaded layers.
Do not remove CPU-offload restrictions to fix unsupported flags; use a build
supporting them. The CLI speed reported by Kiran is not a server benchmark.

## Terminal 2: Keep Existing LifeLine Application Running

From the repository root, set the same model path:

```powershell
$env:LIFELINE_GGUF_PATH = 'C:\path\to\qwen2.5-3b-instruct-q4_k_m.gguf'
$env:LIFELINE_LLAMA_PORT = '8081'
$env:LIFELINE_LLAMA_MAX_TOKENS = '160'
$env:LIFELINE_LLAMA_TIMEOUT = '120'
Invoke-RestMethod http://127.0.0.1:8081/health
& .\offline_ai\.venv-x64\Scripts\python.exe -m uvicorn offline_ai.llama_adapter:app --host 127.0.0.1 --port 8000 --workers 1
```

Stop the old PyTorch FastAPI process on port 8000 first. Open
**http://127.0.0.1:8000/**. The existing website still posts `{question}` to
`/api/ask`; FastAPI alone talks to llama-server. No frontend/CORS changes.
Keep both terminals running. Requests use no proxies and never follow redirects.
Port and generation limit are configurable; the inference host is not.

`ready` reflects the last successful generation, not a live process monitor.
It starts false; the existing website allows a first question regardless.
Each ask checks `/health`; failure clears readiness. Missing binaries/stopped
servers, loading errors, bad responses, empty text, and timeouts return 503.
Timeout is a socket inactivity limit (maximum configurable value 150 seconds),
not guaranteed cancellation of the remote generation. Wait before retrying.
`--parallel 1` limits server execution even after a disconnected/timed-out client.
Use one FastAPI worker; do not share this demo server with other clients.

The adapter trusts the local server's model/configuration: it cannot attest which
weights or compute devices a separately started process actually loaded. Match
the same GGUF path in both terminals, use the documented flags, and inspect logs.

## Verification And Fallback

In browser Network tools, compare the displayed text with `/api/ask`'s actual
`data.answer`. Expect `mode=local` and `simulated=false`. Without RAG, sources
remain empty and reference readiness stays false. For the grounded medical demo,
install the pinned references and set `LIFELINE_RAG=1` as in
[MEDICAL_RAG.md](../MEDICAL_RAG.md): sources then come only from validated stored
records, and reference count is 10. This does not imply complete offline readiness.
Repeat with Wi-Fi disconnected. Check the server terminal logs for the request.
Neither runtime coherence nor installed source attribution verifies clinical correctness.

Tests: `python -m unittest -v test_llama_adapter test_chat`. The adapter tests use
a mock loopback HTTP server and explicitly marked nonmedical output; they do
not demonstrate real GGUF inference, Dell performance, or hardware acceleration.

To select the untouched PyTorch fallback explicitly, stop FastAPI, then run:

```powershell
& .\offline_ai\.venv-x64\Scripts\python.exe -m uvicorn offline_ai.qwen_adapter:app --host 127.0.0.1 --port 8000 --workers 1
```

There is no automatic fallback. GGUF weights are ignored by Git anywhere in the
repository, and `offline_ai/models/` remains ignored.
