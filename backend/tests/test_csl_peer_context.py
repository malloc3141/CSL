"""The knowledge-side handoff from a public situation to one peer's private understanding."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app import llm as llm_module
from app.orchestrator import Connection, SessionRunner
from app.pipeline.base import SpeakerDecision
from app.pipeline.csl import CslPipeline, discussion, knowledge
from app.pipeline.csl.prompting import cache_breakpoints, render_message
from app.protocol import Belief, KnowledgeState, Message, Participant, StateVersion
from app.session import Session


@pytest.fixture
def session():
    session = Session("example", "How should we read this poem?", "en", 60)
    session.participants = [
        Participant(id="tutor", name="Tutor", role="tutor"),
        Participant(id="peer1", name="Min", role="peer", origin="PRIVATE-ORIGIN"),
        Participant(id="peer2", name="June", role="peer", description="PRIVATE-PERSONA"),
    ]
    session.scratch["baseline"] = {"tutor": {"reference": "PRIVATE-KEY", "key_points": ["PRIVATE-POINT"]}}
    session.messages = [
        Message(id="setup", channel="init", role="user", speaker_id="user", speaker_name="Learner",
                text="PRIVATE-SETUP", created_at=0),
        Message(id="one", channel="discussion", role="tutor", speaker_id="tutor", speaker_name="Tutor",
                turn_number=1, text="What does the repeated image suggest?", created_at=1),
        Message(id="two", channel="discussion", role="user", speaker_id="user", speaker_name="Learner",
                turn_number=2, text="I read the image as a memory.", meta={"extra": "PRIVATE-META"}, created_at=2),
    ]
    states = {
        "peer1": KnowledgeState(
            beliefs=[Belief(id="private-id-1", text="I first compare where the image appears.", accuracy="partial")],
            explanation="I can find repetitions but cannot yet interpret their order.",
            open_questions=["Does the final repetition change its meaning?"],
        ),
        "peer2": KnowledgeState(
            beliefs=[Belief(id="private-id-2", text="The narrator treats silence as a sign of trust.")],
            explanation="I read the pause as an invitation to listen.",
            open_questions=["Whose voice interrupts the pause?"],
        ),
    }
    session.states = {
        peer_id: [StateVersion(agent_id=peer_id, version=0, state=state, created_at=0)]
        for peer_id, state in states.items()
    }
    return session


@pytest.fixture
def complete(monkeypatch):
    complete = AsyncMock(return_value="The learner interprets the recurring image as a memory.")
    monkeypatch.setattr(llm_module, "_llm", SimpleNamespace(complete=complete))
    return complete


@pytest.fixture
def stream(complete, monkeypatch):
    async def chunks(*args, **kwargs):
        yield "Min:"
        yield " I still have a question."

    stream = Mock(side_effect=chunks)
    monkeypatch.setattr(llm_module._llm, "stream", stream, raising=False)
    return stream


def state_texts(state):
    return [*(belief.text for belief in state.beliefs), state.explanation, *state.open_questions]


async def test_public_extraction_is_repeatable_and_independent_of_private_state(session, complete):
    original = session.dump()
    context = await knowledge.prepare_peer_context(session, "peer1", respond_to=1)
    assert await knowledge.prepare_peer_context(session, "peer1", respond_to=1) == context
    other_context = await knowledge.prepare_peer_context(session, "peer2", respond_to=1)
    assert session.dump() == original

    first, second = session.states["peer1"][-1], session.states["peer2"][-1]
    first_texts, second_texts = state_texts(first.state), state_texts(second.state)
    first.state, second.state = second.state, first.state
    swapped = session.dump()
    swapped_context = await knowledge.prepare_peer_context(session, "peer1", respond_to=1)
    assert session.dump() == swapped
    assert complete.await_count == 4
    calls = complete.await_args_list
    assert all(call == calls[0] for call in calls)
    messages = calls[0].args[0]
    kwargs = calls[0].kwargs
    assert (kwargs["fast"], kwargs["temperature"], kwargs["max_tokens"]) == (True, 0, 120)
    assert [b["text"] for b in messages[1]["content"][:-1]] == [
        render_message(message, session.language) for message in session.transcript
    ]
    assert "[T1]" in messages[1]["content"][-1]["text"]
    assert "cache_control" not in messages[1]["content"][-1]
    assert cache_breakpoints(messages) <= 4
    public = json.dumps(messages, ensure_ascii=False)
    assert "PRIVATE-" not in public
    assert all(text not in public for text in first_texts + second_texts)
    assert complete.return_value not in public
    assert complete.return_value in context
    assert all(text in context for text in first_texts)
    assert all(text not in context for text in second_texts)
    for response in (other_context, swapped_context):
        assert all(text in response for text in second_texts)
        assert all(text not in response for text in first_texts)
    first.state.beliefs[0].accuracy = "incorrect"
    first.state.explanation_accuracy = "incorrect"
    assert await knowledge.prepare_peer_context(session, "peer1", respond_to=1) == swapped_context


@pytest.mark.parametrize("invalid_target", [True, "1", 99])
async def test_invalid_target_uses_same_public_input_as_omitting_it(session, complete, invalid_target):
    await knowledge.prepare_peer_context(session, "peer1")
    await knowledge.prepare_peer_context(session, "peer1", respond_to=invalid_target)
    assert complete.await_count == 2
    assert complete.await_args_list[0] == complete.await_args_list[1]


async def test_speech_preserves_who_reported_an_explicit_experience(session, stream):
    personal_history = "I heard the author read the poem aloud."
    learner_history = "At our book club, we heard the final line twice."
    session.states["peer1"][-1].state.explanation = personal_history
    session.transcript[-1].text = learner_history

    await CslPipeline().speak(session, SpeakerDecision(agent_id="peer1"), SimpleNamespace(write=AsyncMock()))

    request = stream.call_args.args[0]
    transcript, tail = request[1]["content"][:-1], request[1]["content"][-1]["text"]
    assert transcript[-1]["text"] == render_message(session.transcript[-1], "en")
    assert learner_history in transcript[-1]["text"] and learner_history not in tail
    assert personal_history in tail and all(personal_history not in block["text"] for block in transcript)


async def test_speech_uses_the_current_belief_after_a_challenge_and_each_state_update(session, stream):
    challenge = "Could the repeated image represent a memory instead?"
    session.transcript[-1].text = challenge
    original = Belief(id="image-rule", text="The repeated image announces the next scene.", accuracy="incorrect")
    unrelated = Belief(id="stanza-length", text="The stanzas alternate in length.")
    revised = Belief(id=original.id, text="The image marks a return to an earlier scene.", accuracy="partial")
    session.states["peer1"] = []
    pipeline = CslPipeline()
    for version, beliefs in enumerate(([original], [original, unrelated], [revised, unrelated])):
        session.states["peer1"].append(StateVersion(
            agent_id="peer1", version=version, state=KnowledgeState(beliefs=beliefs), created_at=version,
        ))
        await pipeline.speak(session, SpeakerDecision(agent_id="peer1"), SimpleNamespace(write=AsyncMock()))

        request = stream.call_args.args[0]
        transcript, tail = request[-1]["content"][:-1], request[-1]["content"][-1]["text"]
        assert challenge in transcript[-1]["text"]
        assert "An active belief is still yours" in request[0]["content"][1]["text"]
        assert "speak from the beliefs and explanation above" in tail.lower()
        for belief in (original, unrelated, revised):
            assert (belief.text in tail) == (belief in beliefs)
        assert "accuracy" not in tail and original.id not in tail
        assert "PRIVATE-KEY" not in json.dumps(request)
    assert stream.call_count == 3


@pytest.mark.parametrize("state", [
    KnowledgeState(explanation="I follow the first two steps and lose track at the third."),
    KnowledgeState(open_questions=["Could the second voice be quoting the first?"]),
    KnowledgeState(),
])
async def test_partial_and_empty_states_do_not_borrow_from_other_peers(session, complete, state):
    session.states["peer1"][-1].state = state
    context = await knowledge.prepare_peer_context(session, "peer1")
    assert complete.return_value in context
    assert all(text in context for text in state_texts(state) if text)
    assert all(text not in context for text in state_texts(session.state_of("peer2")))


@pytest.mark.parametrize("failure", ["blank", "error", "timeout"])
async def test_extraction_failure_still_returns_own_knowledge(session, complete, monkeypatch, caplog, failure):
    previous_summary = complete.return_value
    assert previous_summary in await knowledge.prepare_peer_context(session, "peer1")
    complete.reset_mock()
    if failure == "blank":
        complete.return_value = " \n\t"
    elif failure == "error":
        complete.side_effect = RuntimeError("provider unavailable")
    else:
        monkeypatch.setattr(knowledge, "EXTRACTION_TIMEOUT_SECONDS", 0.01)

        async def stall(*args, **kwargs):
            await asyncio.Event().wait()

        complete.side_effect = stall
    original = session.dump()
    async with asyncio.timeout(1):
        context = await knowledge.prepare_peer_context(session, "peer1")
    assert complete.await_count == 1
    assert previous_summary not in context
    assert all(text in context for text in state_texts(session.state_of("peer1")))
    assert all(text not in context for text in state_texts(session.state_of("peer2")))
    assert any(record.levelname == "WARNING" for record in caplog.records)
    assert session.dump() == original


@pytest.mark.parametrize("extraction", ["The question concerns the recurring image.", " "], ids=["success", "blank"])
async def test_peer_speech_streams_once_with_own_context_in_tail(session, complete, stream, extraction):
    complete.return_value = extraction
    decision = SpeakerDecision(agent_id="peer1", directive="react", meta={"respondTo": 1})
    sink = SimpleNamespace(write=AsyncMock())
    before = session.dump()
    await CslPipeline().speak(session, decision, sink)
    assert session.dump() == before and decision.meta == {"respondTo": 1}
    complete.assert_awaited_once()
    stream.assert_called_once()
    sink.write.assert_awaited_once_with("I still have a question.")
    assert stream.call_args.kwargs == {"temperature": 0.8, "max_tokens": 400}

    extract_request = complete.await_args.args[0]
    speak_request = stream.call_args.args[0]
    assert "[T1]" in extract_request[1]["content"][-1]["text"]
    assert extract_request[0]["content"][0] == speak_request[0]["content"][0]
    assert extract_request[1]["content"][:-1] == speak_request[1]["content"][:-1]
    assert cache_breakpoints(speak_request) <= 4
    tail = speak_request[1]["content"][-1]
    assert "cache_control" not in tail
    assert all(tail["text"].count(text) == 1 for text in state_texts(session.state_of("peer1")))
    assert all(text not in tail["text"] for text in state_texts(session.state_of("peer2")))
    assert discussion.PEER_DIRECTIVES["react"] in tail["text"]
    assert "[T1] from Tutor" in tail["text"]
    if extraction.strip():
        assert tail["text"].count(extraction) == 1
        assert json.dumps(speak_request).count(extraction) == 1


async def test_tutor_speech_skips_peer_context(session, complete, stream):
    decision = SpeakerDecision(agent_id="tutor", directive="open")
    await CslPipeline().speak(session, decision, SimpleNamespace(write=AsyncMock()))
    complete.assert_not_awaited()
    stream.assert_called_once_with(discussion.speak_request(session, decision), temperature=0.8, max_tokens=400)


async def test_learner_interruption_cancels_peer_speech_while_extracting(session, complete, stream):
    started = asyncio.Event()

    async def stall(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    complete.side_effect = stall
    original = session.dump()
    sink = SimpleNamespace(write=AsyncMock())
    task = asyncio.create_task(CslPipeline().speak(session, SpeakerDecision(agent_id="peer1"), sink))
    try:
        async with asyncio.timeout(1):
            await started.wait()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    stream.assert_not_called()
    sink.write.assert_not_awaited()
    assert session.dump() == original


async def speak_character_by_character(session, monkeypatch, text, *, speaker="peer1"):
    """Exercise both the prefix stripper and the speech guard across arbitrary token splits."""
    async def split_stream(*args, **kwargs):
        for char in text:
            yield char

    monkeypatch.setattr(llm_module._llm, "stream", split_stream, raising=False)
    events = []
    session.log = lambda kind, data: events.append((kind, data))
    sink = SimpleNamespace(write=AsyncMock())
    await CslPipeline().speak(session, SpeakerDecision(agent_id=speaker), sink)
    heard = "".join(call.args[0] for call in sink.write.await_args_list)
    return heard, events


@pytest.mark.parametrize("unsupported", [
    "That’s what I’ve been going by when sorting them.",
    "That’s what I’ve been told, and it’s how I’ve sorted every booklet so far.",
    "I’m pretty sure about that—it’s what we’ve been using to identify which readings are plausible.",
    "I'm assuming this reading works because that's how we've sorted them before—tone was the main thing we checked.",
    "The rhythm seems to be the key thing we check—slow means sad.",
    "That’s what I’ve always seen the volunteers do.",
    "We've often been told to mark that passage.",
])
async def test_peer_stream_suppresses_unsupported_histories_across_chunk_boundaries(
    session, complete, monkeypatch, unsupported,
):
    first, last = "I think the rhythm suggests sadness.", "What makes you doubt that?"
    heard, events = await speak_character_by_character(
        session, monkeypatch, f"[T3] Min: {first} {unsupported} {last}",
    )
    assert heard.strip() == f"{first} {last}"
    [(kind, data)] = events
    assert kind == "peer.history_suppressed" and data["agentId"] == "peer1" and data["count"] == 1
    assert unsupported not in json.dumps(data, ensure_ascii=False)


async def test_habitual_experience_and_current_reasoning_have_different_grounding(session, complete, monkeypatch):
    # Perfect contractions and their expanded forms cite the same assigned account.
    session.states["peer1"][-1].state.explanation = "I have always seen a signature below the left margin."
    sentences = [
        "I’ve always seen a signature below the left margin.",
        "I’ve always assumed the reader would notice it.",
        "That’s what we have usually thought about the ending.",
        "I've often been wondering whether the last line changes that.",
    ]
    text = " ".join(sentences)
    heard, events = await speak_character_by_character(session, monkeypatch, text)
    assert heard == text and not events


@pytest.mark.parametrize(("lang", "past", "attributed", "ordinary"), [
    ("en", "I heard the author read the final line twice.",
     "The learner said, “I heard the author read the final line twice.”",
     "I thought the repeated line was important. I used to think the voice was different. I would read it as a question."),
    ("ko", "저는 작가가 마지막 구절을 두 번 읽는 걸 들었어요.",
     "학습자가 “저는 작가가 마지막 구절을 두 번 읽는 걸 들었어요.”라고 말했어요.",
     "저는 마지막 구절이 중요하다고 생각했어요. 저는 그 구절을 질문으로 해석할 것 같아요."),
])
async def test_peer_speech_preserves_supported_and_correctly_attributed_experiences(
    session, complete, monkeypatch, lang, past, attributed, ordinary,
):
    session.language = lang
    state = session.states["peer1"][-1].state
    state.explanation = past
    heard, events = await speak_character_by_character(session, monkeypatch, f"{past} {ordinary}")
    assert heard.strip() == f"{past} {ordinary}" and not events

    # A report by someone else supports quotation with attribution, not a new account in my voice.
    state.explanation = ""
    session.transcript[-1].text = past
    heard, events = await speak_character_by_character(session, monkeypatch, f"{past} {ordinary}")
    assert heard.strip() == ordinary and len(events) == 1
    heard, events = await speak_character_by_character(session, monkeypatch, attributed)
    assert heard.strip() == attributed and not events


async def test_history_must_come_from_the_named_speaker(session, complete, monkeypatch):
    report = "I heard the author read the final line twice."
    session.transcript[-1].text = report
    wrong = f"The tutor said, “{report}”"
    invented = "The learner said, “I saw the author erase two stanzas.”"
    last = "I would try reading it aloud."
    heard, events = await speak_character_by_character(session, monkeypatch, f"{wrong} {invented} {last}")
    assert heard.strip() == last
    assert len(events) == 1 and events[0][1]["count"] == 2


async def test_repeating_someones_quotation_does_not_turn_it_into_peer_experience(session, complete, monkeypatch):
    account = "I heard the author read the final line twice."
    attributed = f"The learner said, “{account}”"
    session.transcript[-1].text = account
    session.messages.append(Message(
        id="three", channel="discussion", role="peer", speaker_id="peer1", speaker_name="Min",
        turn_number=3, text=attributed, created_at=3,
    ))
    heard, events = await speak_character_by_character(session, monkeypatch, f"{account} {attributed}")
    assert heard == attributed
    assert len(events) == 1 and events[0][1]["count"] == 1


async def test_conditional_experience_in_state_stays_conditional(session, complete, monkeypatch):
    condition = "If I heard the song, I could compare the tune with the poem."
    session.states["peer1"][-1].state.explanation = condition
    heard, events = await speak_character_by_character(session, monkeypatch, f"I heard the song. {condition}")
    assert heard == condition
    assert len(events) == 1 and events[0][1]["count"] == 1


async def test_speech_filters_invented_learning_and_group_habits_while_preserving_a_physical_rule(
    session, complete, monkeypatch,
):
    belief = "The planets always follow orbits."
    session.states["peer1"][-1].state.explanation = "Planets remain in orbit around their star."
    generated = f"I remember learning about this in class. The readers always sign their cards. {belief}"
    heard, events = await speak_character_by_character(session, monkeypatch, generated)
    assert heard == belief
    assert len(events) == 1 and events[0][1]["count"] == 2


@pytest.mark.parametrize(("lang", "unsupported", "belief"), [
    ("en", "That’s what I’ve been told.", "The rhythm suggests sadness."),
    ("ko", "저는 그 설명을 선생님께 들었어요.", "그 운율은 슬픔을 나타내요."),
])
async def test_all_suppressed_peer_speech_falls_back_to_its_own_understanding(
    session, complete, monkeypatch, lang, unsupported, belief,
):
    session.language = lang
    state = session.states["peer1"][-1].state
    state.beliefs = [Belief(id="stress", text=belief)]
    state.explanation = ""
    state.open_questions = []
    heard, events = await speak_character_by_character(session, monkeypatch, unsupported)
    assert heard.strip() and unsupported not in heard
    assert belief.rstrip(".") in heard
    assert len(events) == 1


async def test_suppressed_speech_with_empty_state_still_has_a_reply(session, complete, monkeypatch):
    unsupported = "That’s what I’ve been going by when sorting them."
    session.states["peer1"][-1].state = KnowledgeState()
    heard, events = await speak_character_by_character(session, monkeypatch, unsupported)
    assert heard.strip() and unsupported not in heard
    assert len(events) == 1
    assert all(text not in heard for text in state_texts(session.state_of("peer2")) if text)


async def test_hypothetical_measurements_keep_their_original_decimal_points(session, complete, monkeypatch):
    text = "I would compare 1.5 units with 2.5 units first. Would that help?"
    heard, events = await speak_character_by_character(session, monkeypatch, text)
    assert heard == text and not events


async def test_interruption_discards_buffered_partial_history_while_finished_sentence_is_live(
    session, complete, monkeypatch,
):
    first = "I think the rhythm suggests sadness."
    stalled = asyncio.Event()

    async def split_stream(*args, **kwargs):
        for char in first + " That’s what I’ve been going by when sorting":
            yield char
        stalled.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(llm_module._llm, "stream", split_stream, raising=False)
    sink = SimpleNamespace(write=AsyncMock())
    task = asyncio.create_task(CslPipeline().speak(session, SpeakerDecision(agent_id="peer1"), sink))
    try:
        await asyncio.wait_for(stalled.wait(), 1)
        assert "".join(call.args[0] for call in sink.write.await_args_list).strip() == first
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert "".join(call.args[0] for call in sink.write.await_args_list).strip() == first


async def test_tutor_stream_bypasses_peer_history_guard(session, complete, monkeypatch):
    spoken = "That’s what I’ve been going by when sorting them."
    heard, events = await speak_character_by_character(session, monkeypatch, spoken, speaker="tutor")
    assert heard == spoken and not events
    complete.assert_not_awaited()


async def test_peer_history_is_absent_from_public_deltas_committed_message_and_state_tracker(
    session, complete, monkeypatch, store, settings,
):
    safe = "I would read the rhythm as a clue."
    unsupported = "That’s what I’ve been going by when sorting them."

    async def model_stream(*args, **kwargs):
        for part in ("Min: ", safe, " That’s what I’ve been going ", "by when sorting them."):
            yield part

    monkeypatch.setattr(llm_module._llm, "stream", model_stream, raising=False)
    session.phase = "discussion"
    pipeline = CslPipeline()
    monkeypatch.setattr(pipeline, "select_speaker", AsyncMock(return_value=SpeakerDecision(agent_id="peer1")))
    track = AsyncMock(return_value=[])
    monkeypatch.setattr(pipeline, "update_states", track)
    runner = SessionRunner(session, pipeline, store, settings)
    conn = Connection()
    runner.attach(conn)
    await asyncio.wait_for(runner._agent_turn(), 2)

    assert session.last_message.text == safe
    track.assert_awaited_once_with(session, session.last_message)
    public_events = []
    while not conn.queue.empty():
        public_events.append(conn.queue.get_nowait())
    assert "".join(e["data"]["text"] for e in public_events if e["type"] == "message.delta") == safe
    [message] = [e["data"]["message"] for e in public_events if e["type"] == "message.completed"]
    assert message["text"] == safe
    assert all(e["type"] != "peer.history_suppressed" for e in public_events)
    assert unsupported not in json.dumps(public_events, ensure_ascii=False)
    diagnostics = [e for e in await store.list_events(session.id) if e["type"] == "peer.history_suppressed"]
    assert len(diagnostics) == 1 and diagnostics[0]["data"]["count"] == 1
