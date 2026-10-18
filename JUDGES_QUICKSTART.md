# LifeLine — Judges' offline AI quickstart

**Submission branch:** `feature/executorch-classifier`. The old `main` branch does **not** represent the working Dell AI setup. Clone or download this branch explicitly.

**What works:** LifeLine serves a browser UI and FastAPI on `127.0.0.1:8000`. Qwen2.5-3B-Instruct (Q4_K_M GGUF) generates local responses through a separate llama.cpp server on `127.0.0.1:8081`. An optional ExecuTorch 1.5.1 CPU classifier (`offline_ai/emergency_classifier.pte`) classifies emergency topics and can help prioritize pinned medical-reference context. **Qwen itself does not run inside ExecuTorch.** Neither inference path has verified NPU execution.

**Platform tested by the team:** Dell Latitude 7455, Windows 11 ARM64, Snapdragon X Elite. The llama.cpp executable is **Windows ARM64**. The ExecuTorch Python wheel is **Windows x64**, so the Dell uses **x64 Python under Windows emulation** for the FastAPI/ExecuTorch environment. Other operating systems and hardware require their corresponding native llama.cpp binaries and compatible Python wheels; a complete clean-machine install on every judge laptop has **not** been independently validated.

**Downloads happen during initial installation.** Once packages, weights and binary are installed, both AI servers use localhost; inference does not require internet. Do not download packages while performing the offline demo.

## 1. Clone the correct branch

In **Windows PowerShell** (with Git and Python 3.11 x64 installed):

```powershell
git clone --branch feature/executorch-classifier --single-branch https://github.com/kjblue3/lifeline.git
cd lifeline
```

If this repository is still private, you must be granted access by the team before cloning.

## 2. Create the Python environment

Use the **64-bit x86-64 Python 3.11 interpreter** on Windows, including Windows ARM64 devices. PyPI provides ExecuTorch 1.5.1 `win_amd64` wheels, not native Windows ARM64 wheels. Windows on ARM supports x64 emulation, but your system must support it.

```powershell
py -3.11-64 -m venv offline_ai\.venv-x64
$python = '.\offline_ai\.venv-x64\Scripts\python.exe'
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt
& $python -m pip install torch executorch==1.5.1
& $python -c "import sys,platform,torch,executorch; print(sys.version); print(platform.machine()); print('torch:',torch.__version__); print('ExecuTorch imports OK')"
```

Installation requires internet. The project intentionally does not vendor a virtual environment or runtime packages. If `py -3.11-64` is unavailable, install **Python 3.11 x64** before continuing; do not silently switch to native ARM64 Python for the ExecuTorch runtime.

The compiled `.pte` model and `emergency_classifier_meta.json` **are included** in this branch.

### Check the ExecuTorch classifier

From the repository root:

```powershell
& $python -c "from offline_ai.executorch_classifier import predict_category; print('Bleeding:',predict_category('My friend is bleeding')); print('Forest fire:',predict_category('There is a forest fire'))"
```

Expected on the tested model: `medical` for bleeding and `fire` for forest fire. If this fails, record the exact error and verify the Python architecture, torch and ExecuTorch install. General Qwen chat may still run with optional reference context disabled.

## 3. Download the exact Qwen model (internet required once)

Official model: [Qwen/Qwen2.5-3B-Instruct-GGUF — Q4_K_M](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/blob/main/qwen2.5-3b-instruct-q4_k_m.gguf).

```powershell
New-Item -ItemType Directory -Force -Path .\offline_ai\models | Out-Null
$gguf = (Join-Path (Resolve-Path .\offline_ai\models).Path 'qwen2.5-3b-instruct-q4_k_m.gguf')
curl.exe -fL --retry 3 -o "$gguf" "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
if ($LASTEXITCODE -ne 0) { throw "Qwen download failed" }
Get-FileHash -Algorithm SHA256 -LiteralPath $gguf
```

**Expected SHA256** as published in the upstream model-file page (verify the remote checksum again if upstream updates its weights):

`626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`

The roughly 2.1 GB GGUF is intentionally **not in this Git repo**. Respect the upstream model license (`qwen-research`) and terms.

## 4. Download the validated llama.cpp server (internet required once)

The team validated the official **llama.cpp b11490 Windows ARM64 CPU** release on its Snapdragon laptop. Use that specific binary on Windows ARM64; a different newer build is not automatically equivalent.

Release asset: [llama-b11490-bin-win-cpu-arm64.zip](https://github.com/ggml-org/llama.cpp/releases/download/b11490/llama-b11490-bin-win-cpu-arm64.zip)

```powershell
$llamaDir = Join-Path $env:LOCALAPPDATA 'LifeLine\llama-b11490-arm64'
New-Item -ItemType Directory -Force -Path $llamaDir | Out-Null
$zip = Join-Path $env:TEMP 'llama-b11490-bin-win-cpu-arm64.zip'
curl.exe -fL --retry 3 -o "$zip" "https://github.com/ggml-org/llama.cpp/releases/download/b11490/llama-b11490-bin-win-cpu-arm64.zip"
if ($LASTEXITCODE -ne 0) { throw "llama.cpp download failed" }
Expand-Archive -LiteralPath $zip -DestinationPath $llamaDir -Force
$server = Get-ChildItem $llamaDir -Recurse -File -Filter 'llama-server.exe' | Select-Object -First 1 -ExpandProperty FullName
if (!$server) { throw 'llama-server.exe not found in release' }
Write-Host "llama-server: $server"
```

For Windows x64 use the **Windows x64 CPU** asset of b11490 and adjust the path; for macOS/Linux download the matching official platform-specific b11490 release. Those alternatives have **not** been validated as end-to-end LifeLine reproductions by this team.

## 5. Install offline medical references (no internet required)

The approved source JSON is tracked; the local generated SQLite installation is not. Install it once:

```powershell
& $python -B medical_data/install_references.py
& $python -B medical_data/install_references.py --check
```

Expect a check indicating **10 approved reference topics**. An optional browser library uses the tracked static `web/official_first_aid.json`. The default chat returns **no certified medical citations**; the optional reference context is only supplemental prompt context, not a medical validation system.

## 6. Run LifeLine (TWO separate PowerShell windows)

**Window A — Qwen model server**, from the project folder:

```powershell
$gguf = (Resolve-Path .\offline_ai\models\qwen2.5-3b-instruct-q4_k_m.gguf).Path
$llamaDir = Join-Path $env:LOCALAPPDATA 'LifeLine\llama-b11490-arm64'
$server = Get-ChildItem $llamaDir -Recurse -File -Filter 'llama-server.exe' | Select-Object -First 1 -ExpandProperty FullName
& $server -m $gguf --host 127.0.0.1 --port 8081 --alias lifeline-qwen --n-gpu-layers 0 --device none --no-kv-offload --no-op-offload --temp 0 --chat-template chatml --check-tensors --ctx-size 4096 --parallel 1 --offline
```

Wait for the model to load. Don't close this window.

**Window B — LifeLine FastAPI website**, from the **same project folder**:

```powershell
$python = '.\offline_ai\.venv-x64\Scripts\python.exe'
$env:LIFELINE_GGUF_PATH = (Resolve-Path .\offline_ai\models\qwen2.5-3b-instruct-q4_k_m.gguf).Path
$env:LIFELINE_LLAMA_PORT = '8081'
$env:LIFELINE_LLAMA_MAX_TOKENS = '160'
$env:LIFELINE_LLAMA_TIMEOUT = '120'
$env:LIFELINE_EXECUTORCH_CONTEXT = '1'
$env:LIFELINE_RAG = '0'
& $python -m uvicorn offline_ai.llama_adapter:app --host 127.0.0.1 --port 8000 --workers 1
```

**Do not use** `uvicorn app:app` for the offline Qwen chat: it does not select the required `LlamaCPUProvider`. The `LIFELINE_EXECUTORCH_CONTEXT=1` flag activates optional ExecuTorch-assisted local reference enrichment. If the classifier or its dependencies are unavailable, the system is designed to retain the normal Qwen chat path, but the classifier feature then cannot be claimed as running.

Open **http://127.0.0.1:8000/**.

## 7. Prove genuine local generation

In a **third** PowerShell window:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8081/health'
Invoke-RestMethod 'http://127.0.0.1:8000/api/status' | ConvertTo-Json -Depth 5
$result = Invoke-RestMethod 'http://127.0.0.1:8000/api/ask' -Method POST -ContentType 'application/json' -Body '{"question":"Tell me one short joke."}'
$result.data | Format-List mode,simulated,answer
```

Expected: llama-server healthy, a real generated answer with `mode=local` and `simulated=False`. The classifier test above separately verifies actual ExecuTorch runtime invocation. For offline proof, **disconnect Wi-Fi only after installation**, then ask a **new** question. Both services must stay running locally. A web page loading is *not* sufficient proof that inference works.

**Known limitations:** A 160-token generation limit may truncate lengthy answers; brief questions are best for demonstrations. The local medical summaries cover only ten topics. Unverified model output must not be presented as medically validated. The optional classifier is CPU-based, not NPU-accelerated. Android/Samsung AI deployment and AI-driven Get Prepared checklists are not demonstrated as complete. No cloud inference is required for this judge setup.

## Troubleshooting

- **Website loads but chat fails:** check that **both** servers are running and the FastAPI process was launched with `offline_ai.llama_adapter:app`, not `app:app`. The `LIFELINE_GGUF_PATH` must point to the actual GGUF file.
- **ExecuTorch import fails:** use Python 3.11 **x64** on Windows and install `torch` and `executorch==1.5.1`. The included `.pte` is a runtime artifact, not an installer.
- **Medical references missing:** run the offline reference installer and `--check`. Reference context may fail gracefully; it is not an assurance of verified output.
- **Failed model download:** verify internet access during *installation* and the GGUF SHA256. Once correctly installed, running the model does not use the internet.
- **Other OS:** obtain the appropriate native llama.cpp binary and Python wheels; commands above target the tested Windows ARM64 Dell configuration. End-to-end compatibility on arbitrary judges' hardware is not guaranteed.

Source implementation: `offline_ai/llama_adapter.py`, `offline_ai/executorch_classifier.py`, `offline_ai/qwen_context.py`, `offline_ai/reference_context.py`, `medical_rag.py`, `web/`.
