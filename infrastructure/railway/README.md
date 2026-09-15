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

- `api.railway.json` / `worker.railway.json` — per-service build/deploy
  config, applied via the Railway dashboard or CLI (`railway up` from each
  app directory, or a monorepo config pointing `rootDirectory` at
  `apps/api` / `apps/worker`).

These are templates; no Railway project is provisioned yet.
