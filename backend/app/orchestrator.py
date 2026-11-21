"""Runs sessions: one asyncio task per session drives the phases
init -> building -> ready -> discussion -> ended and talks to the pipeline.

How a discussion turn works
---------------------------
1. `select_speaker` and `speak` start right away, while the learner is still
   reading the previous message. The text is buffered.
2. The turn becomes visible when the *gate* opens: the reading gap has passed
   (auto pace), or the learner pressed "next" (control.step). From then on the
   text is streamed live.
3. When the utterance is complete the message is committed, `update_states`
   runs, and the next turn starts.

A learner message at any time throws the unfinished turn away (turn.cancelled
if it was already visible), is committed, and the agents respond to it.
Pausing never cuts a visible message short; it only keeps the gate closed.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from .config import Settings
from .pipeline import SESSION_PIPELINES, make_pipeline
from .pipeline.base import Classroom, Pipeline, PipelineError, SpeakerDecision
from .protocol import (
    ActiveTurn,
    Belief,
    Channel,
    ClassroomReady,
    ErrorEvent,
    KnowledgeState,
    Language,
    Message,
    MessageCompleted,
    MessageDelta,
    PaceChanged,
    PhaseChanged,
    Phase,
    Role,
    StateChange,
    StateUpdated,
    StateVersion,
    Status,
    StatusChanged,
    TurnCancelled,
    UserInvited,
    Wire,
)
from .session import Session, current_session, new_id
from .store import Store

log = logging.getLogger("csl.orchestrator")

GUIDE_NAME = {"ko": "가이드", "en": "Guide"}
USER_NAME = {"ko": "나", "en": "You"}
INTERRUPTING = {"user.message", "session.end"}


class Connection:
    """Outbound queue of one WebSocket. `push` never blocks the orchestrator."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue(maxsize=2000)

    def push(self, envelope: dict[str, Any]) -> bool:
        try:
            self.queue.put_nowait(envelope)
            return True
        except asyncio.QueueFull:
            return False

    def close(self) -> None:
        while True:
            try:
                self.queue.put_nowait(None)
                return
            except asyncio.QueueFull:
                self.queue.get_nowait()


def diff_states(before: KnowledgeState, after: KnowledgeState) -> list[StateChange]:
    changes: list[StateChange] = []
    old = {b.id: b for b in before.beliefs}
    new = {b.id: b for b in after.beliefs}
    for bid, b in new.items():
        if bid not in old:
            changes.append(StateChange(field="beliefs", kind="added", after=b.text, belief_id=bid))
        elif old[bid].text != b.text or old[bid].accuracy != b.accuracy:
            changes.append(
                StateChange(field="beliefs", kind="modified", before=old[bid].text, after=b.text, belief_id=bid)
            )
    for bid, b in old.items():
        if bid not in new:
            changes.append(StateChange(field="beliefs", kind="removed", before=b.text, belief_id=bid))
    if before.explanation != after.explanation or before.explanation_accuracy != after.explanation_accuracy:
        changes.append(
            StateChange(
                field="explanation",
                kind="modified" if before.explanation else "added",
                before=before.explanation or None,
                after=after.explanation or None,
            )
        )
    for q in after.open_questions:
        if q not in before.open_questions:
            changes.append(StateChange(field="openQuestions", kind="added", after=q))
    for q in before.open_questions:
        if q not in after.open_questions:
            changes.append(StateChange(field="openQuestions", kind="removed", before=q))
    return changes


def _normalize_state(state: KnowledgeState) -> KnowledgeState:
    """Give every belief a unique, non-empty id."""
    seen: set[str] = set()
    beliefs: list[Belief] = []
    for i, b in enumerate(state.beliefs):
        bid = b.id if b.id and b.id not in seen else f"b{i + 1}-{new_id()[:6]}"
        seen.add(bid)
        beliefs.append(b if bid == b.id else b.model_copy(update={"id": bid}))
    return state.model_copy(update={"beliefs": beliefs})


class _TurnSink:
    """Collects an utterance. Buffers until opened, then streams deltas."""

    def __init__(self, runner: "SessionRunner", turn: ActiveTurn):
        self.runner = runner
        self.turn = turn
        self.text = ""
        self.opened = False

    async def write(self, text: str) -> None:
        if not text:
            return
        self.text += text
        if self.opened:
            self.turn.text = self.text
            self.runner.emit("message.delta", MessageDelta(turn_id=self.turn.turn_id, text=text), persist=False)

    def open(self) -> None:
        if self.opened:
            return
        self.opened = True
        self.runner.session.active_turn = self.turn
        self.runner.emit("turn.started", self.turn)
        if self.text:
            self.turn.text = self.text
            self.runner.emit(
                "message.delta", MessageDelta(turn_id=self.turn.turn_id, text=self.text), persist=False
            )


class SessionRunner:
    def __init__(self, session: Session, pipeline: Pipeline, store: Store, settings: Settings):
        self.session = session
        self.pipeline = pipeline
        self.store = store
        self.settings = settings
        self.inbox: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self.connections: set[Connection] = set()
        self.last_activity = time.time()
        self.task: Optional[asyncio.Task] = None
        # gate: reading gap of `_gate_base` seconds (at speed 1) counted from `_gate_from`
        self._wake = asyncio.Event()
        self._gate_from = 0.0
        self._gate_base = 0.0
        self._step_credit = False
        self._committing = False
        self._error_hold = False
        self._auto_paused = False
        session.log = lambda type_, data: self.emit(type_, data, broadcast=False)

    # ------------------------------------------------------------------ lifecycle / io

    def start(self) -> None:
        self.task = asyncio.create_task(self._run(), name=f"session-{self.session.id}")

    async def stop(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
        for conn in list(self.connections):
            conn.close()
        self.connections.clear()
        self.session.active_turn = None
        self._save()

    def emit(self, type_: str, data: Wire | dict[str, Any], *, persist: bool = True, broadcast: bool = True) -> None:
        s = self.session
        payload = data.wire() if isinstance(data, Wire) else data
        ts = time.time()
        seq: Optional[int] = None
        if persist:
            s.seq += 1
            seq = s.seq
            self.store.log_event(s.id, seq, ts, type_, payload)
        if broadcast:
            envelope = {"type": type_, "seq": seq, "ts": ts, "data": payload}
            for conn in list(self.connections):
                if not conn.push(envelope):
                    self.connections.discard(conn)
                    conn.close()

    def attach(self, conn: Connection) -> None:
        """Register a WebSocket. It first receives the full snapshot, then live events."""
        conn.push({"type": "session.snapshot", "seq": None, "ts": time.time(), "data": self.session.snapshot().wire()})
        self.connections.add(conn)
        self.last_activity = time.time()
        self.emit("client.connected", {"connections": len(self.connections)}, broadcast=False)
        if self._auto_paused:
            self.inbox.put_nowait(("_auto_resume", None))

    def detach(self, conn: Connection) -> None:
        self.connections.discard(conn)
        self.last_activity = time.time()
        self.emit("client.disconnected", {"connections": len(self.connections)}, broadcast=False)
        if not self.connections:
            # Nobody is watching: stop spending tokens.
            self.inbox.put_nowait(("_auto_pause", None))

    def submit(self, type_: str, data: Wire) -> None:
        """Queue a validated client command."""
        self.last_activity = time.time()
        self.emit(f"client.{type_}", data, broadcast=False)
        self.inbox.put_nowait((type_, data))

    def _save(self) -> None:
        s = self.session
        self.store.save_session(s.id, s.topic, s.created_at, s.dump(), s.user_id)

    # ------------------------------------------------------------------ state helpers

    def _set_phase(self, phase: Phase, reason: Optional[str] = None) -> None:
        s = self.session
        s.phase = phase
        if phase == "discussion":
            s.status = "running"
            self._open_gate_now()
        if phase == "ended":
            s.active_turn = None
            s.invited_turn_id = None
        self.emit("phase.changed", PhaseChanged(phase=phase, reason=reason))
        if phase == "discussion":
            self.emit("status.changed", StatusChanged(status=s.status))
        self._save()

    def _set_status(self, status: Status) -> None:
        s = self.session
        if s.status == status:
            return
        s.status = status
        self.emit("status.changed", StatusChanged(status=status))
        self._wake.set()
        self._save()

    def _open_gate_now(self) -> None:
        """Let the next turn appear without a reading gap."""
        self._gate_from = asyncio.get_running_loop().time()
        self._gate_base = 0.0
        if not self.session.pace.auto:
            self._step_credit = True
        self._wake.set()

    def _error(self, code: str, message: str, *, recoverable: bool = True) -> None:
        self.emit("error", ErrorEvent(code=code, message=message, recoverable=recoverable))

    def _report_failure(self, exc: BaseException, what: str) -> None:
        log.error("session %s: %s failed: %r", self.session.id, what, exc, exc_info=exc)
        self.session.log("server.error", {"what": what, "detail": repr(exc)})
        code = "timeout" if isinstance(exc, TimeoutError) else "pipeline_error"
        if isinstance(exc, PipelineError) or self.settings.debug:
            detail = str(exc) or type(exc).__name__
        else:
            detail = "The agents could not respond."
        self._error(code, f"{what}: {detail}")

    def _commit_message(
        self,
        *,
        message_id: str,
        channel: Channel,
        role: Role,
        speaker_id: str,
        speaker_name: str,
        text: str,
        peer_index: Optional[int] = None,
        invited: bool = False,
        client_message_id: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> Message:
        s = self.session
        message = Message(
            id=message_id,
            channel=channel,
            role=role,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            peer_index=peer_index,
            text=text,
            turn_number=s.turn_count + 1 if channel == "discussion" else None,
            invited=invited,
            client_message_id=client_message_id,
            meta=meta or {},
            created_at=time.time(),
        )
        s.messages.append(message)
        if s.active_turn and s.active_turn.turn_id == message_id:
            s.active_turn = None
        self.emit("message.completed", MessageCompleted(message=message))
        return message

    def _discard(self, sink: Optional[_TurnSink], reason: str) -> None:
        s = self.session
        if sink and sink.opened and s.active_turn and s.active_turn.turn_id == sink.turn.turn_id:
            s.active_turn = None
            self.emit("turn.cancelled", TurnCancelled(turn_id=sink.turn.turn_id, reason=reason))  # type: ignore[arg-type]

    async def _apply_state_updates(self, message: Message) -> None:
        s = self.session
        try:
            async with asyncio.timeout(self.settings.turn_timeout_seconds):
                updates = await self.pipeline.update_states(s, message)
        except Exception as exc:  # state tracking must never stall the discussion
            log.error("session %s: update_states failed: %r", s.id, exc, exc_info=exc)
            s.log("server.error", {"what": "update_states", "detail": repr(exc)})
            return
        for update in updates or []:
            versions = s.states.get(update.agent_id)
            if not versions:
                continue
            prev = versions[-1]
            state = _normalize_state(update.state)
            if state == prev.state:
                continue
            changes = update.changes if update.changes is not None else diff_states(prev.state, state)
            version = StateVersion(
                agent_id=update.agent_id,
                version=prev.version + 1,
                turn_id=message.id,
                turn_number=message.turn_number,
                state=state,
                changes=changes,
                created_at=time.time(),
            )
            versions.append(version)
            self.emit("state.updated", StateUpdated(update=version))

    async def _handle_common(self, ctype: str, data: Any) -> None:
        s = self.session
        if ctype == "control.set_pace":
            pace = s.pace.model_copy()
            if data.auto is not None:
                pace.auto = data.auto
            if data.speed is not None:
                pace.speed = data.speed
            s.pace = pace
            self.emit("pace.changed", PaceChanged(pace=pace))
            self._wake.set()
            self._save()
        elif ctype == "session.end":
            if s.phase != "ended":
                self._set_phase("ended", "user")
        elif ctype in ("ui.event", "_auto_pause", "_auto_resume"):
            pass  # ui.event is only logged (in submit)
        else:
            self._error("invalid_command", f"'{ctype}' is not valid in phase '{s.phase}'.")

    # ------------------------------------------------------------------ main loop

    async def _run(self) -> None:
        current_session.set(self.session)
        s = self.session
        try:
            while True:
                if s.phase == "init":
                    await self._phase_init()
                elif s.phase == "building":
                    await self._phase_building()
                elif s.phase == "ready":
                    await self._phase_ready()
                elif s.phase == "discussion":
                    await self._phase_discussion()
                else:
                    await self._handle_common(*(await self.inbox.get()))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - a bug in the orchestrator itself
            log.exception("session %s crashed", s.id)
            s.log("server.error", {"what": "orchestrator", "detail": repr(exc)})
            self._error("internal_error", "The session stopped because of a server error.", recoverable=False)

    # ------------------------------------------------------------------ init chat

    async def _phase_init(self) -> None:
        s = self.session
        failed = False
        while s.phase == "init":
            transcript = s.init_transcript
            if not failed and (not transcript or transcript[-1].role == "user"):
                done = await self._init_agent_turn()
                if done is None:
                    failed = True
                elif done:
                    self._set_phase("building")
                continue
            ctype, data = await self.inbox.get()
            if ctype == "init.reply":
                failed = False
                text = data.text.strip()[: self.settings.max_user_message_chars]
                if text:
                    self._commit_message(
                        message_id=new_id(), channel="init", role="user", speaker_id="user",
                        speaker_name=USER_NAME[s.language], text=text,
                    )
                    self._save()
            elif ctype == "control.resume" and failed:
                failed = False
            elif ctype == "init.finish":
                self._set_phase("building")
            else:
                await self._handle_common(ctype, data)

    async def _init_agent_turn(self) -> Optional[bool]:
        """Returns InitResult.done, or None if the pipeline failed."""
        s = self.session
        turn = ActiveTurn(
            turn_id=new_id(), channel="init", role="system", speaker_id="guide", speaker_name=GUIDE_NAME[s.language]
        )
        sink = _TurnSink(self, turn)
        sink.open()
        try:
            async with asyncio.timeout(self.settings.turn_timeout_seconds):
                result = await self.pipeline.init_turn(s, sink)
            text = sink.text.strip()
            if not text:
                raise PipelineError("init_turn wrote no text")
        except asyncio.CancelledError:
            self._discard(sink, "interrupted")
            raise
        except Exception as exc:
            self._discard(sink, "error")
            self._report_failure(exc, "init_turn")
            return None
        self._commit_message(
            message_id=turn.turn_id, channel="init", role="system", speaker_id="guide",
            speaker_name=turn.speaker_name, text=text,
        )
        self._save()
        return bool(result.done)

    # ------------------------------------------------------------------ classroom

    async def _phase_building(self) -> None:
        s = self.session
        try:
            async with asyncio.timeout(self.settings.turn_timeout_seconds):
                classroom = await self.pipeline.build_classroom(s)
            self._install_classroom(classroom)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._report_failure(exc, "build_classroom")
            while s.phase == "building":
                ctype, data = await self.inbox.get()
                if ctype in ("control.resume", "init.finish"):
                    return  # the main loop calls _phase_building again
                await self._handle_common(ctype, data)
            return
        self._set_phase("ready")

    def _install_classroom(self, classroom: Classroom) -> None:
        s = self.session
        participants = []
        ids: set[str] = set()
        peer_index = 0
        for p in classroom.participants:
            if not p.id or p.id in ids or p.id in ("user", "guide"):
                raise PipelineError(f"participant ids must be unique and not reserved: {p.id!r}")
            ids.add(p.id)
            if p.role == "peer":
                p = p.model_copy(update={"peer_index": peer_index})
                peer_index += 1
            participants.append(p)
        if peer_index == 0:
            raise PipelineError("build_classroom returned no peers")
        now = time.time()
        states = {
            p.id: [
                StateVersion(
                    agent_id=p.id,
                    version=0,
                    state=_normalize_state(classroom.states.get(p.id) or KnowledgeState()),
                    created_at=now,
                )
            ]
            for p in participants
            if p.role == "peer"
        }
        s.participants = participants
        s.focus = classroom.focus
        s.states = states
        self.emit(
            "classroom.ready",
            ClassroomReady(participants=participants, focus=s.focus, states={k: v[0] for k, v in states.items()}),
        )

    async def _phase_ready(self) -> None:
        s = self.session
        while s.phase == "ready":
            ctype, data = await self.inbox.get()
            if ctype == "discussion.start":
                self._set_phase("discussion")
            else:
                await self._handle_common(ctype, data)

    # ------------------------------------------------------------------ discussion

    async def _phase_discussion(self) -> None:
        s = self.session
        turn_task: Optional[asyncio.Task] = None
        get_task: Optional[asyncio.Task] = None
        try:
            while s.phase == "discussion":
                if s.turn_count >= s.turn_limit:
                    if turn_task is not None:
                        await self._abort_turn(turn_task)
                        turn_task = None
                    self._set_phase("ended", "turn_limit")
                    break
                if turn_task is None and s.status != "waiting_user" and not self._error_hold:
                    turn_task = asyncio.create_task(self._agent_turn())
                if get_task is None:
                    get_task = asyncio.create_task(self.inbox.get())
                waiting = {get_task} if turn_task is None else {get_task, turn_task}
                done, _ = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
                if turn_task is not None and turn_task in done:
                    turn_task.result()  # _agent_turn reports its own failures
                    turn_task = None
                if get_task in done:
                    ctype, data = get_task.result()
                    get_task = None
                    if ctype in INTERRUPTING and turn_task is not None:
                        await self._abort_turn(turn_task)
                        turn_task = None
                    await self._handle_discussion_command(ctype, data)
        finally:
            for task in (turn_task, get_task):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*(t for t in (turn_task, get_task) if t is not None), return_exceptions=True)

    async def _abort_turn(self, turn_task: asyncio.Task) -> None:
        if not self._committing:
            turn_task.cancel()
        # If the message is being committed, let it finish: it is already part of the discussion.
        await asyncio.gather(turn_task, return_exceptions=True)

    async def _handle_discussion_command(self, ctype: str, data: Any) -> None:
        s = self.session
        if s.phase != "discussion":
            await self._handle_common(ctype, data)
        elif ctype == "user.message":
            await self._on_user_message(data)
        elif ctype == "control.pause":
            self._auto_paused = False
            self._set_status("paused" if s.status == "running" else s.status)
        elif ctype == "_auto_pause":
            # The last client left. Resume by itself when one comes back.
            if not self.connections and s.status == "running":
                self._auto_paused = True
                self._set_status("paused")
        elif ctype == "_auto_resume":
            if self._auto_paused and s.status == "paused":
                self._set_status("running")
            self._auto_paused = False
        elif ctype == "control.resume":
            self._error_hold = False
            self._auto_paused = False
            if s.status == "waiting_user":
                s.invited_turn_id = None
                self._open_gate_now()
            self._set_status("running")
            self._wake.set()
        elif ctype == "control.step":
            self._error_hold = False
            if s.status == "waiting_user":
                s.invited_turn_id = None
                self._set_status("running" if s.pace.auto else "paused")
            self._step_credit = True
            self._wake.set()
        else:
            await self._handle_common(ctype, data)

    async def _on_user_message(self, data: Any) -> None:
        s = self.session
        text = data.text.strip()[: self.settings.max_user_message_chars]
        if not text:
            return
        invited = s.status == "waiting_user"
        s.invited_turn_id = None
        message = self._commit_message(
            message_id=new_id(), channel="discussion", role="user", speaker_id="user",
            speaker_name=USER_NAME[s.language], text=text, invited=invited,
            client_message_id=data.client_message_id,
        )
        await self._apply_state_updates(message)
        self._error_hold = False
        self._step_credit = False
        self._open_gate_now()  # the agents answer right away
        self._set_status("running")
        self._save()

    def _gap_for(self, text: str) -> float:
        st = self.settings
        return min(st.pace_base_seconds + len(text) * st.pace_seconds_per_char, st.pace_max_seconds)

    async def _wait_gate(self) -> None:
        s = self.session
        loop = asyncio.get_running_loop()
        while True:
            if self._step_credit:
                self._step_credit = False
                return
            timeout: Optional[float] = None
            if s.status == "running" and s.pace.auto:
                timeout = self._gate_from + self._gate_base / max(s.pace.speed, 0.01) - loop.time()
                if timeout <= 0:
                    return
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout)
            except asyncio.TimeoutError:
                pass

    async def _speak(self, decision: SpeakerDecision, sink: _TurnSink) -> None:
        async with asyncio.timeout(self.settings.turn_timeout_seconds):
            await self.pipeline.speak(self.session, decision, sink)

    async def _agent_turn(self) -> None:
        s = self.session
        sink: Optional[_TurnSink] = None
        children: list[asyncio.Task] = []
        try:
            async with asyncio.timeout(self.settings.turn_timeout_seconds):
                decision = await self.pipeline.select_speaker(s)
            if decision.end:
                await self._wait_gate()
                self._set_phase("ended", "completed")
                return
            agent = s.participant(decision.agent_id or "")
            if agent is None:
                raise PipelineError(f"select_speaker returned unknown agent {decision.agent_id!r}")
            turn = ActiveTurn(
                turn_id=new_id(), channel="discussion", role=agent.role, speaker_id=agent.id,
                speaker_name=agent.name, peer_index=agent.peer_index,
            )
            sink = _TurnSink(self, turn)
            speak = asyncio.create_task(self._speak(decision, sink))
            gate = asyncio.create_task(self._wait_gate())
            children += [speak, gate]
            await asyncio.wait({speak, gate}, return_when=asyncio.FIRST_COMPLETED)
            if speak.done():
                speak.result()  # raise early if generation already failed
            await gate
            sink.open()
            await speak
            text = sink.text.strip()
            if not text:
                raise PipelineError("speak wrote no text")

            self._committing = True
            try:
                message = self._commit_message(
                    message_id=turn.turn_id, channel="discussion", role=agent.role, speaker_id=agent.id,
                    speaker_name=agent.name, peer_index=agent.peer_index, text=text, meta=decision.meta,
                )
                self._gate_from = asyncio.get_running_loop().time()
                self._gate_base = self._gap_for(text)
                await self._apply_state_updates(message)
                if decision.invite_user:
                    s.invited_turn_id = message.id
                    self._set_status("waiting_user")
                    self.emit("user.invited", UserInvited(turn_id=message.id))
                self._save()
            finally:
                self._committing = False
        except asyncio.CancelledError:
            self._discard(sink, "interrupted")
            raise
        except Exception as exc:
            self._discard(sink, "error")
            self._report_failure(exc, "agent turn")
            self._error_hold = True  # no automatic retry: wait for resume / step / a learner message
            if s.status == "running":
                self._set_status("paused")
        finally:
            for task in children:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*children, return_exceptions=True)


class SessionRegistry:
    """All live sessions of this process. Restores evicted ones from the store."""

    def __init__(self, settings: Settings, store: Store, pipeline: Pipeline):
        self.settings = settings
        self.store = store
        self.pipeline = pipeline
        # Pipelines sessions asked for by name (SESSION_PIPELINES), created on first use.
        self._named: dict[str, Pipeline] = {}
        self.runners: dict[str, SessionRunner] = {}
        self._restore_lock = asyncio.Lock()
        self._janitor: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._janitor = asyncio.create_task(self._evict_idle(), name="session-janitor")

    async def stop(self) -> None:
        if self._janitor:
            self._janitor.cancel()
            await asyncio.gather(self._janitor, return_exceptions=True)
        for runner in list(self.runners.values()):
            await runner.stop()
        self.runners.clear()

    @property
    def has_capacity(self) -> bool:
        return len(self.runners) < self.settings.max_active_sessions

    def knows_pipeline(self, name: str) -> bool:
        return name == self.pipeline.name or name in SESSION_PIPELINES

    def pipeline_for(self, name: Optional[str]) -> Pipeline:
        """The pipeline that runs a session: the server's PIPELINE (no name, or its own name), or the
        entry of SESSION_PIPELINES the session asked for.

        Raises KeyError for a name that is not registered and whatever the import raises for an entry
        that cannot be loaded. One instance per name serves all its sessions.
        """
        if not name or name == self.pipeline.name:
            return self.pipeline
        pipeline = self._named.get(name)
        if pipeline is None:
            if name not in SESSION_PIPELINES:
                raise KeyError(name)
            pipeline = make_pipeline(name)
            if type(pipeline) is type(self.pipeline):
                pipeline = self.pipeline  # the server already runs this class
            elif name == "mock":
                pipeline.delay = self.settings.mock_chunk_delay  # type: ignore[attr-defined]
            self._named[name] = pipeline
        return pipeline

    def create(
        self, topic: str, language: Language, pipeline: Optional[str] = None, user_id: Optional[str] = None
    ) -> SessionRunner:
        chosen = self.pipeline_for(pipeline)
        session = Session(new_id(), topic.strip(), language, self.settings.max_turns)
        session.pipeline = pipeline or self.pipeline.name
        session.user_id = user_id
        runner = SessionRunner(session, chosen, self.store, self.settings)
        self.runners[session.id] = runner
        runner.emit(
            "session.created",
            {"topic": session.topic, "language": language, "pipeline": session.pipeline, "userId": user_id},
            broadcast=False,
        )
        runner._save()
        runner.start()
        return runner

    async def get(self, session_id: str) -> Optional[SessionRunner]:
        runner = self.runners.get(session_id)
        if runner is not None:
            return runner
        async with self._restore_lock:
            runner = self.runners.get(session_id)
            if runner is not None:
                return runner
            raw = await self.store.load_session(session_id)
            if raw is None:
                return None
            session = Session.restore(raw)
            # A session keeps the pipeline it was created with. If that one is gone (not registered
            # any more, fails to load, or stored before per-session pipelines), the server's PIPELINE
            # takes over.
            try:
                chosen = self.pipeline_for(session.pipeline)
            except Exception as exc:
                log.warning("session %s: pipeline %r unavailable (%r), using %s",
                            session_id, session.pipeline, exc, self.pipeline.name)
                chosen, session.pipeline = self.pipeline, ""
            session.pipeline = session.pipeline or self.pipeline.name
            runner = SessionRunner(session, chosen, self.store, self.settings)
            self.runners[session_id] = runner
            runner.emit("session.restored", {}, broadcast=False)
            runner.start()
            return runner

    async def _evict_idle(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = time.time()
            for sid, runner in list(self.runners.items()):
                if runner.connections:
                    continue
                limit = 300 if runner.session.phase == "ended" else self.settings.session_idle_minutes * 60
                if now - runner.last_activity > limit:
                    self.runners.pop(sid, None)
                    await runner.stop()
