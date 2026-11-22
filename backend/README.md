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
| `app/session.py` | In-memory state of one session, the snapshot sent to clients, dump/restore. What a pipeline reads. |
| `app/store.py` | SQLite: append-only event log, latest snapshot per session, `config` table, `users`. |
| `app/config.py` | Every setting, with its default. |
| `app/main.py` | REST + WebSocket endpoints, access code, rate limit. |
| `app/users.py` | Nickname login and a user's session list. |
| `app/admin.py` | Admin API for the frontend's `/admin` page: usage and cost, runtime model switch, session history, event export. |
| `app/openrouter.py` | OpenRouter model list (prices) and key spend, for the admin page. |
| `app/pipeline/base.py` | The interface the agent code implements. |
| `app/pipeline/mock.py` | Scripted lo-fi scenario, no LLM. For frontend work and tests. |
| `app/pipeline/baseline.py` | Simple reference pipeline on OpenRouter. The csl pipeline calls its setup chat and its classroom call. |
| `app/pipeline/csl/` | The team's pipeline, registered as `csl`; the live server's default. `discussion.py`: who speaks next and what they say. `knowledge.py`: setup chat and classroom (the baseline's code plus csl's rules), what a peer is given before it speaks. `_state_updates.py`: knowledge-state updates (edits with quoted evidence, checked in code, then graded). `_peer_speech.py`: drops sentences in which a peer claims an experience nobody stated. `prompting.py`: request assembly laid out for the prompt cache. |
| `app/llm.py` | OpenRouter client: streaming, JSON calls, retries, per-call usage, cost and cache log, runtime model override. Sends the session id with every call so one session stays on one provider (prompt cache). |
| `scripts/cli.py` | Run a session in the terminal, without server or frontend. |
| `scripts/gen_ts.py` | Regenerate `frontend/src/lib/csl/protocol.ts` after changing `protocol.py`. |
| `tests/` | 153 tests, no network: orchestrator, REST/WebSocket, baseline, csl (discussion, classroom, state updates, peer context) and LLM client with fakes, admin API, per-session pipelines, users. |

## Run

Python 3.11+.

```bash
uv sync --extra dev                         # or: pip install fastapi "uvicorn[standard]" pydantic pydantic-settings openai pytest pytest-asyncio httpx
cp .env.example .env                        # PIPELINE=mock works without any key
uv run uvicorn app.main:app --reload        # http://localhost:8000/api/health
uv run pytest
uv run python scripts/cli.py "Why is summer hotter than winter?"
```

To use real models set `PIPELINE=csl` (or `baseline`), `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`.
To use your own pipeline set `PIPELINE=your.module:YourPipeline` (see [docs/PIPELINE.md](docs/PIPELINE.md)).
The module is imported with `backend/` as the working directory, so `backend/app/pipeline/mine.py` is
`PIPELINE=app.pipeline.mine:MyPipeline`. The pipeline is loaded once at startup; changing it needs a restart.
**Per-session pipelines.** `PIPELINE` is only the server's default. A single session can run on any pipeline
registered in `SESSION_PIPELINES` (`app/pipeline/__init__.py`; now `mock`, `baseline`, `csl`): `POST /api/sessions` with
`"pipeline": "<name>"`, or the "Agents" selector on `/dev`. `GET /api/health` lists the names
(`sessionPipelines`) and which of them are free (`freePipelines`).

- `mock` is free: no LLM calls, no access code. Frontend work never needs the real agents.
- To try a new pipeline on the deployed server, add one line to `SESSION_PIPELINES` and push. No `.env`
  change, and the server's default stays what it was. A registered name also works as `PIPELINE=<name>`.
- The module is imported the first time a session asks for it. If that fails, only that request fails
  (500; the reason is in the server log, and in the response when `DEBUG=true`). A test checks that every
  registered entry loads, so a broken registration does not get deployed.
- The name is stored with the session and kept when it is restored after a restart. If the name is no
  longer registered, the server's default takes the session over.

All settings are in `app/config.py`; each can be set as an environment variable or in `.env`.
The ones that matter in production:

| Variable | Meaning |
| --- | --- |
| `PIPELINE` | `mock` (default), `baseline`, `csl` (the live server's setting) or `module:Class`. |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_MODEL_FAST` | Needed unless `PIPELINE=mock`. The fast model is used for calls made with `fast=True` and falls back to the main one. Both ids can be switched from the admin page without a restart. |
| `PEER_COUNT` | Number of peers the baseline pipeline creates (default 2). |
| `CORS_ORIGINS` | Origins allowed to call the API and open the WebSocket. |
| `ACCESS_CODE` | If set, creating a session needs this code. Protects the API budget on a public URL. Sessions that ask for a free pipeline (`pipeline: "mock"`) are exempt (they cost nothing). |
| `ADMIN_TOKEN` | If set, enables the admin API and the `/admin` page (below). Off (404) when empty. |
| `LLM_REASONING` | `off` (default), `low`, `medium`, `high` or `default`. Models such as claude-haiku-5.5 "think" on their own and the thinking tokens count against `max_tokens`, so short replies can come back empty (`init_turn wrote no text`). `off` turns thinking off; a model that rejects that gets the call again without the field. |
| `MAX_TURNS`, `MAX_ACTIVE_SESSIONS`, `SESSIONS_PER_IP_PER_HOUR` | Cost guards. |
| `TURN_TIMEOUT_SECONDS` | Limit for one pipeline call (default 90). |
| `PACE_BASE_SECONDS`, `PACE_SECONDS_PER_CHAR`, `PACE_MAX_SECONDS` | Reading gap between two agent messages. |
| `DEBUG` | `true` sends exception details to the client in `error` events. Keep it off in production; details always go to the log. |

## Things to know

* **Users.** Login is a nickname, nothing else (`app/users.py`). `POST /api/users/login {name}` returns the
  user, creating it if the nickname is new; case and extra spaces do not make a different user. A session
  created with that `userId` is recorded as the user's (`sessions.user_id`), and
  `GET /api/users/{userId}/sessions` lists them, so a learner who left midway finds the session again from
  any browser. This identifies learners for the usage analysis; it is **not access control**: whoever knows
  a nickname signs in as it, and a session still opens by its id alone. Sessions without a user remain
  possible (`/dev` allows them; the product start page asks for a nickname first). The admin page shows the
  user of each session. A database from before this feature gets the `user_id` column added at startup.
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
    *Cache hit rate* (total, by model, by day): input tokens read from the provider's prompt cache
    (`usage.prompt_tokens_details.cached_tokens`, logged as `cachedTokens`) divided by the input tokens of
    the calls that reported that figure. Older calls, logged before this was recorded, are left out.
    Some providers, Anthropic among them, only cache when the request asks for it (`cache_control`). The
    csl pipeline's discussion calls and state-update proposals do (`app/pipeline/csl/prompting.py`); the
    baseline, and with it csl's setup chat and classroom call, does not, so those calls show 0%.
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
