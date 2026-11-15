# CSL

2026F CS473 Term Project (Team CSTL) - Classroom Simulation for Learning

A learner watches, inspects and joins a discussion between a tutor agent and peer agents that hold
different, partly wrong mental models of a topic, in order to notice gaps in their own understanding.

**Live prototype: https://csl.kimhm.in** (every push to `main` is tested and deployed there)

| Page | What |
| --- | --- |
| `/` | Static demo of the common UI components. The product UI goes here. |
| `/dev` | Bare page that runs a whole session against the backend: setup chat → classroom → discussion → knowledge-state panels. Also the deployment smoke test. |
| `/admin` | LLM usage and cost, runtime model switch, session history and event log. Needs the admin token. |

Working on this project? Start with **[HANDOFF.md](HANDOFF.md)** (한국어 / English): who works where, and how
to run, test and ship each part.

## Status (2026-11-16)

| Part | State |
| --- | --- |
| Serving layer (sessions, pacing, interruption, WebSocket, storage, event log) | Working, deployed |
| Agents | `baseline`: a simple reference pipeline on OpenRouter, a **placeholder** for the real one. `mock`: a scripted scenario without an LLM |
| Product UI | Not built yet. `/dev` shows every piece of state the UI will need |
| Deployment | Live, continuous deployment from `main`. The server runs `baseline` |

## Layout

| Path | What |
| --- | --- |
| `frontend/` | Next.js UI. `src/lib/csl/` is the connection to the backend (generated types, WebSocket client, `useCslSession` hook, admin client). `src/app/dev/` and `src/app/admin/` are the two pages above. `src/common/`, `src/styles/` hold the shared components and theme. |
| `backend/` | FastAPI server. `app/orchestrator.py` runs sessions (turn loop, pacing, interruption); `app/main.py` is the REST + WebSocket API; `app/admin.py` the admin API; `app/protocol.py` defines every message on the wire; `app/pipeline/` holds the agent pipelines behind one interface (`base.py`); `app/llm.py` is the OpenRouter client. |
| `deploy/` | systemd units, reverse-proxy examples (Caddy, nginx) and the deploy script for running both services on one server. |
| `.github/workflows/deploy.yml` | Push to `main` → backend tests, frontend build, deploy. |

Docs: [HANDOFF.md](HANDOFF.md) (who works where) ·
[backend/README.md](backend/README.md) (run, configure, admin page, deploy) ·
[backend/docs/PROTOCOL.md](backend/docs/PROTOCOL.md) (frontend ↔ backend) ·
[backend/docs/PIPELINE.md](backend/docs/PIPELINE.md) (how to plug in the agents)

## Run locally

Needs [uv](https://docs.astral.sh/uv/) (it downloads Python 3.11+ if needed), Node 20+ and pnpm 10.

```bash
# terminal 1: backend on http://localhost:8000 (scripted mock pipeline, no API key needed)
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload

# terminal 2: frontend on http://localhost:3000
cd frontend
pnpm install
pnpm dev          # open http://localhost:3000/dev
```

To run on real models, copy `backend/.env.example` to `backend/.env` and set `PIPELINE=baseline`,
`OPENROUTER_API_KEY` and `OPENROUTER_MODEL`. `.env` files are never committed.

A session can always ask for the scripted mock, whatever the server runs ("Mock" on `/dev`, or
`createSession({ topic, pipeline: "mock" })`): no LLM calls, no cost, no access code.

## Check before pushing

A push to `main` goes live only if both of these pass on the server:

```bash
cd backend  && uv run pytest        # 26 tests, ~4 s, no network
cd frontend && pnpm build           # includes the type check
```

After changing `backend/app/protocol.py`, run `uv run python scripts/gen_ts.py` in `backend/` (a test
fails if `frontend/src/lib/csl/protocol.ts` is stale).

## Built with

- Backend: Python 3.11+, FastAPI, uvicorn, Pydantic v2, pydantic-settings, openai SDK (pointed at
  OpenRouter), httpx, SQLite; pytest, pytest-asyncio; uv
- Frontend: Next.js 16, React 19, TypeScript, styled-components, lucide-react, Pretendard; ESLint; pnpm
- LLM access: OpenRouter
- Hosting: Oracle Cloud (Ubuntu, ARM64), nginx, systemd, Let's Encrypt, Cloudflare DNS, GitHub Actions
  (self-hosted runner)
- Coding support tools: Claude Code (Anthropic)
