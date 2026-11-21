# HANDOFF

Who works where, as of 2026-11-21. · 2026-11-21 기준, 누가 어디서 무엇을 작업하는지.

**[한국어](#한국어)** · **[English](#english)** (same content in both)

---

## 한국어

### 1. 지금 상태

- 실서버: **https://csl.kimhm.in** . `main`에 push하면 테스트와 빌드를 거쳐 자동 배포됩니다.
- 서빙 레이어(세션, 읽기 속도 조절, 끼어들기, WebSocket, 저장, 이벤트 로그)는 완성되어 돌아가고 있습니다.
- 에이전트: 팀 파이프라인 `csl`이 실서버에 올라가 있습니다(`/dev`의 Agents에서 `csl` 선택). 토론 부분
  (`discussion.py`)은 구현되어 있고, 설정 대화와 knowledge state 부분(`knowledge.py`)은 아직 임시 구현
  `baseline`을 그대로 호출합니다. 서버 기본값은 여전히 `PIPELINE=baseline`이고, 모델은 두 종류 모두
  `anthropic/claude-haiku-5.5`입니다.
- 제품 UI: 시작 화면(`/`)과 교실 화면(`/chat`)이 백엔드에 연결되어 실제 세션으로 동작합니다. 세션은 서버
  기본 파이프라인(지금은 `baseline`)으로 만들어집니다. `/dev`는 모든 상태를 그대로 보여 주는 확인용 페이지입니다.
- 로그인: 닉네임만 입력합니다(비밀번호 없음). 로그인한 사용자가 만든 세션은 그 사용자의 것으로 기록되어,
  중간에 나가도 어느 브라우저에서든 같은 닉네임으로 다시 찾아 이어갈 수 있습니다. 제품 시작 화면(`/`)은 로그인이
  필수이고 `/dev`는 선택입니다.
- 실서버에는 access code가 걸려 있습니다. 실제 LLM 세션을 만들 때 필요하고, mock 세션에는 필요 없습니다.
- 일정: Studio 4 발표 2026-11-24, 보고서는 다음 날. 채점이 끝날 때까지 실서버가 동작해야 합니다.

| 페이지 | 용도 |
| --- | --- |
| `/` | 제품 시작 화면 (주제 입력, 설정 단계) |
| `/chat` | 제품 교실 화면 |
| `/dev` | 실제 세션 전체를 돌려보는 페이지 (설정 대화 → 교실 → 토론 → knowledge state 패널). 파이프라인 선택 가능 |
| `/mypage` | 로그인, 내 세션 목록, 이어가기 |
| `/admin` | LLM 사용량, 비용, 캐시 적중률, 모델 교체, 세션 기록(사용자 포함)과 이벤트 로그. admin token 필요 |

### 2. 공통: 실행과 배포

```bash
# 백엔드: http://localhost:8000 (기본값 PIPELINE=mock, API 키 불필요)
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload

# 프론트엔드: http://localhost:3000/dev
cd frontend
pnpm install
pnpm dev
```

- 로컬 프론트엔드는 **로컬 백엔드**에 붙여야 합니다. 실서버 백엔드는 `https://csl.kimhm.in` 에서 온 요청만 받습니다.
- 실제 모델로 돌리려면 `backend/.env.example`을 `backend/.env`로 복사하고 `PIPELINE`, `OPENROUTER_API_KEY`,
  `OPENROUTER_MODEL`을 채웁니다. `.env`는 커밋되지 않습니다. 키와 토큰을 추적되는 파일에 넣지 마세요.
- `main`에 push하면 서버에서 `uv run pytest`(백엔드 48개)와 `pnpm build`(타입 검사 포함)를 먼저 돌립니다.
  하나라도 실패하면 배포되지 않고 실서버는 그대로입니다. push 전에 로컬에서 두 명령을 돌려 보세요.
- push가 곧 배포이므로, 브랜치에서 작업하고 통과한 뒤 `main`에 합치는 것을 권장합니다.
- 배포는 코드만 바꿉니다. 서버의 `backend/.env`(기본 `PIPELINE`, 키, access code)는 Hyunmin이 직접 바꿉니다.
  자기 파이프라인을 실서버에서 돌려보는 데는 `.env` 변경이 필요 없습니다(6절).

### 3. 담당별 작업 위치

| 담당 | 맡은 것 | 작업 위치 | 읽을 문서 |
| --- | --- | --- | --- |
| Alex | 설정 대화, 에이전트 knowledge state | `Pipeline`의 `init_turn`, `build_classroom`, `update_states` | [PIPELINE.md](backend/docs/PIPELINE.md) |
| Seongho | 토론 진행, 발화 순서, 학습자 참여 | `Pipeline`의 `select_speaker`, `speak` | [PIPELINE.md](backend/docs/PIPELINE.md) |
| Jeeyun | 프론트엔드 UI | `frontend/` (`src/lib/csl`, `src/app/dev`, `src/app/admin` 제외) | [PROTOCOL.md](backend/docs/PROTOCOL.md) |
| Hyunmin | 서빙 레이어, 프론트↔에이전트 연결, 배포, 관리자 페이지 | `backend/`(실제 파이프라인 제외), `frontend/src/lib/csl`, `src/app/dev`, `src/app/admin`, `deploy/` | [backend/README.md](backend/README.md) |

### 4. Alex: 설정 대화와 knowledge state

**어디서.** [csl/knowledge.py](backend/app/pipeline/csl/knowledge.py)의 `init_turn`, `build_classroom`,
`update_states`. 지금은 세 함수 모두 baseline을 그대로 호출합니다. 참고 구현은
[baseline.py](backend/app/pipeline/baseline.py)의 `CLASSROOM_SYSTEM`, `STATE_SYSTEM`, `INIT_SYSTEM`, `INIT_STAGES`
프롬프트와 같은 이름의 메서드입니다.

**가장 급한 문제** (Seongho의 11-19 보고: Studio4 문서의 "Discussion module update" 탭). `update_states` 호출의
70–90%가 `max_tokens=700`에 걸려 JSON이 잘리고, 그래서 세션에 따라 5–15턴 이후로 피어의 상태가 더 바뀌지
않습니다. 피어가 튜터가 이미 설명한 것을 계속 모른다고 말하는 원인입니다. 보고서의 제안은 두 가지입니다.
(1) 바뀐 부분만 출력하게 하거나 `max_tokens`를 올린다. (2) 요청을 `csl/prompting.py`의 `build_messages`로
조립해 프롬프트 캐시를 쓴다(상태 갱신이 세션 비용의 약 90%).

**무엇을 반환하나.**
- `init_turn(session, out)` → 가이드의 다음 말을 `out.write()`로 쓰고 `InitResult(done)`을 반환합니다. 처음에는
  빈 `session.init_transcript`로, 그 뒤로는 학습자가 답할 때마다 호출됩니다. `done=True`를 반환하면 설정 대화가
  끝나고 `build_classroom`이 호출됩니다. 이 대화의 내용이 `build_classroom`의 입력입니다. baseline은
  질문 → 되묻기 → (가이드가 더 필요하다고 보면 추가 되묻기) → 마무리 순서입니다. 답이 2번 온 뒤부터는
  가이드가 메시지와 종료 여부를 JSON(`{"message": ..., "done": true|false}`)으로 함께 답합니다(답이 4번 오면
  마무리하라고 지시). `done`이 true이고 메시지가 질문으로 끝나지 않을 때만 교실 구성으로 넘어가고, 그 밖에는
  학습자의 답을 기다립니다. 이 단계의 메시지는 스트리밍 없이 한 번에 나옵니다. 빈 발화는 오류로 처리됩니다.
- `build_classroom(session)` → `Classroom(participants, states, focus)`. 튜터 1명과 피어들, 피어 id별 초기
  `KnowledgeState`. 입력은 `session.topic`과 설정 대화 `session.init_transcript`입니다.
- `update_states(session, message)` → `list[StateUpdate]`. 토론에 들어간 메시지(에이전트, 학습자 모두)마다
  정확히 한 번 호출됩니다. 상태가 바뀐 피어만, **전체 새 상태**로 반환합니다(patch가 아님).

**`KnowledgeState`는 학습자가 패널에서 보는 형태입니다.** `beliefs[{id, text, accuracy?}]`, `explanation`,
`explanation_accuracy`, `open_questions`. 내부 표현(belief graph 등)은 자유이며 `session.scratch`에 둡니다.

**알아둘 것.**
- `session.states`에 직접 쓰지 않습니다. 반환하면 서버가 버전 번호, 원인 메시지, 변경 내역(diff)을 붙여 저장하고 전송합니다.
- 유지되는 belief는 `id`를 그대로 둡니다. 그래야 패널에서 "변화 없음"으로 보입니다.
- 튜터용 정답 같은 숨은 정보는 `session.scratch`에 둡니다(baseline은 `scratch["baseline"]["tutor"]`).
  `scratch`는 JSON으로 저장되어 서버 재시작 후에도 남습니다. 세션별 상태를 `self`에 두면 사라집니다.
- 토론 쪽이 읽는 키는 `scratch["baseline"]["tutor"]`(`reference`, `key_points`)와
  `scratch["baseline"]["last_invite"]`입니다. 이 키를 옮기면 `discussion.py`의 `tutor_notes` / `last_invite`도
  같은 변경에서 고쳐야 합니다(`knowledge.py` 맨 위 주석).
- `update_states`가 실패하면 로그만 남고 토론은 계속됩니다(상태는 그대로). 실패를 놓치지 않으려면 `/admin`의
  이벤트 로그에서 `server.error`를 확인하세요.
- 다음 발화는 `update_states`가 끝나야 시작됩니다. baseline은 피어별 호출을 병렬로, `fast=True` 모델로 돌립니다.
- `accuracy`(`correct` / `partial` / `incorrect`)는 선택 항목입니다. UI가 틀린 belief를 강조하는 데 쓸 수 있습니다.

### 5. Seongho: 토론 진행

**어디서.** [csl/discussion.py](backend/app/pipeline/csl/discussion.py)의 `select_speaker`와 `speak`, 그리고
모든 호출의 요청을 조립하는 [csl/prompting.py](backend/app/pipeline/csl/prompting.py).

**지금 동작.** 보이지 않는 moderator가 매 턴 대화 전체를 읽고 다음에 말할 학생과 그 학생이 먼저 답할 열린
질문을 고릅니다. 튜터는 발화 후보가 아니고, 주제 이탈, 정체, 정보 부족 중 하나일 때만 개입합니다. 6턴 이후
학습자를 초대할 수 있고(최소 8턴 간격), 16턴 이후 핵심에 도달했다고 판단되면 튜터가 토론을 마무리합니다.

**무엇을 반환하나.**
- `select_speaker(session)` → `SpeakerDecision(agent_id, invite_user, end, directive, meta)`.
  `invite_user=True`면 이 발화 뒤에 서버가 학습자의 설명을 기다립니다. `end=True`면 토론이 끝납니다.
  `directive`는 `speak`로 전달되고, `meta`는 메시지에 저장되어 프론트엔드까지 그대로 갑니다.
- `speak(session, decision, out)` → `await out.write(chunk)`로 발화를 씁니다. 스트리밍해도 되고 한 번에 써도 됩니다.
  빈 발화는 오류로 처리됩니다.

**알아둘 것.**
- **두 메서드는 아무것도 바꾸면 안 됩니다.** 서버는 학습자가 이전 메시지를 읽는 동안 다음 발화를 미리 만들고,
  학습자가 먼저 말하면 버립니다. 같은 턴이 두 번 요청될 수 있습니다. 기록(예: 마지막 초대 시점)은 전부
  `update_states`에서 합니다. 그 메서드는 Alex 담당이므로 **둘이 조율이 필요한 지점**입니다.
- 학습자는 언제든 말할 수 있습니다. `session.last_message.role == "user"`는 `select_speaker`의 정상 입력이고,
  `message.invited`로 튜터의 초대에 대한 답인지 알 수 있습니다.
- 초대 후 학습자가 넘길 수도 있습니다. 그러면 튜터의 초대가 마지막 메시지인 채로 `select_speaker`가 다시 호출됩니다.
- 피어 프롬프트에 넣을 현재 상태는 `session.state_of(agent_id)`로 읽습니다.
- 읽는 시간(메시지 사이 간격), 일시정지, 끼어들기 처리는 서버가 합니다. 파이프라인에서 `sleep`하지 마세요.
- 턴 수가 `MAX_TURNS`(60)에 닿으면 서버가 세션을 끝냅니다.

### 6. Alex + Seongho 공통

**한 클래스를 둘이 채웁니다.** 서버는 `PIPELINE` 하나만 불러오므로 다섯 메서드가 한 클래스에 있어야 합니다.
코드는 `backend/app/pipeline/csl/`에 있고 `csl`이라는 이름으로 등록되어 있습니다.

```
backend/app/pipeline/csl/
  __init__.py      class CslPipeline: 다섯 메서드, 각각 아래 모듈을 호출
  knowledge.py     Alex: init_turn, build_classroom, update_states (지금은 baseline 호출)
  discussion.py    Seongho: select_speaker, speak
  prompting.py     공용: 프롬프트 캐시에 맞춘 요청 조립 (build_messages)
```

`baseline.py`는 서버 기본값이고 `knowledge.py`가 아직 호출하므로 지우거나 이름을 바꾸지 마세요.

**둘 사이의 계약.** (1) `speak`가 프롬프트에 넣는 `KnowledgeState`의 모양, (2) `session.scratch`의 키(각자
다른 키를 쓰기), (3) `select_speaker`가 필요로 하는 기록을 `update_states`에 넣는 방법. 현재 합의된 키는
`knowledge.py` 맨 위 주석에 적혀 있습니다.

**LLM 호출.** `app.llm`의 `get_llm()`을 씁니다: `stream`, `complete`, `complete_json`. 작은 호출에는 `fast=True`.
모델 id는 관리자 페이지에서 실행 중에 바뀔 수 있으므로 직접 저장해 두지 마세요. 호출마다 모델, 지연, 토큰,
비용, 캐시에서 읽은 토큰이 기록됩니다. 모델의 reasoning은 기본으로 꺼져 있습니다(`LLM_REASONING=off`). 켜면
reasoning 토큰이 `max_tokens`를 써 버려 빈 응답이 나올 수 있습니다.

**프롬프트 캐시.** 요청을 `prompting.build_messages`로 조립하면 캐시가 걸립니다(세션 블록 → 역할 블록 → 메시지별
블록 → 매번 바뀌는 꼬리). 세션 동안 바뀌는 값(상태, 턴 수, 지시문)은 꼬리에만 넣어야 합니다. 모든 호출에는
세션 id가 함께 전달되어 한 세션의 요청이 같은 제공자로 가고 서로의 캐시를 읽습니다. 적중률은 `/admin`의
Usage 탭에서 볼 수 있습니다.

**돌려보기.**

```bash
cd backend
uv run python scripts/cli.py "Why is summer hotter than winter?" --pipeline csl
#   Enter = 다음 메시지, 글자를 치면 학습자 발화, /state = knowledge state 출력, /auto = 자동 진행
uv run pytest
```

- 서버와 함께 보려면 `backend/.env`에 `PIPELINE`을 넣고 서버를 띄운 뒤 `http://localhost:3000/dev`.
- 테스트는 `backend/tests/`에 추가합니다. [test_csl_pipeline.py](backend/tests/test_csl_pipeline.py)와
  [test_baseline.py](backend/tests/test_baseline.py)가 가짜 LLM으로 파이프라인을 돌리는 예시입니다. CI에서 함께
  실행됩니다.
- 새 Python 패키지는 `backend/pyproject.toml`의 `dependencies`에 넣습니다.
- 실서버에서 확인: `/admin` → Sessions에서 세션별 대화, 모든 state 버전, `scratch`, 이벤트 로그, 비용을 볼 수 있습니다.

**실서버에서 돌려보기 (Hyunmin을 거치지 않음).** `csl`은 `backend/app/pipeline/__init__.py`의
`SESSION_PIPELINES`에 이미 등록되어 있습니다. `main`에 push하면 배포되고, `https://csl.kimhm.in/dev`의
"Agents"에서 `csl`을 골라 세션을 시작하면 됩니다. **그 세션만** `csl`로 돌고, 다른 사람의 세션과 서버 기본값
(`baseline`)은 그대로입니다. LLM을 쓰므로 access code가 필요합니다.

```python
SESSION_PIPELINES: dict[str, str] = {
    "mock": "app.pipeline.mock:MockPipeline",
    "baseline": "app.pipeline.baseline:BaselinePipeline",
    "csl": "app.pipeline.csl:CslPipeline",
}
```

다른 버전을 나란히 시험하려면 여기에 한 줄을 더 추가합니다. 등록한 모듈이 import되지 않으면 `uv run pytest`가
실패해서 배포되지 않습니다.

**기본값으로 만들기.** `csl`을 서버 기본값으로 쓸 때가 되면 Hyunmin에게 `PIPELINE=csl`로 바꿔 달라고 요청합니다.
그 전까지 이름 없이 만든 세션은 `baseline`으로 돕니다.

**인터페이스가 부족하면.** `base.py`나 `protocol.py`를 바꿔야 하는 경우(예: 패널에 보여줄 새 필드) Hyunmin에게
알려 주세요. `protocol.py`를 바꾸면 `uv run python scripts/gen_ts.py`로 프론트엔드 타입을 다시 만들어야 합니다.

### 7. Jeeyun: 프론트엔드 UI

**어디서.** `frontend/src/app/page.tsx`(시작 화면), `src/app/chat/`(교실 화면), `src/common`, `src/styles`.

**지금 연결된 상태** (11-21, 디자인은 그대로 두고 데이터만 실제 세션으로 바꿨습니다).
- `page.tsx`: 주제를 입력하면 세션을 만들고(`createSession`) 주소가 `/?session=<id>`가 됩니다. 세 단계는 서버의
  `snapshot.phase`를 따라갑니다: Initial question = `init`(가이드와의 설정 대화, Composer는 `actions.replyInit`),
  Learning direction = `building`, Classroom setup = `ready`(`ClassroomOverview`에 실제 참가자 전달). `init`에서
  Next는 설정 대화의 나머지를 건너뜁니다(`actions.finishInit`). "Start learning session"은 `/chat?session=<id>`로
  이동합니다. 서버에 access code가 걸려 있으면 주제 아래에 입력 칸이 나오고, 한 번 통과한 값은 브라우저가 기억합니다.
- `chat/ChatSession.tsx`: 주소의 `?session=<id>`로 세션을 엽니다. 들어오면 토론이 시작되고(`ready`일 때
  `actions.startDiscussion`), 메시지는 `snapshot.messages`의 discussion 채널, 입력 중 표시는 `snapshot.activeTurn`,
  Pause/Resume는 `actions.pause` / `actions.resume`, Composer는 `actions.say`, 오른쪽 패널은 선택한 참가자의
  최신 `snapshot.states[id]`입니다. 참가자를 누르면 `actions.track("panel.open")`으로 기록됩니다. 아직 설정 중인
  세션으로 들어오면 `/?session=<id>`로 돌려보냅니다.
- `ClassroomOverview`는 `participants` prop을 받습니다(없으면 기존 예시 데이터).
- `/?pipeline=mock`으로 열면 그 세션은 비용 없는 mock으로 만들어집니다(UI 확인용, access code 불필요).
  `/?pipeline=csl`도 같은 방식입니다.

**Studio 3 인터뷰에서 나온 것 중 교실 화면에 넣은 것** (11-21, `chat/ChatSession.tsx`).
- 4번(Peer의 말을 정답으로 오해): 패널의 belief와 설명 옆에 Correct / Partly correct / Incorrect 표시
  (`accuracy`, `explanationAccuracy`), 패널 아래의 "Mark what is correct and incorrect"로 끌 수 있습니다. 패널과
  교실 소개 화면에 "Peer는 전문가가 아니라 학습자"라는 안내 문구가 있습니다.
- 6번(진행 속도): 대화 위에 Auto-advance 켜기/끄기, 속도(0.5× ~ 2×), "Next message" 버튼
  (`actions.setPace`, `actions.step`). 패널 아래의 "Pause the discussion when I open a panel"을 켜면 참가자를 고를 때
  일시정지됩니다.
- 9번(상태가 언제 바뀌었는지): 상태가 바뀐 참가자는 목록에 점이 붙고, 그 변화를 일으킨 메시지 아래에
  "…'s understanding changed" 링크가 생깁니다. 패널에는 "Updated after turn N: show the message"(그 메시지로
  이동), 이번에 바뀐 내용(`changes`의 전/후), 접혀 있는 "Earlier understanding"(이전 버전 전체)이 있습니다.
- 두 설정은 브라우저의 localStorage(`csl.classroomPrefs`)에 남습니다.

**아직 UI에 없는 것.** 토론 언어 선택(지금은 영어 고정, Navbar의 Language 버튼은 연결 안 됨), Peer들의 상태를
나란히 비교하는 화면(10번), Open question 접기와 질문 로그(11번), 패널 접기와 위치(12번), 음성 입력(14번).
아래 표의 값들로 만들 수 있습니다.

**백엔드 연결은 이미 있습니다.** 두 개만 쓰면 됩니다.

```tsx
import { createSession, useCslSession } from "@/lib/csl";

const { sessionId } = await createSession({ topic, language: "en" });
const { snapshot, connection, error, actions } = useCslSession(sessionId);
```

- `snapshot`은 항상 세션의 현재 상태 전체입니다. 이것만 보고 그리면 됩니다. 필드와 `actions` 목록은
  [PROTOCOL.md](backend/docs/PROTOCOL.md)에, 실제로 다 쓰는 예시는 [dev/page.tsx](frontend/src/app/dev/page.tsx)에 있습니다.
- **UI 작업에는 mock 세션을 쓰세요.** `createSession({ topic, pipeline: "mock" })`. LLM 호출과 비용이 없고
  access code도 필요 없습니다. 고정 시나리오("Why is summer hotter than winter?", 15턴, 영어/한국어)를
  재생하며 주제는 무시합니다. 15번째 턴에서 튜터가 학습자에게 설명을 요청합니다.
- 실제 에이전트는 `pipeline: "csl"`로 만듭니다(`pipeline`을 빼면 서버 기본값인 `baseline`). 실서버에서는
  access code 입력이 필요합니다. 고를 수 있는 이름 목록은 `fetchHealth()`가 돌려줍니다.

**알아둘 것.**
- `src/lib/csl/protocol.ts`는 생성되는 파일입니다. 손으로 고치지 마세요. 타입이 부족하면 Hyunmin에게 알려 주세요.
- `/dev`와 `/admin`은 그대로 두세요. 배포 스크립트가 `/dev`의 200 응답을 확인합니다.
- **로그인은 닉네임만 받습니다.** `src/lib/csl`의 `useCurrentUser()`, `signIn(name)`, `signOut()`,
  `fetchUserSessions(userId)`를 씁니다. `createSession()`은 로그인한 사용자를 알아서 붙이므로 따로 넘길 것이
  없습니다. 이미 들어가 있는 것:
  - `Navbar`의 프로필 버튼이 `/mypage`로 가고, 로그인하면 닉네임이 옆에 보입니다.
  - `src/common/components/LoginCard.tsx`: 로그인 폼. `/`는 로그인 전에는 이 폼을 보여 줍니다(`page.tsx` 맨 위의
    `if (!user)` 분기).
  - `src/app/mypage/page.tsx`: 내 세션 목록. "Continue"는 `/chat?session=<id>&topic=<주제>`로 이동합니다.
- **이어가기.** 두 화면 모두 주소의 `?session=<id>`(`useCurrentSessionId()`)로 세션을 열기 때문에 새로고침,
  뒤로 가기, 링크 공유, 마이페이지의 Continue가 모두 같은 세션으로 돌아옵니다. 화면을 떠나면 토론은 서버에서
  일시정지되고, 다시 들어오면 이어집니다.
- 서버가 볼 수 없는 UI 동작은 `actions.track(name, data)`로 기록하세요(예: 패널 열기). Milestone 5의 사용 분석에 씁니다.
- UI 문구는 영어가 기본입니다. 토론 언어는 세션을 만들 때 `language: "en" | "ko"`로 고릅니다.
- Next.js 16입니다. 코드를 쓰기 전에 [frontend/AGENTS.md](frontend/AGENTS.md)를 보세요.
- 확인: `pnpm exec next typegen && pnpm exec tsc --noEmit`, `pnpm lint`, `pnpm build`.
  `src/styles/styled.d.ts`, `themes.d.ts`의 eslint 오류 2개는 기존 것입니다.

**Studio 3 인터뷰에서 나온 항목 (프로토콜은 이미 지원):**

| 항목 | 쓰는 것 |
| --- | --- |
| 속도 조절, 자동 진행 끄기 | `actions.setPace({ auto, speed })`, `actions.step()` |
| 패널을 열면 자동 일시정지 | `actions.pause()` / `actions.resume()` |
| 입력 중 표시 | `snapshot.activeTurn` (`text`가 비어 있는 동안) |
| 상태 변화 기록, "N번째 턴에서 바뀜" 링크 | `snapshot.states[agentId][i]`의 `turnId`, `turnNumber`, `changes` |
| 피어 나란히 비교 | `snapshot.states` |
| 틀린 belief 강조 (선택) | `belief.accuracy`, `explanationAccuracy` |
| 튜터의 설명 요청 | `snapshot.status === "waiting_user"`, `invitedTurnId` |

### 8. Hyunmin에게 요청할 것

- 실서버 access code, admin token(`/admin`), OpenRouter 키
- 서버 기본 `PIPELINE`이나 다른 `.env` 값 변경, 서비스 재시작
- `protocol.py`, `base.py`, 서버 동작(속도, 끼어들기, 저장)에 대한 변경
- 배포 실패(GitHub Actions의 Deploy 워크플로)

### 9. 남은 일

- Alex: `knowledge.py`의 실제 구현(설정 대화, 교실 구성, 상태 갱신). 상태 갱신이 중간에 멈추는 문제가 가장 급합니다(4절).
- Seongho: 토론 다듬기. 브랜치 `seongho/cache-friendly-discussion`에 `main`에 없는 커밋이 하나 있습니다(`78a1244`).
- Jeeyun: 제품 UI 다듬기. 연결은 되어 있고, 아직 UI에 없는 것은 7절에 적혀 있습니다.
- Hyunmin: 서버 기본값을 `csl`로 전환, 서버 재부팅 확인, 동시 사용자 확인, 보고서(URL, access code,
  라이브러리와 도구 목록, 스크린샷, System Architecture 탭)
- 팀: 토론에서 학습자를 어떻게 부를지 정하기(지금 화면에는 "나", 프롬프트에는 "Learner")

---

## English

### 1. Where things stand

- Live server: **https://csl.kimhm.in** . A push to `main` is tested, built and deployed automatically.
- The serving layer (sessions, reading pace, interruption, WebSocket, storage, event log) is finished and running.
- Agents: the team's pipeline **`csl`** is on the live server (pick `csl` under "Agents" on `/dev`). The
  discussion side (`discussion.py`) is implemented; the setup chat and knowledge-state side (`knowledge.py`) still
  calls the placeholder `baseline`. The server's default is still `PIPELINE=baseline`, with
  `anthropic/claude-haiku-5.5` as both models.
- Product UI: the start page (`/`) and the classroom page (`/chat`) are connected to the backend and run real
  sessions, created on the server's default pipeline (`baseline` at the moment). `/dev` remains the bare page that
  shows every piece of state.
- Login: a nickname and nothing else (no password). Sessions created while signed in are recorded as that
  user's, so a learner who leaves midway finds the session again with the same nickname, from any browser. The
  product start page (`/`) requires it; `/dev` makes it optional.
- The live server has an access code. Sessions on the real LLM need it; mock sessions do not.
- Dates: Studio 4 presentation 2026-11-24, report the day after. The live server has to keep working until grading is done.

| Page | Purpose |
| --- | --- |
| `/` | Product start page (topic, setup steps) |
| `/chat` | Product classroom page |
| `/dev` | Runs a whole real session (setup chat → classroom → discussion → knowledge-state panels). Lets you pick the pipeline |
| `/mypage` | Sign in, my sessions, continue one |
| `/admin` | LLM usage, cost, cache hit rate, model switch, session history (with the user) and event log. Needs the admin token |

### 2. Everyone: run and deploy

```bash
# backend: http://localhost:8000 (PIPELINE=mock by default, no API key needed)
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload

# frontend: http://localhost:3000/dev
cd frontend
pnpm install
pnpm dev
```

- A local frontend has to talk to a **local backend**. The live backend only accepts requests from `https://csl.kimhm.in`.
- For real models, copy `backend/.env.example` to `backend/.env` and fill in `PIPELINE`, `OPENROUTER_API_KEY` and
  `OPENROUTER_MODEL`. `.env` is not committed. Never put keys or tokens in a tracked file.
- On a push to `main` the server first runs `uv run pytest` (48 backend tests) and `pnpm build` (includes the type
  check). If either fails, nothing is deployed and the live site stays as it was. Run both locally before pushing.
- A push is a deploy, so working on a branch and merging into `main` once both pass is recommended.
- A deploy only changes code. The server's `backend/.env` (default `PIPELINE`, keys, access code) is changed by
  Hyunmin by hand. Trying your own pipeline on the live server needs no `.env` change (section 6).

### 3. Who works where

| Person | Area | Where | Read |
| --- | --- | --- | --- |
| Alex | The setup chat, agent knowledge states | `init_turn`, `build_classroom`, `update_states` of the `Pipeline` | [PIPELINE.md](backend/docs/PIPELINE.md) |
| Seongho | Discussion dynamics, turn allocation, learner participation | `select_speaker`, `speak` of the `Pipeline` | [PIPELINE.md](backend/docs/PIPELINE.md) |
| Jeeyun | Frontend UI | `frontend/` (except `src/lib/csl`, `src/app/dev`, `src/app/admin`) | [PROTOCOL.md](backend/docs/PROTOCOL.md) |
| Hyunmin | Serving layer, frontend↔agent integration, deployment, admin page | `backend/` (except the real pipeline), `frontend/src/lib/csl`, `src/app/dev`, `src/app/admin`, `deploy/` | [backend/README.md](backend/README.md) |

### 4. Alex: the setup chat and knowledge states

**Where.** `init_turn`, `build_classroom` and `update_states` in
[csl/knowledge.py](backend/app/pipeline/csl/knowledge.py). Right now all three call the baseline unchanged. The
reference is in [baseline.py](backend/app/pipeline/baseline.py): the `CLASSROOM_SYSTEM`, `STATE_SYSTEM`,
`INIT_SYSTEM` and `INIT_STAGES` prompts and the methods of the same names.

**Most urgent problem** (Seongho's report of 11-19: the "Discussion module update" tab of the Studio4 document).
70–90% of `update_states` calls hit `max_tokens=700` and the JSON is cut off, so the peers' states stop changing
after turn 5–15, depending on the session. That is why peers keep saying they do not understand something the tutor
already explained. The report suggests two things: (1) output only what changed, or raise `max_tokens`; (2) build
the request with `build_messages` from `csl/prompting.py` so it uses the prompt cache (the state update is about
90% of a session's cost).

**What to return.**
- `init_turn(session, out)` → write the guide's next message with `out.write()` and return `InitResult(done)`.
  Called first with an empty `session.init_transcript`, then again after every learner reply. Returning
  `done=True` ends the setup chat and `build_classroom` is called; what was said here is the input of
  `build_classroom`. The baseline goes ask → probe → (more follow-ups if the guide needs them) → closing message.
  From the second reply on the guide answers with its message and whether it is done, as JSON
  (`{"message": ..., "done": true|false}`; after four replies it is told to close). The classroom is built only
  when `done` is true and the message does not end with a question; otherwise the chat waits for the learner's
  answer. Messages of this stage arrive whole, not streamed. An empty message counts as an error.
- `build_classroom(session)` → `Classroom(participants, states, focus)`: one tutor, the peers, and an initial
  `KnowledgeState` per peer id. The inputs are `session.topic` and the setup chat, `session.init_transcript`.
- `update_states(session, message)` → `list[StateUpdate]`. Called exactly once for every message that entered the
  discussion (agent or learner). Return only the peers whose state changed, each as the **complete new state** (not a patch).

**`KnowledgeState` is what the learner sees in the panel:** `beliefs[{id, text, accuracy?}]`, `explanation`,
`explanation_accuracy`, `open_questions`. Your internal representation (a belief graph, for example) is up to you
and lives in `session.scratch`.

**Good to know.**
- Do not write to `session.states`. Return the update; the server adds the version number, the message that caused
  it and the list of changes (diff), stores it and sends it out.
- Keep the `id` of a belief that survives an update, so the panel shows it as unchanged.
- Hidden information such as the tutor's reference answer goes in `session.scratch` (the baseline uses
  `scratch["baseline"]["tutor"]`). `scratch` is stored as JSON and survives a server restart. Per-session state kept
  on `self` is lost.
- The discussion side reads `scratch["baseline"]["tutor"]` (`reference`, `key_points`) and
  `scratch["baseline"]["last_invite"]`. If these keys move, change `tutor_notes` / `last_invite` in `discussion.py`
  in the same change (see the comment at the top of `knowledge.py`).
- If `update_states` fails, the error is only logged and the discussion goes on with the states unchanged. To catch
  failures, look for `server.error` in the event log on `/admin`.
- The next utterance starts only after `update_states` has finished. The baseline runs one call per peer in parallel
  on the `fast=True` model.
- `accuracy` (`correct` / `partial` / `incorrect`) is optional. The UI can use it to highlight wrong beliefs.

### 5. Seongho: discussion dynamics

**Where.** `select_speaker` and `speak` in [csl/discussion.py](backend/app/pipeline/csl/discussion.py), and
[csl/prompting.py](backend/app/pipeline/csl/prompting.py), which assembles the request of every call.

**How it works now.** On every turn a hidden moderator reads the whole discussion and picks the student who speaks
next and the open question that student should answer first. The tutor is not a speaker candidate; it steps in only
when the discussion is off topic, has stalled, or lacks a fact. The learner can be invited after turn 6 (at least 8
turns apart), and from turn 16 on the tutor closes the discussion once the key points have been reached.

**What to return.**
- `select_speaker(session)` → `SpeakerDecision(agent_id, invite_user, end, directive, meta)`.
  `invite_user=True` makes the server wait for the learner's explanation after this utterance. `end=True` ends the
  discussion. `directive` is passed to `speak`; `meta` is stored on the message and reaches the frontend untouched.
- `speak(session, decision, out)` → write the utterance with `await out.write(chunk)`, streamed or all at once.
  An empty utterance counts as an error.

**Good to know.**
- **Neither method may change anything.** The server generates the next utterance while the learner is still reading
  the previous one and throws it away if the learner speaks first. The same turn may be asked for twice. All
  bookkeeping (for example, when the last invitation was) goes in `update_states`. That method is Alex's, so this is
  **a point the two of you have to agree on**.
- The learner can speak at any time. `session.last_message.role == "user"` is a normal input to `select_speaker`,
  and `message.invited` says whether it answers the tutor's invitation.
- After an invitation the learner may also pass. `select_speaker` is then called again with the tutor's invitation
  still the last message.
- Read the current state for a peer's prompt with `session.state_of(agent_id)`.
- Reading time between messages, pause and interruption are handled by the server. Do not `sleep` in the pipeline.
- When the turn count reaches `MAX_TURNS` (60) the server ends the session.

### 6. Alex + Seongho together

**Two people fill one class.** The server loads a single `PIPELINE`, so all five methods have to be on one class.
The code is in `backend/app/pipeline/csl/` and is registered under the name `csl`.

```
backend/app/pipeline/csl/
  __init__.py      class CslPipeline: the five methods, each calling into the modules below
  knowledge.py     Alex: init_turn, build_classroom, update_states (currently calls the baseline)
  discussion.py    Seongho: select_speaker, speak
  prompting.py     shared: request assembly laid out for the prompt cache (build_messages)
```

`baseline.py` is the server's default and `knowledge.py` still calls it, so do not delete or rename it.

**The contract between you.** (1) the shape of the `KnowledgeState` that `speak` puts into prompts, (2) the keys in
`session.scratch` (use a different key each), (3) how the bookkeeping `select_speaker` needs gets into `update_states`.
The keys agreed so far are in the comment at the top of `knowledge.py`.

**LLM calls.** Use `get_llm()` from `app.llm`: `stream`, `complete`, `complete_json`; `fast=True` for small calls.
The model ids can change at runtime from the admin page, so do not store them yourself. Every call is logged with
model, latency, tokens, cost and the tokens read from the cache. Model reasoning is off by default
(`LLM_REASONING=off`); with it on, reasoning tokens can use up `max_tokens` and leave an empty reply.

**Prompt cache.** A request assembled with `prompting.build_messages` is cached (session block → role block → one
block per message → a tail that changes every call). Anything that changes during a session (state, turn counts,
directives) belongs in the tail only. Every call carries the session id, so one session's requests go to the same
provider and read each other's cache. The hit rate is on the Usage tab of `/admin`.

**Try it.**

```bash
cd backend
uv run python scripts/cli.py "Why is summer hotter than winter?" --pipeline csl
#   Enter = next message, typing = learner message, /state = print knowledge states, /auto = run by itself
uv run pytest
```

- With the server: set `PIPELINE` in `backend/.env`, start the server, open `http://localhost:3000/dev`.
- Add tests under `backend/tests/`. [test_csl_pipeline.py](backend/tests/test_csl_pipeline.py) and
  [test_baseline.py](backend/tests/test_baseline.py) show how to run a pipeline on a fake LLM. They run in CI.
- New Python packages go in `dependencies` in `backend/pyproject.toml`.
- On the live server: `/admin` → Sessions shows each session's messages, every state version, `scratch`, the event
  log and the cost.

**Trying it on the live server (without Hyunmin).** `csl` is already registered in `SESSION_PIPELINES` in
`backend/app/pipeline/__init__.py`. Push to `main`, wait for the deploy, then pick `csl` under "Agents" on
`https://csl.kimhm.in/dev` and start a session. **Only that session** runs on `csl`; other people's sessions and
the server's default (`baseline`) are untouched. It calls an LLM, so it needs the access code.

```python
SESSION_PIPELINES: dict[str, str] = {
    "mock": "app.pipeline.mock:MockPipeline",
    "baseline": "app.pipeline.baseline:BaselinePipeline",
    "csl": "app.pipeline.csl:CslPipeline",
}
```

To try another version side by side, add one more line here. If a registered module cannot be imported,
`uv run pytest` fails and nothing is deployed.

**Making it the default.** When it is time for `csl` to be the server's default, ask Hyunmin to set
`PIPELINE=csl`. Until then sessions created without a name run on `baseline`.

**If the interface is not enough.** If `base.py` or `protocol.py` has to change (a new field for the panel, for
example), tell Hyunmin. After a change to `protocol.py` the frontend types are regenerated with
`uv run python scripts/gen_ts.py`.

### 7. Jeeyun: frontend UI

**Where.** `frontend/src/app/page.tsx` (start page), `src/app/chat/` (classroom page), `src/common`, `src/styles`.

**What is connected now** (11-21; the design is unchanged, only the data became a real session).
- `page.tsx`: entering a topic creates a session (`createSession`) and the address becomes `/?session=<id>`. The
  three steps follow the server's `snapshot.phase`: Initial question = `init` (the setup chat with the guide; the
  Composer sends `actions.replyInit`), Learning direction = `building`, Classroom setup = `ready` (the real
  participants go into `ClassroomOverview`). In `init`, Next skips the rest of the setup chat
  (`actions.finishInit`). "Start learning session" goes to `/chat?session=<id>`. If the server has an access code,
  a field appears under the topic; a code that worked is remembered by the browser.
- `chat/ChatSession.tsx`: opens the session named by `?session=<id>`. Entering starts the discussion
  (`actions.startDiscussion` when the phase is `ready`). Messages are the discussion channel of
  `snapshot.messages`, the typing bubble is `snapshot.activeTurn`, Pause / Resume are `actions.pause` /
  `actions.resume`, the Composer sends `actions.say`, and the right panel shows the latest
  `snapshot.states[id]` of the selected participant. Selecting a participant is logged with
  `actions.track("panel.open")`. A session that is still being set up is sent back to `/?session=<id>`.
- `ClassroomOverview` takes a `participants` prop (without it, the earlier sample data).
- Opening `/?pipeline=mock` creates that session on the free mock (for checking the UI; no access code).
  `/?pipeline=csl` works the same way.

**From the Studio 3 interviews, now in the classroom page** (11-21, `chat/ChatSession.tsx`).
- Item 4 (peers mistaken for correct information): Correct / Partly correct / Incorrect marks next to the
  beliefs and the explanation in the panel (`accuracy`, `explanationAccuracy`); "Mark what is correct and
  incorrect" at the bottom of the panel turns them off. The panel and the classroom introduction say that a peer
  is a learner, not an expert.
- Item 6 (pace): above the conversation, Auto-advance on/off, speed (0.5× to 2×) and a "Next message" button
  (`actions.setPace`, `actions.step`). With "Pause the discussion when I open a panel" on, selecting a participant
  pauses the discussion.
- Item 9 (when a state changed): a participant whose state changed gets a dot in the list, and the message that
  caused the change gets a "…'s understanding changed" link under it. The panel has "Updated after turn N: show
  the message" (scrolls to that message), what changed this time (before / after from `changes`) and a collapsed
  "Earlier understanding" with every earlier version.
- The two options are kept in the browser's localStorage (`csl.classroomPrefs`).

**Not in the UI yet.** Choosing the discussion language (English for now; the Language button in the Navbar is
not connected), a side-by-side comparison of the peers' states (item 10), collapsing Open question and a question
log (item 11), collapsing and moving the panel (item 12), voice input (item 14). The table below says what to
build them from.

**The backend connection already exists.** Two things are all you need:

```tsx
import { createSession, useCslSession } from "@/lib/csl";

const { sessionId } = await createSession({ topic, language: "en" });
const { snapshot, connection, error, actions } = useCslSession(sessionId);
```

- `snapshot` is always the complete current state of the session; render from it. Its fields and the list of
  `actions` are in [PROTOCOL.md](backend/docs/PROTOCOL.md); [dev/page.tsx](frontend/src/app/dev/page.tsx) is a
  working example that uses all of them.
- **Use mock sessions for UI work:** `createSession({ topic, pipeline: "mock" })`. No LLM calls, no cost, no access
  code. It replays a fixed scenario ("Why is summer hotter than winter?", 15 turns, English or Korean) and ignores
  the topic. In turn 15 the tutor asks the learner to explain.
- For the real agents use `pipeline: "csl"` (leaving `pipeline` out gives the server's default, `baseline`). On
  the live server that needs an access-code field. `fetchHealth()` returns the names that can be picked.

**Good to know.**
- `src/lib/csl/protocol.ts` is generated. Do not edit it by hand; if a type is missing, tell Hyunmin.
- Leave `/dev` and `/admin` in place. The deploy script checks that `/dev` answers 200.
- **Login takes a nickname only.** Use `useCurrentUser()`, `signIn(name)`, `signOut()` and
  `fetchUserSessions(userId)` from `src/lib/csl`. `createSession()` attaches the signed-in user by itself, so
  there is nothing to pass. Already in place:
  - The profile button of `Navbar` goes to `/mypage` and shows the nickname once signed in.
  - `src/common/components/LoginCard.tsx`: the sign-in form. `/` shows it until someone is signed in (the
    `if (!user)` branch at the top of `page.tsx`).
  - `src/app/mypage/page.tsx`: the list of my sessions. "Continue" goes to `/chat?session=<id>&topic=<topic>`.
- **Continuing a session.** Both pages open the session named by `?session=<id>` (`useCurrentSessionId()`), so a
  reload, the back button, a shared link and "Continue" on My page all return to the same session. Leaving a page
  pauses the discussion on the server; coming back resumes it.
- Log UI actions the server cannot see with `actions.track(name, data)` (opening a panel, for example). Milestone 5
  analyses usage from these.
- UI text is English by default. The discussion language is chosen per session with `language: "en" | "ko"`.
- This is Next.js 16. Read [frontend/AGENTS.md](frontend/AGENTS.md) before writing code.
- Checks: `pnpm exec next typegen && pnpm exec tsc --noEmit`, `pnpm lint`, `pnpm build`. The two eslint errors in
  `src/styles/styled.d.ts` and `themes.d.ts` were there before.

**Items from the Studio 3 interviews (the protocol already supports them):**

| Item | Use |
| --- | --- |
| Pace control, auto-advance off | `actions.setPace({ auto, speed })`, `actions.step()` |
| Auto-pause when a panel opens | `actions.pause()` / `actions.resume()` |
| Typing indicator | `snapshot.activeTurn` (while its `text` is empty) |
| State history, "changed in turn N" links | `turnId`, `turnNumber`, `changes` of `snapshot.states[agentId][i]` |
| Side-by-side peer comparison | `snapshot.states` |
| Highlighting wrong beliefs (optional) | `belief.accuracy`, `explanationAccuracy` |
| The tutor's request to explain | `snapshot.status === "waiting_user"`, `invitedTurnId` |

### 8. Ask Hyunmin for

- The live server's access code, the admin token (`/admin`), an OpenRouter key
- Changes to the server's default `PIPELINE` or any other `.env` value, service restarts
- Changes to `protocol.py`, `base.py` or server behaviour (pacing, interruption, storage)
- Failed deploys (the Deploy workflow in GitHub Actions)

### 9. What is left

- Alex: the real implementation of `knowledge.py` (setup chat, classroom, state updates). The state update that
  stops partway is the most urgent item (section 4).
- Seongho: refining the discussion. The branch `seongho/cache-friendly-discussion` has one commit that is not on
  `main` (`78a1244`).
- Jeeyun: refine the product UI. It is connected; what is not in the UI yet is listed in section 7.
- Hyunmin: switch the server's default to `csl`, reboot test, check with several simultaneous users, the report
  (URL, access code, list of libraries and tools, screenshots, the System Architecture tab)
- Team: decide how the discussion refers to the learner (the screen shows "나" / "You", the prompt says "Learner")
