# Frontend ↔ backend protocol

Types: `frontend/src/lib/csl/protocol.ts` (generated from `backend/app/protocol.py`; never edit by hand,
run `python scripts/gen_ts.py`).

## The short version (React)

```tsx
import { createSession, useCslSession } from "@/lib/csl";

const { sessionId } = await createSession({ topic, language: "en" });
const { snapshot, connection, error, actions } = useCslSession(sessionId);
```

`snapshot` is always the complete, current state of the session; render from it.
`src/app/dev/page.tsx` is a working example of everything below; the product pages (`src/app/page.tsx`,
`src/app/chat/ChatSession.tsx`) use the same calls.

**Free sessions for UI work.** `createSession({ topic, pipeline: "mock" })` runs that one session on the
scripted mock, whatever pipeline the server uses: no LLM calls, no cost, no access code. It replays the
"Why is summer hotter than winter?" scenario (en or ko) and ignores `topic`. Use it for frontend
development against the deployed server; leave `pipeline` out for the real agents.

**Other pipelines.** `pipeline` takes any name the server has registered. `fetchHealth()` returns them:
`{ pipeline, sessionPipelines, freePipelines }` (the server's default, the names a session can ask for, and
the ones among them that need no access code). The agent developers use this to try their pipeline on the
deployed server; `/dev` shows the list as the "Agents" selector.

**Signing in.** Login is a nickname only (no password; it identifies the learner, it is not access control).
`src/lib/csl` holds it:

```tsx
import { fetchUserSessions, signIn, signOut, useCurrentUser } from "@/lib/csl";

const user = useCurrentUser();                   // undefined while hydrating, null = signed out, else { userId, name }
await signIn("minsu");                           // a new nickname creates the user; remembered in this browser
const mine = await fetchUserSessions(user.userId); // their sessions, newest first: topic, phase, status, messageCount, updatedAt
signOut();
```

`createSession()` attaches the signed-in user by itself, so every session started while signed in is theirs
and shows up in `fetchUserSessions` from any browser. `<LoginCard />` (`src/common/components`) is the
sign-in form; `/mypage` lists the sessions and links to `/chat?session=<id>` (or `/?session=<id>` while a
session is still being set up); the start page shows the
form until someone is signed in. `snapshot.userId` says whose a session is (null = nobody's).

**Staying in a session.** The session id is all a page has to remember: the server keeps every session and
sends the full snapshot on connect. `src/lib/csl/browserSession.ts` keeps the id in the URL
(`?session=<id>`) and, for sessions without a user, a short list in localStorage:

```tsx
import { rememberSession, setCurrentSessionId, useCslSession, useCurrentSessionId, useRecentSessions } from "@/lib/csl";

const sessionId = useCurrentSessionId();        // undefined while hydrating, null = no session in the URL
const { snapshot, actions } = useCslSession(sessionId ?? null);

const created = await createSession({ topic });
rememberSession({ sessionId: created.sessionId, topic, pipeline: created.snapshot.pipeline, createdAt: created.snapshot.createdAt });
setCurrentSessionId(created.sessionId);          // reload, back button and a shared link now return here
setCurrentSessionId(null);                       // leave: the session pauses on the server and can be reopened
const recent = useRecentSessions();              // "continue where you left off"
```

If the id in the URL does not exist, `connection` becomes `closed` and `snapshot` stays `null`.

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
| `pipeline` | Which agents run the session: the server's default (e.g. `csl`) or the name the session asked for (e.g. `mock`) |
| `userId` | The signed-in learner who created the session, or null |

| `actions` | Effect |
| --- | --- |
| `replyInit(text)`, `finishInit()` | Answer the setup guide / skip the rest of the setup chat |
| `startDiscussion(language?)` | `ready` → `discussion`. With `"en"` or `"ko"` the discussion runs in that language from here on (`snapshot.language` changes); the classroom and the states built before stay as they were |
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
  a session after a reload, keep the `sessionId` and pass it to `useCslSession` (`useCurrentSessionId`
  above does this with the URL).
* **Errors.** When the agents fail, the discussion pauses and `error` is set. `resume()` retries.

## Wire format

REST (JSON, camelCase):

| | |
| --- | --- |
| `POST /api/sessions` `{ topic, language?, accessCode?, pipeline?, userId? }` | → `{ sessionId, snapshot }`. `pipeline` is a name from `sessionPipelines`; `"mock"` needs no access code. `userId` records the session as that user's. 403 = wrong access code, 404 = unknown user, 422 = unknown pipeline or empty topic, 429 / 503 = rate limit / server full |
| `GET /api/sessions/{id}` | → snapshot (404 = no such session) |
| `GET /api/health` | → `{ ok, pipeline, sessionPipelines, freePipelines, accessCodeRequired, activeSessions, protocolVersion }` |
| `POST /api/users/login` `{ name }` | → `{ user: { userId, name, createdAt }, created }`. 2 to 20 characters; 422 otherwise |
| `GET /api/users/{userId}` | → user (404 = unknown) |
| `GET /api/users/{userId}/sessions` | → `SessionSummary[]`, newest first |
| `/api/admin/*` | admin page only (`src/app/admin`, client `src/lib/csl/admin.ts`); see `backend/README.md` |

WebSocket `ws(s)://<host>/ws/sessions/{id}`. Close code 4404 = no such session, 4403 = origin not allowed.

Server → client: `{ "type", "seq", "ts", "data" }`

| `type` | `data` |
| --- | --- |
| `session.snapshot` | `SessionSnapshot`, first message after every connect |
| `phase.changed` | `{ phase, language, reason }` (`language`: the session language at that moment; `reason` on `ended`: `completed`, `turn_limit`, `user`) |
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

Client → server: `{ "type", "data" }` with `init.reply`, `init.finish`, `discussion.start` (`{ language? }`),
`user.message`, `control.pause`, `control.resume`, `control.step`, `control.set_pace`, `session.end`,
`ui.event`, `ping`.
