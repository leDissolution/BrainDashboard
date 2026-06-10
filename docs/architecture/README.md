# BrainDashboard Architecture

This directory describes where the running system actually lives in the repository and which pieces are implemented today. The higher-level product overview is [../PROJECT_OVERVIEW.md](../PROJECT_OVERVIEW.md), and delivery status is tracked in [../ROADMAP.md](../ROADMAP.md).

## Runtime Topology

```text
Browser UI
   |
   | REST polling through /api/*
   v
FastAPI process
   |
   +-- API routers
   +-- scheduler loop, when enabled in embedded mode
   +-- hardware monitor loop, when enabled
   +-- collectors and host wrappers
   |
   v
Postgres
   |
   +-- job definitions, parameters, runs, events
   +-- hardware sample buckets and per-run usage summaries

Ubuntu host
   |
   +-- optional braindashboard-worker process
   +-- native job processes
   +-- nvidia-smi through a constrained sudo wrapper
   +-- llama-swap and child model backends
   +-- Docker CLI for service status
```

The API can run the scheduler in-process for development, or leave job execution to the
`braindashboard-worker` process in deployment. The worker uses the same durable queue and scheduler
service, so API redeploys do not interrupt active jobs.

## Source Map

| Area | Primary files | Responsibility |
| --- | --- | --- |
| App factory | `src/braindashboard/main.py` | Creates FastAPI app, installs CORS, includes routers, starts/stops background services. |
| Settings | `src/braindashboard/core/config.py` | Pydantic settings, env prefix, scheduler/hardware/GPU/job settings. |
| API routes | `src/braindashboard/api/routes/` | HTTP surface for health, hardware, GPU profiles, services, and jobs. |
| Database models | `src/braindashboard/db/models.py` | SQLAlchemy ORM records for implemented durable state. |
| Database helpers | `src/braindashboard/db/` | Query/write helpers for job definitions, job runs/events, and hardware buckets. |
| Migrations | `migrations/versions/` | Versioned schema for job catalog, job runs/events, and hardware telemetry. |
| Scheduler | `src/braindashboard/scheduler/service.py` | Polling scheduler, active-run reconciliation, queue admission, native launch, supervision. |
| Executors | `src/braindashboard/executors/` | Native executor, event parser, shared execution request/handle types, Docker stub. |
| Collectors | `src/braindashboard/collectors/` | Host/GPU/network snapshots, llama-swap polling, Docker status, GPU profile command wrapper client. |
| Monitoring service | `src/braindashboard/monitoring/hardware.py` | One-second in-memory samples folded into one-minute hardware buckets. |
| Adapters | `src/braindashboard/adapters/` | Future integration boundaries; Home Assistant and direct NVIDIA write adapters are placeholders. |
| Frontend | `frontend/src/` | Vite/React dashboard, typed API client, Overview, Hardware, and Jobs views. |
| Deployment | `deploy/` | systemd units, env examples, sudoers templates, server helper scripts. |
| Tests | `tests/` | Backend coverage for health, hardware, services, GPU profiles, jobs, native executor, events. |

## Implemented API Surface

Health:

- `GET /api/health`

Hardware:

- `GET /api/hardware/snapshot`
- `GET /api/hardware/history`

GPU profiles:

- `GET /api/gpu/profiles`
- `POST /api/gpu/profiles/{profile_name}/apply`
- `POST /api/gpu/reset`

Services:

- `GET /api/services/snapshot`

Jobs:

- `GET /api/jobs/definitions`
- `POST /api/jobs/definitions`
- `PUT /api/jobs/definitions/{definition_id}`
- `DELETE /api/jobs/definitions/{definition_id}`
- `POST /api/jobs/definitions/{definition_id}/queue`
- `GET /api/jobs/runs`
- `GET /api/jobs/runs/{run_id}`
- `GET /api/jobs/runs/{run_id}/events`
- `GET /api/jobs/runs/{run_id}/logs`
- `POST /api/jobs/runs/{run_id}/cancel`

Planned but not implemented:

- `/api/schedules`
- `/api/settings`
- `/api/events` live SSE/WebSocket stream
- General service definition/action endpoints
- GPU audit/history endpoints

## Background Services

The app lifespan in `src/braindashboard/main.py` starts optional background services:

- `SchedulerService`, controlled by `BRAINDASHBOARD_SCHEDULER_ENABLED` and started in the API only
  when `BRAINDASHBOARD_SCHEDULER_PROCESS_MODE=embedded`.
- `HardwareMonitorService`, controlled by `BRAINDASHBOARD_HARDWARE_MONITOR_ENABLED`.

`braindashboard-worker` starts `SchedulerService` when `BRAINDASHBOARD_SCHEDULER_ENABLED=true` and
`BRAINDASHBOARD_SCHEDULER_PROCESS_MODE=offprocess`. Background loops catch loop-level exceptions so
a transient collector or scheduler failure does not crash the owning process, but detailed collector
health is not yet exposed as first-class telemetry.

## Detailed Architecture Files

- [BACKEND.md](BACKEND.md): backend process and HTTP route layout.
- [JOBS.md](JOBS.md): job catalog, queueing, scheduler, executor, logs, and events.
- [MONITORING.md](MONITORING.md): hardware/service/GPU profile monitoring and control.
- [DATA_MODEL.md](DATA_MODEL.md): implemented and planned database tables.
