from unittest.mock import AsyncMock

from app import llm
from app.pipeline.baseline import BaselinePipeline
from app.pipeline.csl import CslPipeline, CslShortenPipeline, knowledge
from app.protocol import Message
from app.session import Session


async def test_csl_classroom_changes_peer_instructions_and_preserves_draft_processing(monkeypatch):
    client = AsyncMock()
    client.complete_json.return_value = {
        "focus": "Who is narrating the last paragraph?",
        "tutor": {"reference": "The narrator changes.", "key_points": ["Change of voice"]},
        "peers": [{
            "name": "Min",
            "beliefs": [{"text": "A tense change signals a new narrator.", "accuracy": "partial"}],
            "explanation": "I follow the changes in tense to identify the narrator.",
            "open_questions": ["Which tense does the last paragraph use?"],
        }],
    }
    monkeypatch.setattr(llm, "_llm", client)
    session = Session("s", "Narrative voice", "en", 60)
    session.messages.append(Message(id="setup", channel="init", role="user", speaker_id="user",
                                    speaker_name="Learner", text="I listen for changes in tense.", created_at=0))
    baseline_session = Session.restore(session.dump())

    expected = await BaselinePipeline().build_classroom(baseline_session)
    actual = await CslPipeline().build_classroom(session)

    baseline_call, csl_call = client.complete_json.await_args_list
    baseline_system, baseline_input = baseline_call.args[0]
    csl_system, csl_input = csl_call.args[0]
    assert csl_input == baseline_input
    assert session.topic in csl_input["content"] and session.messages[0].text in csl_input["content"]
    assert csl_call.kwargs == baseline_call.kwargs
    assert "including what they cannot explain" in baseline_system["content"]
    assert "including what they cannot explain" not in csl_system["content"]
    assert "one coherent mental model" in csl_system["content"]
    assert "how this student currently thinks it works" in csl_system["content"]
    assert "neutral question" in csl_system["content"]
    assert actual == expected
    assert session.scratch == baseline_session.scratch
    # The learning goal must not give the answer away: both csl and csl-shorten ask for a plain question.
    assert knowledge.FOCUS_RULE in csl_system["content"]
    assert knowledge.OPEN_QUESTION_RULE not in csl_system["content"]
    await CslShortenPipeline().build_classroom(Session.restore(baseline_session.dump()))
    shorten_system = client.complete_json.await_args_list[-1].args[0][0]["content"]
    assert knowledge.FOCUS_RULE in shorten_system and knowledge.OPEN_QUESTION_RULE in shorten_system
