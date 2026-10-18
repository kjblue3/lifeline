# Voice, Guidance, And Library

## Current Standalone Library

The First-Aid Library now loads `web/official_first_aid.json` directly as a
bundled static asset. This is an exact copy of the existing
`medical_data/official_first_aid.json`: ten populated MedlinePlus summaries,
not the other 90 catalog-only entries. No medical text is generated or rewritten.
Source credits embedded in the summaries, original URLs, IDs and provenance
are retained. Missing detailed first-aid sections are not invented.

Open `http://localhost:8000/#library` for the running website. Search includes
titles and the full summary text; categories and A-Z filters run locally.
Backend reference readiness no longer controls this standalone collection.
These are medical information summaries, not complete first-aid protocols or
clinically reviewed LifeLine guidance. Source phone numbers may be US-specific.

For installed-app offline refresh, open `/assets/index.html#library` once while
the local server is available and let offline setup complete. The existing
service worker caches the local JSON alongside the app shell. Its scope does
not include `/`; use the installed entry for refreshing with the network fully
disabled. No Python, model or API is needed to render the cached library.
`python library_check.py` verifies all ten displayed summaries byte-for-byte
against the served JSON, every topic page, search, A-Z, categories, responsive
widths, blocked backend APIs, and true browser-offline refresh. Original-source
links still need internet. Re-export/revalidate this copy if the medical source
snapshot changes. The historical backend-dependent library details below have
been superseded by this static collection.

These changes extend the existing vanilla frontend. No FastAPI, SQLite, model,
or ExecuTorch files were changed. The interface retains dark green/white styling,
Chat, Get Prepared, Medical Profile, demo account forms, and Emergency Help.
Internet-based background switching is disabled; the UI stays neutral.

## Current Capabilities

Get Prepared now places a single conversational trip-description input above
the supply checklist. Environment cards and separate activity/duration fields
have been removed. Until a local preparedness conversation adapter is connected,
submissions are explicitly labeled session-only trip notes, not AI messages.
They make no network requests, generate no follow-up questions, and do not
personalize the checklist. Notes clear on reload; saved checklist IDs still
restore. A future adapter must support conversation context and verified supply
selection before AI follow-up questions can be enabled. The medical `/api/ask`
endpoint is not repurposed for this unimplemented planning contract.

| Feature | Implemented | Not Yet Connected |
| --- | --- | --- |
| Response display | Actual answer text, paragraphs and existing numbering; safe source links; source-gated structured warning/step components | Backend generation of verified structured steps |
| First-Aid Library | Navigation, readiness states, local search/filter, cards, article/back view, source/warning/date display | Actual completed medical records and reference retrieval endpoint |
| Voice | Microphone dialog, gated permission/record/stop controller, automatic draft insertion for editing, cancellation cleanup | Genuine local speech recognition and confirmed transcription endpoint |

There are no sample medical articles, diagnoses, or treatment steps. The bundled
NPS packing checklist remains separate from the medical library. An indexed
topic count is not treated as proof of complete readable medical content.

## Existing API

`GET /api/status` and `POST /api/ask` are unchanged. Chat still sends only
`{question}`; no profile, transcript history, or recording is added. Existing
loading/progress UI, local-CPU timeout, actual error messages, retained drafts,
and manual retry remain. A 503 never creates an assistant answer.

`LifeLineLibrary.updateStatus(data)` reads `references.installed` and `count`.
Uninstalled status says **First-aid library is not installed yet**. Installed
status reports the actual indexed count and explains that browsing is not yet
connected. Failed status checks clear readiness claims. AI readiness is independent
of browsing, and missing AI does not disable local library controls.

## Proposed Structured Guidance Contract

Aryan can extend the existing answer envelope without changing `answer`, `mode`,
or `sources`. The renderer does not parse prose into medical instructions.

```json
{
  "answer": "Actual backend answer text",
  "mode": "local",
  "simulated": false,
  "heading": "Optional backend-supplied heading",
  "steps": [
    {
      "number": 1,
      "instruction": "Actual verified reference instruction, not a UI placeholder",
      "verified": true,
      "source_ids": ["installed-reference-id"]
    }
  ],
  "warnings": [
    {
      "text": "Actual verified reference warning",
      "verified": true,
      "source_ids": ["installed-reference-id"]
    }
  ],
  "sources": [
    {
      "id": "installed-reference-id",
      "title": "Actual reference title",
      "url": "https://example.org/original-reference",
      "verified": true,
      "locally_available": true
    }
  ]
}
```

This is a proposed schema, **not real content or an implemented backend response**.
Only steps/warnings explicitly marked verified and linked to returned verified,
locally available source IDs render as structured guidance. Warnings appear before
the main answer. Steps use accessible disclosure controls with the first open;
numbers come from the backend, not inferred ordering of treatments. All content
uses plain DOM text, not HTML. Existing unstructured answers and optional text
sections still render unchanged; the UI cannot independently medically verify them.
When no sources are returned, an explicit reference limitation is displayed.

## Proposed Library Contract

No browsing endpoint was found. `web/api.js` declares reference endpoints as
null and capabilities false. No guessed route is requested. Aryan can provide
local-only `GET /api/references` and `GET /api/references/{id}` (proposals) or a
bundled, reviewed corpus. Search should operate on locally completed records,
not use inference or external search. Permissions to reproduce source content
must be settled before distributing articles.

`LifeLineLibrary.setRecords(records)` accepts this proposed shape:

```text
{title,content,category?,completed:true,verified:true,locally_available:true,
 source:{title,organisation,url},warnings?:string[],
 published?:string,updated?:string,reviewed?:string}
```

Records missing complete local content, verification flags, or valid source
metadata are excluded. URLs must be HTTP(S), with no embedded credentials.
The current adapter requires a valid source URL. Optional dates are shown only
when supplied. Search and category filtering run in browser memory, independently
of AI. No records are supplied by default. The library does not persist/copy API
responses into the offline cache; adding real downloadable records requires an
explicit backend storage and readiness contract.

## Voice Contract And Privacy

Opening the microphone panel currently says **Offline voice input is not ready
yet**. Start is disabled; it does not request microphone permission, record,
simulate transcription, or call browser speech recognition. Typing still works.

After a genuine offline engine is tested on the Dell, configure:

```js
LifeLineVoice.configure({
  localOnly: true,
  ready: true,
  transcribe: async (audioBlob) => {
    // Implement only against the team's confirmed local speech adapter.
    // Return { text: actualTranscript }; never use a cloud fallback.
  }
});
```

`LifeLineAPI.transcribe()` currently rejects without making any request. Aryan
must agree on a local audio endpoint, MIME/container support, size/duration limits,
permission/privacy policy, readiness, timeout/cancellation behavior, and `{text}`
response. Whisper.cpp/Vosk availability is not claimed or installed here.

With an explicitly configured adapter, clicking the microphone requests access
and starts recording. It records at most 60 seconds using MediaRecorder and exposes Stop and
Cancel. Audio stays in memory until passed to that adapter, not browser storage.
Closing, navigating, or page hiding releases tracks and discards pending results.
Late permission grants after cancellation immediately release their tracks.
Denied/unavailable devices give typing-friendly errors.

A completed transcript automatically appends to the current draft, closes the
voice dialog, and focuses the editable input without sending. It preserves edits
made while transcription runs. If the input is busy or the combined text exceeds
the limit, the dialog retains the transcript and offers manual **Insert into chat**
after the user resolves the issue. No text is silently truncated or overwritten.
Sending is blocked while capture/transcription is active. No smartphone-local
AI or speech capability is implied.

## Offline Testing

Start the existing server on the Dell as documented in `FRONTEND.md`, then open
http://127.0.0.1:8000/. Disconnect Wi-Fi while keeping the local server running.

1. Open First-Aid Library. With current backend metadata, expect an explicit uninstalled/not-connected state, not fabricated topics. Emergency Help opens the library too.
2. Open the microphone panel. Expect unavailable transcription and disabled Start. Type normally afterwards.
3. Ask a fictional question. Actual AI output depends on Kiran's adapter. Until it works, verify the actual error and Retry without losing messages.
4. After verified references and structured generation are connected, test actual source-backed steps, warnings, local search, and readable article content without Wi-Fi.

The PWA entry is `/assets/index.html`, within the existing worker scope. New
scripts are precached by `lifeline-shell-v7`, and missing PNG references were
corrected to the existing SVG icon. Close other installed-app windows so an
updated worker can activate before testing offline reopen. Cache installation
must finish while the local server is reachable. API responses, recordings,
profiles, and medical articles are not cached by this worker. Cached UI does not
make backend AI available. Native-device install UI is not validated by these tests.

## Automated Checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe feature_check.py localhost8000
.\.venv\Scripts\python.exe preparedness_check.py http://localhost:8000
```

The new feature suite intercepts every API request. Successful answers, articles,
steps, and voice adapters use explicitly nonmedical TEST fixtures. It does not
run live inference or demonstrate medical correctness. Chromium fake-device
audio verifies capture into a Blob and cleanup, not an actual microphone or
speech recognition. Real Dell microphone permissions, Windows ARM64 capture,
and genuine offline transcription remain hardware-integration tests.

Verified: local search/filter/detail, invalid-record rejection, plain text and
safe citations, source-gated steps, permission denial and close races, cancellation,
automatic draft insertion without sending, four-section navigation, profile/demo accounts,
emergency shortcut, widths 320/390/768/1440, reduced motion, fresh PWA installation,
offline reopen/reload and checklist controls, and no cached APIs.

Screenshots: `artifacts/lifeline-library.png`, `artifacts/lifeline-voice.png`,
and `artifacts/lifeline-steps-fixture.png` (explicit nonmedical rendering fixture).
