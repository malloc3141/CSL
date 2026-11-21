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
| `backend/app/main.py`, `users.py`, `protocol.py` | REST + WebSocket API, nickname login, and every message on the wire. |
| `frontend/src/app/` | Pages: `page.tsx` (start), `chat/` (classroom), `mypage/` (sign in, continue a session), `dev/` (bare page over the whole flow), `admin/` (usage, models, session history). |
| `frontend/src/lib/csl/` | Connection to the backend: generated types, WebSocket client, `useCslSession` hook. |
| `deploy/`, `.github/workflows/` | systemd units, proxy examples, and the deploy on every push to `main`. |

More: [HANDOFF.md](HANDOFF.md) (who works where, 한국어 / English) ·
[backend/README.md](backend/README.md) (run, configure, deploy) ·
[backend/docs/](backend/docs/) (protocol, pipeline interface)

## Run locally

Set up dependencies from the repository root on the first run:

```bash
(cd backend && uv sync --extra dev)
(cd frontend && pnpm install)
```

Start both development servers from the repository root with Bash 4.3 or newer:

```bash
./dev.sh
```

Open [the development page](http://localhost:3000/dev). The backend listens on
`http://localhost:8000` and defaults to mock agents, which need no API key.
Press `Ctrl+C` to stop both servers.

## Built with

Python, FastAPI, uvicorn, Pydantic, openai SDK (via OpenRouter), httpx, SQLite, pytest, uv ·
Next.js, React, TypeScript, styled-components, lucide-react, Pretendard, ESLint, pnpm ·
nginx, systemd, GitHub Actions · Coding support tool: Claude Code
