# Deployment

Nothing is deployed yet — this documents the target topology for when it is.

| Component                    | Platform                         | Notes                                                 |
| ---------------------------- | -------------------------------- | ----------------------------------------------------- |
| `apps/web`                   | Vercel                           | Next.js. Env vars: see `apps/web/.env.example`        |
| `apps/api`                   | Railway                          | FastAPI. Env vars: see `apps/api/.env.example`        |
| `apps/worker`                | Railway (worker + beat services) | Celery. Env vars: see `apps/worker/.env.example`      |
| Redis                        | Railway (managed plugin)         | Shared by `worker`/`beat`                             |
| Supabase                     | Supabase Cloud                   | Auth, primary Postgres, RLS                           |
| `apps/network-agent`         | Dedicated Ubuntu VPS             | Not Railway. See `infrastructure/wireguard/README.md` |
| FreeRADIUS + RADIUS Postgres | Same Network VPS                 | See `infrastructure/freeradius/README.md`             |

See `infrastructure/railway/` for per-service Railway configs and
`docs/architecture.md` for how these talk to each other.

## Order of operations (first real deploy, once business modules exist)

1. Provision Supabase project; run Alembic migrations against it.
2. Provision the Network VPS; install WireGuard, FreeRADIUS, the Network
   Agent, and Nginx/Caddy in front of it.
3. Deploy `apps/api` and `apps/worker`/`beat` to Railway, pointed at
   Supabase Postgres, Redis, and the Network Agent's HTTPS endpoint.
4. Deploy `apps/web` to Vercel, pointed at Supabase and the Railway API URL.
5. Onboard the first router as a WireGuard peer.
