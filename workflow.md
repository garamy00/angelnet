# AngelDash 기능 명세서

> 단일 macOS 사용자용 통합 대시보드. 회사 내부 시스템(`timesheet.uangel.com`)을
> 호출해 회의실 예약 / 일일 업무 보고 / 타임시트 입력 / UpNote·Notion 동기화를
> 한 포트(`5173`)에서 제공한다. 외부 네트워크에서는 동작하지 않는다.

---

## 1. 시스템 개요

### 1.1 실행 환경

- **OS**: macOS (Keychain `security` CLI 필수)
- **Python**: 3.11 이상
- **네트워크**: 사내망 또는 VPN 으로 `timesheet.uangel.com` 접근 가능
- **포트**: 기본 `5173`, 바인딩 호스트 기본 `0.0.0.0`

### 1.2 진입점

- `./angel` 스크립트 — venv 자동 생성/활성화 → 비밀번호 확보 → uvicorn 백그라운드 기동 → 헬스체크 → 브라우저 자동 열기
- 환경변수 `ANGELNET_USER` (필수), `ANGELNET_PWD` (선택), `ANGELDASH_HOST`, `ANGELDASH_PORT`

### 1.3 인증 모델

- **Timesheet 로그인**: 폼 로그인 후 `JSESSIONID` 쿠키 보관, 모든 후속 호출에 자동 포함
- **비밀번호 저장**: macOS Keychain (`service=angeldash`, `account=<user_id>`) → env → prompt 순으로 확보
- **세션 TTL**: 24시간 메모리 캐시. 만료 시 자동 재로그인

---

## 2. 페이지 구조

| 경로             | 페이지       | 핵심 기능                                                       |
| ---------------- | ------------ | --------------------------------------------------------------- |
| `/`              | 일일업무보고 | 주간 보고 입력 + 타임시트/UpNote/Notion 동기화                  |
| `/projects.html` | 프로젝트     | 카테고리 → 회사 시스템 task 매핑                                |
| `/rooms.html`    | 회의실예약   | 회의실 시간표 + 예약 생성/삭제                                  |
| `/vacation.html` | 휴가조회     | 연차 잔여/사용 내역 read-only                                   |
| `/logs.html`     | 로그         | 최근 action 이력 (보고 복사·타임시트 입력·UpNote·Notion 동기화) |
| `/settings.html` | 설정         | UpNote/Notion/템플릿/공휴일 라벨 설정                           |

---

## 3. 일일 업무 보고 (메인 페이지)

### 3.1 데이터 모델

- **day-block** — 날짜 1일 단위 카드. 오늘 날짜 카드는 옅은 블루 배경 + 좌측 액센트 스트라이프로 강조되고, 헤더에 `오늘` 알약 뱃지 표시
- **entry** — 카테고리 1건 = (카테고리명, 시간, 본문 markdown)
- **week_note** — 주별 자유 메모 (UpNote 동기화 본문 + Notion Week Summary DB 양쪽 모두 동기화 대상)
- **저장 시점**: 입력 후 600ms 디바운스로 SQLite 자동 저장. 별도 저장 버튼 없음

### 3.2 UI 요소

- **주차 네비게이션**: `이전 주` / `이번 주` / `다음 주` / 날짜 입력
- **엔트리 행**: 번호 배지 + 카테고리 입력 + 시간 입력 + 본문 textarea + 삭제(`×`)
  - 번호 배지: 날짜별 자동 카운터 (1, 2, 3 …)
  - 본문 색상은 카테고리 입력과 시각적 구분 위해 톤다운 (`#6b7280`)
  - 카테고리/본문/추가 버튼이 번호 배지 폭만큼 좌측 정렬
- **`+ 카테고리 추가`**: 그 날짜에 빈 엔트리 추가
- **오늘 카드 헤더 우측**의 `📋 팀장 보고 복사` 버튼 — 오늘 entries 를 `team_report.template` 로 렌더링 → 클립보드 (오늘 박스에만 표시)
- **주별 메모**: 모든 일 블록 하단의 자유 텍스트 영역

### 3.3 액션 바 (페이지 하단 sticky, 기능별 그룹화 + 세로 구분선)

좌→우로 4개 그룹:

| 그룹        | 항목                                   | 동작                                                                      |
| ----------- | -------------------------------------- | ------------------------------------------------------------------------- |
| 1. 타임시트 | `타임시트 대상:` select (이번 주/오늘) | 아래 두 버튼의 범위                                                       |
|             | `📤 타임시트 입력`                     | 선택 범위의 entries 를 회사 시스템에 일괄 입력                            |
|             | `🔍 타임시트 확인`                     | 회사 시스템에 저장된 시간과 로컬 비교, 차이를 행에 표시                   |
| 2. UpNote   | `🔄 UpNote 저장`                       | 이번 주 전체를 1개 노트로 묶어 UpNote 앱 생성 (옵션)                      |
| 3. Notion   | `🔄 Notion 동기화`                     | 이번 주 엔트리를 Notion DB 에 1엔트리=1행 동기화 + Week Summary DB (옵션) |
|             | (week-header 우측) `📥 다운로드`       | 이 주가 속한 달의 회사 시스템 Excel 보고서                                |

> 오늘 박스 헤더의 `📋 팀장 보고 복사` 와 액션 바의 UpNote/Notion 버튼은 설정 플래그에 따라 자동 표시·숨김.

### 3.4 메시지 패턴

- 장기 작업(타임시트 입력, UpNote/Notion 동기화) 진행 중에는 화면 중앙 spinner overlay 표시 (사용자 입력 차단)
- 작업 결과는 **화면 중앙 큰 박스** (flash) — `확인` 버튼 + Enter/Escape/백드롭 클릭으로 닫기. 성공 6초 자동 닫힘, 실패는 무한 유지 (사용자가 확인 누를 때까지)

---

## 4. UpNote 동기화

### 4.1 메커니즘

- macOS `upnote://x-callback-url/note/new?title=...&text=...&notebook=...` URL 호출
- `open` 명령으로 로컬 UpNote 앱을 깨워 새 노트 생성
- **단방향**: 노트 조회/수정/삭제 endpoint 없음 → 매 호출마다 새 노트
- 외부 네트워크 전송 없음 (로컬 앱 IPC)

### 4.2 설정 항목

| 설정 키                     | UI 라벨                     | 기본값        | 설명                                           |
| --------------------------- | --------------------------- | ------------- | ---------------------------------------------- |
| `upnote.enabled`            | UpNote 동기화 사용          | `true`        | 메인 버튼 표시 토글                            |
| `upnote.notebook_id`        | 노트북 이름                 | (없음)        | UpNote `notebook` 파라미터. 비우면 기본 노트북 |
| `upnote.markdown`           | UpNote markdown 렌더링      | `false`       | UpNote 의 `markdown` 파라미터                  |
| `upnote.wrap_in_code_block` | 본문을 코드 블록으로 감싸기 | `false`       | ` ``` ` 감싸 markdown 자동 변환 차단           |
| `upnote.title_template`     | UpNote 제목                 | (기본 템플릿) | Jinja2                                         |
| `upnote.body_template`      | UpNote 본문                 | (기본 템플릿) | Jinja2                                         |

### 4.3 트리거

- 메인 페이지 `🔄 UpNote 저장` 클릭 → 확인 다이얼로그 → `POST /api/actions/upnote-sync`
- 진행 중에는 중앙 spinner overlay, 결과는 중앙 큰 메시지 박스 (성공 6초 자동 / 실패 무한 유지 + `확인` 버튼)

### 4.4 주의사항

- 같은 주에 여러 번 누르면 노트가 중복 생성됨 (UpNote 의 한계)
- macOS 가 켜져 있고 UpNote 앱이 본인 계정으로 로그인된 상태여야 함

---

## 5. Notion 동기화

### 5.1 메커니즘

- Notion REST API (`api.notion.com/v1`) 호출
- Internal Integration Token (Bearer) 인증
- **엔트리 단위 1행 동기화**: (날짜, 카테고리) 기준 중복 검사 후 존재 시 update, 없으면 create
- 같은 주를 여러 번 동기화해도 행이 중복되지 않음

### 5.2 DB 스키마 (사용자가 Notion 에서 직접 생성)

| Property   | Type   | 용도                                                |
| ---------- | ------ | --------------------------------------------------- |
| `Name`     | Title  | `YYYY-MM-DD · <카테고리>` 형식 자동 생성            |
| `Date`     | Date   | 작업일                                              |
| `Project`  | Select | 카테고리 → 프로젝트 매핑된 이름 (없으면 빈값)       |
| `WorkType` | Select | 프로젝트의 `work_type` (개발/세미나/시험·지원/영업) |
| `Hours`    | Number | 작업 시간 (소수 0.5 단위)                           |
| `Category` | Text   | 카테고리 원본                                       |

> Property 이름은 설정 페이지에서 커스터마이즈 가능.
> Notion Select 옵션 이름의 콤마(`,`)는 코드에서 `·` 로 자동 치환 (Notion 제약).

### 5.3 페이지 본문

- 엔트리의 `body_md` 가 비어있지 않으면 페이지 children 에 `plain text` 코드 블록으로 삽입
- 들여쓰기/줄바꿈 그대로 보존
- 2000자 초과 시 자동 청크 분할

### 5.4 설정 항목

| 설정 키                | UI 라벨            | 기본값     | 저장 위치                                 |
| ---------------------- | ------------------ | ---------- | ----------------------------------------- |
| `notion.enabled`       | Notion 동기화 사용 | `false`    | DB                                        |
| `notion.database_id`   | Database ID        | (없음)     | DB                                        |
| `notion.prop_title`    | Title property     | `Name`     | DB                                        |
| `notion.prop_date`     | Date property      | `Date`     | DB                                        |
| `notion.prop_project`  | Project property   | `Project`  | DB                                        |
| `notion.prop_worktype` | WorkType property  | `WorkType` | DB                                        |
| `notion.prop_hours`    | Hours property     | `Hours`    | DB                                        |
| `notion.prop_category` | Category property  | `Category` | DB                                        |
| Integration Token      | Integration Token  | (없음)     | **Keychain** (`service=angeldash-notion`) |

### 5.5 셋업 절차 (1회)

1. https://www.notion.so/my-integrations → Internal integration 생성 → token 복사
2. Notion 에서 Database 생성, 위 6개 property 추가
3. Database 페이지 `···` → `Connections` → 해당 integration 추가
4. AngelDash 설정 페이지에서:
   - Notion 동기화 사용 체크
   - Token 입력 → 저장 (이후 화면에 다시 표시되지 않음)
   - Database ID 입력 (32자 UUID, 대시 포함/제외 모두 OK)

### 5.6 Week Summary 동기화 (옵션)

엔트리 동기화와 별도로, 메인 페이지의 **📝 이번 주 메모** (week_note) 를 별도 Notion Database 에 주별 1행으로 push.

**Notion DB schema:**
| Property | Type | 값 |
|---|---|---|
| `Week` | Title | `2026-W19` 형식 |
| `Date` | Date | 그 주 월요일 |

본문(page content)에 메모 markdown 이 코드블록으로 삽입. `Week == 2026-W19` 기준 자동 update, 같은 주 여러 번 동기화해도 중복 없음. 메모가 비어 있으면 skip.

**설정 키:**
| 키 | 기본값 |
|---|---|
| `notion.week_enabled` | `false` |
| `notion.week_db_id` | (없음) |
| `notion.week_prop_title` | `Week` |
| `notion.week_prop_date` | `Date` |

**트리거**: 메인 페이지의 `🔄 Notion 동기화` 가 엔트리 + Week Summary 둘 다 같이 실행.

### 5.7 Projects Push (옵션)

AngelDash 의 **등록된 프로젝트** 목록을 Notion 의 별도 DB 로 push. 신규 항목만 추가, 기존 페이지는 본문 보존하면서 비어있는 Code 필드만 backfill.

**Notion DB schema:**
| Property | Type | 값 |
|---|---|---|
| `Name` | Title | 프로젝트 이름 |
| `WorkType` | Select | 개발/세미나/시험·지원/영업 (선택) |
| `Code` | Text | 회사 시스템의 프로젝트 코드 (`cNPDBu2604` 같은 형식) |

**핵심 동작 원칙:**

- **신규 추가만**: 같은 Name 페이지가 이미 있으면 절대 본문 안 건드림
- **Code backfill**: 기존 페이지의 Code 가 비어 있으면 채워줌 (메타데이터만, 본문은 그대로)
- **Code 가 이미 채워진 페이지**: 완전히 그대로 둠 (수동 편집 보호)

**설정 키:**
| 키 | 기본값 |
|---|---|
| `notion.projects_enabled` | `false` |
| `notion.projects_db_id` | (없음) |
| `notion.projects_prop_name` | `Name` |
| `notion.projects_prop_worktype` | `WorkType` |
| `notion.projects_prop_code` | `Code` |

**트리거**: 프로젝트 페이지(`/projects.html`) 의 "등록된 프로젝트" 섹션 우측 상단 `🔄 Notion 업데이트` 버튼.

### 5.8 API 엔드포인트

- `GET /api/settings/notion-token-status` — 토큰 저장 여부만 반환 (값 노출 안 함)
- `PUT /api/settings/notion-token` — 토큰 저장. 빈 문자열이면 키체인 항목 삭제
- `POST /api/actions/notion-sync` — `{ week_iso, dry_run? }` → `{ created, updated, total, week_synced, week_action }`
- `POST /api/actions/notion-projects-sync` — body 없음 → `{ added, skipped_count, code_backfilled, total }`

---

## 6. 회의실 예약

- `/rooms.html` 에서 시간 × 회의실 그리드 표시
- 빈 셀 클릭 → 예약 모달, 본인 예약 클릭 → 상세 + 삭제
- 일(day) / 2주(week2) 뷰 토글
- 층 드롭다운 (8 / 10 / 12) — 실제 회의실 ID/이름은 `rooms.py` 에서 정의 (`rooms.example.py` 복사 후 본인 환경 값으로 수정)

---

## 7. 프로젝트 / 카테고리 매핑

- `/projects.html` — 사용자가 등록한 카테고리 → 회사 시스템 task 매핑
- `work_type` 별로 같은 프로젝트명을 여러 task 로 등록 가능 (UNIQUE(name, work_type))
- 패턴 매핑 (regex) 으로 자동 매핑 지원
- `mappings` 에 매핑되지 않은 카테고리는 타임시트 입력에서 자동 제외 또는 경고

### 7.1 회사 시스템 식별자 — 두 종류

`projects` 테이블이 회사 시스템의 두 가지 식별자를 동시에 보관:

| 컬럼           | 의미                                           | 예시         | 출처                                        |
| -------------- | ---------------------------------------------- | ------------ | ------------------------------------------- |
| `remote_id`    | jobtime 의 task_id (숫자 string)               | `11182`      | `list_jobtime_tasks` 응답의 `id`            |
| `project_code` | 프로젝트 관리의 code (사람이 읽기 좋은 식별자) | `cNPDBu2604` | `search_joinable_projects` 응답의 `data[1]` |

- **타임시트 입력 시**: `remote_id` 사용 (task_id 단위로 시간 push)
- **Notion 표시 시**: `project_code` 사용 (의미 있는 식별자)

신규 프로젝트 등록 시 jobtime task 목록 fetch 가 자동으로 search_joinable_projects 도 호출해 name 으로 매칭, project_code 까지 함께 저장. 매칭 실패 시 code 는 빈 값.

---

## 8. 휴가 / 공휴일

- `/vacation.html` — 연차 요약 + 연도별 사용 내역 read-only
- 메인 페이지의 day-block 헤더에 휴가/공휴일 태그 표시
- `misc.holiday_exclude_labels` — 공휴일 label 중 출근일로 취급할 항목 (단축 근무 등)

---

## 9. 데이터 저장

### 9.1 SQLite DB

- 경로 우선순위: `ANGELDASH_TIMESHEET_DB` env → `ANGELTIME_DB` env (legacy) → `~/.local/share/angeldash/timesheet.sqlite`
- 자동 마이그레이션 (스키마 변경 시 ALTER 또는 rebuild)
- 보존: 무제한. `action_log` 만 90일 자동 정리

### 9.2 테이블

| 테이블             | 용도                                                                                           |
| ------------------ | ---------------------------------------------------------------------------------------------- |
| `days`             | (date, week_iso) 1행                                                                           |
| `entries`          | day 의 카테고리 행들 (date, order_index, category, hours, body_md)                             |
| `week_notes`       | (week_iso, body_md) 주별 메모                                                                  |
| `projects`         | (name, work_type, remote_id, project_code, active) — remote_id=task_id, project_code=회사 코드 |
| `mappings`         | (category → project_id)                                                                        |
| `pattern_mappings` | (regex pattern → project_id)                                                                   |
| `setting`          | key-value (UpNote/Notion 설정 + 템플릿)                                                        |
| `action_log`       | (action_type, target_range, status, message) — UI 의 /logs.html 에 표시                        |

### 9.3 비밀정보

- Timesheet 비밀번호: Keychain `service=angeldash`
- Notion Integration Token: Keychain `service=angeldash-notion`
- DB 에 평문 비밀번호/토큰 저장 안 함

---

## 10. UI 디자인 규칙

### 10.1 다크 팔레트

- `:root` 의 CSS custom properties 로 통일 (`--color-bg`, `--color-surface`, `--color-accent` 등)
- `style.css` (회의실용) 와 `main.css` (그 외) 가 같은 변수 공유

### 10.2 메시지 패턴

- **toast**: 화면 하단 작은 알림, 3초 자동 사라짐 — 가벼운 confirm 용
- **flash**: 화면 중앙 큰 박스, `확인` 버튼 + Enter/Escape/백드롭 클릭 닫기 — 작업 결과 (성공 6초 / 실패 무한)
- **progress overlay**: 작업 중 spinner + 라벨, 사용자 입력 차단

### 10.3 엔트리 번호

- 각 day-block 안의 entries 가 `1, 2, 3 …` 으로 자동 카운터
- CSS `counter-reset` + `counter-increment` 활용

### 10.4 설정 페이지 — 카드형 섹션

- 각 `<section>` 이 카드 (배경 패널 + 상단 회색 헤더로 `<h2>` 강조)
- 섹션 첫 단락(`h2 + p.muted`)은 블루 액센트 박스로 도입 설명 강조
- `<h3>` 서브섹션은 좌측 3px 액센트 바
- 체크박스 라벨은 별도 박스(`background: --color-surface-2`) 로 클릭 영역 명확화
- `<details>` (property 커스터마이즈) 펼침 시 각 필드가 가로줄 구분, 톤다운된 muted 색
- 일반 input 은 라벨 아래에 width 100% 로 가득 채움

### 10.5 액션 그룹 (메인 페이지 액션 바)

- 기능별로 `<div class="action-group">` 묶음
- 그룹 사이에 세로 구분선 (`border-left`) 으로 시각적 분리
- 액션 바 자체는 약간 밝은 배경(`#262a32`) + 상단 그림자로 본문과 분리

---

## 11. 보안

- HTTPS 인증서 검증 비활성 (`httpx.AsyncClient(verify=False)`) — 사내 인증서 호환
- 기본 바인딩 `0.0.0.0` 으로 사내 네트워크 노출. 로컬 전용은 `ANGELDASH_HOST=127.0.0.1`
- 외부에서 접속하는 사람은 **호스트 본인의 권한**으로 동작 — 신뢰 네트워크에서만 사용
- 비밀번호/토큰은 Keychain 또는 환경변수에만 보관, 로그/응답에 평문 출력 없음

---

## 12. 트러블슈팅

| 증상                                               | 원인 / 대처                                                                                                                                                                          |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `bot_blocked` 토스트                               | 서버 자동화 차단. 5분 대기                                                                                                                                                           |
| `auth` 401                                         | Timesheet 비밀번호 변경됨. Keychain Access 에서 `angeldash` 항목 삭제 후 재실행                                                                                                      |
| `current-user missing userId`                      | 키체인의 비밀번호와 env 비밀번호가 다름. 키체인 항목 삭제 후 재시도                                                                                                                  |
| Notion `object_not_found`                          | DB ID 가 틀렸거나 integration 이 DB 에 연결 안 됨                                                                                                                                    |
| Notion `Invalid select option, commas not allowed` | 프로젝트명에 콤마 — 자동으로 `·` 치환되도록 처리됨. 같은 에러가 다시 나면 코드 확인                                                                                                  |
| Notion `is not a property that exists`             | DB 의 property 이름과 설정의 property 이름이 다름. 설정 페이지에서 일치시킬 것                                                                                                       |
| Notion `unauthorized`                              | Integration Token 틀림 또는 만료. 설정 페이지에서 재저장                                                                                                                             |
| Notion Projects Code 가 task_id (숫자) 로 들어감   | 과거 버전에서 등록된 프로젝트. `project_code` 가 비어 있으면 `notion-projects-sync` 가 backfill 안 함 — DB 의 `project_code` 를 수동 보정하거나 `search_joinable_projects` 로 재조회 |
| `notion-sync` 시 같은 select 옵션 콤마 에러        | 프로젝트명에 콤마 — 자동 `·` 치환되도록 처리됨 (notion.py `select_prop`)                                                                                                             |
| 설정 페이지 저장 시 404                            | 서버 재시작 안 함. `Ctrl+C` → `./angel` (SETTING_DEFAULTS 변경 후 필수)                                                                                                              |
| UpNote/Notion 버튼이 설정 변경 후에도 안 사라짐    | 메인 페이지 새로고침 안 함 (Cmd+Shift+R)                                                                                                                                             |

---

## 13. 향후 작업 (TODO)

- Notion 의 본문 markdown → block 단위 변환 (현재는 단일 plain text 코드 블록)
- UA-work 의 `Project` Select → Relation 마이그레이션 — `UA-Projects` DB 와 연결해 양방향 backlink + Rollup 지원
- Notion 대시보드 페이지 (Calendar / By Project Board / Recent Table / Weekly Notes) 사용자 가이드 작성
- 매칭 실패한 프로젝트 (project_code 가 비어 있는 항목) 를 설정 페이지에서 시각화
- `verify=False` 제거 (사내 인증서 정상화 시점에)
