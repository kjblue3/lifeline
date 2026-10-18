# LifeLine — Intelligence Without Interruption

**Offline-first emergency information prototype** for the Qualcomm ExecuTorch Hackathon 2026.

## Start here: [JUDGES_QUICKSTART.md](JUDGES_QUICKSTART.md)

**Judges:** Follow the [complete Windows Snapdragon installation, download and verification instructions](JUDGES_QUICKSTART.md) for this **`feature/executorch-classifier`** branch. Do **not** run `uvicorn app:app` to test offline AI; start the Qwen llama.cpp model server and then `uvicorn offline_ai.llama_adapter:app` as documented in the quickstart.

### Working architecture

- **Main conversational model:** Qwen2.5-3B-Instruct GGUF Q4_K_M (download separately), served entirely on localhost by **llama.cpp**, port 8081.
- **Emergency category classifier:** a real, included **ExecuTorch `.pte`** model, with CPU runtime and metadata, in `offline_ai/`.
- **Application:** FastAPI plus local browser frontend on `127.0.0.1:8000`, communicating only with the local model server for inference.
- **Local medical-reference summaries:** bundled `medical_data/official_first_aid.json` and browser-readable `web/official_first_aid.json`; generated SQLite installation must be created locally.
- **Preparedness:** bundled offline checklist; AI-personalized trip checklists are not proven implemented in this submission.

**Offline after installation:** The initial setup requires internet to obtain Python dependencies, llama.cpp and the approximately 2.1 GB Qwen GGUF. These downloads are **not included in Git**. Once installed, the demonstration operates without internet. We verified offline Qwen generation on the team's Windows 11 ARM64 Snapdragon X Elite Dell; we have **not** completed a clean-install test on arbitrary judge hardware.

**Hardware clarification:** The Dell contains a Qualcomm Hexagon NPU, but verified inference is **CPU-based**; this submission does not claim NPU acceleration. Qwen is served by llama.cpp, **not** ExecuTorch. The ExecuTorch model performs classification, not language generation.

**Safety:** This is a research/hackathon prototype, not medical diagnosis or emergency dispatch. Generated text is not guaranteed correct or source-verified. For immediate danger contact local emergency services. Use fictional scenarios when testing. Do not expose the unauthenticated localhost service to a public network.

### Verify

With the two servers running according to [JUDGES_QUICKSTART.md](JUDGES_QUICKSTART.md):

```powershell
Invoke-RestMethod http://127.0.0.1:8081/health
Invoke-RestMethod http://127.0.0.1:8000/api/status
Invoke-RestMethod http://127.0.0.1:8000/api/ask -Method POST -ContentType 'application/json' -Body '{"question":"Tell me a short joke."}'
```

The AI-generated answer should report `mode=local` and `simulated=false`. Test the ExecuTorch classifier independently with the command in the quickstart. Disconnect Wi-Fi **after installing dependencies** and repeat with a fresh prompt to verify local inference.

### Key source files

`offline_ai/llama_adapter.py`, `offline_ai/executorch_classifier.py`, `offline_ai/emergency_classifier.pte`, `offline_ai/emergency_classifier_meta.json`, `offline_ai/qwen_context.py`, `offline_ai/reference_context.py`, `medical_rag.py`, `web/`.

More background: [offline_ai/LLAMA_CPP.md](offline_ai/LLAMA_CPP.md), and the documentation in the repo. Older files and branches may discuss experimental cloud or alternate model integrations; **this branch's judge quickstart defines the submitted offline pipeline**.
