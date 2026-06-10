# Ubuntu Deployment

This guide describes the current simple homelab deployment: one systemd service for the FastAPI
backend, one systemd service for the job worker, and one systemd service for the Vite frontend dev
server.

The default ports in these templates are:

- API: `9500`
- Frontend: `5175`

This is good enough for early LAN testing. A later production setup should build the frontend with `npm run build` and serve `frontend/dist/` through Caddy, Nginx, Traefik, or the FastAPI backend.

## Assumptions

- Repository path: `/opt/BrainDashboard`
- Linux user: `alex`
- Backend venv: `/opt/BrainDashboard/.venv`
- Postgres database already exists.
- Node/npm is installed.

Adjust the systemd unit files if any of those paths or users differ.

## Backend Setup

```bash
cd /opt/BrainDashboard
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Create the backend environment file:

```bash
sudo mkdir -p /etc/braindashboard
sudo cp deploy/env/backend.env.example /etc/braindashboard/backend.env
sudo nano /etc/braindashboard/backend.env
sudo chmod 640 /etc/braindashboard/backend.env
sudo chown root:alex /etc/braindashboard/backend.env
```

Set `BRAINDASHBOARD_DATABASE_URL` to the Postgres connection string you created. Also set `BRAINDASHBOARD_CORS_ORIGINS` to include the frontend URL as seen by your browser, for example `http://brainsrv:5175`. Keep the JSON array wrapped in single quotes in this systemd environment file.

Migrations are not applied automatically by the FastAPI app, the systemd service, or the optional `post-merge` hook. Apply them explicitly before starting or restarting the API service.

Use the versioned helper script for server-side Alembic commands. It loads `/etc/braindashboard/backend.env` first, so it uses the same `BRAINDASHBOARD_DATABASE_URL` as the service instead of falling back to the `alembic.ini` default.

```bash
cd /opt/BrainDashboard
sudo -u alex python3 ./deploy/sbin/braindashboard-migrate
```

Pass any Alembic subcommand through the helper when you want to inspect state without changing it:

```bash
cd /opt/BrainDashboard
sudo -u alex python3 ./deploy/sbin/braindashboard-migrate current
```

The Jobs migrations create the catalog tables (`job_definitions`, `job_parameters`) and the run history tables (`job_runs`, `job_events`). `GET /api/jobs/definitions` seeds the starter definitions into the catalog tables when they are empty.

Native job queueing is controlled by these backend settings:

```bash
BRAINDASHBOARD_SCHEDULER_ENABLED=true
BRAINDASHBOARD_SCHEDULER_PROCESS_MODE=offprocess
BRAINDASHBOARD_JOB_LOGS_DIR=/var/log/braindashboard/runs
BRAINDASHBOARD_JOB_MAX_ACTIVE_RUNS=1
BRAINDASHBOARD_SCHEDULER_TICK_INTERVAL_SECONDS=2
BRAINDASHBOARD_NATIVE_CANCEL_GRACE_SECONDS=10
```

`BRAINDASHBOARD_SCHEDULER_ENABLED` controls whether the job runner is enabled at all.
`BRAINDASHBOARD_SCHEDULER_PROCESS_MODE=offprocess` keeps the API from owning job subprocesses. Run
`braindashboard-worker.service` on the same host to claim queued runs and supervise active jobs. This
lets you restart or redeploy `braindashboard-api.service` without waiting for jobs to finish.

Create the log directory and make it writable by the backend user before queueing native jobs:

```bash
sudo mkdir -p /var/log/braindashboard/runs
sudo chown alex:alex /var/log/braindashboard/runs
sudo chmod 750 /var/log/braindashboard/runs
```

The first scheduler implementation runs one active native job at a time. Docker and API job definitions may be saved in the catalog, but only native definitions can be queued until their executors are implemented.

For llama-swap and vLLM service polling, point the backend at llama-swap and provide the llama-swap API key:

```bash
BRAINDASHBOARD_LLAMA_SWAP_BASE_URL=http://127.0.0.1:9292
LLAMA_SWAP_API_KEY=change-me
```

The backend calls llama-swap directly, so the key is never exposed to the browser bundle.

Docker service health uses the Docker CLI from the backend service process. Make sure the backend user can run read-only Docker commands:

```bash
docker version
docker ps --all
```

If those fail because of socket permissions, add the service user to the Docker group and restart the API service after the group membership is active:

```bash
sudo usermod -aG docker alex
sudo systemctl restart braindashboard-api.service
```

## GPU Profile Wrapper

GPU profile definitions are editable YAML under `/etc`, while privileged writes go through a root-owned wrapper. Install the example profile file, wrapper, and sudoers rule:

```bash
cd /opt/BrainDashboard
sudo install -o root -g root -m 0644 deploy/etc/gpu-profiles.yaml.example /etc/braindashboard/gpu-profiles.yaml
sudo install -o root -g root -m 0755 deploy/sbin/braindashboard-gpu-profile /usr/local/sbin/braindashboard-gpu-profile
sudo visudo -cf deploy/sudoers/braindashboard-gpu-profile
sudo install -o root -g root -m 0440 deploy/sudoers/braindashboard-gpu-profile /tmp/braindashboard-gpu-profile.sudoers
sudo visudo -cf /tmp/braindashboard-gpu-profile.sudoers
sudo mv /tmp/braindashboard-gpu-profile.sudoers /etc/sudoers.d/braindashboard-gpu-profile
```

If an invalid sudoers file was already installed, remove it first, then re-run the commands above:

```bash
sudo rm -f /etc/sudoers.d/braindashboard-gpu-profile
```

Edit profiles in place:

```bash
sudo nano /etc/braindashboard/gpu-profiles.yaml
```

Supported profile fields are `gpu_index`, `power_limit_watts`, `persistence_mode`, `graphics_clocks_mhz`, `reset_graphics_clocks`, `memory_clocks_mhz`, `reset_memory_clocks`, `lact_device_id`, `gpu_clock_offsets`, and `mem_clock_offsets`. The wrapper validates profile names and fields before constructing `nvidia-smi` calls.

The LACT fields are optional and only used for clock offsets. `gpu_clock_offsets` and `mem_clock_offsets` are pstate-to-MHz-offset mappings applied through LACT's direct `batch_set_clocks_value` API. The wrapper runs the `nvidia-smi` power and locked-clock commands first, applies and immediately confirms LACT's pending overclock config second, then briefly waits and reasserts only non-clock NVIDIA controls such as power limit. This keeps `-lgc` before LACT offsets while still letting power limits win if LACT touches them. If LACT is not installed, `lactd` is not running, the socket is unavailable, or the offset update fails, the profile apply still succeeds and returns a warning so basic power and clock controls are not blocked.

If `lact_device_id` is omitted, the wrapper asks LACT for its device list and uses `gpu_index` over LACT's dedicated devices first. On mixed iGPU/dGPU hosts, setting `lact_device_id` explicitly is still recommended. You can find the exact LACT device id with:

```bash
lact cli list-gpus
```

Check wrapper access as the backend user:

```bash
sudo -u alex sudo -n /usr/local/sbin/braindashboard-gpu-profile list --json
```

The backend command defaults to:

```bash
BRAINDASHBOARD_GPU_PROFILE_COMMAND=sudo -n /usr/local/sbin/braindashboard-gpu-profile
```

## Frontend Setup

```bash
cd /opt/BrainDashboard/frontend
npm install
cp .env.example .env.local
nano .env.local
```

For HTTPS aliases, leave `VITE_API_BASE_URL` blank so the browser calls same-origin `/api/...` URLs. Vite proxies those requests to the backend through `BRAINDASHBOARD_API_PROXY_TARGET`:

```bash
VITE_API_BASE_URL=
BRAINDASHBOARD_API_PROXY_TARGET=http://127.0.0.1:9500
```

Manual `npm run dev` uses `.env.local`. The systemd service below uses `/etc/braindashboard/frontend.env`, so keep both files aligned while testing this early deployment.

Create the frontend service environment file:

```bash
cd /opt/BrainDashboard
sudo cp deploy/env/frontend.env.example /etc/braindashboard/frontend.env
sudo nano /etc/braindashboard/frontend.env
sudo chmod 640 /etc/braindashboard/frontend.env
sudo chown root:alex /etc/braindashboard/frontend.env
```

Set `BRAINDASHBOARD_FRONTEND_ALLOWED_HOSTS` to the hostnames you will use in the browser. For your LAN URL, include `brainsrv`:

```bash
BRAINDASHBOARD_FRONTEND_ALLOWED_HOSTS=brainsrv
```

## Install systemd Services

```bash
cd /opt/BrainDashboard
sudo cp deploy/systemd/braindashboard-api.service /etc/systemd/system/
sudo cp deploy/systemd/braindashboard-worker.service /etc/systemd/system/
sudo cp deploy/systemd/braindashboard-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now braindashboard-api.service
sudo systemctl enable --now braindashboard-worker.service
sudo systemctl enable --now braindashboard-frontend.service
```

## Optional Git Pull Restart Hook

Install the versioned `post-merge` hook if you want `git pull` on the server to restart the dashboard services after new commits are merged:

```bash
cd /opt/BrainDashboard
sudo visudo -cf deploy/sudoers/braindashboard-service-restart
sudo install -o root -g root -m 0440 deploy/sudoers/braindashboard-service-restart /tmp/braindashboard-service-restart.sudoers
sudo visudo -cf /tmp/braindashboard-service-restart.sudoers
sudo mv /tmp/braindashboard-service-restart.sudoers /etc/sudoers.d/braindashboard-service-restart
install -m 0755 deploy/git-hooks/post-merge .git/hooks/post-merge
```

After that, a normal pull restarts the API and frontend services without prompting for sudo:

```bash
cd /opt/BrainDashboard
git pull --ff-only
```

If the hook reports that passwordless sudo is unavailable, re-check the sudoers file with:

```bash
sudo visudo -cf /etc/sudoers.d/braindashboard-service-restart
```

## Check Status

```bash
systemctl status braindashboard-api.service
systemctl status braindashboard-worker.service
systemctl status braindashboard-frontend.service
curl http://127.0.0.1:9500/api/health
curl http://127.0.0.1:9500/api/hardware/snapshot
curl http://127.0.0.1:9500/api/gpu/profiles
curl http://127.0.0.1:9500/api/services/snapshot
curl http://127.0.0.1:5175/
```

Useful logs:

```bash
journalctl -u braindashboard-api.service -f
journalctl -u braindashboard-worker.service -f
journalctl -u braindashboard-frontend.service -f
```

## Restart After Config Changes

```bash
sudo systemctl restart braindashboard-api.service
sudo systemctl restart braindashboard-worker.service
sudo systemctl restart braindashboard-frontend.service
```

## Common Issues

### npm cannot be found

Find npm with:

```bash
command -v npm
```

If it is not `/usr/bin/npm`, update `ExecStart` in `/etc/systemd/system/braindashboard-frontend.service` and run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart braindashboard-frontend.service
```

### Frontend shows API offline

Check that:

- The API service is running.
- `VITE_API_BASE_URL` is blank when using an HTTPS frontend alias, so browser requests stay on same-origin `/api/...` paths.
- `BRAINDASHBOARD_API_PROXY_TARGET` points to the local backend URL reachable from the Vite process, usually `http://127.0.0.1:9500`.
- If you intentionally set `VITE_API_BASE_URL` to a cross-origin API URL, `BRAINDASHBOARD_CORS_ORIGINS` must include the frontend origin reachable from the browser.

Example backend CORS setting:

```bash
BRAINDASHBOARD_CORS_ORIGINS='["http://brainsrv:5175","http://192.168.1.50:5175"]'
```

### Browser says host is not allowed

This comes from Vite's host-header protection. Add the browser hostname to `/etc/braindashboard/frontend.env`:

```bash
BRAINDASHBOARD_FRONTEND_ALLOWED_HOSTS=brainsrv
```

For multiple names, use a comma-separated list:

```bash
BRAINDASHBOARD_FRONTEND_ALLOWED_HOSTS=brainsrv,192.168.1.50
```

Then restart the frontend service.

### Browser reports blocked mixed active content

This means the HTTPS frontend is trying to call an HTTP API URL directly. Remove or blank `VITE_API_BASE_URL` in `/etc/braindashboard/frontend.env` and use the Vite proxy instead:

```bash
VITE_API_BASE_URL=
BRAINDASHBOARD_API_PROXY_TARGET=http://127.0.0.1:9500
```

Then restart the frontend service.

### Docker shows offline

The Docker card is collected by the backend service using the local Docker CLI. Check Docker access as the service user:

```bash
sudo -u alex docker version
sudo -u alex docker ps --all
```

If permissions changed, restart `braindashboard-api.service` after the service user can access Docker.

### GPU profiles are unavailable

Check the wrapper and sudoers path as the service user:

```bash
sudo -u alex sudo -n /usr/local/sbin/braindashboard-gpu-profile list --json
sudo -u alex cat /etc/braindashboard/gpu-profiles.yaml
```

If `sudo` requires a password, re-check `/etc/sudoers.d/braindashboard-gpu-profile` with `sudo visudo -cf /etc/sudoers.d/braindashboard-gpu-profile`. If `nvidia-smi` fails, test the same profile directly on the host before applying it through the dashboard. If only LACT offset warnings appear, check that `lactd` is running and that `/run/lactd.sock` is reachable by the wrapper.

To test the LACT offset API directly:

```bash
echo '{"command":"batch_set_clocks_value","args":{"id":"10DE:2BB1-10DE:204B-0000:01:00.0","commands":[{"type":{"gpu_clock_offset":0},"value":100},{"type":{"mem_clock_offset":0},"value":250}]}}' | sudo nc -U /run/lactd.sock | jq .
```

### Alembic says password authentication failed

Manual SSH shells do not automatically load `/etc/braindashboard/backend.env`. If `BRAINDASHBOARD_DATABASE_URL` is unset, Alembic falls back to the localhost URL in `alembic.ini`, which can point at the wrong password or even the wrong Postgres instance.

Use the helper instead of calling `.venv/bin/alembic` directly:

```bash
cd /opt/BrainDashboard
sudo -u alex python3 ./deploy/sbin/braindashboard-migrate current
sudo -u alex python3 ./deploy/sbin/braindashboard-migrate
```

If you need to inspect the deployed settings directly, check `/etc/braindashboard/backend.env` before retrying.

### Service uses the wrong port

Check the environment files:

```bash
cat /etc/braindashboard/backend.env
cat /etc/braindashboard/frontend.env
```

Then restart both services.
