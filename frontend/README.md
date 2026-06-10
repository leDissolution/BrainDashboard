# BrainDashboard Frontend

This is the Vite + React + TypeScript dashboard app for BrainDashboard.

## Commands

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev -- --host 127.0.0.1
npm run build
npm run lint
```

On Ubuntu:

```bash
npm install
cp .env.example .env.local
npm run dev -- --host 0.0.0.0
npm run build
npm run lint
```

The frontend reads `VITE_API_BASE_URL` from `.env.local`. Leave it blank to use same-origin `/api` requests through the Vite proxy. Set `BRAINDASHBOARD_API_PROXY_TARGET` to the backend URL reachable from the Vite process.

The overview currently polls `/api/hardware/snapshot` for CPU temperature, memory, GPU VRAM-first, mounted storage, and uplink gauges, `/api/gpu/profiles` for YAML-backed GPU profile controls, and `/api/services/snapshot` for llama-swap, its vLLM/llama.cpp child rows, and Docker service cards. The Jobs view polls `/api/jobs/definitions` for the first definition catalog, including collapsed persisted editing for queue-required and default-overridable CLI parameters.

See [../docs/FRONTEND.md](../docs/FRONTEND.md) for structure and deployment notes.
