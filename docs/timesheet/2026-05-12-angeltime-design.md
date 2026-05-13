# angeltime — 일일 업무 보고 통합 도구 설계서

작성일: 2026-05-12
대상 사용자: 단일 사용자 (작성자 본인)

---

## 1. 목적

사용자는 하루 업무를 세 곳에 기입한다.

- **UpNote**: 본인 기록용 주간 누적 노트
- **팀장 일일 보고**: 사내 메신저로 텍스트 전송
- **타임시트 웹 페이지** (`https://timesheet.uangel.com/times/timesheet/jobtime/create.htm`): 프로젝트별 시간 입력

세 곳의 포맷이 다르고 프로젝트명도 다르다. 사용자는 같은 내용을 형식만 바꿔서 세 번 입력하고 있다.

본 도구는 **단일 웹 UI**(`http://127.0.0.1:5174`)에서 주간 업무 보고를 한 번 작성하면 세 채널로 분배하도록 한다.

- 작성한 내용은 SQLite DB 에 보관된다.
- 작성 후 사용자가 명시적으로 버튼을 눌러 각 채널로 전송한다 (자동 전송 아님).
- 같은 회사 시스템 `timesheet.uangel.com` 을 다루는 기존 도구 [`angelnet`](../../../../angelnet) (회의실 대시보드) 과 동일한 스택 · 인증 방식 · 디렉토리 구조를 채택하여 향후 단일 저장소로 통합 가능하도록 한다.

## 2. 비-목표 (Non-goals)

- 메신저/이메일 자동 전송. 팀장 보고는 클립보드 복사로 충분하다.
- 파일 변경 감지를 통한 자동 동기화. 외부 시스템 (특히 타임시트) 에 무인 쓰기는 위험하다.
- 다중 사용자. 단일 사용자 로컬 도구다.
- 회의실 예약 기능. `angelnet` 의 역할이다.

## 3. 사용자 워크플로우

```
사용자                          angeltime                       외부
───────────────────────────────────────────────────────────────────────
./time 실행          ─▶ FastAPI 서버 5174 기동
                       브라우저 자동 open

월~금 저녁           ─▶ 웹 UI 에서 그날 업무 입력
                       (카테고리 · 시간 · 하위 작업 내용)
                       ─▶ SQLite 저장 (실시간 autosave)

[📋 팀장 보고]       ─▶ 일일 보고 텍스트 생성
                       ◀── clipboard 복사
                          사용자가 메신저에 붙여넣기

[🔄 UpNote 저장]     ─▶ x-callback-url 생성
                       ─▶ subprocess open      ─▶ UpNote 앱이 노트 생성

[📤 타임시트 입력]   ─▶ 매핑 검증 (누락 시 경고)
                       ─▶ Spring REST 호출      ─▶ timesheet.uangel.com
                       ◀── 성공/실패 알림
```

## 4. 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│   브라우저  http://127.0.0.1:5174                            │
│   ─ 주간 보고서 작성                                          │
│   ─ 프로젝트 매핑 관리                                        │
│   ─ 동작 버튼 (보고 / 타임시트 / UpNote)                      │
│   ─ 동작 로그 패널                                            │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP / JSON
                      ▼
┌─────────────────────────────────────────────────────────────┐
│   FastAPI 백엔드 (./time 으로 기동)                          │
│                                                             │
│   ┌──────────┐  ┌──────────┐  ┌────────────────────────┐  │
│   │ Reports  │  │ Mappings │  │ Actions                │  │
│   │ API      │  │ API      │  │  - team-report (텍스트)│  │
│   └────┬─────┘  └────┬─────┘  │  - timesheet-submit    │  │
│        │             │        │  - upnote-sync         │  │
│        ▼             ▼        └─────────┬──────────────┘  │
│   ┌──────────────────────┐              │                  │
│   │  SQLite (db.sqlite)  │              │                  │
│   └──────────────────────┘              │                  │
│                                          │                  │
│   ┌──────────────────────────────────────┴──────────────┐  │
│   │ Common (angelnet 에서 복제하여 출발)                │  │
│   │  - KeychainStore (service="angeldash" — 패스워드   │  │
│   │    공유로 angelnet 과 같은 항목 사용)               │  │
│   │  - TokenCache (세션 TTL 24h)                        │  │
│   │  - login() 로직 (form login → JSESSIONID)           │  │
│   │  - ApiError / AuthError / BotBlockedError           │  │
│   └─────────────────────────────────────────────────────┘  │
│                          │                                  │
│                          ▼                                  │
│   ┌────────────────────────────────────────────────────┐   │
│   │ Timesheet Spring REST (jobtime 엔드포인트)         │   │
│   │  ※ 구현 1단계에서 DevTools 캡처로 발견             │   │
│   └────────────────────────────────────────────────────┘   │
│                                                             │
│   UpNote 호출: subprocess.run(["open", "upnote://..."])    │
└─────────────────────────────────────────────────────────────┘
```

핵심 원칙:

- Core 모듈(`db`, `client`, `formatter`, `upnote`) 은 GUI 의존성 없이 단위 테스트 가능
- `server` 는 얇은 어댑터: 요청을 받아 Core 함수 호출 후 결과 반환
- 모든 외부 동작은 미리보기(dry-run) API 를 별도 제공한다 (예: `POST /api/actions/team-report?dry_run=true`)
- 외부 시스템(타임시트) 쓰기는 UI 에서 확인 다이얼로그를 띄운다

## 5. 데이터 모델 (SQLite)

저장 경로: `~/.local/share/angeltime/db.sqlite` (XDG Base Directory 관례)

```sql
-- 하루 단위
CREATE TABLE days (
    date TEXT PRIMARY KEY,              -- 'YYYY-MM-DD'
    week_iso TEXT NOT NULL              -- 'YYYY-Www' (ISO 8601)
);

-- 보고서 항목 (한 카테고리 = 한 row)
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL REFERENCES days(date) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,       -- 같은 date 안에서의 순서
    category TEXT NOT NULL,             -- 'SKT SMSC 리빌딩'
    hours REAL NOT NULL DEFAULT 0,      -- 4.0 (0 허용; 보고만 하고 타임시트엔 안 올리는 항목)
    body_md TEXT NOT NULL DEFAULT ''    -- 들여쓰기 라인들 (markdown 원본)
);
CREATE INDEX idx_entries_date ON entries(date);

-- 타임시트 프로젝트 마스터
-- 사용자가 매핑 관리 페이지에서 수동 등록하거나, 추후 타임시트 API 가
-- 프로젝트 목록을 제공하면 자동 동기화
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,          -- '25년 SKT SMSC MAP 프로토콜 제거'
    remote_id TEXT,                     -- 타임시트 시스템상의 프로젝트 코드(있을 때)
    active INTEGER NOT NULL DEFAULT 1
);

-- 카테고리 → 프로젝트 매핑
CREATE TABLE mappings (
    category TEXT PRIMARY KEY,          -- 'SKT SMSC 리빌딩'
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    -- project_id 가 NULL 이면 의도적으로 타임시트에 올리지 않는 항목
    -- (예: '소스 Commit' 같은 일상 활동)
    excluded INTEGER NOT NULL DEFAULT 0
);

-- 주별 자유 메모 (한 주 = 한 textarea)
-- 업무 보고와 완전히 분리. 타임시트/팀장 보고에 영향 없음. UpNote 동기화에만 포함.
CREATE TABLE week_notes (
    week_iso TEXT PRIMARY KEY,          -- '2026-W19'
    body_md TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 동작 이력
CREATE TABLE action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,          -- 'timesheet' | 'upnote' | 'report'
    target_range TEXT NOT NULL,         -- 'YYYY-MM-DD' 또는 'YYYY-Www'
    status TEXT NOT NULL,               -- 'ok' | 'fail'
    message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_action_logs_created_at ON action_logs(created_at);

-- 환경 설정 (단일 row key/value)
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- 예시 키:
--   'upnote.notebook_id'        '0889cff8-407b-4181-a887-22d8d6f09a58'
--   'upnote.note_strategy'      'weekly' | 'daily'
--   'upnote.title_template'     '{yy}년 W{ww} ({week_start_mmdd} ~ {week_end_mmdd})'
--   'upnote.body_template'      '<Jinja2 템플릿 — 6.4 참조>'
--   'team_report.template'      '<Jinja2 템플릿 — 6.4 참조>'
```

데이터 수명 주기:

- `days`, `entries`, `mappings`, `settings`, `week_notes`: 영구 보관
- `action_logs`: 90일 후 자동 정리 (시작 시 cleanup)
- `projects`: `active=0` 로 표시는 가능, 삭제는 매핑 영향 때문에 신중

`week_notes` 운영 정책:

- 주 단위 보관. 이전 주의 메모는 해당 주를 열어 조회.
- 이월(carry-over) · 핀 기능 없음 (단순화).

## 6. 일일 보고 / UpNote / 팀장 보고 포맷

### 6.1 사용자가 웹 UI 에서 입력하는 모델

DB 에 저장되는 형태와 입력 폼은 동일하다.

**날짜별 업무 보고 (entries)** — 카테고리 · 시간 · 본문이 구조화됨:

```
date: 2026-05-12
entries:
  - category: "SKT SMSC 리빌딩"
    hours: 4
    body: |
      - VM1.0.5 PKG 신규 통계(KCTHLR) 기능 개발
        . 시험 및 패키지 배포
  - category: "EM 고도화"
    hours: 4
    body: |
      - 신규 OAM 서버 공통 패키지 개발
        . 코어 인프라 구현 (05/06 ~ 05/29)
          -> 공통 로깅/설정 모듈 구현
  - category: "소스 Commit"
    hours: 0
    body: |
      - 완료
```

**주별 자유 메모 (week_notes)** — 비구조화 마크다운 텍스트:

```
week_iso: 2026-W19
body_md: |
  "남성 수염 5회 패키지 문의드립니다. 인중과 턱이 포함된 '얼굴 전체' 패키지가
   60만 원(부가세 포함)인가요?"
  시술 시 어떤 모델을 사용하게 되나요?
  ...

  강남에서…
  기계 : 젠틀맥스 프로
  가격 : 1회 120,000원 / 5회 450,000원 / 10회 790,000원 (부가세별도)
```

자유 메모는 **타임시트/팀장 보고에는 포함되지 않고 UpNote 동기화에만 포함된다.**

### 6.2 팀장 보고 출력 (기본 템플릿)

본 도구는 출력 포맷을 hardcode 하지 않고 **Jinja2 템플릿**으로 렌더링한다. 출력 템플릿 시스템 전체 명세는 6.4 절 참조.

**기본 템플릿** (코드 안 default, settings 에 사용자 값 없으면 사용):

```jinja2
{%- for entry in entries -%}
*) {{ entry.category }}
{{ entry.body }}
{% if not loop.last %}
{% endif -%}
{%- endfor %}
```

**기본 렌더링 결과** (사용자 본인 포맷):

```
*) SKT SMSC 리빌딩
 - VM1.0.5 PKG 신규 통계(KCTHLR) 기능 개발
   . 시험 및 패키지 배포

*) EM 고도화
 - 신규 OAM 서버 공통 패키지 개발
   . 코어 인프라 구현 (05/06 ~ 05/29)
     -> 공통 로깅/설정 모듈 구현

*) 소스 Commit
 - 완료
```

**고정 규칙** (템플릿과 무관하게 보장됨):

- 자유 메모(`week_notes`) 는 템플릿 컨텍스트에 변수로 제공되지 않으므로 **팀장 보고에는 절대 포함되지 않는다**
- 대상 범위 (오늘만 / 이번 주 전체 / 특정 일자) 의 entries 만 컨텍스트에 들어간다
- 본문(`entry.body`) 은 사용자가 UI 에 입력한 `body_md` 원본 그대로 (마커 자동 변환 없음)

### 6.3 UpNote 출력 (기본 템플릿)

주별 누적 노트 한 개. 제목과 본문 모두 Jinja2 템플릿.

**기본 제목 템플릿** (`settings.upnote.title_template`):

```
{{ yy }}년 W{{ ww }} ({{ week_start_mmdd }} ~ {{ week_end_mmdd }})
```

→ 렌더 결과: `26년 W19 (05/11 ~ 05/15)`

**기본 본문 템플릿** (`settings.upnote.body_template`):

```jinja2
{%- for day in days -%}
{{ yy }}년 < {{ day.mm }}/{{ day.dd }}, {{ day.day_kr }} >
{%- for entry in day.entries %}
*) {{ entry.category }}
{{ entry.body }}
{% if not loop.last %}
{% endif -%}
{%- endfor %}
{% if not loop.last %}

{% endif -%}
{%- endfor %}
{%- if week_notes %}


───────────────────────────────
📝 메모

{{ week_notes }}
{%- endif %}
```

**기본 렌더링 결과**:

```
26년 < 05/12, 화 >
*) SKT SMSC 리빌딩
 - VM1.0.5 PKG 신규 통계(KCTHLR) 기능 개발
   . 시험 및 패키지 배포

*) EM 고도화
 - 신규 OAM 서버 공통 패키지 개발
   . 코어 인프라 구현 (05/06 ~ 05/29)
     -> 공통 로깅/설정 모듈 구현

*) 소스 Commit
 - 완료

26년 < 05/13, 수 >
... (그 주의 모든 날짜 반복)


───────────────────────────────
📝 메모

"남성 수염 5회 패키지 문의드립니다. 인중과 턱이 포함된 '얼굴 전체'
 패키지가 60만 원(부가세 포함)인가요?"
...

강남에서…
기계 : 젠틀맥스 프로
가격 : 1회 120,000원 / 5회 450,000원 / 10회 790,000원 (부가세별도)
```

**고정 규칙** (템플릿이 따르도록 기본값 작성):

- `days` 는 entries 가 있는 날짜만 오름차순 (entries 없는 날짜는 컨텍스트에서 제외)
- `week_notes` 는 공백 트림 후 비어있으면 `None` 으로 컨텍스트 전달 → 템플릿의 `{%- if week_notes %}` 분기로 헤더/구분선 자체가 출력되지 않음

**전송 정책** (템플릿과 별개의 동작 규약):

- 주별 노트 한 개 (`upnote.note_strategy=weekly`)
- 매번 새 노트가 만들어진다 (UpNote API 가 update 를 지원하지 않음)
- **같은 주를 다시 동기화하면 같은 제목의 새 노트가 추가된다.** 사용자가 이전 노트를 수동 삭제하는 것을 권장한다.
- 향후 개선 여지: 노트 제목으로 식별해 사용자에게 "기존 노트가 있습니다 — 덮어쓸지 새로 만들지" 안내 토스트를 띄울 수 있다 (자동 삭제는 위험하므로 안 함)

### 6.4 출력 템플릿 시스템

본 도구는 출력 포맷을 hardcode 하지 않는다. 모든 출력 (팀장 보고 텍스트, UpNote 제목, UpNote 본문) 은 Jinja2 템플릿으로 렌더링되며, 사용자가 settings 페이지에서 자유롭게 수정할 수 있다.

#### 6.4.1 사용 라이브러리

- **Jinja2** >= 3.1 (의존성 추가)
- 샌드박스 모드: `jinja2.sandbox.SandboxedEnvironment` 사용 — 사용자 입력 템플릿이므로 위험한 접근을 차단

#### 6.4.2 제공 컨텍스트 (변수)

**글로벌 컨텍스트** (모든 템플릿에서 사용 가능):

| 변수 | 예시 값 | 설명 |
|---|---|---|
| `yy` | `26` | 2자리 연도 |
| `yyyy` | `2026` | 4자리 연도 |
| `ww` | `19` | ISO 주차 |
| `week_iso` | `2026-W19` | ISO 8601 주 식별자 |
| `week_label` | `26년 W19 (05/11 ~ 05/15)` | 표시용 라벨 |
| `week_start` | `2026-05-11` | 그 주의 월요일 |
| `week_end` | `2026-05-15` | 그 주의 금요일 |
| `week_start_mmdd` | `05/11` | 그 주 월요일 MM/DD |
| `week_end_mmdd` | `05/15` | 그 주 금요일 MM/DD |
| `target_label` | `이번 주 전체` 또는 `05/12 (화)` | 대상 범위 라벨 (팀장 보고 UI 의 라디오 선택) |
| `week_notes` | `"메모 본문..."` 또는 `None` | 자유 메모 (UpNote 컨텍스트에서만 제공. 팀장 보고에는 항상 미제공) |

**`days` 리스트** (UpNote 본문 / 다일치 보고 시 제공):

```
days = [
  Day {
    date: "2026-05-12",
    yy: "26", mm: "05", dd: "12",
    day_kr: "화",       # 한글 요일 1글자
    day_en: "Tue",      # 영문 요일 약자
    weekday: 1,         # 0=월
    entries: [Entry, Entry, ...]
  },
  ...
]
```

**`entries` 리스트** (팀장 보고 — 단일 일자 또는 전체 평탄화):

각 `Entry` 는:

| 속성 | 설명 |
|---|---|
| `entry.date` | `2026-05-12` |
| `entry.category` | `SKT SMSC 리빌딩` |
| `entry.hours` | `4.0` (float) |
| `entry.body` | 사용자가 입력한 본문 원본 (markdown) |
| `entry.body_first_line` | 본문 첫 줄 (헤더와 본문을 한 줄에 합치는 포맷용) |
| `entry.body_rest` | 본문 둘째 줄부터 (rstrip 처리) |
| `entry.project_name` | 매핑된 타임시트 프로젝트명 또는 `None` |
| `entry.has_mapping` | 매핑 존재 여부 boolean |

#### 6.4.3 사용자가 settings 페이지에서 수정

settings 페이지에는 세 개의 큰 textarea:

- **팀장 보고 템플릿**
- **UpNote 제목 템플릿**
- **UpNote 본문 템플릿**

각 textarea 옆에:

- **[미리보기]** 버튼: 현재 주 데이터로 렌더링 결과를 토글로 보여줌
- **[기본값으로 복원]** 버튼: 코드 안 default 값으로 되돌림
- 저장 시 Jinja2 syntax error 가 발생하면 toast 로 표시하고 저장 중단

#### 6.4.4 본문 마커 자동 변환 (비-목표)

본문(`entry.body`) 은 사용자 입력 원본을 그대로 유지한다. 만약 본문의 들여쓰기/마커 자체 ( ` - ` ↔ ` * ` ↔ ` — ` ) 를 다른 포맷으로 자동 변환하고 싶다면 별도 변환 규칙 시스템이 필요하다 — **본 spec 범위 외**. 단일 사용자가 일관된 입력 마커를 사용한다는 가정.

## 7. 외부 시스템 연동

### 7.1 Timesheet (Spring REST)

**인증**: angelnet 의 `client.py` 의 `login()` 그대로 사용.

- `POST https://timesheet.uangel.com/home/login.json`
  - form: `userId`, `password`, `redirectUrl=/times/timesheet/jobtime/create.htm`
- 응답으로 받은 JSESSIONID 쿠키를 `httpx.AsyncClient` 가 자동 보관
- 이후 jobtime API 호출에 자동 포함

**jobtime API 엔드포인트 발견 절차** (구현 시 첫 작업):

1. Chrome DevTools 의 Network 탭을 열고 Preserve log 활성화
2. `https://timesheet.uangel.com/times/timesheet/jobtime/create.htm` 접속 후 로그인
3. 페이지에서 1회 정상 입력 후 "저장" 클릭
4. 발생한 XHR/Fetch 요청 추출:
   - Request URL · Method
   - Request Headers · Cookies
   - Request Payload (form-encoded vs JSON)
   - Response Body 구조
5. 프로젝트 드롭다운을 열 때 발생하는 GET 도 함께 캡처 (프로젝트 목록 API)
6. 결과를 `docs/superpowers/specs/2026-05-12-angeltime-design.md` 부록으로 추가
7. `client.py` 에 `submit_jobtime()`, `list_remote_projects()` 메서드 구현

**대안**: 만약 jobtime 페이지가 SPA가 아니라 form POST 만 사용한다면, HTML 폼의 action / hidden inputs 를 분석해 직접 form-encoded POST 를 보낼 수 있다. DevTools 캡처 단계에서 결정한다.

**Bot block 처리**: angelnet 과 동일하게 응답 본문의 `Automated requests are not allowed` 마커를 감지해 `BotBlockedError` 로 변환한다. 호출 빈도는 사용자 액션 단위 (1회 클릭 = 1회 호출 묶음) 이므로 봇 차단에 걸릴 가능성은 낮다.

### 7.2 UpNote

x-callback-url 의 `note/new` 엔드포인트 사용. 공식 문서: https://help.getupnote.com/resources/x-callback-url-endpoints

```python
url = (
    "upnote://x-callback-url/note/new"
    f"?title={url_quote(title)}"
    f"&text={url_quote(body)}"
    f"&notebook={url_quote(notebook_id)}"
    "&markdown=true"
)
subprocess.run(["open", url], check=True)
```

- 노트북 UUID 는 `settings.upnote.notebook_id` 에 저장. 사용자가 UpNote 사이드바에서 우클릭으로 링크를 복사해 UI 에 붙여넣는다 (사용자가 발견한 `upnote://x-callback-url/openNotebook?notebookId=...` 형태에서 UUID 추출).
- `subprocess.run` 은 `shell=False` (리스트 인자) — 사용자 입력이 URL 에 포함되므로 셸 인젝션 방지.

### 7.3 팀장 보고 (클립보드)

서버는 텍스트만 생성해 응답한다. 클립보드 복사는 브라우저의 `navigator.clipboard.writeText()` 로 처리. 보안 컨텍스트 제약이 있으므로 `127.0.0.1` 바인딩은 `localhost` 와 동등하게 secure context 로 취급된다.

## 8. UI 구성

### 8.1 라우트

| 경로 | 역할 |
|---|---|
| `/` | 주간 보고서 작성 (메인) |
| `/projects` | 프로젝트 목록 등록 + 카테고리 매핑 관리 |
| `/logs` | 동작 이력 (최근 90일) |
| `/settings` | UpNote 노트북 UUID, 팀장 보고 템플릿 등 |

### 8.2 메인 페이지 와이어프레임

```
┌────────────────────────────────────────────────────────────────┐
│ 📅 2026-W19 (5/11 ~ 5/15)   [◀ 이전 주]  [이번 주] [다음 주 ▶]│
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ▼ 05/12 (화)   합계: 8h ✓                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ *) SKT SMSC 리빌딩                              [ 4 ] h │  │
│  │     ↳ 25년 SKT SMSC MAP 프로토콜 제거                  │  │
│  │  - VM1.0.5 PKG 신규 통계(KCTHLR) 기능 개발            │  │
│  │    . 시험 및 패키지 배포                              │  │
│  │ [+ 하위 항목]                              [편집] [×] │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ *) EM 고도화                                    [ 4 ] h │  │
│  │     ↳ OAM 기능 개선                                    │  │
│  │  ...                                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│  [+ 카테고리 추가]                                             │
│                                                                │
│  ▼ 05/13 (수)   합계: 0h ⚠ (작성 필요)                         │
│  [+ 카테고리 추가]                                             │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  ▼ 📝 이번 주 메모  (UpNote 동기화에만 포함)                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ (큰 textarea, 마크다운 자유 입력, autosave)             │  │
│  │                                                         │  │
│  │ 강남에서…                                                │  │
│  │ 기계 : 젠틀맥스 프로                                    │  │
│  │ 가격 : 1회 120,000원 / 5회 450,000원 (부가세별도)       │  │
│  │ ...                                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  대상: ◉ 이번 주 전체  ○ 오늘만  ○ 선택: [05/12 ▼]            │
│                                                                │
│  [📋 팀장 보고 복사]  [📤 타임시트 입력]  [🔄 UpNote 저장]    │
│                                                                │
│  최근 동작: 타임시트 입력 완료 (05/12, 2개 항목, 8h) ✓        │
└────────────────────────────────────────────────────────────────┘
```

표시 규칙:

- 합계 시간 행: 0h = 누락(노란 아이콘), 합계 8h = 정상(녹색), 8h 초과 = 야근(파란색 ℹ️), 8h 미만이면서 0보다 크면 회색
- 카테고리 헤더 아래 `↳` 로 매핑된 타임시트 프로젝트명을 표시. 매핑 없음이면 `⚠ 매핑 필요` 클릭 시 매핑 관리 페이지의 해당 카테고리로 이동
- `[📤 타임시트 입력]` 클릭 시:
  1. 대상 범위의 entries 를 매핑과 함께 dry-run 으로 미리 보여줌
  2. 매핑 누락 / `hours=0` 인 비-제외 항목 등 경고 표시
  3. 사용자 확인 후 실제 호출

### 8.3 동작 결과 알림

- 성공: 페이지 하단 toast (3초 후 fade)
- 실패: toast + `/logs` 페이지로 점프하는 링크
- 모든 동작은 `action_logs` 에 기록

## 9. 디렉토리 구조 (angelnet 호환)

```
~/source/timesheet/
├── pyproject.toml
├── time                       # bash launcher (angelnet 의 `angel` 과 같은 패턴)
├── README.md
├── .gitignore
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-05-12-angeltime-design.md   ← 본 문서
├── src/
│   └── angeltime/
│       ├── __init__.py
│       ├── __main__.py        # uvicorn 진입점
│       ├── auth.py            # angelnet 에서 복제 (KeychainStore, TokenCache)
│       ├── client.py          # angelnet login() 복제 + jobtime 메서드
│       ├── errors.py          # angelnet 에서 복제
│       ├── db.py              # SQLite 스키마/마이그레이션
│       ├── models.py          # Pydantic 모델 (Entry, Day, Project, Mapping ...)
│       ├── formatter.py       # Jinja2 환경 구성, 컨텍스트 빌드, 렌더링
│       ├── templates.py       # 기본 템플릿 문자열 상수 (settings 미설정 시 default)
│       ├── upnote.py          # x-callback-url 빌더 + subprocess.open
│       ├── server.py          # FastAPI 앱 + 라우터
│       └── static/            # HTML/CSS/JS
│           ├── index.html
│           ├── projects.html
│           ├── logs.html
│           ├── settings.html
│           ├── css/main.css
│           └── js/
│               ├── main.js
│               ├── projects.js
│               └── ...
└── tests/
    ├── test_db.py
    ├── test_formatter.py
    ├── test_upnote.py
    ├── test_client.py         # respx 로 mock
    └── test_server.py         # httpx.AsyncClient + ASGI
```

### 9.1 launcher `time`

`angelnet/angel` 과 같은 패턴:

- `ANGELNET_USER` 환경변수 필수
- venv 활성화 → uvicorn 백그라운드 기동 → 헬스체크 → 브라우저 자동 열기
- 기본 포트 5174 (angelnet 의 5173 과 충돌 회피)
- `ANGELTIME_HOST` / `ANGELTIME_PORT` 환경변수로 변경 가능
- Ctrl+C 로 깔끔 종료

⚠️ launcher 이름 주의: `time` 은 bash 빌트인 명령어와 동명이다. 항상 `./time` 으로 명시 실행하거나, PATH 에 추가하지 말고 alias (`alias angeltime=~/source/timesheet/time`) 로 노출할 것.

### 9.2 pyproject.toml

`angelnet/pyproject.toml` 과 같은 의존성 버전:

```toml
[project]
name = "angeltime"
version = "0.1.0"
description = "일일 업무 보고 → 타임시트/UpNote/팀장보고 분배기"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "httpx>=0.27",
    "pydantic>=2.9",
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
    "ruff>=0.7",
]

[project.scripts]
angeltime = "angeltime.__main__:main"
```

## 10. 보안

- 패스워드는 macOS Keychain 에만 저장 (`service=angeldash` — angelnet 과 동일 항목 공유)
- 환경변수 `ANGELNET_PWD` 가 있으면 그것을 우선 (angelnet 동작과 동일)
- 패스워드는 로그 · 응답 · 에러 메시지에 절대 평문 노출 금지
- 서버 바인딩 기본 `127.0.0.1` (외부 노출 안 함). `ANGELTIME_HOST=0.0.0.0` 으로 사내 네트워크 허용 가능하나 권장하지 않음
- 외부 데이터(타임시트 API 응답) 는 Pydantic 으로 검증
- `httpx` 호출 시 `verify=False` — 사내 인증서 사정으로 angelnet 과 동일. TODO 주석으로 향후 인증서 검증 활성화 명시
- UpNote URL 생성 시 사용자 입력은 `urllib.parse.quote` 로 이스케이프
- `subprocess.run` 은 항상 리스트 인자, `shell=False`

## 11. 에러 처리

도메인 예외 계층 (angelnet 에서 복제):

- `AngelNetError` (base)
- `AuthError`: 로그인 실패, 패스워드 오류
- `ApiError`: 4xx/5xx, JSON 파싱 실패
- `BotBlockedError`: 자동화 차단 응답
- `MappingError`: 카테고리 매핑 누락 — 타임시트 입력 시도 시

UI 동작:

- `AuthError`: 패스워드 재입력 모달 표시 후 Keychain 갱신
- `ApiError` / `BotBlockedError`: toast + `/logs` 링크
- `MappingError`: 누락 카테고리 목록을 모달로 보여주고 매핑 관리 페이지로 이동 버튼 제공

## 12. 테스트 전략

CLAUDE.md "실제 동작을 검증하는 테스트를 우선한다" 원칙에 따라 다음 핵심만 단위 테스트:

| 테스트 | 검증 대상 |
|---|---|
| `test_formatter` | 기본 템플릿 + 샘플 데이터 → 사용자 제공 예시와 정확히 일치. 본문 첫 줄/나머지 분리, 자유 메모 조건부 출력, 잘못된 템플릿 syntax error 분기 |
| `test_db` | 스키마 마이그레이션, FK cascade, action_logs 90일 정리 |
| `test_upnote` | URL 인코딩 정확성, 멀티라인 본문 처리 |
| `test_client` | respx 로 timesheet REST mock, 로그인 / 봇 차단 / 401 분기 |
| `test_server` | API CRUD 라운드트립, dry-run vs 실제 호출 분리 |

수동 검증 체크리스트는 README 에 두고 첫 실행 시 사용자가 확인 (angelnet 패턴).

## 13. 첫 실행 검증 체크리스트

```
[ ] ANGELNET_USER 환경변수 설정 후 ./time 실행 시 패스워드 prompt 또는 Keychain 자동 로드
[ ] 브라우저가 http://127.0.0.1:5174 으로 자동 열림
[ ] 헤더에 사용자 이름 표시 (current-user API 호출 성공)
[ ] 빈 주차에 카테고리 추가 / 시간 입력 / 본문 입력이 정상 autosave
[ ] 📝 메모 textarea 에 자유 입력 후 다른 주로 이동했다 돌아와도 내용이 유지됨
[ ] /projects 에서 타임시트 프로젝트 등록 가능
[ ] /projects 에서 카테고리 → 프로젝트 매핑 가능
[ ] /settings 에서 UpNote notebook UUID 입력 후 저장됨
[ ] /settings 에서 출력 템플릿 3종(팀장보고/UpNote 제목/본문) 편집 → 미리보기 정상 → 저장 후 동작에 반영됨
[ ] 잘못된 Jinja2 syntax 입력 시 저장이 거부되고 에러 토스트 표시
[ ] [기본값으로 복원] 클릭 시 default 템플릿으로 되돌아옴
[ ] [📋 팀장 보고 복사] 클릭 시 클립보드에 정확한 포맷으로 복사됨
[ ] [🔄 UpNote 저장] 클릭 시 UpNote 앱에 새 노트가 생성되고, 본문에 그 주의 모든 날짜 업무 보고 + 메모(있을 경우) 가 포함됨
[ ] 메모가 빈 주를 UpNote 동기화하면 구분선과 📝 헤더가 출력되지 않음
[ ] 같은 주를 두 번 동기화하면 새 노트가 추가됨 (사용자가 이전 노트 수동 삭제 필요)
[ ] [📤 타임시트 입력] 클릭 시 미리보기 모달 표시 → 확인 후 실제 입력 성공
[ ] /logs 에 동작 이력 기록됨
[ ] Ctrl+C 로 서버 깔끔하게 종료됨
```

## 14. 단계적 구현 순서

다음 순서로 sub-task 를 진행한다 (writing-plans 스킬에서 세부 plan 으로 확장):

1. **프로젝트 스캐폴딩**: `pyproject.toml`, `src/angeltime/`, `time` launcher, `.gitignore`, `README.md` 초기 생성
2. **angelnet 핵심 모듈 복제**: `auth.py`, `errors.py`, `client.py` (login 까지만)
3. **DB 계층**: `db.py` 스키마 + 마이그레이션, `models.py` Pydantic
4. **포맷터 + 템플릿 시스템**: `templates.py` 기본 템플릿 정의, `formatter.py` Jinja2 SandboxedEnvironment 구성 / 컨텍스트 빌드 / 렌더링. 기본 템플릿이 사용자 예시와 일치하는지 단위 테스트
5. **UpNote 어댑터**: `upnote.py` x-callback-url 생성 + subprocess
6. **FastAPI 서버 + 정적 페이지 (보고서 작성 + 주별 메모)**: 최소 기능으로 작성/저장/팀장 보고 복사/ UpNote 저장 동작까지 (`entries`, `week_notes` 둘 다 포함)
7. **타임시트 API 발견**: DevTools 캡처로 jobtime 엔드포인트 파악, 결과를 본 design 문서 부록에 추가
8. **타임시트 입력 기능**: `client.py` 에 `submit_jobtime()` 추가, UI 의 `[📤 타임시트 입력]` 버튼 연결
9. **프로젝트/매핑 관리 페이지**
10. **동작 로그 페이지 + 90일 정리**
11. **설정 페이지** (UpNote notebook UUID, 출력 템플릿 3종 편집 + 미리보기 + 기본값 복원)
12. **수동 검증 체크리스트 1회 수행**

## 15. 향후 angelnet 통합 경로 (옵션, 본 작업 범위 외)

옵션 A 로 흡수하기로 결정될 경우의 마이그레이션 절차 (참고용):

1. `~/source/angelnet/src/common/` 디렉토리 신설
2. 본 도구의 `auth.py`, `errors.py`, 그리고 `client.py` 의 `login()` 메서드를 `common/` 으로 이동
3. `angeldash`, `angeltime` 모듈이 모두 `from common.auth import KeychainStore` 식으로 import
4. launcher 통합 방안 결정:
   - 별도 launcher 유지 (`./angel`, `./time`)
   - 또는 단일 진입점 (`./angel meeting`, `./angel time`)
5. `~/source/timesheet/` 디렉토리 archived

이를 가능케 하기 위해 본 도구는:

- angelnet 의 코드 스타일 · 명명 패턴 · 모듈 분할 · 의존성 버전을 100% 일치시킨다
- `auth.py` 의 `KEYCHAIN_SERVICE = "angeldash"` 상수를 그대로 사용한다 (이름 변경하지 않음)
- `errors.py` 의 예외 계층 최상위는 `AngelNetError` 로 유지 (모듈 이동 시 import 만 바꾸면 되도록)

## 16. 결정 이력 요약

| 결정 | 채택 안 | 사유 |
|---|---|---|
| Source of truth | SQLite DB | 구조화 데이터 / 매핑 검증 / 시간 합산 UI 가 자연스럽다 |
| UI | 로컬 웹 (FastAPI + Vanilla JS) | angelnet 과 동일 패턴, 화면 표현력 |
| 실행 방식 | `./time` 명시 실행 | 외부 시스템 쓰기 안전 |
| UpNote 통합 방향 | 로컬 → UpNote (쓰기) | UpNote 공식 API 없음, x-callback-url 의 `note/new` 활용 |
| 타임시트 호출 | httpx + Spring REST | angelnet 동일 시스템, Playwright 불필요 |
| 인증 | Keychain 공유 (service=angeldash) | 사용자가 한 번 입력으로 두 도구 모두 사용 |
| 통합 전략 | 별도 저장소 + 코드 복제 (옵션 B) | 빠른 시작 + 향후 통합 경로 열어둠 |
| 팀장 보고 채널 | 클립보드 출력만 | 자동 전송은 부담스럽고 채널이 다양 |
| 시간 입력 | UI 의 시간 칸 (DB 저장) | markdown 마커는 import 시에만 (현 단계에서는 사용 안 함) |
| 주별 자유 메모 | `week_notes` 테이블, UpNote 전용 | 사용자가 기존 UpNote 에 함께 쓰던 패턴 재현. 타임시트/팀장보고에는 절대 포함 안 함 |
| 메모 이월 정책 | 주단위 보관만 | 단순함 우선, 이월/핀 기능 추가 안 함 |
| 출력 포맷 | Jinja2 템플릿 (settings 에 자유 편집 가능) | 팀원마다 보고 포맷이 다양. 기본값은 사용자 본인 포맷, 변경 자유 |
| 본문 마커 변환 | 미지원 (raw 그대로) | placeholder 시스템 범위를 넘는 변환은 본 spec 범위 외 |

---

## 부록 A: Timesheet jobtime API 캡처 (2026-05-12)

읽기 전용 정찰 (login + HTML GET + search.json/codeSearch.json GET) 으로 파악한 결과. POST 저장 시도는 하지 않았다.

### A.1 시스템 개요

- Spring MVC + JSP 페이지 + jQuery + **dhtmlxGrid** UI
- 인증은 `home/login.json` form POST → JSESSIONID 쿠키 (angelnet 과 동일)
- jobtime 페이지는 그 달의 task 들을 grid 로 표시, 사용자가 셀에 시간 숫자를 채워넣는 매트릭스 모델

### A.2 데이터 모델 — task 행 × 날짜 열 매트릭스

핵심: 시스템은 **프로젝트별 시간 입력**이 아니라 **task 별 (날짜, 시간) 매트릭스**다. task 가 미리 등록되어 있어야 하고, 사용자는 각 task 의 일자별 시간 셀에 숫자를 채운다.

본 도구는 따라서 다음과 같이 동작해야 한다:

1. 사용자가 매월 회사 jobtime 페이지에서 그 달에 사용할 task 들을 미리 등록 (본 도구 밖)
2. 본 도구의 `projects.remote_id` 에는 **task 의 정확한 이름** (search.json 응답의 첫 컬럼) 을 저장
3. 타임시트 입력 시 search.json 으로 그 달의 task 목록을 가져와 이름 일치하는 task 의 `id` (= task_id) 를 찾아 save.json 호출
4. task 이름이 search 결과에 없으면 매핑 누락으로 처리 — 사용자가 회사 페이지에서 task 를 먼저 등록해야 함

### A.3 API 엔드포인트

| URL | Method | Content-Type | 용도 |
|---|---|---|---|
| `https://timesheet.uangel.com/home/login.json` | POST | form | 로그인 (angelnet 과 동일) |
| `https://timesheet.uangel.com/times/timesheet/jobtime/create.htm` | GET | - | 페이지 HTML (세션 컨텍스트 진입) |
| `https://timesheet.uangel.com/times/timesheet/jobtime/search.json` | POST | form | 그 달 task 목록 + 이미 입력된 시간 조회 |
| `https://timesheet.uangel.com/times/timesheet/jobtime/save.json` | POST | form | 시간 저장 (멀티 row 일괄) |
| `.../jobtime/codeSearch.json` | POST | form | 휴가 코드 시간 검색 (**본 도구 미사용**) |
| `.../jobtime/holidayTagSearch.json` | POST | form | 공휴일 정보 (**본 도구 미사용**) |
| `.../jobtime/vacationSearch.json` | POST | form | 휴가 정보 (**본 도구 미사용**) |
| `.../jobtime/excelbyday.json` | POST | form | Excel export (**본 도구 미사용**) |

### A.4 search.json

**Request:**

```
POST /times/timesheet/jobtime/search.json
Content-Type: application/x-www-form-urlencoded

dept_code=&year_month=2026-05
```

- `dept_code`: HTML 의 `$("#userDept").val()` 인데 페이지에 input 이 없어 실제로는 빈 문자열. 서버가 세션의 user 로 자동 결정.
- `year_month`: `YYYY-MM` 형식 (페이지 input 의 datepicker 형식과 동일)

**Response:** dhtmlxGrid JSON 형식.

```json
{
  "rows": [
    {
      "id": "11113",
      "data": [
        "KT 2026년 LTER 대전1호선 구축사업",
        "개발",
        "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
        "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
        "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
        "0", "0", "0", "0"
      ]
    },
    { "id": "-1000", "data": ["", "소계", ...] }
  ]
}
```

- `rows[*].id`: 정수 문자열. **save.json 의 `task_id` 로 사용**.
- `rows[*].data[0]`: task 정식 이름 — 본 도구의 매핑 키로 활용
- `rows[*].data[1]`: 작업 종류 (예: "개발")
- `rows[*].data[2..]`: 그 달의 1일부터 N일까지 일별 시간 (`"0"` ~ )
- `id` 가 `"-1000"` 같은 음수면 합계/소계 행 — **무시한다**

### A.5 save.json

**Request:**

```
POST /times/timesheet/jobtime/save.json
Content-Type: application/x-www-form-urlencoded;charset=utf-8

rows=[{"task_id":"11113","work_hour":4,"work_day":"20260512","user_id":"dgson"},...]
```

- 페이로드 form field 는 단 하나: `rows`. 값은 `JSON.stringify(array)` 결과.
- Array 의 각 element 구조:
  - `task_id`: search 결과의 `id` 그대로 (문자열 또는 정수)
  - `work_hour`: 숫자 (정수 또는 실수)
  - `work_day`: **`YYYYMMDD` 형식 (대시 없음!)** 예: `"20260512"`
  - `user_id`: 로그인한 사용자 ID
- 여러 row 를 한 번에 묶어서 보낸다 — 한 주치를 한 번의 호출로 처리 가능.

**Response:** `text/plain` 추정 (브라우저 코드가 `response.startsWith("error:")` 로 분기).

- 성공: 임의의 텍스트 (browser 는 "정상적으로 등록하였습니다." 라는 alert 만 표시)
- 실패: `"error:<message>"` 로 시작하는 텍스트
- 24시간 초과 등은 client-side 검사로 차단되므로 서버 응답으로는 거의 안 옴

### A.6 코드 발췌 — 클라이언트 동작 참고

`/times/timesheet/jobtime/create.htm` 의 인라인 script:

```javascript
// AjaxJsonSave 의 핵심 (행 단위 array 를 form-encoded 의 rows 키로)
$.ajax({
  contentType: 'application/x-www-form-urlencoded;charset=utf-8',
  url: '/times/timesheet/jobtime/save.json',
  type: 'post',
  data: { rows: JSON.stringify(data) },
  success: function(response) {
    if (response.startsWith("error:")) {
      alert(response.substring(6) || "저장에 실패했습니다.");
    } else {
      alert('정상적으로 등록하였습니다.');
    }
  }
});

// 한 row 의 생성 — 셀 변경 이벤트에서
jsonStr = {
  "task_id": rid,             // grid row id (= search 응답의 id)
  "work_hour": nValue,        // 셀 값
  "work_day": DateFormat(curday),  // YYYYMMDD
  "user_id": "dgson"
};

// DateFormat 정의
function DateFormat(obj) {
  var yy = obj.getFullYear();
  var mm = (obj.getMonth() + 1).toString().padStart(2, '0');
  var dd = obj.getDate().toString().padStart(2, '0');
  return yy + mm + dd;        // 'YYYYMMDD'
}
```

### A.7 본 도구 적용 흐름

타임시트 입력 액션 (`/api/actions/timesheet-submit`) 실행 시:

```
1. 대상 범위(일/주)의 entries 수집
2. 각 entry 의 카테고리 → 매핑 → projects.remote_id (= task 정식 이름)
   - 매핑 누락 / excluded / project_id NULL 인 항목 분류
3. 그 달의 search.json 호출 → {task_name → task_id} 맵 빌드
   (월 단위 호출: 같은 달 안에선 한 번만)
4. entries 의 (project_remote_id == task_name) 으로 task_id 찾기
   - task 미존재 항목은 "task_not_registered" 로 분류, 사용자에게 회사 페이지에서 추가 필요 알림
5. save.json 호출용 row array 빌드:
   [{task_id, work_hour=entry.hours, work_day=YYYYMMDD, user_id}, ...]
6. 한 번의 save.json POST 로 일괄 전송
7. response 가 'error:' 로 시작하면 ApiError raise, action_log 에 fail 기록
```

### A.8 정찰 산출물 위치

본 정찰의 원본 데이터는 다음에 저장됨 (gitignore 됨):

- `/tmp/angeltime-recon/jobtime-page.html`
- `/tmp/angeltime-recon/inline-scripts.js`
- `/tmp/angeltime-recon/search-2026-05.json`
- `/tmp/angeltime-recon/codesearch-vacation.txt`

이 파일들은 일회성 분석용. 구현 시 본 부록 내용으로 충분.

---

## 부록 B: UpNote x-callback-url 실제 동작 (2026-05-12 검증)

`note/new` 의 `notebook` 파라미터와 `markdown` 파라미터는 공식 문서가 모호하다. 실제 동작 확인 결과:

### B.1 `notebook` 파라미터는 노트북 **이름**

- UUID 가 아니라 **노트북 표시 이름** 으로 매칭한다.
- 매칭 실패 시 **그 문자열을 이름으로 새 노트북을 만들어** 노트를 추가한다 (의도적 동작인 듯).
- 폴더(노트북 그룹) 안의 노트북은 슬래시 경로로 지정 가능:
  ```
  notebook=##### 업무 #####/### 일일 업무 보고 ###
  ```
- 단순 이름 (`### 일일 업무 보고 ###`) 만 입력하면 폴더 안의 노트북은 매칭 안 됨 → root 에 새 노트북이 생성됨.

본 도구의 `settings.upnote.notebook_id` 값은 사용자가 위 경로 형식으로 입력해야 한다.

### B.2 `markdown=false` 가 자체적으로 plain text 를 보존하지 않음

- `markdown=false` 를 보내도 UpNote 의 입력 처리기가 자체적으로 `*` → bullet 변환, `1.` → ordered list 변환, 들여쓰기 평탄화를 적용한다.
- plain text 형식 (들여쓰기 + `*)` 마커 등) 을 정확히 보존하려면 본문을 코드 블록(``` `\`\`\`` ... `\`\`\`` ```) 으로 감싸는 것이 유일한 안정적인 방법.

본 도구의 `settings.upnote.wrap_in_code_block=true` 옵션을 사용하면 자동 wrap 한다. 단점: 본문이 monospace 폰트로 표시됨. 사용자가 본인 환경에서 트레이드오프를 선택.

### B.3 동기화 중복 처리는 여전히 사용자 책임

- 같은 주를 두 번 동기화하면 같은 제목의 새 노트가 추가된다 (UpNote 의 `note/new` 가 update 를 지원하지 않음).
- 사용자가 이전 노트를 수동 삭제하거나, 중복 노트가 쌓여도 무방하다고 판단해야 함.
