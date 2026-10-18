# b11680 Correctness Investigation

**Current status:** Kiran has validated the official **b11490 Windows ARM64 CPU
build** with the identical Qwen Q4_K_M GGUF: short/long CLI prompts and server
requests including the full LifeLine safety instruction were coherent. The
b11680 CPU build failed long prompts. Prefer b11490 for this Dell; see
[runtime validation and regression checklist](LLAMA_RUNTIME_VALIDATION.md).
The hypotheses/commands below are historical b11680 investigation material,
not a requirement to continue debugging b11680 before the demo. The precise
upstream regression remains unidentified; website testing is in progress.

No Dell experiment has been executed in CoShell. These are reproducible tests,
not a confirmed fix. Keep corrupted output out of the medical demo. No output
filtering can establish that an apparently fluent answer is medically safe.

## Evidence And Ranked Hypotheses

The three corrupted direct `/v1/chat/completions` responses exclude LifeLine's
frontend/adapter as a necessary cause. Intermittently coherent CLI/server output
does not certify the backend. PyTorch coherence argues against model capability
being the issue, but does not validate a GGUF or its execution kernels.

1. **Effective binary/backend/configuration mismatch.** WinGet's b11680 ARM64
   package selects the Vulkan ARM64 archive, not the CPU-only archive. A stale
   process, a different executable on PATH, DLL/plugin selection, environment
   overrides, or remaining device operations could explain different runs.
   Earlier GPU corruption makes this a priority, not proof of current GPU use.
2. **CPU kernel/repacking/batched-prefill correctness.** Severe garbling in a
   Q4_K model is consistent with bad arithmetic. Native ARM CPU optimizations
   still run with `--device none`. Repacking, instruction dispatch, compiler,
   and batch/thread execution must be isolated. Historical ARM Q4_K faults are
   real, but their known fixes are included in b11680.
3. **Persistent state/prefix-cache/slot reuse.** A coherent first turn followed
   by corruption makes this test-worthy, but fresh corrupted server responses
   would weaken it. Independent requests do not append hidden chat history;
   slots can still reuse matching prefixes. Distinguish prefix reuse, chunk
   shifting, RAM prompt-state cache, and context-capacity shifting.
4. **Prompt/template/tokenization/sampling mismatch.** Match the exact model,
   system/user messages, ChatML, context, output limit and temperature. Template
   mismatch can degrade quality, but is not by itself evidence of the severe
   numerical corruption described. Long-context shifting is less plausible for
   short independent questions unless actually triggered.
5. **GGUF integrity/quantization-specific fault.** Check the exact file hash,
   every shard, model metadata, and tensor validation. A repeatably coherent run
   with exactly the same hashed file weakens simple file corruption. Neither
   `--check-tensors` nor one good answer proves runtime math correctness.

Windows x64 emulation is a hypothesis only until the actual PE architecture is
identified. A native ARM64 Python environment is not required to run a separate
native ARM64 llama-server. An x64 Python environment does not make that server
run under x64 emulation.

## Version-Pinned Research

Upstream tag `b11680` resolves to `b797b9ca816bbced1e71c29c8b28cb35b103b624`
(October 16, 2026). No source found establishes an unfixed b11680 CPU corruption
bug for this exact Dell/Qwen2.5-3B/Q4_K_M combination.

- [Exact release](https://github.com/ggml-org/llama.cpp/releases/tag/b11680)
- [WinGet package selection](https://github.com/microsoft/winget-pkgs/blob/master/manifests/g/ggml/llamacpp/b11680/ggml.llamacpp.installer.yaml)
- [Exact-version server docs](https://github.com/ggml-org/llama.cpp/blob/b11680/tools/server/README.md)
- [Argument parsing/scopes](https://github.com/ggml-org/llama.cpp/blob/b11680/common/arg.cpp)
- [CLI embedded server](https://github.com/ggml-org/llama.cpp/blob/b11680/tools/cli/cli-server.h)
- [Server cache/slot implementation](https://github.com/ggml-org/llama.cpp/blob/b11680/tools/server/server-context.cpp)
- [ARM Q4_K repack issue #19561](https://github.com/ggml-org/llama.cpp/issues/19561):
  Linux ARM build 8014; `--no-repack` avoided it. Its fix
  [#19575](https://github.com/ggml-org/llama.cpp/pull/19575) is already in b11680.
- [X Elite Vulkan corruption #28290](https://github.com/ggml-org/llama.cpp/issues/28290):
  Qwen3 Q8_0, different commit, GPU execution; reporter measured NaN/numerical
  errors. Driver root cause remains a hypothesis; not proof of a CPU bug.
- [Qwen2.5 context-shift repetition #14759](https://github.com/ggml-org/llama.cpp/issues/14759):
  older 0.5B/Metal server regression; fix
  [#14760](https://github.com/ggml-org/llama.cpp/pull/14760) is already in b11680.

At this exact version, llama-cli uses an embedded HTTP server unless pointed at
an external server. Fresh `--single-turn` CLI runs therefore change process
lifetime as well as client behavior. Interactive CLI retains chat history;
LifeLine sends only the current question and system instruction. A fair parity
test must use the same messages. `--single-turn` is a CLI flag, **not a server
reset option**; do not pass it to llama-server.

## 1. Capture Provenance Before Changing Anything

From the LifeLine repository root, in PowerShell. Stop asking questions from the
website during experiments. Do not run another inference client concurrently.

```powershell
$server = (Get-Command llama-server.exe -ErrorAction Stop).Source
$cli = (Get-Command llama-cli.exe -ErrorAction Stop).Source
$py = (Resolve-Path .\offline_ai\.venv-x64\Scripts\python.exe).Path
$gguf = (Resolve-Path 'C:\REPLACE\actual-qwen2.5-3b-instruct-q4_k_m.gguf').Path
$run = Join-Path $env:TEMP ('lifeline-llama-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $run -ErrorAction Stop | Out-Null

Get-Command llama-server.exe,llama-cli.exe -All | Format-List Source,Version
& $server --version 2>&1 | Tee-Object (Join-Path $run 'server-version.txt')
& $cli --version 2>&1 | Tee-Object (Join-Path $run 'cli-version.txt')
$serverHelp = (& $server --help 2>&1 | Out-String)
$serverHelp | Set-Content (Join-Path $run 'server-help.txt')
& $cli --help 2>&1 | Set-Content (Join-Path $run 'cli-help.txt')
Get-FileHash -LiteralPath $server,$cli,$gguf -Algorithm SHA256 |
  Format-List | Out-File (Join-Path $run 'hashes.txt')
Get-ChildItem Env: | Where-Object Name -Match '^(LLAMA_ARG_|GGML_|OMP_)' |
  Sort-Object Name | Out-File (Join-Path $run 'runtime-env.txt')
Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^llama-(server|cli).*' } |
  Select-Object ProcessId,ExecutablePath,CommandLine | Format-List
Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

If GGUF is sharded, hash **all** shards too. Compare CLI and server paths,
versions, GGUF metadata and hash with the previously coherent run. Inspect the
server terminal's backend/buffer logs; enumerating Vulkan devices is not proof
that tensors were placed there. Verify actual layers/buffers and no RPC/Hexagon
or other accelerator execution. Don't publish environment logs without checking
for credentials/private paths.

Read the executable PE machine field without installing tools:

```powershell
function Get-PeMachine([string]$Path) {
  $s = [IO.File]::OpenRead($Path)
  $r = [IO.BinaryReader]::new($s)
  try {
    $s.Position = 0x3c
    $offset = $r.ReadInt32()
    $s.Position = $offset
    if ($r.ReadUInt32() -ne 0x00004550) { throw 'Not a PE executable' }
    $machine = $r.ReadUInt16()
    $arch = switch ($machine) { 0xAA64 {'ARM64'} 0x8664 {'x64 (emulated on ARM64)'} default {'Other'} }
    [pscustomobject]@{ Path=$Path; Machine=('0x{0:X4}' -f $machine); Architecture=$arch }
  } finally { $r.Dispose() }
}
Get-PeMachine $server
Get-PeMachine $cli
```

## 2. Fresh-Process Experiments

Only stop the old 8081 process after confirming its identity above. Prefer Ctrl+C
in its own terminal. The helper below refuses to replace an existing listener.
It starts a **fresh process for each experiment**, waits for health, records
stdout/stderr, runs serialized independent prompts, then stops only that process.
It does not start FastAPI or change adapters.

All following flags were verified in upstream b11680. The helper also requires
the **installed server's help** to advertise each flag; if that check fails,
stop and compare the installed executable/help instead of guessing a substitute.

```powershell
$base = @(
  '-m', $gguf, '--host', '127.0.0.1', '--port', '8081', '--alias', 'lifeline-qwen',
  '--offline', '--n-gpu-layers', '0', '--device', 'none',
  '--no-kv-offload', '--no-op-offload', '--check-tensors',
  '--parallel', '1', '--ctx-size', '2048', '--chat-template', 'chatml',
  '--temp', '0', '--seed', '1234', '--no-context-shift',
  '--cache-type-k', 'f16', '--cache-type-v', 'f16', '--cache-reuse', '0',
  '--cache-ram', '0', '--no-kv-unified', '--flash-attn', 'off', '--fit', 'off'
)

function Invoke-LlamaExperiment {
  param([string]$Name, [string[]]$Extra=@(), [string]$Cache='off', [string]$System='lifeline', [int]$Rounds=3)
  if (Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8081 is occupied. Stop the identified old server first.'
  }
  $allArgs = @($base) + @($Extra)
  foreach ($flag in ($allArgs | Where-Object { $_ -match '^--' } | Select-Object -Unique)) {
    if ($serverHelp -notmatch ([regex]::Escape($flag) + '(?=[\s,=]|$)')) {
      throw "Installed server help does not advertise $flag; inspect it before proceeding"
    }
  }
  # Start-Process joins arguments; explicitly quote the model/slot-directory paths.
  $quoted = $allArgs | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
  $process = Start-Process -FilePath $server -ArgumentList $quoted -PassThru -NoNewWindow `
    -RedirectStandardOutput (Join-Path $run "$Name.stdout.log") `
    -RedirectStandardError (Join-Path $run "$Name.stderr.log")
  try {
    $healthy = $false
    for ($i=0; $i -lt 120; $i++) {
      if ($process.HasExited) { throw "Server exited. Inspect $Name.stderr.log" }
      try {
        $health = Invoke-RestMethod http://127.0.0.1:8081/health -TimeoutSec 2
        if ($health.status -eq 'ok') { $healthy=$true; break }
      } catch { }
      Start-Sleep -Seconds 1
    }
    if (!$healthy) { throw 'Server never became healthy' }
    & $py .\offline_ai\probe_llama_quality.py --label $Name --cache $Cache --system $System --rounds $Rounds --review --output (Join-Path $run "$Name.jsonl")
    if ($LASTEXITCODE -ne 0) { throw 'Probe collection failed; inspect JSONL and logs' }
  } finally {
    if (!$process.HasExited) { Stop-Process -Id $process.Id; $process.WaitForExit() }
  }
}
```

### Immediate Runs, In Order

```powershell
# A: Forced CPU, defaults for repacking; caches disabled. 15 questions.
Invoke-LlamaExperiment -Name 'A-repack-on-cache-off' -Extra @('--repack','--no-cache-prompt')

# B: One variable changed: disable weight repacking. 15 questions.
Invoke-LlamaExperiment -Name 'B-repack-off-cache-off' -Extra @('--no-repack','--no-cache-prompt')

# C: If B fails, isolate threading before blaming state. Still a fresh process.
Invoke-LlamaExperiment -Name 'C-no-repack-one-thread' -Extra @('--no-repack','--no-cache-prompt','--threads','1','--threads-batch','1')

# D: Identical to B except enable prefix reuse at both default and request level.
Invoke-LlamaExperiment -Name 'D-prefix-cache-on' -Extra @('--no-repack','--cache-prompt') -Cache on

# E: Same server as D, but omit request cache/slot fields just like LifeLine.
Invoke-LlamaExperiment -Name 'E-adapter-request-shape' -Extra @('--no-repack','--cache-prompt') -Cache default

# F: Control for LifeLine's safety prompt, not a replacement for it.
Invoke-LlamaExperiment -Name 'F-simple-system-control' -Extra @('--no-repack','--no-cache-prompt') -System simple
```

Every prompt is independent, with no preceding assistant messages. Five prompts
are repeated in the same order for three rounds. First-round versus later-round
output localizes sequence dependence. The script logs latency, all raw bodies,
request messages, usage/token counts (when reported), finish reasons and server
timings (in the raw response). Wall output tokens/second includes prompt
processing/HTTP overhead; it is **not** pure decode throughput.

`--review` asks for coherent/corrupted/unclear. Review instruction following,
language, repetitions, truncation, and meaning, not just spelling. Safety-preface
text may legitimately differ from an exact-format test expectation. No flags
does not mean good quality. Heuristics never filter or modify the answer; all
output is preserved. No seed/temperature claim implies bitwise determinism.
Responses include lossless base64 bytes and a UTF-8 decoding-error flag as well
as decoded text, so malformed transport bytes are not confused with a model
actually emitting a Unicode replacement character.
Choose fresh names/output files when rerunning; existing JSONL files are refused.

If B/C fail on the **first question in every fresh process**, persistent cache
reuse is not necessary for corruption. Then test a fresh process for each prompt
or repeat the first prompt across at least three process restarts. If B passes
but D fails only after reuse, cache is implicated, not proven: investigate logs,
batch-size differences and exact cached token counts. Prefix caching can alter
numerical batch paths even when the request is logically identical.

### Slot Erase Control (Only If Cache Dependence Emerges)

At b11680, **`POST /slots/0?action=erase` requires `--slot-save-path`**, even for
erase. `--slots` alone is not sufficient. Erase clears that slot's sequence/token
state, **not the separate RAM cache**. Keep `--cache-ram 0`. Fresh process restart
remains the stronger reset.

For this one experiment start the following server in a separate terminal with
the same `$server`, `$base`, `$run` values. Run only one erase experiment at once:

```powershell
$slots = Join-Path $run 'slots'
New-Item -ItemType Directory -Path $slots -Force | Out-Null
& $server @base --no-repack --cache-prompt --slot-save-path $slots
```

In the probe terminal, using the `$py` and `$run` from above:

```powershell
& $py .\offline_ai\probe_llama_quality.py --label 'G-erase-each' --cache on --erase-between --rounds 3 --review --output (Join-Path $run 'G-erase-each.jsonl')
```

Ctrl+C the test server afterwards. A failed erase stops the script; it never
silently treats an unsupported reset as successful.

## Flag Meaning And CLI Parity

- `--no-kv-offload` keeps KV processing off accelerators; it does not turn off KV
  state, prefix reuse or RAM caching. Q4_K_M weights and f16 KV are different.
- `--cache-reuse 0` disables extra shifted-chunk matching, not prefix reuse.
- `--no-cache-prompt` sets the request default; `cache_prompt:false` overrides it
  explicitly. Do not assume it purges all stored RAM prompt state.
- `--cache-ram 0` disables saved prompt-state RAM cache, not active slot prefixes.
- `--no-context-shift` does not disable those caching mechanisms; it is already
  the default at b11680. The small probes should fit well below 2048 tokens.
- `--parallel 1` means one slot, not one CPU thread. Explicit non-unified KV avoids
  the auto mode (four slots/unified KV). Do not send concurrent requests.
- `--check-tensors` checks stored tensor validity, not logits, semantic quality,
  checksums or transient numeric errors. Repacking-on/off is a CPU test.
- `--device none` does not disable CPU SIMD, dotprod/i8mm or all optimized CPU
  implementations. `--no-repack` is not a scalar/reference execution mode.
- Do not add `--single-turn`, CLI `/clear`, or old `--prompt-cache` options to
  server experiments. Server and CLI flag scopes differ in this version.
- Cache/repack/KV flags above are confirmed in the upstream tag; local help and
  actual logs remain authoritative for the installed package/build.

For a fresh CLI comparison use only its supported flags, not `$base` (which
contains server-only arguments). This has a different system prompt unless you
also supply the same LifeLine instruction via CLI's supported system option.
It is a simple-control test, not full prompt parity:

```powershell
1..5 | ForEach-Object {
  & $cli -m $gguf --offline --device none --n-gpu-layers 0 --no-kv-offload --no-op-offload --check-tensors --no-repack --ctx-size 2048 --parallel 1 --cache-ram 0 --flash-attn off --temp 0 --chat-template chatml --single-turn -n 160 -p 'In English, name three ordinary nonmedical supplies to pack for a day hike.' 2>&1 |
    Tee-Object (Join-Path $run "cli-fresh-$_.log")
}
```

Check CLI `--help` first. Its system-prompt and one-turn flags are not server
flags. Interactive CLI conversations are a separate full-history experiment,
not independent-question evidence. Raw `/completion` also bypasses automatic
chat templating; do not compare untemplated raw text with chat as equivalent.

## Escalation If Configuration Does Not Fix It

1. Same b11680 commit, **native ARM64 CPU-only archive** in its own directory,
   not the WinGet Vulkan directory. Match EXE/DLL bundle; never mix backend DLLs
   across releases/architectures. Repeat B/C against the same hashed GGUF.
2. Compare a separate native ARM64 build with repacking disabled; if rebuilding,
   `GGML_CPU_REPACK=OFF` and `GGML_CPU_KLEIDIAI=OFF` are CMake options, not runtime
   flags. Record compiler and CPU feature dispatch. Do not assume MSVC versus
   LLVM is the answer; the packaged Vulkan ARM64 workflow uses LLVM.
3. If needed, compare x64 CPU execution under emulation as a **separate** control
   with a matching DLL bundle. Expect lower speed; do not infer its architecture
   from Python. Change no other variable in that comparison.
4. Try another official Qwen2.5-3B GGUF quantization such as Q8_0, outside Git.
   Record hash and exact metadata, change only model file, repeat B/C. Q8_0
   coherence with Q4_K_M corruption implicates quantized paths but does not alone
   distinguish a faulty file from a kernel. Larger downloads need approval and
   must happen before the offline demo, never in runtime inference.
5. Compare another pinned build with the **same** GGUF and experiment. No build
   is currently established as known-good for this Dell's repeated requests.
   Revalidate flags for that version. Keep the original package intact and
   avoid an unrecorded rolling update. Report minimal failing logs upstream.

## Reliability Gate And Demo Recommendation

Prefer a persistent server only after the exact chosen configuration gives
coherent results across all prompts and multiple fresh-process sessions. Start
with B (or C if needed); restore thread counts/performance one change at a time.
Before the website demo, run **`--cache default`** on the chosen server, because
the current adapter does not send cache controls. A server launched with
`--no-cache-prompt --cache-ram 0 --cache-reuse 0` applies conservative defaults
without modifying the adapter. Use the unchanged website launch command in
`LLAMA_CPP.md`; retain the 2048 context and chosen diagnostic flags initially.

If only fresh processes are coherent, restarting per independent question is a
diagnostic/temporary execution strategy with load overhead, **not an implemented
website integration** or proof of high throughput. Do not silently deploy it.
Use the already-working PyTorch provider for the demo until a multi-request
llama.cpp configuration passes. If every fresh CPU run corrupts output, do not
use llama.cpp for answers. No automatic runtime fallback or filtering is added.

No finite nonmedical suite certifies medical accuracy. Keep the existing safety
instruction and missing-reference notice unchanged. Archive raw outputs, startup
logs, help/version, file hashes, architecture and human judgments before any
performance tuning or claim of a reliable fix.
