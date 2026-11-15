# Plugging in the agents

The server owns sessions, timing, the WebSocket and storage. The agents are one class with five async
methods (`app/pipeline/base.py`). Implement it, set `PIPELINE=your.module:YourPipeline` in `backend/.env`,
and it runs behind the same frontend.

```python
from app.llm import get_llm
from app.pipeline import Classroom, InitResult, SpeakerDecision, StateUpdate, TextSink
from app.protocol import KnowledgeState, Belief, Message, Participant
from app.session import Session

class MyPipeline:
    name = "my-pipeline"

    async def init_turn(self, session: Session, out: TextSink) -> InitResult: ...
    async def build_classroom(self, session: Session) -> Classroom: ...
    async def select_speaker(self, session: Session) -> SpeakerDecision: ...
    async def speak(self, session: Session, decision: SpeakerDecision, out: TextSink) -> None: ...
    async def update_states(self, session: Session, message: Message) -> list[StateUpdate]: ...
```

`app/pipeline/baseline.py` is a complete example on OpenRouter; `mock.py` is one without an LLM.

## When each method is called

| Method | Called | Returns |
| --- | --- | --- |
| `init_turn` | Once at the start, then after each learner reply in the setup chat | Write the guide's message to `out`. `InitResult(done=True)` ends the chat |
| `build_classroom` | After the setup chat | `Classroom(participants, states, focus)`: one tutor, the peers, each peer's initial `KnowledgeState` |
| `select_speaker` | Before every agent turn | `SpeakerDecision(agent_id=...)`. `invite_user=True` makes the server wait for the learner's explanation after this utterance. `end=True` ends the discussion |
| `speak` | Right after `select_speaker` | Write the utterance to `out` (`await out.write(chunk)`; streaming or all at once) |
| `update_states` | Exactly once after every message that entered the discussion, agent or learner | The peers whose state changed, each as a complete new `KnowledgeState` |

Who owns what: turn allocation and learner participation are `select_speaker`; knowledge states are
`build_classroom` and `update_states`; `speak` uses both.

## What you can read

```python
session.topic, session.language            # "ko" | "en"
session.focus                              # from build_classroom
session.transcript                         # discussion messages, oldest first (agents and learner)
session.init_transcript                    # the setup chat
session.last_message, session.turn_count
session.participants, session.peers, session.tutor, session.participant(agent_id)
session.state_of(agent_id)                 # current KnowledgeState (a copy)
session.state_history(agent_id)            # all versions
session.scratch                            # your private dict, persisted with the session
```

A `Message` has `role` (`tutor` / `peer` / `user`), `speaker_id`, `speaker_name`, `text`, `turn_number`,
`invited` (the learner was answering the tutor's invitation) and `meta` (whatever you put in
`SpeakerDecision.meta`).

## Rules

1. **Do not append to `session.messages` or `session.states`.** Return values; the server applies them,
   versions the states and computes the diff shown in the panel.
2. **`select_speaker` and `speak` must not change anything.** The server generates the next turn while
   the learner is still reading, and throws it away if the learner speaks first. The same turn may be
   asked for twice. Put all bookkeeping in `update_states`.
3. **The learner can speak at any time.** `session.last_message.role == "user"` is a normal input to
   `select_speaker`. After an invitation the learner may also pass, in which case `select_speaker` is
   called again with the tutor's invitation still last.
4. **`session.scratch` must stay JSON-serializable.** It is how your internal state (a belief graph, a
   moderator's notes) survives a server restart. Do not keep per-session state on `self`.
5. **`KnowledgeState` is what the learner sees**, not necessarily what you store: `beliefs` (each with a
   stable `id`, `text`, optional `accuracy`), `explanation`, `explanation_accuracy`, `open_questions`.
   Keep a belief's `id` when it survives an update so the panel can show it as unchanged.
6. **Failures.** Raise `PipelineError("...")` (or let an exception escape): the discussion pauses, the
   learner sees an error and can retry. Each call has `TURN_TIMEOUT_SECONDS` (90 s).

## LLM calls

```python
llm = get_llm()                                           # OpenRouter, configured in .env
async for chunk in llm.stream(messages, temperature=0.8): # messages = [{"role": ..., "content": ...}]
    await out.write(chunk)
text = await llm.complete(messages)
data = await llm.complete_json(messages, fast=True)       # dict; fast=True uses OPENROUTER_MODEL_FAST
```

Every call is logged (`llm.call`) with model, latency, token usage and the cost OpenRouter reports; the
admin page (`/admin`) sums these. The model ids can be switched at runtime from the admin page, so do not
cache `settings.openrouter_model` yourself: pass `fast=True` / `fast=False` and let `get_llm()` pick. You may
use another client or framework inside the methods; the interface is all the server needs (but then your
calls are missing from the usage figures and ignore the model switch).

## Try it without the frontend

```bash
python scripts/cli.py "Why is summer hotter than winter?" --lang en --pipeline your.module:YourPipeline
```

Enter shows the next message, typing something sends it as the learner, `/state` prints the knowledge
states, `/auto` lets it run.
