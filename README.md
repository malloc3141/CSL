# CSL

2026F CS473 Term Project - Classroom Simulation for Learning

A learner watches, inspects and joins a discussion between a tutor agent and peer agents that hold
different, partly wrong mental models of a topic, in order to notice gaps in their own understanding.

## Layout

| Path | What |
| --- | --- |
| `frontend/` | Next.js UI. `src/lib/csl/` is the connection to the backend (generated types, WebSocket client, `useCslSession` hook). `src/app/dev/` is a bare page that exercises the whole flow. |
| `backend/` | FastAPI server. `app/orchestrator.py` runs sessions (turn loop, pacing, interruption); `app/main.py` is the REST + WebSocket API; `app/protocol.py` defines every message on the wire; `app/pipeline/` holds the agent pipelines behind one interface (`base.py`). |
| `deploy/` | systemd units and reverse-proxy examples (Caddy, nginx) for running both services on one server. |

Docs: [backend/README.md](backend/README.md) (run, configure, deploy) ·
[backend/docs/PROTOCOL.md](backend/docs/PROTOCOL.md) (frontend ↔ backend) ·
[backend/docs/PIPELINE.md](backend/docs/PIPELINE.md) (how to plug in the agents)

## Run locally

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
