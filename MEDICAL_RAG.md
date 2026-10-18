# Offline Medical References

## What Is Implemented

The existing `POST /api/ask` can retrieve local references and pass them to the
currently selected `chat.provider.answer(question)`. Neither Qwen adapter, the
model, `app.py`, the public preview, nor the frontend was modified.

This first version is deliberately **extractive RAG, not free-form medical
synthesis**. Qwen receives the question, source titles, source IDs, and whole
source paragraphs. It selects up to two reference IDs as JSON. The backend
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
`medical_rag.py`. The pinned file is the local trust root; checksums establish
integrity relative to this installation, not a publisher signature or clinical
review. Changing content requires inspecting a newly obtained official snapshot
and deliberately updating that pin. A hostname or `official_summary` flag alone
is never sufficient to admit a database row.

The installer creates **a new database**, `lifeline_medical_installed.db`, using
SQLite backup plus ten exact-title updates. It never overwrites an existing
output, substitutes titles, modifies the original, or changes legacy reports.
The installed copy has 10 populated official summaries and 90 catalog-only rows.

The ten topics are Bleeding, Burns, Choking, Poisoning, Heat Illness, Hypothermia,
Frostbite, Dehydration, Sprains and Strains, and Wounds and Injuries. These are
source-extracted topic overviews, **not ten clinically reviewed, complete
first-aid protocols**. MedlinePlus is the source; no Red Cross verification is
claimed. Some topics include US-specific service numbers. The answer notice
warns that these may not apply outside the US.

## Dell Setup

1. Back up the Dell's existing `chat.py` before merging this update. Bring over
   only the backend additions listed below, the small `chat.py` change, and
   the `medical_data/` folder. Do not replace Kiran's model adapters, startup
   commands, virtual environments, or `app.py`. If Dell `chat.py` has additional
   changes, merge the RAG import, optional library, status count, and ask branch
   rather than replacing it wholesale.
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
the installer intentionally refuses to overwrite it: verify it with the second
command and keep it if correct. Back up and move aside an incompatible generated
copy before explicitly reinstalling; do not delete/replace the original catalog.

4. Keep the working model server unchanged. Stop only the existing FastAPI
   process when ready to restart it, set the following in **its terminal**, then
   rerun **Kiran's same successful startup command** on the same port:

```powershell
$env:LIFELINE_RAG = '1'
# Rerun the EXISTING working FastAPI startup command here, unchanged.
```

For example, if the existing command uses `offline_ai.llama_adapter:app`, keep
that module, all current model environment variables, and the same port. If it
uses `offline_ai.qwen_adapter:app`, keep that instead. Do not start both. The
adapter still selects the provider in exactly the same way after importing
`chat`; no wrapping/replacement of its engine or private methods is performed.

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
unsupported phrases even when a supported topic is also mentioned. It does not
infer negation. A match is not evidence that a medical procedure is appropriate.

Prompts include at most two original first paragraphs and have a conservative
2400 UTF-8-byte budget, leaving space in the existing 4096-token server for the
unchanged system prompt, template, and output. Full selected topics are returned
after selection, so clinical source text is never arbitrarily cut for display.
Actual tokenizer behavior and selection quality still require Dell testing.

No network, cloud API, embedding API, new runtime dependency, startup process,
or extra port is used by retrieval. The temporary public website remains
frontend-only and is intentionally not connected to this medical API/model.

## Tests And File List

```powershell
& $python -B -m unittest -v test_medical_rag test_chat test_llama_adapter
```

The 25 medical tests block sockets and DNS. They cover ten real topic searches,
aliases, singular burn queries, unsupported mixed requests, FTS fallback,
read-only/missing DB behavior, source integrity, fake citation rejection,
bounded context, installer no-overwrite, and API shapes. Model outputs in tests
are explicitly labeled fixtures, not live Qwen generations. Existing adapter
tests use mock loopback responses; no actual Dell model is run by these tests.

Only existing project code changed: `chat.py`.

New backend/data files: `medical_rag.py`, `test_medical_rag.py`, this document,
`medical_data/install_references.py`, `medical_data/official_first_aid.json`,
and generated `medical_data/lifeline_medical_installed.db`, plus the five original
files imported unchanged from GitHub. Preserve the imported originals.

Pre-edit copies of `chat.py`, `app.py`, `inference.py`, and the original reference
database are under `backups/medical-rag-20261018/` in the development workspace,
not in the integration commit. Git delivery includes only the RAG changes and
required reference files. No reset, frontend edit, inference-file edit,
database-report migration, or service restart was performed for this integration.
