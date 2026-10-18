# Validated Runtime And Regression Gate

## Current Decision

**Currently validated: official llama.cpp b11490 Windows ARM64 CPU build**, on
Kiran's Dell Latitude 7455, Snapdragon X Elite, Windows 11 ARM64. Retain its
matching DLL bundle and the existing Qwen2.5-3B-Instruct Q4_K_M GGUF. Use CPU-only
execution and ChatML, as in the working Dell tests. Do not change the model,
LifeLine system instruction or sampling settings to mask runtime corruption.

These results were reported by Kiran from real Dell tests, not executed in
Linux CoShell. They establish the following scope, not universal correctness:

| Runtime / Test | Reported Result |
| --- | --- |
| b11680 Windows ARM64 CPU, long ordinary/hiking text | Gibberish |
| b11680 Windows ARM64 CPU, LifeLine safety prompt | Gibberish |
| b11490 CLI, long prompt | Coherent; 39.6 output tokens/s, 311.2 prompt tokens/s |
| b11490 CLI, short prompt | Coherent; 41.1 output tokens/s |
| b11490 server, full LifeLine SYSTEM_INSTRUCTION | Coherent |
| b11490 server, long ordinary prompt | Coherent |
| b11490 server, short prompt | Coherent |
| Complete LifeLine website -> port 8000 -> server | Testing in progress |

Both builds used the **exact same GGUF**, per Kiran. This is strong evidence for
a build-dependent runtime problem, not evidence that streaming, changing the
safety prompt or a new quantization was necessary. The specific faulty commit,
kernel or compiler setting is still unknown. CLI throughput is not a measured
website/server throughput guarantee. No ExecuTorch or NPU execution is claimed.

Official release: https://github.com/ggml-org/llama.cpp/releases/tag/b11490

## Preserve The Working Installation

Record the actual paths, `--version` output, launch command, CPU/backend startup
logs and SHA256 hashes of the EXE, GGUF and every model shard. Do not replace the
working bundle with a rolling update, select an unverified WinGet executable,
or combine its DLLs with another build. Keep binaries/weights outside Git.
Verify future upgrades side-by-side against this version before switching.

From PowerShell, using your **actual** working paths:

```powershell
$server = 'C:\REPLACE\b11490-cpu-arm64\llama-server.exe'
$cli = 'C:\REPLACE\b11490-cpu-arm64\llama-cli.exe'
$gguf = 'C:\REPLACE\actual-qwen2.5-3b-instruct-q4_k_m.gguf'
& $server --version
& $cli --version
Get-FileHash -LiteralPath $server,$cli,$gguf -Algorithm SHA256
```

Keep the exact server command that passed on the Dell. Historical b11680 cache
and slot-erasure commands are not automatically certified for b11490; inspect
the selected binary's help before using them. No b11490 binary is checked in.

## Runtime Regression Check

With the working b11490 server idle on **127.0.0.1:8081**, from the repository
root, run the following. It sends **nine independent requests**, three cases
repeated in order for three rounds, without changing the server configuration:

```powershell
$out = Join-Path $env:TEMP ('lifeline-b11490-regression-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.jsonl')
& .\offline_ai\.venv-x64\Scripts\python.exe .\offline_ai\probe_llama_quality.py --suite runtime --cache default --rounds 3 --label b11490-win-arm64-cpu --review --output $out
```

1. **Short prompt:** ordinary hiking supplies under a simple nonmedical system
   prompt. Check intelligible English and sensible instruction following.
2. **Long ordinary prompt:** over 2,000 characters of nonmedical hiking notes.
   Check a coherent summary without multilingual corruption or token loops.
3. **Full LifeLine safety prompt:** the identical long user passage under the
   complete `SYSTEM_INSTRUCTION`, loaded verbatim from `inference.py`, not a
   shortened copy. Check coherent output without weakening safety instructions.

The first two are isolated diagnostic controls, not production system-prompt
changes. Every request is stateless; earlier answers are not included. Default
cache fields are omitted, matching the adapter, with temperature 0, output limit
160, and nonstreaming delivery. Inspect reported prompt-token counts to verify
the selected context fits the prompt plus output; context overflow is a failure
to investigate, not evidence of corrupt numerical inference.

The script stores complete payloads, raw bytes, usage/timings when available,
latency and manual judgments. It does not manufacture expected answers, filter
gibberish or claim that no heuristic flags means a pass. Exit 0 means capture
completed; **human review of all outputs is required**. Ordinary truncation at
the output limit is distinct from corruption and may require a separate limit
test. Fluent output does not establish medical correctness.

### Checklist Before Upgrading Or Changing Runtime Settings

- [ ] Confirm both executable versions and native ARM64 CPU bundle; no mixed DLLs.
- [ ] Confirm the same model SHA256/shards, ChatML and CPU-only execution.
- [ ] Preserve the exact LifeLine system instruction and output/sampling settings.
- [ ] Run short, long ordinary and full-safety cases on a fresh server process.
- [ ] Review all three rounds, not just a coherent first response.
- [ ] Restart the same server configuration and repeat the suite in a new file.
- [ ] Retain raw responses, token counts, startup logs, version and hashes.
- [ ] Reject corruption/repetition; do not hide it through output filtering.
- [ ] Compare any candidate build against b11490 using the same inputs/settings.
- [ ] Do not call an upgrade validated until runtime and website checks pass.

## Website Gate: Port 8000

Keep both the b11490 llama-server process and the existing FastAPI process
running. This is the same application/adapter, not a new server implementation.
Use the explicit model path already selected on the Dell:

```powershell
$env:LIFELINE_GGUF_PATH = 'C:\REPLACE\actual-qwen2.5-3b-instruct-q4_k_m.gguf'
$env:LIFELINE_LLAMA_PORT = '8081'
& .\offline_ai\.venv-x64\Scripts\python.exe -m uvicorn offline_ai.llama_adapter:app --host 127.0.0.1 --port 8000 --workers 1
```

Do not start a second process on an already occupied port 8000. Open
**http://127.0.0.1:8000/** and complete these checks without other inference
clients running concurrently:

- [ ] Submit a short nonmedical question; verify actual POST `/api/ask` succeeds.
- [ ] Submit a long nonmedical question below the UI/API 2,000-character limit.
- [ ] Repeat several independent questions; confirm no later-request corruption.
- [ ] Verify the response displayed matches the final API answer; retain logs.
- [ ] Verify the adapter still sends the unchanged safety instruction upstream.
- [ ] If RAG is enabled, check its configured supported-topic flow separately;
      nonmedical questions may correctly fail closed instead of invoking Qwen.
- [ ] Do not equate model-selector output with the RAG final reference answer.
- [ ] Disconnect Wi-Fi, keep both local processes alive, and repeat the checks.
- [ ] Keep error/draft/retry behavior and accurate source/safety notices intact.

RAG and source availability depend on Aryan's integration. Do not disable that
validation or invent citations to make a nonmedical website test pass. The
long runtime regression deliberately bypasses the UI question-length limit;
it is a direct-server correctness check, not a browser request fixture.

The complete website is **not yet recorded as validated**. Update this record
only after the Dell end-to-end tests actually pass. The existing PyTorch CPU
adapter remains an explicit fallback, unchanged.
