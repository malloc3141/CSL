from unittest.mock import AsyncMock

from app import llm
from app.pipeline.baseline import BaselinePipeline
from app.pipeline.csl import CslPipeline
from app.protocol import Message
from app.session import Session


async def test_csl_classroom_generation_matches_the_original_pipeline(monkeypatch):
    client = AsyncMock()
    client.complete_json.return_value = {
        "focus": "Who is narrating the last paragraph?",
        "tutor": {"reference": "The narrator changes.", "key_points": ["Change of voice"]},
        "peers": [{"name": "Min", "beliefs": [{"text": "A tense change signals a new narrator."}]}],
    }
    monkeypatch.setattr(llm, "_llm", client)
    session = Session("s", "Narrative voice", "en", 60)
    session.messages.append(Message(id="setup", channel="init", role="user", speaker_id="user",
                                    speaker_name="Learner", text="I listen for changes in tense.", created_at=0))
    baseline_session = Session.restore(session.dump())

    expected = await BaselinePipeline().build_classroom(baseline_session)
    actual = await CslPipeline().build_classroom(session)

    baseline_call, csl_call = client.complete_json.await_args_list
    assert csl_call == baseline_call
    assert actual == expected
    assert session.scratch == baseline_session.scratch
