# CSL

2026F CS473 Term Project (Team CSTL) - Classroom Simulation for Learning

A learner watches, inspects and joins a discussion between a tutor agent and peer agents that hold
different, partly wrong mental models of a topic, in order to notice gaps in their own understanding.

Live prototype: https://csl.kimhm.in

## Spec

`frontend/` is the UI (Next.js, TypeScript) and `backend/` runs the agents (Python, FastAPI).

 They communicate over REST and single WebSocket per session. Entry points: `frontend/src/app/page.tsx` and `backend/app/main.py`.

Main features are implemented in...

| Feature | Frontend (`frontend/src/`) | Backend (`backend/app/`) |
| --- | --- | --- |
| Set up a classroom for a topic | `app/page.tsx` | `pipeline/csl/knowledge.py` |
| Observe the discussion | `app/chat/ChatSession.tsx` | `orchestrator.py` (turn loop, pace, pause), `pipeline/csl/discussion.py` (who speaks next, what they say) |
| Inspect each peer's understanding and how it changes | understanding panel in `app/chat/ChatSession.tsx` | `pipeline/csl/_state_updates.py` |
| Explain your own understanding, get peer reactions and tutor feedback | message box in `app/chat/ChatSession.tsx` | `orchestrator.py` (the learner can interject at any time), `pipeline/csl/discussion.py` |

Shared by all of them: `frontend/src/lib/csl/` (WebSocket client, `useCslSession` hook) and
`backend/app/protocol.py` (every message on the wire; the frontend types are generated from it).

## Run locally

```bash
(cd backend && uv sync --extra dev)   # first run only
(cd frontend && pnpm install)         # first run only
./dev.sh                              # both dev servers; Bash 4.3 or newer
```

Open http://localhost:3000. The backend (`http://localhost:8000`) defaults to mock agents, which need
no API key.
