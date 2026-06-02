# Meituan Planner Technical Handoff

This repo contains a Python route-planning backend and a React/Vite frontend. The runtime depends on a local Yelp city-subset data package, which is not committed to GitHub.

## Repository Layout

```text
.
+-- src/planner/                 # Python backend package
|   +-- api.py                   # HTTP API server
|   +-- modules/                 # intent, POI, comments, routing logic
|   +-- io/                      # cache and JSONL readers
|   +-- llm/                     # OpenAI-compatible client and prompts
+-- scripts/                     # CLI utilities for data and pipeline debugging
+-- meituan_map/                 # React/Vite frontend
+-- tests/                       # Python tests
+-- cache/                       # generated runtime cache, optional
+-- data/                        # local data package, not in GitHub
+-- requirements.txt             # Python dependencies
+-- pyproject.toml               # Python package metadata
```

## Data Placement

The app expects the Philadelphia subset under this exact path:

```text
<repo-root>/
+-- data/
    +-- interim/
        +-- city_subsets/
            +-- philadelphia_pa/
                +-- metadata.json
                +-- yelp_academic_dataset_business.json
                +-- yelp_academic_dataset_review.json
                +-- yelp_academic_dataset_tip.json
                +-- yelp_academic_dataset_user.json
                +-- yelp_academic_dataset_checkin.json
```

Runtime-required files:

```text
metadata.json
yelp_academic_dataset_business.json
yelp_academic_dataset_review.json
yelp_academic_dataset_tip.json
```

`user.json` and `checkin.json` are not required by the current route-planning API, but keep them in the data package if available.

If sending data separately, zip the `data/` folder itself so the receiver can extract it directly at repo root:

```text
repo-root/data/interim/city_subsets/philadelphia_pa/...
```

Do not extract to:

```text
repo-root/data/data/interim/...
repo-root/philadelphia_pa/...
```

The review file is large. Make sure the target machine has enough disk space before extracting.

## Recommended Environment: Windows + WSL2 Ubuntu

This is the preferred setup because it matches the original development environment more closely.

### 1. Install System Tools

Install WSL2 Ubuntu, then inside Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm curl
```

Node.js from apt may be old. If `node --version` is below 20, install Node 20+ using NodeSource or nvm.

### 2. Create Python Virtual Environment

From repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Install Frontend Dependencies

```bash
cd meituan_map
npm install
cd ..
```

### 4. Place Data

Extract or copy the data package so this file exists:

```bash
test -f data/interim/city_subsets/philadelphia_pa/metadata.json
test -f data/interim/city_subsets/philadelphia_pa/yelp_academic_dataset_business.json
test -f data/interim/city_subsets/philadelphia_pa/yelp_academic_dataset_review.json
test -f data/interim/city_subsets/philadelphia_pa/yelp_academic_dataset_tip.json
```

### 5. Configure Environment Variables

Create `meituan_map/.env.local`:

```bash
cp meituan_map/.env.example meituan_map/.env.local
```

Edit it and set the keys needed by the frontend and backend:

```text
VITE_GOOGLE_MAPS_API_KEY=...

VITE_MIMO_API_KEY=...
MIMO_API_KEY=...
VITE_MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
VITE_MIMO_MODEL=mimo-v2.5-pro
VITE_MIMO_PROXY_PATH=/api/mimo

VITE_DEEPSEEK_API_KEY=...
DEEPSEEK_API_KEY=...
VITE_DEEPSEEK_BASE_URL=https://api.siliconflow.cn/v1
VITE_DEEPSEEK_MODEL=deepseek-ai/DeepSeek-V4-Flash
VITE_DEEPSEEK_PROXY_PATH=/api/deepseek

VITE_PLANNER_API_BASE_URL=http://127.0.0.1:8000
VITE_PLANNER_API_PATH=/api/planner/routes
VITE_PLANNER_CLARIFICATION_API_PATH=/api/planner/clarifications
```

Optional backend-only route provider:

```text
OPENROUTESERVICE_API_KEY=...
ORS_TIMEOUT_SEC=20
```

Without OpenRouteService, the backend falls back to approximate straight-line route legs.

### 6. Run Backend

Open terminal 1 from repo root:

```bash
source .venv/bin/activate
PYTHONPATH=src:. python src/planner/api.py --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/planner/health
```

Expected:

```json
{"ok": true}
```

### 7. Run Frontend

Open terminal 2:

```bash
cd meituan_map
npm run dev -- --host 127.0.0.1 --port 5174
```

Open:

```text
http://127.0.0.1:5174/
```

## Alternative Environment: Native Windows PowerShell

Use this if WSL2 is unavailable.

### 1. Install Tools

Install:

```text
Python 3.11+ from https://www.python.org/
Node.js 20+ from https://nodejs.org/
Git for Windows from https://git-scm.com/
```

During Python install, enable:

```text
Add python.exe to PATH
```

Verify in PowerShell:

```powershell
python --version
node --version
npm --version
```

### 2. Create Python Virtual Environment

From repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### 3. Install Frontend Dependencies

```powershell
cd meituan_map
npm install
cd ..
```

### 4. Place Data

After extracting the separate data package, verify:

```powershell
Test-Path .\data\interim\city_subsets\philadelphia_pa\metadata.json
Test-Path .\data\interim\city_subsets\philadelphia_pa\yelp_academic_dataset_business.json
Test-Path .\data\interim\city_subsets\philadelphia_pa\yelp_academic_dataset_review.json
Test-Path .\data\interim\city_subsets\philadelphia_pa\yelp_academic_dataset_tip.json
```

All four commands should return `True`.

### 5. Configure Environment Variables

Copy:

```powershell
Copy-Item .\meituan_map\.env.example .\meituan_map\.env.local
```

Edit `meituan_map/.env.local` with API keys and planner endpoints as shown in the WSL2 section.

### 6. Run Backend

Open PowerShell terminal 1 from repo root:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="src;."
python src\planner\api.py --host 127.0.0.1 --port 8000
```

Health check in another PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/planner/health
```

### 7. Run Frontend

Open PowerShell terminal 2:

```powershell
cd meituan_map
npm run dev -- --host 127.0.0.1 --port 5174
```

Open:

```text
http://127.0.0.1:5174/
```

## API Endpoints

Backend server:

```text
GET  /api/planner/health
POST /api/planner/clarifications
POST /api/planner/routes
```

The frontend calls `/api/planner/...` through Vite proxy. Proxy target is controlled by:

```text
VITE_PLANNER_API_BASE_URL=http://127.0.0.1:8000
```

## Model Selection

The frontend has two independent model selectors:

```text
理解行程模型    -> request field: modelChoice
解析评论模型    -> request field: commentModelChoice
```

Backend behavior:

```text
modelChoice        controls intent parsing
commentModelChoice controls comment parsing
```

Both models must be OpenAI-compatible chat completion APIs.

Supported configured choices:

```text
mimo
deepseek
```

## Cache

Generated artifacts are written under:

```text
cache/intents/
cache/pois/
cache/comments/
cache/comment_summaries/
cache/aggregated_pois/
cache/routes/
```

The app can run without pre-existing cache if `data/` is present. Cache can be deleted for a clean run.

Comment loading scans large Yelp JSONL files on first run for a new POI set. Later matching runs are faster because comment and summary cache files are reused.

## Tests and Build

Python tests:

```bash
PYTHONPATH=src:. pytest -q
```

Windows PowerShell:

```powershell
$env:PYTHONPATH="src;."
pytest -q
```

Frontend build:

```bash
cd meituan_map
npm run build
```

## Common Failures

### `ModuleNotFoundError: No module named planner`

Set `PYTHONPATH`.

Linux or WSL2:

```bash
PYTHONPATH=src:. python src/planner/api.py --host 127.0.0.1 --port 8000
```

Windows PowerShell:

```powershell
$env:PYTHONPATH="src;."
python src\planner\api.py --host 127.0.0.1 --port 8000
```

### Frontend loads but route generation fails

Check backend is running:

```text
http://127.0.0.1:8000/api/planner/health
```

Check `meituan_map/.env.local`:

```text
VITE_PLANNER_API_BASE_URL=http://127.0.0.1:8000
```

### No POIs found

Check data path:

```text
data/interim/city_subsets/philadelphia_pa/yelp_academic_dataset_business.json
```

Check `metadata.json` city/state values. The current resolver expects Philadelphia, PA.

### Comment parsing is slow

First run may scan:

```text
yelp_academic_dataset_review.json
yelp_academic_dataset_tip.json
```

This is expected. Subsequent runs should use `cache/comments/` and `cache/comment_summaries/`.

### Google map does not render

Set:

```text
VITE_GOOGLE_MAPS_API_KEY=...
```

If the key requires a Map ID, also set:

```text
VITE_GOOGLE_MAP_ID=...
```
