# HANDOFF

Who works where, as of 2026-11-16. · 2026-11-16 기준, 누가 어디서 무엇을 작업하는지.

**[한국어](#한국어)** · **[English](#english)** (same content in both)

---

## 한국어

### 1. 지금 상태

- 실서버: **https://csl.kimhm.in** . `main`에 push하면 테스트와 빌드를 거쳐 자동 배포됩니다.
- 서빙 레이어(세션, 읽기 속도 조절, 끼어들기, WebSocket, 저장, 이벤트 로그)는 완성되어 돌아가고 있습니다.
- 에이전트는 **임시 구현**(`baseline`)입니다. 실서버는 `PIPELINE=baseline`, 모델은 두 종류 모두
  `anthropic/claude-haiku-5.5`입니다. Alex와 Seongho가 이것을 실제 구현으로 교체합니다.
- 제품 UI는 **아직 없습니다**. `/`는 공통 컴포넌트 데모이고, `/dev`가 전체 흐름을 보여주는 확인용 페이지입니다.
- 실서버에는 access code가 걸려 있습니다. 실제 LLM 세션을 만들 때 필요하고, mock 세션에는 필요 없습니다.
- 일정: Studio 4 발표 2026-11-24, 보고서는 다음 날. 채점이 끝날 때까지 실서버가 동작해야 합니다.

| 페이지 | 용도 |
| --- | --- |
| `/` | 공통 컴포넌트 정적 데모. 제품 UI가 들어갈 자리 |
| `/dev` | 세션 전체를 돌려보는 페이지 (설정 대화 → 교실 → 토론 → knowledge state 패널) |
| `/admin` | LLM 사용량과 비용, 모델 교체, 세션 기록과 이벤트 로그. admin token 필요 |

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
- `main`에 push하면 서버에서 `uv run pytest`(백엔드 27개)와 `pnpm build`(타입 검사 포함)를 먼저 돌립니다.
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

**어디서.** `init_turn`, `build_classroom`, `update_states`. 참고 구현은
[baseline.py](backend/app/pipeline/baseline.py)의 `CLASSROOM_SYSTEM`, `STATE_SYSTEM`, `INIT_SYSTEM`, `INIT_STAGES`
프롬프트와 같은 이름의 메서드입니다.

**무엇을 반환하나.**
- `init_turn(session, out)` → 가이드의 다음 말을 `out.write()`로 쓰고 `InitResult(done)`을 반환합니다. 처음에는
  빈 `session.init_transcript`로, 그 뒤로는 학습자가 답할 때마다 호출됩니다. `done=True`를 반환하면 설정 대화가
  끝나고 `build_classroom`이 호출됩니다. 이 대화의 내용이 `build_classroom`의 입력입니다. baseline은
  질문 → 되묻기 → 마무리의 3단계입니다. 빈 발화는 오류로 처리됩니다.
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
- `update_states`가 실패하면 로그만 남고 토론은 계속됩니다(상태는 그대로). 실패를 놓치지 않으려면 `/admin`의
  이벤트 로그에서 `server.error`를 확인하세요.
- 다음 발화는 `update_states`가 끝나야 시작됩니다. baseline은 피어별 호출을 병렬로, `fast=True` 모델로 돌립니다.
- `accuracy`(`correct` / `partial` / `incorrect`)는 선택 항목입니다. UI가 틀린 belief를 강조하는 데 쓸 수 있습니다.

### 5. Seongho: 토론 진행

**어디서.** `select_speaker`와 `speak`. 참고 구현은 [baseline.py](backend/app/pipeline/baseline.py)의
`MODERATOR_SYSTEM`, `PEER_SYSTEM`, `TUTOR_SYSTEM`, `*_DIRECTIVES`와 같은 이름의 메서드입니다.

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
아직 파일은 만들지 않았습니다. 제안하는 구조(이름은 바꿔도 됩니다):

```
backend/app/pipeline/csl/
  __init__.py      class CslPipeline: 다섯 메서드, 각각 아래 모듈을 호출
  knowledge.py     Alex: init_turn, build_classroom, update_states
  discussion.py    Seongho: select_speaker, speak
```

`baseline.py`를 복사해서 시작하면 바로 돌아갑니다. `baseline.py` 자체는 참고용으로 남겨 두세요.

**둘 사이의 계약.** (1) `speak`가 프롬프트에 넣는 `KnowledgeState`의 모양, (2) `session.scratch`의 키(각자
다른 키를 쓰기), (3) `select_speaker`가 필요로 하는 기록을 `update_states`에 넣는 방법.

**LLM 호출.** `app.llm`의 `get_llm()`을 씁니다: `stream`, `complete`, `complete_json`. 작은 호출에는 `fast=True`.
모델 id는 관리자 페이지에서 실행 중에 바뀔 수 있으므로 직접 저장해 두지 마세요. 호출마다 모델, 지연, 토큰,
비용이 기록됩니다. 모델의 reasoning은 기본으로 꺼져 있습니다(`LLM_REASONING=off`). 켜면 reasoning 토큰이
`max_tokens`를 써 버려 빈 응답이 나올 수 있습니다.

**돌려보기.**

```bash
cd backend
uv run python scripts/cli.py "Why is summer hotter than winter?" --pipeline app.pipeline.csl:CslPipeline
#   Enter = 다음 메시지, 글자를 치면 학습자 발화, /state = knowledge state 출력, /auto = 자동 진행
uv run pytest
```

- 서버와 함께 보려면 `backend/.env`에 `PIPELINE`을 넣고 서버를 띄운 뒤 `http://localhost:3000/dev`.
- 테스트는 `backend/tests/`에 추가합니다. [test_baseline.py](backend/tests/test_baseline.py)가 가짜 LLM으로
  파이프라인을 돌리는 예시입니다. CI에서 함께 실행됩니다.
- 새 Python 패키지는 `backend/pyproject.toml`의 `dependencies`에 넣습니다.
- 실서버에서 확인: `/admin` → Sessions에서 세션별 대화, 모든 state 버전, `scratch`, 이벤트 로그, 비용을 볼 수 있습니다.

**실서버에서 돌려보기 (Hyunmin을 거치지 않음).** `backend/app/pipeline/__init__.py`의 `SESSION_PIPELINES`에
한 줄을 추가하고 `main`에 push합니다.

```python
SESSION_PIPELINES: dict[str, str] = {
    "mock": "app.pipeline.mock:MockPipeline",
    "baseline": "app.pipeline.baseline:BaselinePipeline",
    "csl": "app.pipeline.csl:CslPipeline",       # <- 추가
}
```

배포가 끝나면 `https://csl.kimhm.in/dev`의 "Agents"에서 `csl`을 고르고 세션을 시작합니다. **그 세션만** 여러분의
파이프라인으로 돌고, 다른 사람의 세션과 서버 기본값(`baseline`)은 그대로입니다. LLM을 쓰므로 access code가
필요합니다. 등록한 모듈이 import되지 않으면 `uv run pytest`가 실패해서 배포되지 않습니다.

**기본값으로 만들기.** 실제 파이프라인이 준비되면 Hyunmin에게 서버 기본값(`PIPELINE=csl`)을 바꿔 달라고 요청합니다.
그 전까지 이름 없이 만든 세션은 `baseline`으로 돕니다.

**인터페이스가 부족하면.** `base.py`나 `protocol.py`를 바꿔야 하는 경우(예: 패널에 보여줄 새 필드) Hyunmin에게
알려 주세요. `protocol.py`를 바꾸면 `uv run python scripts/gen_ts.py`로 프론트엔드 타입을 다시 만들어야 합니다.

### 7. Jeeyun: 프론트엔드 UI

**어디서.** `frontend/src/app/page.tsx`(지금은 정적 데모)와 새 라우트, `src/common`, `src/styles`.

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
- 실제 에이전트는 `pipeline`을 빼고 만듭니다. 실서버에서는 access code 입력이 필요합니다.
  Alex와 Seongho가 등록한 파이프라인은 이름으로 고를 수 있고, 목록은 `fetchHealth()`가 돌려줍니다.

**알아둘 것.**
- `src/lib/csl/protocol.ts`는 생성되는 파일입니다. 손으로 고치지 마세요. 타입이 부족하면 Hyunmin에게 알려 주세요.
- `/dev`와 `/admin`은 그대로 두세요. 배포 스크립트가 `/dev`의 200 응답을 확인합니다.
- **로그인은 없습니다.** 세션 id만 기억하면 됩니다. 서버가 모든 세션을 보관하고 연결할 때마다 전체 snapshot을
  보냅니다. `src/lib/csl`에 이미 도구가 있습니다: `useCurrentSessionId()`(URL의 `?session=<id>`),
  `setCurrentSessionId(id | null)`(들어가기 / 나가기), `rememberSession()`과 `useRecentSessions()`(이 브라우저가
  만든 세션 목록). 새로고침, 뒤로 가기, 링크 공유가 모두 같은 세션으로 돌아옵니다. 사용 예는 `/dev`와
  [PROTOCOL.md](backend/docs/PROTOCOL.md)에 있습니다.
- 서버가 볼 수 없는 UI 동작은 `actions.track(name, data)`로 기록하세요(예: 패널 열기). Milestone 5의 사용 분석에 씁니다.
- UI 문구는 영어가 기본입니다(11-16에 `page.tsx`, `Composer`, `layout.tsx`의 문구가 영어로 바뀌었습니다).
  토론 언어는 세션을 만들 때 `language: "en" | "ko"`로 고릅니다.
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

- Alex, Seongho: 실제 파이프라인 구현
- Jeeyun: 제품 UI
- Hyunmin: 서버 기본값을 실제 파이프라인으로 전환, 서버 재부팅 확인, 동시 사용자 확인, 보고서(URL, access code,
  라이브러리와 도구 목록, 스크린샷, System Architecture 탭)

---

## English

### 1. Where things stand

- Live server: **https://csl.kimhm.in** . A push to `main` is tested, built and deployed automatically.
- The serving layer (sessions, reading pace, interruption, WebSocket, storage, event log) is finished and running.
- The agents are a **placeholder** (`baseline`). The live server runs `PIPELINE=baseline` with
  `anthropic/claude-haiku-5.5` as both models. Alex and Seongho replace it with the real implementation.
- There is **no product UI yet**. `/` is a demo of the common components; `/dev` is a bare page that shows the whole flow.
- The live server has an access code. Sessions on the real LLM need it; mock sessions do not.
- Dates: Studio 4 presentation 2026-11-24, report the day after. The live server has to keep working until grading is done.

| Page | Purpose |
| --- | --- |
| `/` | Static demo of the common components. Where the product UI goes |
| `/dev` | Runs a whole session (setup chat → classroom → discussion → knowledge-state panels) |
| `/admin` | LLM usage and cost, model switch, session history and event log. Needs the admin token |

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
- On a push to `main` the server first runs `uv run pytest` (27 backend tests) and `pnpm build` (includes the type
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

**Where.** `init_turn`, `build_classroom` and `update_states`. The reference is in
[baseline.py](backend/app/pipeline/baseline.py): the `CLASSROOM_SYSTEM`, `STATE_SYSTEM`, `INIT_SYSTEM` and
`INIT_STAGES` prompts and the methods of the same names.

**What to return.**
- `init_turn(session, out)` → write the guide's next message with `out.write()` and return `InitResult(done)`.
  Called first with an empty `session.init_transcript`, then again after every learner reply. Returning
  `done=True` ends the setup chat and `build_classroom` is called; what was said here is the input of
  `build_classroom`. The baseline does it in three steps: ask → probe → close. An empty message counts as an error.
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
- If `update_states` fails, the error is only logged and the discussion goes on with the states unchanged. To catch
  failures, look for `server.error` in the event log on `/admin`.
- The next utterance starts only after `update_states` has finished. The baseline runs one call per peer in parallel
  on the `fast=True` model.
- `accuracy` (`correct` / `partial` / `incorrect`) is optional. The UI can use it to highlight wrong beliefs.

### 5. Seongho: discussion dynamics

**Where.** `select_speaker` and `speak`. The reference is in [baseline.py](backend/app/pipeline/baseline.py):
`MODERATOR_SYSTEM`, `PEER_SYSTEM`, `TUTOR_SYSTEM`, `*_DIRECTIVES` and the methods of the same names.

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
No file exists yet. A suggested structure (rename as you like):

```
backend/app/pipeline/csl/
  __init__.py      class CslPipeline: the five methods, each calling into the modules below
  knowledge.py     Alex: init_turn, build_classroom, update_states
  discussion.py    Seongho: select_speaker, speak
```

Starting from a copy of `baseline.py` gives you something that runs at once. Leave `baseline.py` itself in place
as the reference.

**The contract between you.** (1) the shape of the `KnowledgeState` that `speak` puts into prompts, (2) the keys in
`session.scratch` (use a different key each), (3) how the bookkeeping `select_speaker` needs gets into `update_states`.

**LLM calls.** Use `get_llm()` from `app.llm`: `stream`, `complete`, `complete_json`; `fast=True` for small calls.
The model ids can change at runtime from the admin page, so do not store them yourself. Every call is logged with
model, latency, tokens and cost. Model reasoning is off by default (`LLM_REASONING=off`); with it on, reasoning
tokens can use up `max_tokens` and leave an empty reply.

**Try it.**

```bash
cd backend
uv run python scripts/cli.py "Why is summer hotter than winter?" --pipeline app.pipeline.csl:CslPipeline
#   Enter = next message, typing = learner message, /state = print knowledge states, /auto = run by itself
uv run pytest
```

- With the server: set `PIPELINE` in `backend/.env`, start the server, open `http://localhost:3000/dev`.
- Add tests under `backend/tests/`. [test_baseline.py](backend/tests/test_baseline.py) shows how to run a pipeline
  on a fake LLM. They run in CI.
- New Python packages go in `dependencies` in `backend/pyproject.toml`.
- On the live server: `/admin` → Sessions shows each session's messages, every state version, `scratch`, the event
  log and the cost.

**Trying it on the live server (without Hyunmin).** Add one line to `SESSION_PIPELINES` in
`backend/app/pipeline/__init__.py` and push to `main`:

```python
SESSION_PIPELINES: dict[str, str] = {
    "mock": "app.pipeline.mock:MockPipeline",
    "baseline": "app.pipeline.baseline:BaselinePipeline",
    "csl": "app.pipeline.csl:CslPipeline",       # <- add
}
```

When the deploy has finished, pick `csl` under "Agents" on `https://csl.kimhm.in/dev` and start a session. **Only
that session** runs on your pipeline; other people's sessions and the server's default (`baseline`) are untouched.
It calls an LLM, so it needs the access code. If the registered module cannot be imported, `uv run pytest` fails and
nothing is deployed.

**Making it the default.** When the real pipeline is ready, ask Hyunmin to change the server's default
(`PIPELINE=csl`). Until then sessions created without a name run on `baseline`.

**If the interface is not enough.** If `base.py` or `protocol.py` has to change (a new field for the panel, for
example), tell Hyunmin. After a change to `protocol.py` the frontend types are regenerated with
`uv run python scripts/gen_ts.py`.

### 7. Jeeyun: frontend UI

**Where.** `frontend/src/app/page.tsx` (currently a static demo) and new routes, `src/common`, `src/styles`.

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
- For the real agents leave `pipeline` out. On the live server that needs an access-code field. Pipelines that
  Alex and Seongho register can be picked by name; `fetchHealth()` returns the list.

**Good to know.**
- `src/lib/csl/protocol.ts` is generated. Do not edit it by hand; if a type is missing, tell Hyunmin.
- Leave `/dev` and `/admin` in place. The deploy script checks that `/dev` answers 200.
- **There is no login.** The session id is all a page has to remember: the server keeps every session and sends
  the full snapshot on every connect. The tools are already in `src/lib/csl`: `useCurrentSessionId()` (the
  `?session=<id>` in the URL), `setCurrentSessionId(id | null)` (enter / leave), `rememberSession()` and
  `useRecentSessions()` (the sessions this browser started). A reload, the back button and a shared link all return
  to the same session. `/dev` and [PROTOCOL.md](backend/docs/PROTOCOL.md) show how to use them.
- Log UI actions the server cannot see with `actions.track(name, data)` (opening a panel, for example). Milestone 5
  analyses usage from these.
- UI text is English by default (on 11-16 the text in `page.tsx`, `Composer` and `layout.tsx` was switched to
  English). The discussion language is chosen per session with `language: "en" | "ko"`.
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

- Alex, Seongho: the real pipeline
- Jeeyun: the product UI
- Hyunmin: switch the server's default to the real pipeline, reboot test, check with several simultaneous users, the report
  (URL, access code, list of libraries and tools, screenshots, the System Architecture tab)
