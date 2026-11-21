# CSL

2026F CS473 Term Project (Team CSTL) - Classroom Simulation for Learning

A learner watches, inspects and joins a discussion between a tutor agent and peer agents that hold
different, partly wrong mental models of a topic, in order to notice gaps in their own understanding.

Live prototype: https://csl.kimhm.in

## Where the code is

| Path | What |
| --- | --- |
| `backend/app/orchestrator.py` | Runs a session: setup chat → classroom → discussion. Turn loop, reading pace, pause, and the learner interjecting at any time. |
| `backend/app/pipeline/csl/` | The agents. `discussion.py`: who speaks next and what they say. `knowledge.py`: setup chat, classroom, each peer's knowledge state. |
| `backend/app/main.py`, `protocol.py` | REST + WebSocket API and every message on the wire. |
| `frontend/src/app/` | Pages: `page.tsx` (start), `chat/` (classroom), `dev/` (bare page over the whole flow), `admin/` (usage, models, session history). |
| `frontend/src/lib/csl/` | Connection to the backend: generated types, WebSocket client, `useCslSession` hook. |
| `deploy/`, `.github/workflows/` | systemd units, proxy examples, and the deploy on every push to `main`. |

More: [HANDOFF.md](HANDOFF.md) (who works where, 한국어 / English) ·
[backend/README.md](backend/README.md) (run, configure, deploy) ·
[backend/docs/](backend/docs/) (protocol, pipeline interface)

## Run locally

```bash
cd backend && uv sync --extra dev && uv run uvicorn app.main:app --reload   # http://localhost:8000, mock agents, no API key
cd frontend && pnpm install && pnpm dev                                     # http://localhost:3000/dev
```

## Built with

Python, FastAPI, uvicorn, Pydantic, openai SDK (via OpenRouter), httpx, SQLite, pytest, uv ·
Next.js, React, TypeScript, styled-components, lucide-react, Pretendard, ESLint, pnpm ·
nginx, systemd, GitHub Actions · Coding support tool: Claude Code
