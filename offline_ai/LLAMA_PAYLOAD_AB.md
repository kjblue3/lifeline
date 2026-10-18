# UI Versus LifeLine Payload A/B

No production behavior changes. These diagnostics cannot establish inference
correctness in Linux CoShell; run the real comparisons on the Dell. Keep model,
binary, launch flags and safety instructions unchanged during this investigation.

## What The Adapter Actually Constructs

`offline_ai/llama_adapter.py` currently checks `/health`, then POSTs this shape
directly to `127.0.0.1:8081/v1/chat/completions`, without proxies or redirects:

```json
{
  "model": "lifeline-qwen",
  "messages": [
    {"role": "system", "content": "<unchanged SYSTEM_INSTRUCTION from inference.py>"},
    {"role": "user", "content": "<question passed to provider.answer()>"}
  ],
  "temperature": 0,
  "max_tokens": 160,
  "stream": false
}
```

160 is the default; the running process can override it through
`LIFELINE_LLAMA_MAX_TOKENS`. This is source inspection, not a capture of the
request emitted by the currently running Dell process. An old process can use
old code. The in-progress `chat.py`/`medical_rag.py` integration can also wrap the
browser question in a reference-selection prompt before provider invocation.
When RAG is enabled, browser `{"question":"yo"}` does not establish the actual
provider's user-message content. We did not change this teammates' work.

Compared with the reported UI request, the adapter explicitly changes sampling,
output length, streaming, system prompt and history, and omits the UI's progress,
reasoning, backend-sampling and tools parameters. Missing temperature/token
fields mean **server defaults**, not necessarily temperature 0 or unlimited
generation. Record server defaults/launch arguments, not assumptions.

## Required Capture

The complete known-working UI JSON body has not been supplied to CoShell. Capture
Network -> the successful `/v1/chat/completions` request -> Payload -> source JSON.
Use a harmless nonmedical text question ending in a user turn. Include all
messages and fields verbatim. Do not hand-reconstruct it from the field summary.
Do not copy authentication headers, a whole HAR, or personal medical history.

In PowerShell, after copying the **JSON body only** to the clipboard:

```powershell
$py = (Resolve-Path .\offline_ai\.venv-x64\Scripts\python.exe).Path
$dir = Join-Path $env:TEMP ('lifeline-payload-ab-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $dir -ErrorAction Stop | Out-Null
$ui = Join-Path $dir 'ui-request.json'
Get-Clipboard -Raw | Set-Content -LiteralPath $ui -Encoding UTF8
Get-Content -LiteralPath $ui -Raw | ConvertFrom-Json | Out-Null
```

Do not commit request/result files; they contain the captured conversation.
PowerShell UTF-8 BOM is supported. JSON must be the request object, not a cURL
command, HAR wrapper or quoted JSON string. Multimodal final user turns are
deliberately rejected so image handling does not confound this text experiment.

## Replay And One-Field Controls

Keep the current known-working server running, idle, and close/stop other clients
from making inference calls. These commands only send to numeric loopback.
They never launch a server, download a model, or execute advertised tools.

```powershell
& $py .\offline_ai\compare_llama_payloads.py --ui-request $ui --output (Join-Path $dir 'unused.jsonl') --list

# Replay the complete captured UI payload first, unchanged as a JSON object.
& $py .\offline_ai\compare_llama_payloads.py --ui-request $ui --case ui --review --output (Join-Path $dir '01-ui.jsonl')

# Change ONLY stream:true -> false. Retain progress/reasoning/tools fields.
& $py .\offline_ai\compare_llama_payloads.py --ui-request $ui --case stream-off --review --output (Join-Path $dir '02-stream-off.jsonl')

# Recheck baseline immediately; corruption can depend on process/request sequence.
& $py .\offline_ai\compare_llama_payloads.py --ui-request $ui --case ui --review --output (Join-Path $dir '03-ui-again.jsonl')
```

If the original UI is coherent but exact replay is not, do not proceed as though
the baseline is reproduced. Capture the exact request/response sequence, server
state/logs and effective settings. Headers, hidden UI follow-up requests,
concurrent traffic, sampling randomness and time-dependent state remain possible
differences. This replays the HTTP **body semantically**, not identical browser
headers or original JSON whitespace/byte ordering.

For each following variant, repeat `ui -> variant -> ui`, with new output names:

| Case | Only Change Relative To Captured UI Baseline |
| --- | --- |
| `stream-off` | Set `stream=false`; keep all other fields |
| `system-lifeline` | Replace system messages with the exact LifeLine instruction; retain history and developer messages |
| `temperature-zero` | Set `temperature=0`; preserve all other sampling settings |
| `max-tokens` | Set `max_tokens=160` (or explicit `--max-tokens` matching the Dell adapter) |
| `history-last` | Keep original system/developer messages and last user turn; remove prior conversation |
| `omit-return-progress` | Omit only `return_progress` |
| `omit-sse-ping-interval` | Omit only `sse_ping_interval` |
| `omit-reasoning-format` | Omit only `reasoning_format` |
| `omit-reasoning-control` | Omit only `reasoning_control` |
| `omit-backend-sampling` | Omit only `backend_sampling` |
| `omit-timings-per-token` | Omit only `timings_per_token` |
| `omit-tools` | Omit only `tools`; dependent `tool_choice` may make this an HTTP-error control |
| `adapter` | Reconstruct the current adapter request using the same last question; **multi-variable control**, not one-field A/B |

Example of the priority cases, each interleaved with baseline checks:

```powershell
$sequence = @('ui','system-lifeline','ui','temperature-zero','ui','max-tokens','ui','history-last','ui','adapter','ui')
$i = 10
foreach ($case in $sequence) {
  $name = '{0:D2}-{1}.jsonl' -f $i,$case
  & $py .\offline_ai\compare_llama_payloads.py --ui-request $ui --case $case --review --output (Join-Path $dir $name)
  if ($LASTEXITCODE -ne 0) { throw "Capture failed in $case; inspect raw records before continuing" }
  $i++
}
```

The harness records changed top-level fields before sending; a no-op is visible
as `[]` (for example if a captured field was already omitted). It does not add a
seed, cache controls, stream usage options or a generation limit to the exact UI
baseline. A 180-second capture deadline and 16 MiB cap prevent an unlimited
request from collecting forever. A timeout does not prove model cancellation;
wait for the slot to become idle or restart before the next experiment.

Repeat each suspected difference at least three times and counterbalance order
(`A-B-B-A`, then `B-A-A-B`). Also repeat **each arm as the first request after a
fresh server restart with identical launch flags**. Use the process/provenance
instructions in `LLAMA_CORRUPTION.md`, but do not switch to its different runtime
baseline while attributing a result to a payload field. Record both first and
subsequent outputs. Exact UI requests without a fixed seed can legitimately vary;
after reproducing baseline, a separate both-arms seed control can reduce this
confound, but must not be called an exact baseline replay.

One-field controls may not reveal interactions. Only after individual results,
test the smallest implicated combination, label every changed field and retain
all raw evidence. No configuration is a fix until repeated sessions reproduce it.

## Capture Details And Quality Review

Every received chunk is recorded in base64 before decoding, with elapsed time.
The parser handles fragmented UTF-8, CRLF/LF SSE framing, comments/pings,
multiline data, progress/role chunks, null content, empty `choices` usage chunks,
reasoning, tool deltas, finish reasons and `[DONE]`. Reasoning and tool calls are
kept separate from the displayed-answer reconstruction. They are not invented
or executed. A tool-call-only response is **not** a corrupt English answer:
the UI may execute that tool and send another HTTP request. Capture the entire
sequence if comparing the UI's eventual visible answer, not one intermediate
tool-call response against a completed LifeLine answer.

The full event stream preserves timing/progress/usage metadata even when those
are not in the final summary. Missing usage stays missing; chunks are not counted
as tokens. TTFT is time to first nonempty `delta.content`, not time to headers,
progress, role, reasoning or ping. Nonstreamed TTFT is unknown, not assumed equal
to generation time. Premature EOF or a streamed error is incomplete, never a
successful final answer. Human quality is saved separately after raw evidence,
so interruption during review does not lose the response.

## Smallest Adapter Decision After Evidence

Do not remove `SYSTEM_INSTRUCTION`, copy tools, enable chat-history upload or
drop safety notices simply to imitate the UI. A different system prompt changes
token sequences; coherence with a weaker prompt does not establish a safe fix.

- If explicit `temperature=0` is consistently causal, test one explicit stable
  sampling setting with the unchanged LifeLine prompt rather than blindly
  inheriting unknown server defaults. Zero temperature is not supposed to make
  correct inference become multilingual corruption; numerical defects remain.
- If output limit is causal, separate ordinary truncation (`finish_reason=length`)
  from corrupted tokens before the limit. Make only the verified limit change.
- If upstream streaming is consistently causal with otherwise identical messages,
  an adapter can collect SSE into one final `Answer`, retaining the current API.
  That would **not** display live tokens in the website. Validate with LifeLine's
  safety prompt and default independent-question shape before deployment.
- If only conversation history changes the result, do not upload visible history
  as a silent fix: privacy, stateless semantics, context limits and state reuse
  need review. Investigate runtime correctness using equivalent prompt lengths.
- If both baseline and variant sometimes fail, retain runtime/state debugging;
  there is no demonstrated payload-only fix yet.

## True Browser Streaming: Separate Reviewed Change

At b11680 UI stream/nonstream share task submission and sampling. `stream` changes
delivery and incremental parsing, not a selected precision/kernel. See exact
[UI builder](https://github.com/ggml-org/llama.cpp/blob/b11680/tools/ui/src/lib/services/chat.service.ts),
[server handler](https://github.com/ggml-org/llama.cpp/blob/b11680/tools/server/server-context.cpp),
and [chunk serializer](https://github.com/ggml-org/llama.cpp/blob/b11680/tools/server/server-task.cpp).
Schedule/timing effects remain hypotheses, not proof that these paths are
bit-identical. UI `backend_sampling:false` is also the upstream target default;
reasoning and tools can alter parsing/templates without selecting new kernels.

Actual early token display requires coordinated changes across:

1. A separate incremental provider interface, while preserving `answer()->Answer`.
2. An explicitly negotiated FastAPI streaming response with progress, permitted
   content deltas, validated final `Answer`, terminal error and cancellation.
3. Browser POST `fetch()` + `ReadableStream` decoding, not `response.json()` or
   native EventSource (which cannot carry this JSON POST body). Render plain text,
   mark partial answers incomplete, and show the safety notice before tokens.

Keep `/api/ask` JSON compatible by default; Aryan should approve an opt-in stream
contract before implementation. Check failures before response headers where
possible; failures after headers require an error event, not a new HTTP 503.
Use bounded buffers and explicit cancellation; never re-label a disconnect as
success, or split completed output and call it real generation streaming.

**RAG caveat:** current in-progress `grounded_answer()` asks for source-ID JSON,
validates the completed selection, and returns trusted source text. Raw selector
tokens/reasoning are not safe user-facing guidance. That path should stream
retrieval/selection status followed by the validated source-grounded answer,
not raw model prose. Its validation must not be bypassed for faster display.

No streaming production changes are included in this investigation.
