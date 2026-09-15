# Railway

Hosts three services, each built from its own `apps/*` directory:

| Service  | Source        | Start command                                      |
| -------- | ------------- | -------------------------------------------------- |
| `api`    | `apps/api`    | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| `worker` | `apps/worker` | `celery -A app.celery_app worker --loglevel=info`  |
| `beat`   | `apps/worker` | `celery -A app.celery_app beat --loglevel=info`    |

Redis is provisioned as a managed Railway plugin/service and shared by
`worker` and `beat` via `REDIS_URL`.

The Network Agent is **not** deployed on Railway — it runs on the separate
Network VPS (see `infrastructure/wireguard/README.md`), reachable from `api`
only over HTTPS via `NETWORK_AGENT_BASE_URL`.

## Files

- `api.railway.json` / `worker.railway.json` — the legacy Railway/Nixpacks
  config schema (`builder: NIXPACKS`, `buildCommand`, `startCommand`,
  `healthcheckPath`). Railway's current build system does **not** read
  this format or filename at all — confirmed against a real deploy on
  2026-09-15, where a service rooted at `apps/api` fell back to Railpack
  auto-detection and failed with "No start command detected" even with
  `api.railway.json` present one level up. Kept here only as a
  historical/reference record of the intended build+start commands.
- Railpack (`apps/api/railpack.json`) was also tried and abandoned: its
  config schema rejected `{"local": true}` on any custom-named install
  step ("inputs must be an image or step input"), contradicting its own
  published docs, and Railpack's file format is explicitly documented as
  "not yet finalized and subject to change."
- **What Railway actually builds from now: `apps/api/Dockerfile`**, a
  plain `python:3.12-slim` image (`pip install -e .`, then
  `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`). Railway's
  builder auto-detects a Dockerfile and uses it in preference to
  Railpack, and this has proven far more stable than fighting Railpack's
  evolving schema. `apps/worker` has no Dockerfile yet — add one the same
  way before deploying the worker/beat services.
- Deploying via `railway up` from the monorepo root requires
  `railway up ./apps/api --path-as-root --service <name>` — the CLI's
  linked-project directory is the monorepo root here, so a bare
  `railway up` (even run with cwd inside `apps/api`) uploads the whole
  repo and Railpack misdetects it as the Node/pnpm workspace at the root.
  `--path-as-root` scopes the uploaded archive to `apps/api` so the
  Dockerfile there is found.

The `infinity-radius` Railway project (workspace "Masanja paul's
Projects") and its backend service are deployed and live — see the root
README's deployment section for status. `worker`/`beat` are not deployed
yet.
