# CSL backend

The serving layer between the frontend and the agents.

```
browser ── REST + WebSocket ──> FastAPI (one process)
                                 ├─ SessionRunner per session   app/orchestrator.py
                                 │    init chat → classroom → discussion loop
                                 ├─ Pipeline (the agents)        app/pipeline/
                                 ├─ OpenRouter wrapper           app/llm.py
                                 └─ SQLite: event log + session snapshots   app/store.py
```

| File | Role |
| --- | --- |
| `app/protocol.py` | Every message on the wire (Pydantic). Source of the frontend's TypeScript types. |
| `app/orchestrator.py` | Session state machine: turn loop, reading-pace gate, prefetch, learner interruption, pause/resume, error recovery, restore after restart. |
| `app/main.py` | REST + WebSocket endpoints, access code, rate limit. |
| `app/admin.py` | Admin API for the frontend's `/admin` page: usage and cost, runtime model switch, session history, event export. |
| `app/openrouter.py` | OpenRouter model list (prices) and key spend, for the admin page. |
| `app/pipeline/base.py` | The interface the agent code implements. |
| `app/pipeline/mock.py` | Scripted lo-fi scenario, no LLM. For frontend work and tests. |
| `app/pipeline/baseline.py` | Simple reference pipeline on OpenRouter. A placeholder for the real one. |
| `app/llm.py` | OpenRouter client: streaming, JSON calls, retries, per-call usage and cost log, runtime model override. |
| `scripts/cli.py` | Run a session in the terminal, without server or frontend. |
| `scripts/gen_ts.py` | Regenerate `frontend/src/lib/csl/protocol.ts` after changing `protocol.py`. |

## Run

Python 3.11+.

```bash
uv sync --extra dev                         # or: pip install fastapi "uvicorn[standard]" pydantic pydantic-settings openai pytest pytest-asyncio httpx
cp .env.example .env                        # PIPELINE=mock works without any key
uv run uvicorn app.main:app --reload        # http://localhost:8000/api/health
uv run pytest
uv run python scripts/cli.py "Why is summer hotter than winter?"
```

To use real models set `PIPELINE=baseline`, `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`.
To use your own pipeline set `PIPELINE=your.module:YourPipeline` (see [docs/PIPELINE.md](docs/PIPELINE.md)).

All settings are in `app/config.py`; each can be set as an environment variable or in `.env`.
The ones that matter in production:

| Variable | Meaning |
| --- | --- |
| `CORS_ORIGINS` | Origins allowed to call the API and open the WebSocket. |
| `ACCESS_CODE` | If set, creating a session needs this code. Protects the API budget on a public URL. |
| `ADMIN_TOKEN` | If set, enables the admin API and the `/admin` page (below). Off (404) when empty. |
| `MAX_TURNS`, `MAX_ACTIVE_SESSIONS`, `SESSIONS_PER_IP_PER_HOUR` | Cost guards. |
| `PACE_BASE_SECONDS`, `PACE_SECONDS_PER_CHAR`, `PACE_MAX_SECONDS` | Reading gap between two agent messages. |

## Things to know

* **One process only.** Sessions live in memory, so run a single uvicorn worker. A session whose client
  left is paused at once, dropped from memory after `SESSION_IDLE_MINUTES`, and restored from SQLite when
  the client comes back (also after a server restart).
* **Nothing is generated for an empty room.** When the last WebSocket of a session closes, the discussion
  pauses, and resumes when a client reconnects.
* **Event log.** Every server event, every client command (`client.*`), every LLM call (`llm.call`) and
  every UI event the frontend reports (`client.ui.event`) is appended to the `events` table. Export:

  ```bash
  curl -H "Authorization: Bearer $ADMIN_TOKEN" https://<host>/api/admin/sessions
  curl -H "Authorization: Bearer $ADMIN_TOKEN" https://<host>/api/admin/sessions/<id>/events
  ```
* **Admin page.** `https://<host>/admin`, sign in with `ADMIN_TOKEN`. Tabs:
  - *Usage*: the OpenRouter key's real spend and limit (`GET /api/v1/key`), plus calls, tokens, latency and
    cost from the `llm.call` events, by model and by day. `llm.call` carries the cost OpenRouter reports
    (`usage.cost`); calls without it are estimated from list prices (marked ≈). Streams cancelled by a
    learner interjection report no usage and are missing from the log figures, so the key spend is the
    number to trust.
  - *Models*: switch `OPENROUTER_MODEL` / `OPENROUTER_MODEL_FAST` without a restart. The override is stored in
    the `config` table of the SQLite database and survives restarts; empty fields fall back to `.env`. It
    applies from the next LLM call. Ids are checked against the OpenRouter model list. It does nothing while
    `PIPELINE=mock`.
  - *Sessions*: every stored session (cost per session), its setup chat and discussion, every knowledge-state
    version, the pipeline's `scratch`, and the raw event log (filter, JSON download). Viewing a session does
    not load it into memory.

  API (all need `Authorization: Bearer $ADMIN_TOKEN`): `GET /api/admin/sessions`, `GET /api/admin/sessions/{id}`,
  `GET /api/admin/sessions/{id}/events`, `GET /api/admin/usage?tzOffset=<minutes east of UTC>`,
  `GET|PUT /api/admin/config` (`{model, modelFast}`, `""` = back to `.env`), `GET /api/admin/models[?refresh=true]`.
  Types: the `Admin*`, `Usage*`, `ModelConfig*`, `ModelInfo` models in `app/protocol.py`.

## Deploy (uv + pnpm, one server)

Needs uv, Node 20+ and pnpm on the server. Both services listen on localhost only; the reverse proxy of
your domain terminates TLS and routes `/api/*` and `/ws/*` to the backend (with WebSocket upgrade) and
everything else to the frontend. `deploy/Caddyfile.example` and `deploy/nginx.conf.example` show both.

```bash
# backend -> 127.0.0.1:8000
cd backend
cp .env.example .env        # PIPELINE, OPENROUTER_*, ACCESS_CODE, ADMIN_TOKEN, CORS_ORIGINS=https://your.domain
uv sync

# frontend -> 127.0.0.1:3000
cd ../frontend
echo "NEXT_PUBLIC_CSL_API_URL=https://your.domain" > .env.production   # baked in at build time
pnpm install --frozen-lockfile
pnpm build

# keep both running (restart on crash and on reboot)
sudo cp ../deploy/csl-backend.service ../deploy/csl-frontend.service /etc/systemd/system/   # edit <user> and paths first
sudo systemctl daemon-reload
sudo systemctl enable --now csl-backend csl-frontend
```

`CORS_ORIGINS` must contain the public origin, otherwise the WebSocket is closed with code 4403.

Update: `git pull`, then `uv sync` in `backend/`, `pnpm install --frozen-lockfile && pnpm build` in
`frontend/`, then `sudo systemctl restart csl-backend csl-frontend`. Sessions survive the restart.
Logs: `journalctl -u csl-backend -f`.

### Continuous deployment

On the course server this is automated: every push to `main` runs `.github/workflows/deploy.yml` on a
self-hosted GitHub Actions runner on that server. The workflow runs the backend tests and a frontend
build in the runner's workspace first; only if both pass does `deploy/deploy.sh` move the server checkout
to the pushed commit, rebuild, restart both services and check `/api/health` and `/dev`. A failing
test or build therefore leaves the live site as it was. To redeploy without a push, use
"Run workflow" on the Deploy workflow in the Actions tab. The frontend is rebuilt in place, so it can
answer with errors for ~15 s during a deploy.

On Oracle Cloud, ports 80/443 must be open in the instance's security list **and** in the host firewall
(Oracle's Ubuntu images ship iptables rules that reject them by default).

The SQLite file is `backend/data/csl.db`.
