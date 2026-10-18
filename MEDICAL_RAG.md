# Offline Medical References

## Merged Baseline And Runtime

Verified `origin/main` merge `e2880a8` against the shared checkout: the tracked
trees matched, all required RAG files were present, and the index contained no
unmerged entries. No branch switch, merge, reset or cherry-pick was performed.

Use the existing **Qwen2.5-3B-Instruct Q4_K_M / llama.cpp b11490 Windows ARM64 CPU**
pipeline, port 8081 for inference and 8000 for the existing website/API. No model,
system instruction, frontend contract or runtime binary is changed here. The
complete live Dell RAG acceptance run remains required; local fixtures are not
proof that the real Qwen selector follows the JSON contract or selects well.

## What Is Implemented

The existing `POST /api/ask` can retrieve local references and pass them to the
currently selected `chat.provider.answer(question)`. Neither Qwen adapter, the
model, `app.py`, the public preview, nor the frontend was modified.

This first version is deliberately **extractive RAG, not free-form medical
synthesis**. Qwen receives the original trimmed question, source titles, source
IDs, and up to two complete source summaries as indivisible passages. It selects
up to two reference IDs as JSON. The backend
validates that those IDs were actually supplied, then displays the complete
original topic text and source links. Model-written medical prose and citations
are never published. This prevents invented treatments from escaping through
this path; it does not prove that the model selected an appropriate reference.

The existing engine's safety prompt and generation settings remain unchanged.
Whether the real Dell Qwen follows the selector JSON format still needs testing.
Noncompliant output fails closed with HTTP 503 instead of fabricated guidance.

## Data Audit And Provenance

The five original `medical_data/` files were imported from GitHub `origin/main`
without checking out/resetting shared files. The original SQLite database has
100 `catalog_only` entries, all with empty summaries. The three emergency cards
are marked `source_checked_demo_note`; they are not used for retrieval.

The originals remain unchanged:

- `medical_data/README.md`
- `medical_data/db.py`
- `medical_data/seed_data.py`
- `medical_data/refresh_medlineplus.py`
- `medical_data/lifeline_medical.db`

`official_first_aid.json` contains actual health-topic summaries extracted using
the supplied refresh helper from the official MedlinePlus XML feed:

`https://medlineplus.gov/xml/mplus_topics_compressed_2026-10-17.zip`

The snapshot retains topic IDs, URLs, source markup, extracted text, feed date,
import UTC, and checksums. Its canonical digest is independently pinned in
`medical_data/install_references.py`, shared by runtime and installer. The pinned
file is the local trust root; checksums establish
integrity relative to this installation, not a publisher signature or clinical
review. Changing content requires inspecting a newly obtained official snapshot
and deliberately updating that pin. A hostname or `official_summary` flag alone
is never sufficient to admit a database row.

The installer creates **a new database**, `lifeline_medical_installed.db`, using
SQLite backup plus ten exact-title updates. It never overwrites an existing
output, substitutes titles, modifies the original, or changes legacy reports.
The installed copy has 10 populated official summaries and 90 catalog-only rows.
The installer independently pins the committed catalog SHA256 before copying
its schema/triggers. It rejects malformed JSON, duplicate keys, altered or
unapproved snapshots, untrusted URLs and invalid types/dates before creating
output. FTS5 is required for installation; retrieval alone has a lexical fallback.

Generated `cases` metadata distinguishes `feed_generated_at` (feed build time),
`source_created_date` (source topic creation), and `imported_at` (snapshot import).
`published_date` stays empty: no clinical publication/review date is established.
**Older generated databases must be backed up and regenerated** to correct this
metadata. They fail closed rather than silently treating a feed date as clinical
publication. No migration overwrites the committed catalog or existing output.
Generated schema version **2** is recorded in SQLite `PRAGMA user_version`.
The offline `--check` command verifies that version, all ten exact passage/source
and date records, counts, and integrity. Ten rows alone do not prove currency.

The ten topics are Bleeding, Burns, Choking, Poisoning, Heat Illness, Hypothermia,
Frostbite, Dehydration, Sprains and Strains, and Wounds and Injuries. These are
source-extracted topic overviews, **not ten clinically reviewed, complete
first-aid protocols**. MedlinePlus is the source; no Red Cross verification is
claimed. Some topics include US-specific service numbers. The answer notice
warns that these may not apply outside the US.

## Dell Setup

1. Use the reviewed merged project files. Stop the existing FastAPI process
   before replacing its generated reference database. Do not perform another
   merge or replace model adapters, runtime binaries, environments or `app.py`.
2. Ensure `medical_data/lifeline_medical.db` and `official_first_aid.json` are
   present. The integration branch explicitly includes the original reference
   database despite the general SQLite Git-ignore rule. The installed database
   is intentionally not committed: generate it offline using the installer.
   Never copy `lastline.db` or private report/profile data for this integration.
3. From the project root, use the same Python environment as the working backend:

```powershell
$python = '.\offline_ai\.venv-x64\Scripts\python.exe'
# Change only this path if the working application uses a different environment.
& $python -B medical_data/install_references.py
& $python -B -c "from medical_rag import MedicalLibrary; l=MedicalLibrary(); print('Reference topics:', l.count()); print([(r['title'],r['source_url']) for r in l.search('twisted ankle')])"
```

Expected: 10 reference topics and a Sprains and Strains source. The default
installer does not access the internet. If the installed DB already exists,
the installer intentionally refuses to overwrite it: run
`& $python -B medical_data/install_references.py --check` and keep it only when
that exits successfully. Back up and move aside an incompatible generated
copy before explicitly reinstalling; do not delete/replace the original catalog.

For an old generated DB from the previous date schema, use this safe setup
sequence. Only the generated copy can be moved; the committed catalog hash is
checked before/after:

```powershell
$python = '.\offline_ai\.venv-x64\Scripts\python.exe'
$catalog = '.\medical_data\lifeline_medical.db'
$generated = '.\medical_data\lifeline_medical_installed.db'
$before = (Get-FileHash -LiteralPath $catalog -Algorithm SHA256).Hash
if (Test-Path -LiteralPath $generated) {
  & $python -B medical_data/install_references.py --check
  if ($LASTEXITCODE -ne 0) {
    Move-Item -LiteralPath $generated -Destination ($generated + '.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) -ErrorAction Stop
  }
}
if (!(Test-Path -LiteralPath $generated)) {
  & $python -B medical_data/install_references.py
  if ($LASTEXITCODE -ne 0) { throw 'Offline reference installation failed' }
}
if ((Get-FileHash -LiteralPath $catalog -Algorithm SHA256).Hash -ne $before) { throw 'Catalog changed unexpectedly' }
& $python -B medical_data/install_references.py --check
if ($LASTEXITCODE -ne 0) { throw 'Installed schema/content verification failed' }
& $python -B -c "from medical_rag import MedicalLibrary; l=MedicalLibrary(); print('Trusted topics:',l.count()); print([r['title'] for r in l.search('I rolled my ankle')]); assert l.count()==10"
```

For an interrupted install, stop FastAPI, back up/move only the partial generated
file, then reinstall. Do not use `refresh_medlineplus.py` or `--download` for
offline setup: those are separate network/content-update workflows.

On macOS, use the working backend's Python environment. The installer uses only
standard-library Python/SQLite with FTS5, not ARM-specific native packages:

```bash
python3 -B medical_data/install_references.py
python3 -B medical_data/install_references.py --check
python3 -B -c "from medical_rag import MedicalLibrary; assert MedicalLibrary().count() == 10"
export LIFELINE_RAG=1
```

Apply the same generated-file backup rule if output already exists. Windows and
macOS execution must be confirmed on those machines, not inferred from Linux tests.

4. Keep the working model server unchanged. Stop only the existing FastAPI
   process when ready to restart it, set the following in **its terminal**, then
   rerun **Kiran's same successful startup command** on the same port:

```powershell
$env:LIFELINE_RAG = '1'
$env:LIFELINE_GGUF_PATH = 'C:\REPLACE\actual-qwen2.5-3b-instruct-q4_k_m.gguf'
$env:LIFELINE_LLAMA_PORT = '8081'
& $python -m uvicorn offline_ai.llama_adapter:app --host 127.0.0.1 --port 8000 --workers 1
```

For example, if the existing command uses `offline_ai.llama_adapter:app`, keep
that module, all current model environment variables, and the same port. If it
uses `offline_ai.qwen_adapter:app`, keep that instead. Do not start both. The
adapter still selects the provider in exactly the same way after importing
`chat`; no wrapping/replacement of its engine or private methods is performed.

Keep the existing validated b11490 CPU-only model server running in its own
terminal. Reuse the exact command/settings that passed on the Dell. The example
below uses the existing 4096-context setup; check the selected b11490 binary's
help rather than copying b11680 investigation options:

```powershell
$server = 'C:\REPLACE\b11490-cpu-arm64\llama-server.exe'
$gguf = 'C:\REPLACE\actual-qwen2.5-3b-instruct-q4_k_m.gguf'
& $server --version
& $server -m $gguf --host 127.0.0.1 --port 8081 --alias lifeline-qwen --n-gpu-layers 0 --device none --no-kv-offload --no-op-offload --temp 0 --chat-template chatml --check-tensors --ctx-size 4096 --parallel 1 --offline
```

Do not start duplicate listeners. Open **http://127.0.0.1:8000/** and leave both
server terminals running.

5. Test the existing routes:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status
$body = @{question='My hiking partner twisted an ankle. What reference information is available?'} | ConvertTo-Json
$reply = Invoke-RestMethod http://127.0.0.1:8000/api/ask -Method Post -ContentType 'application/json' -Body $body
$reply.data.answer
$reply.data.sources | Format-Table title,url
```

If the working app uses a different port, keep that port in the test URLs.
Expect reference status `{installed:true,count:10}`. Model readiness remains
the adapter's own reported state; a first request may load the model.
`offline_ready` intentionally remains false: a ten-topic overview library does
not establish complete emergency-system readiness or medical validation.

6. Repeat with Wi-Fi disconnected. Open the locally served website and verify
   actual source links appear with the answer. Links identify the source but
   opening the original external website requires internet; the source text
   itself is installed locally. Confirm the displayed medical text is exactly
   the selected stored summary, not generated treatment instructions.
7. Ask about `cardiac arrest` or an unrelated unsupported condition. Expect a
   clear reference-unavailable error, no model call and no medical answer.
   Ask several supported topics and verify the real model returns valid source
   selections. If it emits prose, markdown fences, unknown IDs, or an empty
   selection, expect a structured 503 `medical_grounding_failed`. Do not bypass
   this check to make a demo appear successful.

To restore the original provider-only flow without reverting anyone's code,
remove the opt-in and restart the same backend:

```powershell
Remove-Item Env:LIFELINE_RAG -ErrorAction SilentlyContinue
```

Provider-only behavior is the pre-existing ungrounded flow; it must not be
described as reference-backed. Do not use it to demonstrate grounded guidance.

## API Compatibility And Limits

No routes or successful response fields were removed or renamed. The frontend
still sends only `{question}`. Success remains `{ok:true,data:{id,answer,
mode:"local",simulated:false,sources:[{title,url}],notice}}`.

In RAG mode, `answer` is labeled original reference information, and `notice`
explains that Qwen selected references rather than synthesizing treatments.
Sources come only from selected installed records, never model-provided URLs.

- HTTP 503 `medical_reference_not_found`: missing/untrusted library, no supported
  lexical match, ambiguous/unsupported catalog match, or context cannot fit.
- HTTP 503 `medical_grounding_failed`: unsafe or invalid model selection.
- HTTP 422 `medical_question_too_long`: shorten the question to the reference
  selector's 1200 UTF-8-byte limit. The external 2000-character question schema
  remains unchanged; this is an additional model-context limit in RAG mode.
- Existing provider errors retain their original codes and statuses.

Search uses local SQLite FTS5 and deterministic title/alias evidence, with an
offline lexical fallback for Python builds lacking FTS5. It is not semantic
search, diagnosis, triage, or an exhaustive detector of unsupported conditions.
It abstains on explicit unsupported catalog conditions and several serious
unsupported phrases even when a supported topic is also mentioned. A match is
reference navigation, not evidence that a medical procedure is appropriate.

Reviewed phrases are in `medical_rag.ALIASES`, not written over the catalog.
They expand to canonical titles before FTS5 retrieval. Exact candidate membership
and pinned provenance are enforced after FTS stemming too. Shared body parts and
incidental words alone cannot select a topic:

| Question | Retrieval |
| --- | --- |
| I twisted my ankle / I rolled my ankle | Sprains and Strains |
| I'm freezing and shivering | Hypothermia information, not a diagnosis |
| I'm dehydrated | Dehydration |
| I broke my arm | Limitation; Fractures is catalog-only, never Stroke |
| help / no chest pain / dizzy and weak | Limitation; no inferred condition |

Negation scope is not solved by this small lexical system: it abstains on the
entire question when negation is detected, even if a positive symptom appears
elsewhere. Resource/persistence phrases `no water` and `cannot stop bleeding`
are exceptions, not diagnoses. Nonspecific clusters involving confusion,
weakness/dizziness also abstain rather than becoming dehydration or stroke.
Explicit unsupported titles, suspected fractures, conflicting heat/cold cues
and more than two matched concerns fail closed. These finite rules cannot
recognize every emergency, negation, synonym or hypothetical statement; false
negatives remain possible. Emergency escalation always remains visible.

Prompts include at most two **complete summaries**, never just an introductory
first paragraph. This preserves symptom sections, populations, warnings,
conditions and negative instructions together. The target is approximately
600-900 passage tokens (roughly four English characters/token); safety
qualifications take priority over that soft target. Dehydration + Heat Illness
exceeds it deliberately, rather than dropping warnings or a matched concern.
An absolute 10,000 UTF-8-byte selector ceiling fails closed without truncation.
This is not a tokenizer guarantee: inspect actual usage and configured context
on the Dell. Full selected topics are returned unchanged for display. Alias
expansion never rewrites the original question passed to the selector.

No network, cloud API, embedding API, new runtime dependency, startup process,
or extra port is used by retrieval. The temporary public website remains
frontend-only and is intentionally not connected to this medical API/model.

## Tests And File List

```powershell
& $python -B -m unittest -v test_medical_rag test_chat test_llama_adapter
```

The offline medical tests block sockets and DNS. They cover ten real topic searches,
aliases, singular burn queries, unsupported mixed requests, FTS fallback,
read-only/missing DB behavior, source integrity, fake citation rejection,
bounded context, installer no-overwrite, and API shapes. Model outputs in tests
are explicitly labeled fixtures, not live Qwen generations. Existing adapter
tests use mock loopback responses; no actual Dell model is run by these tests.

The browser regression in this same module serves the existing FastAPI app/UI
with an explicitly labeled selector fixture. It checks question preservation,
complete source text/URL/notice rendering, discarded model citations, and retained
drafts for unsupported questions. Writable DB fixtures are generated in temporary
directories: a clean clone needs no ignored preinstalled database. The browser
check uses the existing Playwright development setup, not a production dependency.

## Live Dell Acceptance And Performance

With both real services running and no other client issuing questions:

```powershell
$results = Join-Path $env:TEMP ('lifeline-rag-live-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.jsonl')
& $python -B test_medical_rag.py --live --output $results
```

This opt-in mode extends the same tests, calling the existing `grounded_answer`
and llama provider, then the real `/api/ask`. It exercises all ten titles, four
natural aliases and five unsupported/ambiguous cases. It requires source URLs
and titles to match retrieved pinned rows, and final text to equal the stored
summaries plus the standard wrapper. Unsupported cases must return structured
503 limitations. Raw selector choices, full request, actual `usage`/`timings`,
retrieval median/max, direct RAG time and API wall time are recorded locally.
No timing fields or new routes are added to the production API.

`usage.prompt_tokens` is actual input-token count when reported.
`timings.prompt_ms`/`predicted_ms` and throughput fields are server-reported when
available; absent metrics stay unknown. If JSON omits timings, retain the model
server's request console logs for prompt-evaluation timing. The test subclass
only observes the existing transport; it does not change payload or sampling.
CLI ~40 output tokens/s is not total RAG or prefill latency.

The API buffers final JSON. Token TTFT/first visible browser content is not
measured by this live CLI and is not interchangeable with decode time. Use
browser Network Timing for request duration and observe final assistant-message
insertion. Selector tokens are IDs, not user-facing medical guidance; streaming
them must not bypass completed selection/provenance validation.

Human relevance review is still required. A valid ID does not establish clinical
appropriateness. Repeat after fresh restarts, then with Wi-Fi disconnected.
Opening external source links needs internet; reading installed passages does not.

For a real missing-reference gate, stop only FastAPI, move the **generated**
installed DB to a uniquely named backup, restart with RAG enabled and ask a
supported topic. Expect reference count 0 and HTTP 503 with no medical text.
Stop FastAPI and restore that generated copy afterwards. Never move or alter
the committed catalog. Unit tests cover this without touching a real installation;
the live helper never moves production files.

No live Dell server/model is accessible from CoShell. Fixture success is not
full model validation. Demo readiness remains conditional on live selector,
browser citations, missing-reference and Wi-Fi-off checks. Ten overviews do not
constitute a complete or clinically validated emergency system; `offline_ready`
remains false.

Development-only benchmark on Linux CoShell (50 searches per question, temporary
freshly installed DB, no model): supported ankle/cold/dehydration retrieval had
median latency **1.02-1.15 ms**, p95 **1.20-1.86 ms**. Unsupported/negated early
abstention was below 0.01 ms; generic `help` had median 0.086 ms. These exclude
snapshot/library construction and are not Dell or model-performance results.

Current finishing changes are confined to `medical_rag.py`,
`medical_data/install_references.py`, `test_medical_rag.py`, and setup documentation.
The committed catalog, snapshot medical text, frontend, `chat.py`, `app.py`,
`inference.py`, Qwen adapter, model and runtime remain unchanged. Generated DBs,
backups, model weights and virtual environments must remain outside commits.
