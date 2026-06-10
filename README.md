# BrainDashboard

BrainDashboard is a local dashboard, scheduler, and orchestrator for a single Ubuntu homelab ML server. It monitors host/GPU resources, manages NVIDIA GPU power/clocks presets through a constrained wrapper, watches local ML services, and runs trusted native jobs from a durable queue. In deployment, a separate worker process owns job execution so API redeploys do not stop active jobs.

Start with these docs:

- [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)
- [docs/architecture/README.md](docs/architecture/README.md)
- [docs/FRONTEND.md](docs/FRONTEND.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/JOB_EVENT_CONTRACT.md](docs/JOB_EVENT_CONTRACT.md)

## Current Implementation

- Backend: Python 3.12 target, FastAPI, Uvicorn hot reload for development.
- Database: Postgres as the durable source of truth for job definitions, run state, structured events, and hardware telemetry buckets.
- Execution: native subprocess jobs are implemented; Docker/API execution modes can be saved in definitions but cannot be queued yet.
- GPU control: NVIDIA profile list/apply/reset through a constrained `nvidia-smi` wrapper rather than running the web server as root.
- Monitoring: live host/GPU/disk/network snapshots, one-minute hardware history buckets, llama-swap/child-backend snapshots, and Docker snapshots.
- Frontend: Vite + React dashboard with live Overview, Hardware, and Jobs views.
- Future: schedule definitions, resource locks, retries, Docker/API executors, service history, GPU audit records, and Home Assistant policy inputs.

## Development Setup

The deliverable runtime target is Python 3.12. The project metadata currently allows Python 3.12 through 3.14 so this Windows development machine can still install and inspect the skeleton until a Python 3.12 environment is available.

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
braindashboard
```

For explicit hot reload during backend development:

```powershell
uvicorn braindashboard.main:app --reload --host 127.0.0.1 --port 9500
```

For production-style local testing, keep the job runner enabled but move it out of the API process,
then run the worker in a second shell:

```powershell
$env:BRAINDASHBOARD_SCHEDULER_ENABLED = "true"
$env:BRAINDASHBOARD_SCHEDULER_PROCESS_MODE = "offprocess"
uvicorn braindashboard.main:app --host 127.0.0.1 --port 9500
braindashboard-worker
```

The default API health endpoint is `GET /api/health`.

Live dashboard data currently includes:

- `GET /api/hardware/snapshot`: current host, CPU temperature, GPU/VRAM, mounted disk, and network/uplink telemetry.
- `GET /api/hardware/history`: durable one-minute host/GPU buckets for charts, energy, cost, and single-active-run usage attribution.
- `GET /api/gpu/profiles`: YAML-backed GPU profile definitions exposed through the host wrapper.
- `POST /api/gpu/profiles/{name}/apply`: apply an allowlisted GPU profile through the wrapper.
- `POST /api/gpu/reset`: reset GPU clocks through the wrapper.
- `GET /api/services/snapshot`: current llama-swap, vLLM/llama.cpp child backend, and Docker status derived from lightweight service collectors.
- `GET /api/jobs/definitions`: Postgres-backed job definition catalog seeded on first database read, including queue-time CLI parameter metadata.
- `POST`, `PUT`, and `DELETE /api/jobs/definitions`: create, save, and delete persisted job definitions.
- `POST /api/jobs/definitions/{id}/queue`: queue native job definitions.
- `GET /api/jobs/runs`: list queued, active, and recent durable job runs.
- `GET /api/jobs/runs/{id}/events`: read parsed structured events.
- `GET /api/jobs/runs/{id}/logs`: tail raw stdout/stderr log files.
- `POST /api/jobs/runs/{id}/cancel`: cancel queued or active runs.

Only native job definitions can be queued in the current release. Docker/API definitions are catalog shape only until their executors are implemented.

Controlled jobs can emit structured stdout/stderr events using the portable contract in [docs/JOB_EVENT_CONTRACT.md](docs/JOB_EVENT_CONTRACT.md). The first job layer parses these log events; HTTP callbacks can reuse the same schema later.

For llama-swap polling, set `BRAINDASHBOARD_LLAMA_SWAP_BASE_URL` to the llama-swap URL reachable from the backend and provide `LLAMA_SWAP_API_KEY` in the backend environment.

## Frontend Setup

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev -- --host 127.0.0.1 --port 5175
```

By default, the frontend uses same-origin `/api` requests through Vite's proxy. Set `BRAINDASHBOARD_API_PROXY_TARGET` to the backend URL reachable from Vite, usually `http://127.0.0.1:9500`.

For LAN testing, add the browser-visible frontend origin to `BRAINDASHBOARD_CORS_ORIGINS` in the backend `.env` file.
