# workflow-mcp 전체 구현 계획

## 1. 문서 목적

이 문서는 현재 저장소에 있는 설계 산출물을 실제로 실행 가능한 `workflow-mcp` 서버로 구현하기 위한 순서와 완료 기준을 정의한다.

현재 저장소에는 다음 파일이 있으며 애플리케이션 소스와 테스트는 아직 없다.

| 파일 | 역할 | 구현 시 기준 |
|---|---|---|
| `workflow-mcp-spec-v0.2.json` | 워크플로 상태, MCP 도구, Artifact 계약, 오류 계약의 기준 명세 | API/도메인 테스트의 기준 |
| `workflow-mcp-schema-v0.1.sql` | SQLite 테이블, 인덱스, 제약조건, 조회용 View | 저장소 계층의 기준 |
| `mcp.drawio` | 사용자–Codex–Skill–workflow MCP–SQLite 관계와 정상 흐름 시각화 | 통합 흐름 및 문서 보조 |

## 2. 구현 목표와 범위

### 목표

사용자의 개발 작업을 하나의 workflow로 관리하고, `DISCOVERY → PLANNING → WAITING_APPROVAL → IMPLEMENTING → REVIEWING → COMPLETED` 흐름을 강제한다. 각 단계의 결과는 Artifact로 저장하고, 상태 변경은 append-only Event로 기록한다.

### 1차 범위

- MCP 서버 실행 진입점과 도구 등록
- workflow 생성/조회
- Context 수집 및 사용자 컨텍스트 대기/제공
- Plan 버전 생성과 명시적 승인
- 승인된 Plan에 대한 Implementation 결과 등록
- Review verdict에 따른 세 갈래 전이
- SQLite 저장소, 트랜잭션, 외래키/유니크 제약
- JSON Schema 기반 입력·출력·Artifact 검증
- 정상 흐름, 분기 흐름, 실패/경계 조건 테스트

### 1차 범위 제외

- Codex 자체의 코드 수정 실행기
- 실제 프로젝트 파일을 수정하는 sandbox/권한 시스템
- 원격 DB 또는 다중 사용자 인증
- 웹 UI와 실시간 알림
- COMPLETED workflow의 재개 기능

## 3. 구현 원칙과 선결 정책

구현 시작 시 다음 정책만 고정한다. API 명세와 DB 스키마는 독립적으로 versioning한다.

1. **버전 관리**: `spec_version = 0.2`, `schema_version = 0.1`을 각각 관리하고, migration 이력을 `schema_migrations` 같은 테이블에 기록한다. 두 파일의 버전이 같아야 한다는 조건은 두지 않는다.
2. **`submit_review` 전이**: `passed → COMPLETED`, `fix_required → IMPLEMENTING`, `context_required → DISCOVERY`를 유지한다. `fix_required`는 기존 승인을 유지하고, `context_required`는 승인을 무효화한다.
3. **승인 경계**: Skill이 “명시적 사용자 승인 전에는 `approve_plan`을 호출하지 않는다”는 정책을 담당한다. MCP는 사용자 자연어 발화의 진위를 독립적으로 판정하지 않고, `WAITING_APPROVAL`, 현재 Plan 존재, `planVersion` 일치 같은 기계적으로 검증 가능한 guard만 수행한다. `APPROVAL_REQUIRED`는 호출 계약 위반을 나타내는 오류 코드로 유지할 수 있다.
4. **구현 쓰기 경계**: 프로젝트 파일 수정은 Codex/Skill의 책임이다. MCP는 파일을 직접 수정하지 않으며, `complete_implementation`을 `IMPLEMENTING`에서만 허용하고 올바른 `ImplementationArtifact`만 등록한다.
5. **동시성·식별자**: 동일 workflow의 상태 변경은 하나의 transaction으로 처리하고, UUID 문자열 ID와 UTC ISO-8601 timestamp를 사용한다.
6. **오류 응답**: 명세의 오류 코드와 공통 응답 형식을 모든 도구에서 일관되게 사용한다.

## 4. 권장 구현 순서

### Phase 0 — 최소 Python/MCP 부트스트랩

**작업**

- Python 프로젝트와 MCP SDK, SQLite 드라이버, Pydantic, 테스트 러너를 추가한다.
- 최소 구조(`server.py`, `models.py`, `state_machine.py`, `db.py`, `services.py`, `tests/`)를 만든다.
- `workflow-mcp-spec-v0.2.json`을 정상적으로 로드하고 기본 구조를 확인한다.
- 최소한의 MCP 서버 실행과 `workflow_start`, `workflow_status` tool registration을 구현한다. 이 단계에서는 두 도구의 동작을 하드코딩해도 된다.

**완료 기준**

- MCP 서버가 정상 실행된다.
- `workflow_start`와 `workflow_status` 정도의 최소 tool registration이 가능하다.
- spec 파일을 정상적으로 로드한다.

### Phase 1 — SQLite와 최소 workflow 수직 슬라이스

**작업**

- `workflow`, `artifact`, `workflow_event` 테이블과 인덱스/View를 migration으로 적용한다.
- 연결 생성 시 `PRAGMA foreign_keys = ON`을 보장한다.
- 우선 `workflow_start`와 `workflow_status`에 필요한 SQL과 간단한 DB helper를 구현한다. 초기 버전에서는 별도 Repository 추상화 계층을 만들지 않는다.
- 이후 Artifact/Event 저장이 필요해질 때 `db.py`의 함수들을 확장한다.
- 모든 쓰기 메서드에 트랜잭션 경계를 둔다.
- JSON payload는 저장 전 검증하고, 읽을 때 typed object로 변환한다.

**완료 기준**

- 외래키, Plan version 유니크 제약, Approval version 유니크 제약이 실제로 동작한다.
- workflow 하나의 상태 변경이 Artifact와 Event를 남기거나, 실패 시 둘 다 남기지 않는다.

### Phase 2 — 도메인 모델과 상태 머신

**작업**

- `WorkflowState`, `ArtifactType`, `ReviewVerdict`, 오류 코드 enum을 정의한다.
- 허용 상태 전이와 전이별 guard/effect를 순수 함수 또는 도메인 서비스로 구현한다.
- 다음 전이를 표로 고정한다.

| 현재 상태 | 명령 | 다음 상태 | 핵심 조건 |
|---|---|---|---|
| 없음 | `workflow_start` | `DISCOVERY` | task 유효 |
| `DISCOVERY` | `submit_context` | `PLANNING` | Context 유효 |
| `DISCOVERY` | `request_user_context` | `WAITING_CONTEXT_INPUT` | 사용자 입력 필요 |
| `WAITING_CONTEXT_INPUT` | `provide_user_context` | `DISCOVERY` | content 존재 |
| `PLANNING` | `submit_plan` | `WAITING_APPROVAL` | 필수 계획·테스트 섹션 존재 |
| `WAITING_APPROVAL` | `approve_plan` | `IMPLEMENTING` | Skill의 명시적 승인 후 호출, 현재 Plan version 일치 |
| 허용 상태 | `require_context` | `DISCOVERY` | 안전한 진행에 추가 정보 필요 |
| `IMPLEMENTING` | `complete_implementation` | `REVIEWING` | 승인 버전과 구현 버전 일치 |
| `REVIEWING` | `submit_review(passed)` | `COMPLETED` | Review 유효 |
| `REVIEWING` | `submit_review(fix_required)` | `IMPLEMENTING` | 승인 Plan 범위 내 수정 |
| `REVIEWING` | `submit_review(context_required)` | `DISCOVERY` | 승인 무효화 |

- 프로젝트 파일 수정은 Codex/Skill의 책임으로 둔다. MCP는 파일을 수정하지 않고, `complete_implementation`을 `IMPLEMENTING`에서만 허용하며 `ImplementationArtifact`만 등록한다.
- 새 Plan 생성 시 `approvedPlanVersion = null`로 만드는 규칙을 도메인에 반영한다.

**완료 기준**

- 상태 머신 단위 테스트가 모든 정상 전이와 금지 전이를 커버한다.
- `COMPLETED`는 passed review 외의 경로로 진입할 수 없다.

### Phase 3 — Pydantic Artifact 모델 및 검증

**작업**

- `ContextArtifact`, `PlanArtifact`, `ApprovalArtifact`, `ImplementationArtifact`, `ReviewArtifact`, `TestScenario` 모델을 구현한다.
- Pydantic 모델을 validation의 1차 구현으로 사용한다. `ContextArtifact`, `PlanArtifact`, `ApprovalArtifact`, `ImplementationArtifact`, `ReviewArtifact`, `TestScenario`를 typed model로 정의한다.
- 명세의 required/optional 필드, enum, 문자열 최소 길이, 추가 필드 금지 정책을 모델 설정에 반영한다.
- Python 내부 필드는 `snake_case`로 두되, MCP 입력/출력의 `camelCase`는 Pydantic alias로 변환한다.
- JSON spec은 설계 계약 문서로 유지하고, 초기 런타임의 source-of-truth로 사용하지 않는다. 안정화 후 Pydantic 모델에서 JSON Schema를 생성해 spec과 비교하는 contract test를 추가한다.
- `submit_plan`의 필수 조건인 goal, scope, steps, runtimeFlow, happyPath, edgeCases, failurePaths를 별도 오류로 식별한다.
- Plan/Approval/Implementation/Review의 `workflowId`와 `planVersion` 일치 여부를 검증한다.

**완료 기준**

- 잘못된 Artifact는 DB에 기록되지 않는다.
- 출력은 명세의 성공/실패 response shape를 만족한다.

### Phase 4 — 전체 MCP 도구 핸들러 연결

명세 순서대로 나머지 도구를 구현해 전체 10개 tool registration을 완성한다. 각 핸들러는 `parse → Pydantic validate → state guard → transaction → response` 구조를 따른다.

1. `workflow_start`
2. `workflow_status`
3. `submit_context`
4. `request_user_context`
5. `provide_user_context`
6. `submit_plan`
7. `approve_plan`
8. `require_context`
9. `complete_implementation`
10. `submit_review`

각 쓰기 도구는 상태 변경과 함께 적절한 Event를 기록한다. 이벤트에는 최소한 `workflow_id`, `event_type`, `from_state`, `to_state`, `plan_version`, `created_at`을 포함한다.

**완료 기준**

- MCP 클라이언트가 각 도구를 호출할 수 있다.
- 도구별 오류 코드가 명세와 일치한다.
- 상태 조회에서 최신 Context/Plan/Approval/Implementation/Review ID가 반환된다.

### Phase 5 — 정상 흐름과 분기 흐름 통합 테스트

**핵심 시나리오**

- 시작 → Context 제출 → Plan 제출 → 명시적 승인 → 구현 완료 → passed review → 완료
- Discovery에서 사용자 컨텍스트 요청 → 사용자 응답 → Discovery 재진입
- 새 Plan 제출로 이전 승인 무효화
- Review `fix_required` → 같은 승인 Plan으로 구현 재진입
- Review `context_required` → 승인 제거 후 Discovery 복귀

**검증할 실패 시나리오**

- 존재하지 않는 workflow
- 현재 상태와 맞지 않는 도구 호출
- 승인되지 않은 Plan으로 구현 완료 시도
- Plan version 불일치
- Skill 정책을 거치지 않고 `approve_plan`이 호출된 경우의 오류 응답
- 잘못된 Review verdict
- 빈 task/context 또는 필수 테스트 섹션 누락
- 중복 Plan/Approval version 저장
- 완료 workflow에 후속 쓰기 시도

### Phase 6 — Codex App 연결

**작업**

- Codex App/Skill에서 workflow ID와 현재 상태를 전달하는 연결 방식을 정의한다.
- Plan 제시 후 사용자 승인 시점에만 Skill이 `approve_plan`을 호출하도록 연결한다.
- MCP가 사용자 발화를 검증한다고 가정하지 않고, Skill 정책과 MCP guard의 책임을 문서화한다.

**완료 기준**

- Codex App에서 workflow 생성부터 상태 조회까지 호출할 수 있다.
- 승인 전후 상태와 Plan version이 일관되게 전달된다.

### Phase 7 — Skill 작성

**작업**

- 상태별 Codex 행동 규칙을 Skill로 정의한다.
- `current_state != IMPLEMENTING`이면 프로젝트 파일 수정을 하지 않도록 안내한다.
- 사용자 승인 없이 `approve_plan`을 호출하지 않도록 명시한다.
- `fix_required`와 `context_required`를 다르게 처리하도록 지시한다.

**완료 기준**

- Skill이 MCP의 기계적 guard와 충돌하지 않는다.
- 승인, 구현, 리뷰, 추가 컨텍스트 요청의 사용자 경험이 재현 가능하다.

### Phase 8 — 운영성, 복구성, 문서화

**작업**

- migration 적용 명령과 DB 백업/복구 절차를 문서화한다.
- 구조화 로그에 workflow ID, 도구명, 이전/다음 상태, plan version, 오류 코드를 포함한다.
- 서버 재시작 후 상태/Artifact/Event가 보존되는지 검증한다.
- README에 설치, 실행, MCP 연결, 예제 호출, 오류 처리, 상태 전이 그림을 추가한다.
- 명세 변경 시 계약 테스트가 먼저 실패하도록 CI를 구성한다.

**완료 기준**

- 새 환경에서 한 번의 초기화 절차로 서버를 실행할 수 있다.
- 모든 테스트와 명세 검증이 CI에서 재현된다.
- 운영자가 workflow의 현재 상태와 이벤트 이력을 추적할 수 있다.

## 5. 권장 초기 모듈 구조

```text
src/workflow_mcp/
  server.py        MCP 서버 진입점과 도구 등록
  models.py        Pydantic 모델과 공통 응답
  state_machine.py 상태, guard, 전이 규칙
  db.py            SQLite 연결, migration, SQL helper
  services.py      workflow 명령과 transaction 조합
tests/
  unit/            상태 머신, validator, repository
  integration/     도구 호출과 SQLite 전이
  contract/         JSON 명세와 실제 응답 비교
migrations/
  001_initial.sql
docs/
  architecture.md
  state-machine.md
```

초기 버전은 이 정도의 경량 구조로 시작한다. 파일이 커지거나 테스트 경계가 뚜렷해질 때만 `domain/`, `persistence/`, `validation/` 패키지로 분리한다. MCP 전송 계층과 상태 머신을 분리하는 원칙은 유지한다.

## 6. 런타임 흐름

```text
MCP Client
  → Tool Handler
  → Input/Artifact Validator
  → Workflow State Machine
  → SQLite Transaction
      ├─ workflow 상태 갱신
      ├─ artifact 저장
      └─ workflow_event append
  → Common Response
```

추가 컨텍스트가 필요하면 `approvedPlanVersion`을 무효화하고 Discovery로 되돌린다. Review에서 수정만 필요한 경우에는 기존 승인 버전을 유지해 Implementing으로 돌아간다.

## 7. 우선순위와 의존성

```text
Python/MCP 실행
  ↓
최소 workflow_start/status → SQLite 저장/조회 → 상태 머신
                                      ↓
                             Pydantic Artifact 모델
                                      ↓
                             전체 MCP 도구 연결
                                      ↓
                    통합 테스트 → Codex App 연결 → Skill → 운영 문서
```

가장 먼저 완성해야 하는 수직 슬라이스는 `workflow_start → workflow_status`이고, 그 다음 `submit_context → submit_plan → approve_plan → complete_implementation → submit_review(passed)` 정상 경로를 끝까지 연결한다. 이후 사용자 입력 대기, 수정 재진입, 컨텍스트 요구 분기를 추가한다.

### 압축된 실행 순서

1. Phase 0: Python 프로젝트와 MCP 서버를 실행하고 `workflow_start`를 하드코딩한다.
2. Phase 1: SQLite를 연결해 `workflow_start`와 `workflow_status`를 실제 저장/조회로 전환한다.
3. Phase 2: 상태 머신과 guard를 구현하고 단위 테스트를 작성한다.
4. Phase 3: Pydantic Artifact 모델과 검증을 추가한다.
5. Phase 4: 나머지 MCP 도구를 연결해 전체 도구 등록을 완성한다.
6. Phase 5: Happy/Edge/Failure 통합 테스트를 완성한다.
7. Phase 6: Codex App 연결을 구현한다.
8. Phase 7: 상태·승인·파일 수정 정책을 Skill로 작성한다.
9. Phase 8: 운영성, 복구성, 문서화, CI를 마무리한다.

## 8. 위험 요소와 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| 명세와 DB 버전 차이 | 계약 해석 혼동 | `spec_version`과 `schema_version`을 독립 관리하고 migration 이력 기록 |
| 상태 갱신과 이벤트 기록 분리 | 감사 이력과 현재 상태 불일치 | 단일 SQLite transaction으로 처리 |
| Plan 승인과 구현 사이 동시 수정 | 잘못된 Plan 구현 | Plan version guard와 write lock 적용 |
| `fix_required` 범위 확대 | 승인 없는 요구사항 변경 | review finding과 plan scope 비교 후 context_required 처리 |
| JSON payload의 자유 형식화 | 런타임 오류 | 저장 전 Pydantic 검증, 이후 Pydantic↔JSON Schema contract test 추가 |
| 초기 구현 범위 과다 | 핵심 흐름 지연 | 정상 경로 수직 슬라이스 우선, UI/원격 기능은 후순위 |

## 9. 최종 완료 체크리스트

- [ ] spec/schema 독립 버전과 ID/시간/동시성 정책 확정
- [ ] SQLite migration과 최소 DB helper 구현
- [ ] 7개 상태와 모든 허용/금지 전이 구현
- [ ] 10개 MCP 도구 등록 및 response/error 계약 준수
- [ ] Artifact 및 Plan version 검증 구현
- [ ] 모든 상태 변경에 Event 기록
- [ ] 정상·분기·실패·경계 테스트 통과
- [ ] Codex App 연결과 Skill 정책 작성
- [ ] 재시작 후 데이터 보존 확인
- [ ] README, 상태 전이 문서, 실행 방법, CI 작성
