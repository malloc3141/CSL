# Frontend ↔ backend protocol

Types: `frontend/src/lib/csl/protocol.ts` (generated from `backend/app/protocol.py`; never edit by hand,
run `python scripts/gen_ts.py`).

## The short version (React)

```tsx
import { createSession, useCslSession } from "@/lib/csl";

const { sessionId } = await createSession({ topic, language: "ko" });
const { snapshot, connection, error, actions } = useCslSession(sessionId);
```

`snapshot` is always the complete, current state of the session; render from it.
`src/app/dev/page.tsx` is a working example of everything below.

| `snapshot` field | Use |
| --- | --- |
| `phase` | `init` (setup chat) → `building` (classroom being created) → `ready` (show the classroom, wait for start) → `discussion` → `ended` |
| `status` | In `discussion`: `running`, `paused`, or `waiting_user` (the tutor asked the learner to explain) |
| `messages` | All messages. `channel` is `init` or `discussion`; `role` is `system` (the setup guide), `tutor`, `peer`, `user`; `peerIndex` picks the peer colour; `turnNumber` is the position in the discussion |
| `activeTurn` | The message being generated now. Show it as a bubble with a typing indicator while `text` is empty |
| `participants` | Tutor and peers, with `origin` and `description` for the classroom cards |
| `states[agentId]` | Every version of a peer's knowledge state, oldest first. The last one is current. Each version has `turnId` / `turnNumber` (the message that caused it) and `changes` (what to mark as changed) |
| `invitedTurnId` | Set while the tutor waits for the learner's explanation |
| `pace` | `{ auto, speed }` |
| `focus` | One line: what the session is built around |

| `actions` | Effect |
| --- | --- |
| `replyInit(text)`, `finishInit()` | Answer the setup guide / skip the rest of the setup chat |
| `startDiscussion()` | `ready` → `discussion` |
| `say(text)` | Learner message. Allowed at any moment; the agents drop what they were about to say and respond |
| `pause()`, `resume()` | `resume` also retries after an error and passes on the tutor's invitation |
| `step()` | Show the next message now |
| `setPace({ auto, speed })` | `auto: false` = advance only on `step()`. `speed` 0.25–4 scales the reading gap |
| `end()` | End the session |
| `track(name, data)` | Log a UI interaction the server cannot see (e.g. `track("panel.open", { agentId })`). Use it for anything we want to count later |

`connection` is `connecting | open | reconnecting | closed`. `error` is the last `error` event
(`{ code, message, recoverable }`) and clears itself when the session moves on.

## Behaviour worth knowing

* **Pacing.** After an agent message the server waits a reading gap (longer for longer messages, divided
  by `pace.speed`) before showing the next one. The next message is usually generated during the gap, so
  it tends to arrive complete: `turn.started` and the whole text come together. If the model is slower
  than the gap you get `turn.started` first, then the text in pieces.
* **Pause** never cuts a visible message short; it stops the next one from appearing.
* **Interruption.** If the learner speaks while a message is streaming, that message is withdrawn
  (`turn.cancelled`, `activeTurn` becomes null) and the learner's message is added.
* **Leaving and returning.** Closing the tab pauses the discussion; reconnecting resumes it. On every
  (re)connect the server sends the full snapshot, so the client never has to replay anything. To continue
  a session after a reload, keep the `sessionId` (URL or sessionStorage) and pass it to `useCslSession`.
* **Errors.** When the agents fail, the discussion pauses and `error` is set. `resume()` retries.

## Wire format

REST (JSON, camelCase):

| | |
| --- | --- |
| `POST /api/sessions` `{ topic, language?, accessCode? }` | → `{ sessionId, snapshot }` |
| `GET /api/sessions/{id}` | → snapshot |
| `/api/admin/*` | admin page only (`src/app/admin`, client `src/lib/csl/admin.ts`); see `backend/README.md` |

WebSocket `ws(s)://<host>/ws/sessions/{id}`. Close code 4404 = no such session, 4403 = origin not allowed.

Server → client: `{ "type", "seq", "ts", "data" }`

| `type` | `data` |
| --- | --- |
| `session.snapshot` | `SessionSnapshot`, first message after every connect |
| `phase.changed` | `{ phase, reason }` (`reason` on `ended`: `completed`, `turn_limit`, `user`) |
| `status.changed` | `{ status }` |
| `pace.changed` | `{ pace }` |
| `classroom.ready` | `{ participants, focus, states }` |
| `turn.started` | `ActiveTurn` |
| `message.delta` | `{ turnId, text }` (append) |
| `message.completed` | `{ message }`; `message.id` equals the `turnId` |
| `turn.cancelled` | `{ turnId, reason }` |
| `state.updated` | `{ update: StateVersion }` |
| `user.invited` | `{ turnId }` |
| `error` | `{ code, message, recoverable }` |

Client → server: `{ "type", "data" }` with `init.reply`, `init.finish`, `discussion.start`,
`user.message`, `control.pause`, `control.resume`, `control.step`, `control.set_pace`, `session.end`,
`ui.event`, `ping`.
