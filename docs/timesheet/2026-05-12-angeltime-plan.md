# angeltime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단일 웹 UI 에서 일일 업무 보고를 작성하면 팀장 보고(클립보드) / UpNote / 사내 타임시트로 자동 분배하는 로컬 단일 사용자 도구를 만든다.

**Architecture:** Python FastAPI 백엔드 + SQLite 데이터 + Vanilla JS 프론트엔드. `./time` 으로 기동되어 `http://127.0.0.1:5174` 에 떠 있는 동안 사용. 외부 시스템 호출은 `httpx` (timesheet.uangel.com Spring REST) 와 `subprocess open` (UpNote x-callback-url). 자매 도구 `~/source/angelnet` 의 인증/HTTP 클라이언트 패턴을 복제해 같은 Keychain 항목을 공유한다.

**Tech Stack:** Python 3.11+ / FastAPI / uvicorn / httpx / Pydantic / Jinja2 (sandboxed) / SQLite (stdlib `sqlite3`) / ruff / pytest / pytest-asyncio / respx / Vanilla JS · HTML · CSS

**Spec:** [docs/superpowers/specs/2026-05-12-angeltime-design.md](../specs/2026-05-12-angeltime-design.md)

---

## File Structure

생성될 파일들과 책임:

```
~/source/timesheet/
├── pyproject.toml                    # 프로젝트 메타데이터 + 의존성
├── time                              # bash launcher (./time)
├── README.md                         # 사용법
├── .gitignore                        # venv, __pycache__, db.sqlite, .angeltime.log 등
├── src/angeltime/
│   ├── __init__.py                   # 빈 패키지 마커
│   ├── __main__.py                   # CLI 진입점 (argparse → uvicorn)
│   ├── errors.py                     # 도메인 예외 계층 (AngelNetError, AuthError, ApiError, BotBlockedError)
│   ├── auth.py                       # macOS Keychain wrapper (KeychainStore)
│   ├── db.py                         # SQLite 연결 + 스키마 + 마이그레이션 + repository 함수
│   ├── models.py                     # Pydantic 모델 (Entry, Day, Project, Mapping, WeekNote, ActionLog, Settings)
│   ├── templates.py                  # 기본 출력 템플릿 문자열 상수
│   ├── formatter.py                  # Jinja2 SandboxedEnvironment + 컨텍스트 빌더 + 렌더 함수
│   ├── upnote.py                     # x-callback-url 빌더 + subprocess.open
│   ├── client.py                     # timesheet.uangel.com Spring REST 호출 (login + jobtime + projects)
│   ├── server.py                     # FastAPI 앱 (라우터, lifespan, dependency injection)
│   └── static/
│       ├── index.html                # 메인: 주간 보고서 작성
│       ├── projects.html             # 프로젝트 + 매핑 관리
│       ├── logs.html                 # 동작 이력
│       ├── settings.html             # UpNote 설정 + 템플릿 편집
│       ├── css/main.css              # 전체 스타일
│       └── js/
│           ├── api.js                # fetch 래퍼 공통
│           ├── main.js               # index.html 컨트롤러
│           ├── projects.js
│           ├── logs.js
│           └── settings.js
└── tests/
    ├── conftest.py                   # 픽스처 (인메모리 DB, mock client, FastAPI TestClient)
    ├── test_db.py
    ├── test_models.py
    ├── test_formatter.py
    ├── test_upnote.py
    ├── test_client.py
    └── test_server.py
```

각 파일은 단일 책임을 가지며, 다른 파일에서 import 만으로 사용 가능한 명확한 인터페이스를 제공한다.

---

## Phase 1: Foundation (Tasks 1-4)

### Task 1: Project scaffolding + git init

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `src/angeltime/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 작업 디렉토리로 이동하고 디렉토리 구조 생성**

```bash
cd ~/source/timesheet
mkdir -p src/angeltime/static/css src/angeltime/static/js tests
```

- [ ] **Step 2: pyproject.toml 작성**

```toml
# pyproject.toml
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

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: .gitignore 작성**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.pytest_cache/
.ruff_cache/

# 빌드 결과물
dist/
build/

# 운영 데이터 (사용자 환경 전용)
*.sqlite
*.sqlite-journal
.angeltime.log

# macOS
.DS_Store

# IDE
.vscode/
.idea/
```

- [ ] **Step 4: README.md 최소 골격 작성**

```markdown
# angeltime

일일 업무 보고를 한 번 작성하면 팀장 보고(클립보드) / UpNote / 사내 타임시트로 분배하는 단일 사용자 로컬 도구.

> **참고:** 사내 시스템 (`timesheet.uangel.com`) 의 Spring REST API 와 macOS Keychain 을 사용. 외부 환경에서는 동작하지 않는다.

## 설치

```bash
cd ~/source/timesheet
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 실행

```bash
export ANGELNET_USER=youruserid   # 한 번만, ~/.zshrc 등에 영구 저장 권장
./time
```

브라우저가 자동으로 `http://127.0.0.1:5174` 를 연다. Ctrl+C 로 종료.

## 개발

```bash
.venv/bin/pytest -v
.venv/bin/ruff check src tests
.venv/bin/ruff format src tests
```

자세한 설계는 [docs/superpowers/specs/2026-05-12-angeltime-design.md](docs/superpowers/specs/2026-05-12-angeltime-design.md) 참조.
```

- [ ] **Step 5: 빈 패키지 마커 생성**

`src/angeltime/__init__.py`:

```python
"""angeltime — 일일 업무 보고 통합 도구."""
```

`tests/__init__.py`: 빈 파일.

`tests/conftest.py`: 빈 파일 (이후 픽스처 추가).

- [ ] **Step 6: venv 생성 및 의존성 설치**

```bash
cd ~/source/timesheet
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

기대 출력: `Successfully installed angeltime-0.1.0 ...`

- [ ] **Step 7: 빈 테스트 실행 확인**

```bash
.venv/bin/pytest -v
```

기대: `no tests ran` 또는 `0 tests collected` (오류 없이 종료)

- [ ] **Step 8: git init + 첫 commit**

```bash
cd ~/source/timesheet
git init
git add .
git status
```

`git status` 출력에 `docs/superpowers/...` 과 새로 만든 파일들이 보여야 한다. `.venv/`, `__pycache__/`, `*.egg-info/` 는 보이지 않아야 한다.

```bash
git commit -m "chore: project scaffolding"
```

---

### Task 2: errors.py 모듈

**Files:**
- Create: `src/angeltime/errors.py`
- Create: `tests/test_errors.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_errors.py`:

```python
"""도메인 예외 계층 테스트."""

import pytest

from angeltime.errors import (
    AngelNetError,
    ApiError,
    AuthError,
    BotBlockedError,
    MappingError,
)


def test_all_errors_inherit_from_base():
    """모든 도메인 예외는 AngelNetError 하위여야 한다."""
    for cls in (AuthError, BotBlockedError, ApiError, MappingError):
        assert issubclass(cls, AngelNetError)


def test_api_error_carries_status_and_payload():
    """ApiError 는 status_code 와 payload 를 보관한다."""
    err = ApiError("bad", status_code=500, payload={"k": "v"})
    assert str(err) == "bad"
    assert err.status_code == 500
    assert err.payload == {"k": "v"}


def test_mapping_error_carries_missing_categories():
    """MappingError 는 누락된 카테고리 목록을 보관한다."""
    err = MappingError(missing=["SKT SMSC 리빌딩", "EM 고도화"])
    assert err.missing == ["SKT SMSC 리빌딩", "EM 고도화"]
    assert "SKT SMSC 리빌딩" in str(err)
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_errors.py -v
```

기대: `ModuleNotFoundError: No module named 'angeltime.errors'`

- [ ] **Step 3: errors.py 작성**

`src/angeltime/errors.py`:

```python
"""angeltime 도메인 예외 계층.

angelnet 의 errors.py 와 호환되도록 최상위 이름은 AngelNetError 로 유지.
향후 두 도구를 한 저장소로 합칠 때 같은 예외 타입을 공유한다.
"""

from __future__ import annotations

from typing import Any


class AngelNetError(Exception):
    """모든 도메인 예외의 기반."""


class AuthError(AngelNetError):
    """로그인/세션 실패 또는 401."""


class BotBlockedError(AngelNetError):
    """서버가 자동화 호출이라고 차단."""


class ApiError(AngelNetError):
    """그 외 4xx/5xx 응답 또는 비-JSON 응답."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class MappingError(AngelNetError):
    """카테고리 → 타임시트 프로젝트 매핑 누락."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        super().__init__(f"unmapped categories: {', '.join(self.missing)}")
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_errors.py -v
```

기대: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/errors.py tests/test_errors.py
git commit -m "feat: add domain exception hierarchy"
```

---

### Task 3: auth.py 모듈 (angelnet 복제)

**Files:**
- Create: `src/angeltime/auth.py`
- Create: `tests/test_auth.py`

`KEYCHAIN_SERVICE` 는 의도적으로 `"angeldash"` 를 사용한다. angelnet 과 같은 Keychain 항목을 공유하여 사용자가 한 번 입력한 패스워드를 둘 다 활용한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_auth.py`:

```python
"""KeychainStore 테스트.

subprocess 를 mock 해 macOS Keychain 의존성 없이 검증.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from angeltime.auth import KEYCHAIN_SERVICE, KeychainStore


def test_keychain_service_is_angeldash():
    """angelnet 과 같은 Keychain 항목을 공유해야 하므로 service 이름을 고정한다."""
    assert KEYCHAIN_SERVICE == "angeldash"


def test_get_returns_stripped_password_on_success():
    """find-generic-password 성공 시 stdout 의 공백을 제거하여 반환."""
    store = KeychainStore(account="alice")
    with patch.object(subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="secret\n", stderr=""
        )
        result = store.get()
    assert result == "secret"


def test_get_returns_none_when_not_found():
    """find-generic-password 가 항목 없음으로 0이 아닌 rc 반환 시 None."""
    store = KeychainStore(account="alice")
    with patch.object(subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=44, stdout="", stderr="not found"
        )
        result = store.get()
    assert result is None


def test_save_calls_add_generic_password_with_update_flag():
    """save 는 -U 플래그로 기존 항목을 덮어쓴다."""
    store = KeychainStore(account="alice")
    with patch.object(subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        store.save("newpass")
    args = run.call_args[0][0]
    assert "add-generic-password" in args
    assert "-U" in args
    assert "newpass" in args
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_auth.py -v
```

기대: `ModuleNotFoundError: No module named 'angeltime.auth'`

- [ ] **Step 3: auth.py 작성 (angelnet 에서 복제)**

`src/angeltime/auth.py`:

```python
"""macOS Keychain wrapper.

angelnet 의 src/angeldash/auth.py 와 동일 동작. service="angeldash" 를 공유해
한 번 입력한 패스워드를 두 도구가 함께 사용한다.

`security` CLI 를 subprocess.run(list) 로 호출 (shell=False). save() 시
패스워드가 프로세스 인자로 전달되어 짧은 시간 ps aux 에 노출될 수 있다 — 단일
사용자 로컬 환경에서 허용되는 위험으로 판단한다.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

KEYCHAIN_SERVICE = "angeldash"


class KeychainStore:
    """generic-password 항목을 다루는 얇은 래퍼."""

    def __init__(self, account: str, service: str = KEYCHAIN_SERVICE) -> None:
        self.account = account
        self.service = service

    def get(self) -> str | None:
        """저장된 패스워드를 반환한다. 없으면 None."""
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                self.service,
                "-a",
                self.account,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.debug(
                "Keychain miss for account=%s rc=%d", self.account, result.returncode
            )
            return None
        return result.stdout.strip() or None

    def save(self, password: str) -> None:
        """패스워드를 저장(또는 덮어쓰기)한다. 실패 시 RuntimeError."""
        result = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-s",
                self.service,
                "-a",
                self.account,
                "-w",
                password,
                "-U",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"security add-generic-password failed: rc={result.returncode} "
                f"stderr={result.stderr.strip()}"
            )
        logger.info("Password stored to keychain for account=%s", self.account)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_auth.py -v
```

기대: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/auth.py tests/test_auth.py
git commit -m "feat: add KeychainStore (shared service with angelnet)"
```

---

### Task 4: models.py — Pydantic 모델

**Files:**
- Create: `src/angeltime/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_models.py`:

```python
"""Pydantic 모델 검증."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from angeltime.models import (
    Entry,
    EntryInput,
    Project,
    Mapping,
    User,
    WeekNoteInput,
)


def test_entry_input_accepts_positive_hours():
    """시간은 0 이상 24 미만의 실수를 허용한다."""
    e = EntryInput(category="X", hours=4.5, body_md="- 어쩌고")
    assert e.hours == 4.5


def test_entry_input_rejects_negative_hours():
    with pytest.raises(ValidationError):
        EntryInput(category="X", hours=-1, body_md="")


def test_entry_input_rejects_too_many_hours():
    with pytest.raises(ValidationError):
        EntryInput(category="X", hours=25, body_md="")


def test_entry_input_strips_category_whitespace():
    """카테고리 앞뒤 공백은 제거된다."""
    e = EntryInput(category="  SKT SMSC 리빌딩 ", hours=4, body_md="")
    assert e.category == "SKT SMSC 리빌딩"


def test_entry_input_rejects_empty_category():
    with pytest.raises(ValidationError):
        EntryInput(category="   ", hours=4, body_md="")


def test_entry_body_first_line_and_rest():
    """본문이 여러 줄일 때 first_line / rest 가 분리된다."""
    e = Entry(
        id=1, date="2026-05-12", order_index=0,
        category="X", hours=1.0,
        body_md="first line\nsecond\nthird",
    )
    assert e.body_first_line == "first line"
    assert e.body_rest == "second\nthird"


def test_entry_body_first_line_when_single_line():
    e = Entry(
        id=1, date="2026-05-12", order_index=0,
        category="X", hours=1.0, body_md="only one",
    )
    assert e.body_first_line == "only one"
    assert e.body_rest == ""


def test_entry_body_first_line_when_empty():
    e = Entry(
        id=1, date="2026-05-12", order_index=0,
        category="X", hours=1.0, body_md="",
    )
    assert e.body_first_line == ""
    assert e.body_rest == ""


def test_project_name_required():
    with pytest.raises(ValidationError):
        Project(id=1, name="", active=True)


def test_week_note_input_allows_empty_body():
    """비어있는 메모도 허용된다 (저장 후 삭제 동작)."""
    n = WeekNoteInput(body_md="")
    assert n.body_md == ""


def test_user_basic():
    u = User(user_id="alice", name="앨리스")
    assert u.user_id == "alice"
    assert u.name == "앨리스"
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_models.py -v
```

기대: `ModuleNotFoundError`

- [ ] **Step 3: models.py 작성**

`src/angeltime/models.py`:

```python
"""Pydantic 모델 — API request/response 및 내부 데이터.

EntryInput / WeekNoteInput 등 *Input* 접미사 모델은 사용자가 보내는 페이로드용 (validation 강함).
Entry / WeekNote 등은 DB 에서 읽어온 도메인 객체 (id 등 자동 필드 포함).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# ─── 도메인 모델 ───────────────────────────────────────


class User(BaseModel):
    """현재 로그인 사용자."""

    user_id: str
    name: str


class EntryInput(BaseModel):
    """클라이언트가 보내는 보고서 항목 페이로드."""

    category: str = Field(min_length=1)
    hours: float = Field(ge=0, lt=24)
    body_md: str = ""

    @field_validator("category")
    @classmethod
    def strip_category(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("category must be non-empty after strip")
        return s


class Entry(BaseModel):
    """DB 의 entries 한 row + 파생 필드."""

    id: int
    date: str
    order_index: int
    category: str
    hours: float
    body_md: str

    @property
    def body_first_line(self) -> str:
        """본문 첫 줄. 본문이 비면 빈 문자열."""
        if not self.body_md:
            return ""
        return self.body_md.split("\n", 1)[0]

    @property
    def body_rest(self) -> str:
        """본문 둘째 줄부터 (rstrip)."""
        if not self.body_md or "\n" not in self.body_md:
            return ""
        return self.body_md.split("\n", 1)[1].rstrip()


class WeekNoteInput(BaseModel):
    """주별 자유 메모 페이로드."""

    body_md: str = ""


class WeekNote(BaseModel):
    week_iso: str
    body_md: str
    updated_at: str


class Project(BaseModel):
    id: int
    name: str = Field(min_length=1)
    remote_id: str | None = None
    active: bool = True


class ProjectInput(BaseModel):
    name: str = Field(min_length=1)
    remote_id: str | None = None
    active: bool = True


class Mapping(BaseModel):
    """카테고리 → 프로젝트 매핑.

    project_id 가 None 이고 excluded=True 면 의도적으로 타임시트 미입력.
    project_id 가 None 이고 excluded=False 면 매핑이 누락된 상태.
    """

    category: str
    project_id: int | None = None
    excluded: bool = False


class ActionLog(BaseModel):
    id: int
    action_type: str
    target_range: str
    status: str
    message: str | None = None
    created_at: str
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_models.py -v
```

기대: 모든 테스트 통과

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/models.py tests/test_models.py
git commit -m "feat: add Pydantic models"
```

---

## Phase 2: Data Layer (Tasks 5-6)

### Task 5: db.py — SQLite 연결 + 스키마

**Files:**
- Create: `src/angeltime/db.py`
- Create: `tests/test_db.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: conftest.py 에 인메모리 DB 픽스처 추가**

`tests/conftest.py`:

```python
"""공통 pytest 픽스처."""

from __future__ import annotations

import sqlite3

import pytest

from angeltime import db as db_module


@pytest.fixture
def conn() -> sqlite3.Connection:
    """인메모리 SQLite 연결 + 스키마 초기화."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db_module.init_schema(c)
    yield c
    c.close()
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_db.py`:

```python
"""DB 스키마와 repository 함수 테스트."""

from __future__ import annotations

import sqlite3

import pytest

from angeltime import db


def test_init_schema_creates_all_tables(conn: sqlite3.Connection) -> None:
    """init_schema 는 모든 테이블을 생성한다."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {row["name"] for row in cur.fetchall()}
    expected = {
        "days",
        "entries",
        "projects",
        "mappings",
        "week_notes",
        "action_logs",
        "settings",
    }
    assert expected.issubset(names)


def test_init_schema_is_idempotent(conn: sqlite3.Connection) -> None:
    """init_schema 를 다시 호출해도 에러나 데이터 손실이 없어야 한다."""
    conn.execute("INSERT INTO days(date, week_iso) VALUES('2026-05-12','2026-W19')")
    conn.commit()
    db.init_schema(conn)
    n = conn.execute("SELECT COUNT(*) AS c FROM days").fetchone()["c"]
    assert n == 1


def test_upsert_entries_replaces_day(conn: sqlite3.Connection) -> None:
    """upsert_entries 는 그 날의 entries 를 완전 교체한다."""
    db.upsert_entries(
        conn,
        date="2026-05-12",
        week_iso="2026-W19",
        entries=[
            {"category": "A", "hours": 4.0, "body_md": "x"},
            {"category": "B", "hours": 4.0, "body_md": "y"},
        ],
    )
    rows = conn.execute(
        "SELECT category, order_index FROM entries WHERE date='2026-05-12' ORDER BY order_index"
    ).fetchall()
    assert [r["category"] for r in rows] == ["A", "B"]

    db.upsert_entries(
        conn, date="2026-05-12", week_iso="2026-W19",
        entries=[{"category": "C", "hours": 1.0, "body_md": ""}],
    )
    rows = conn.execute(
        "SELECT category FROM entries WHERE date='2026-05-12'"
    ).fetchall()
    assert [r["category"] for r in rows] == ["C"]


def test_get_week_aggregates_days(conn: sqlite3.Connection) -> None:
    """get_week 는 그 주의 모든 날짜를 반환한다."""
    db.upsert_entries(
        conn, date="2026-05-12", week_iso="2026-W19",
        entries=[{"category": "A", "hours": 4.0, "body_md": ""}],
    )
    db.upsert_entries(
        conn, date="2026-05-13", week_iso="2026-W19",
        entries=[{"category": "B", "hours": 4.0, "body_md": ""}],
    )
    week = db.get_week(conn, "2026-W19")
    assert {d["date"] for d in week} == {"2026-05-12", "2026-05-13"}


def test_week_notes_upsert_and_get(conn: sqlite3.Connection) -> None:
    """주별 자유 메모는 upsert 가능하고 빈 주는 빈 문자열을 반환한다."""
    assert db.get_week_note(conn, "2026-W19") == ""
    db.upsert_week_note(conn, "2026-W19", "메모 본문")
    assert db.get_week_note(conn, "2026-W19") == "메모 본문"
    db.upsert_week_note(conn, "2026-W19", "수정됨")
    assert db.get_week_note(conn, "2026-W19") == "수정됨"


def test_mapping_lookup_with_project(conn: sqlite3.Connection) -> None:
    """매핑 조회는 project 정보를 함께 반환한다."""
    pid = db.create_project(conn, name="25년 SKT SMSC MAP 프로토콜 제거")
    db.set_mapping(conn, "SKT SMSC 리빌딩", project_id=pid, excluded=False)
    m = db.get_mapping(conn, "SKT SMSC 리빌딩")
    assert m["project_id"] == pid
    assert m["project_name"] == "25년 SKT SMSC MAP 프로토콜 제거"


def test_action_log_insert_and_recent(conn: sqlite3.Connection) -> None:
    """action_log 는 시간 역순으로 조회된다."""
    db.log_action(conn, "report", "2026-05-12", "ok", None)
    db.log_action(conn, "timesheet", "2026-05-12", "fail", "401")
    logs = db.recent_actions(conn, limit=10)
    assert len(logs) == 2
    assert logs[0]["action_type"] == "timesheet"  # 최신이 먼저


def test_action_log_cleanup_drops_older_than_days(conn: sqlite3.Connection) -> None:
    """action_log_cleanup 은 N일 이전 항목을 삭제한다."""
    conn.execute(
        "INSERT INTO action_logs (action_type, target_range, status, created_at) "
        "VALUES (?, ?, ?, datetime('now', '-100 days'))",
        ("report", "old", "ok"),
    )
    conn.execute(
        "INSERT INTO action_logs (action_type, target_range, status, created_at) "
        "VALUES (?, ?, ?, datetime('now', '-10 days'))",
        ("report", "recent", "ok"),
    )
    conn.commit()
    deleted = db.cleanup_action_logs(conn, days=90)
    assert deleted == 1
    remaining = conn.execute(
        "SELECT target_range FROM action_logs"
    ).fetchall()
    assert [r["target_range"] for r in remaining] == ["recent"]


def test_settings_get_set(conn: sqlite3.Connection) -> None:
    """settings 는 key/value upsert."""
    assert db.get_setting(conn, "k") is None
    db.set_setting(conn, "k", "v1")
    assert db.get_setting(conn, "k") == "v1"
    db.set_setting(conn, "k", "v2")
    assert db.get_setting(conn, "k") == "v2"
```

- [ ] **Step 3: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_db.py -v
```

기대: `ModuleNotFoundError: No module named 'angeltime.db'`

- [ ] **Step 4: db.py 작성**

`src/angeltime/db.py`:

```python
"""SQLite 스키마, 연결, repository 함수.

운영 경로: ~/.local/share/angeltime/db.sqlite (XDG Base Directory).
테스트에서는 conftest 의 :memory: 픽스처를 사용.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(
    os.environ.get(
        "ANGELTIME_DB",
        str(Path.home() / ".local" / "share" / "angeltime" / "db.sqlite"),
    )
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS days (
    date TEXT PRIMARY KEY,
    week_iso TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL REFERENCES days(date) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    category TEXT NOT NULL,
    hours REAL NOT NULL DEFAULT 0,
    body_md TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    remote_id TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mappings (
    category TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    excluded INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS week_notes (
    week_iso TEXT PRIMARY KEY,
    body_md TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    target_range TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_action_logs_created_at ON action_logs(created_at);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect(path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """DB 파일 경로를 받아 connection 을 반환한다. 디렉토리가 없으면 생성."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """스키마를 초기화한다 (멱등)."""
    conn.executescript(SCHEMA)
    conn.commit()


# ─── days / entries ────────────────────────────────────


def upsert_entries(
    conn: sqlite3.Connection,
    *,
    date: str,
    week_iso: str,
    entries: list[dict[str, Any]],
) -> None:
    """그 날의 entries 를 완전 교체한다.

    days 행은 없으면 생성. 기존 entries 는 모두 삭제 후 새로 INSERT.
    """
    conn.execute(
        "INSERT OR IGNORE INTO days(date, week_iso) VALUES(?, ?)",
        (date, week_iso),
    )
    conn.execute("DELETE FROM entries WHERE date = ?", (date,))
    for idx, e in enumerate(entries):
        conn.execute(
            "INSERT INTO entries(date, order_index, category, hours, body_md) "
            "VALUES(?, ?, ?, ?, ?)",
            (date, idx, e["category"], e["hours"], e.get("body_md", "")),
        )
    conn.commit()


def get_day(conn: sqlite3.Connection, date: str) -> dict[str, Any]:
    """그 날의 entries 를 order_index 순으로 반환."""
    rows = conn.execute(
        "SELECT id, date, order_index, category, hours, body_md "
        "FROM entries WHERE date = ? ORDER BY order_index",
        (date,),
    ).fetchall()
    return {"date": date, "entries": [dict(r) for r in rows]}


def get_week(conn: sqlite3.Connection, week_iso: str) -> list[dict[str, Any]]:
    """그 주의 entries 가 있는 날짜들을 오름차순으로 반환.

    날짜 자체가 days 테이블에 없으면 결과에 포함되지 않는다.
    """
    dates = [
        r["date"]
        for r in conn.execute(
            "SELECT date FROM days WHERE week_iso = ? ORDER BY date",
            (week_iso,),
        ).fetchall()
    ]
    return [get_day(conn, d) for d in dates]


# ─── week_notes ────────────────────────────────────────


def get_week_note(conn: sqlite3.Connection, week_iso: str) -> str:
    """주별 자유 메모 본문. 없으면 빈 문자열."""
    row = conn.execute(
        "SELECT body_md FROM week_notes WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    return row["body_md"] if row else ""


def upsert_week_note(
    conn: sqlite3.Connection, week_iso: str, body_md: str
) -> None:
    """주별 메모 upsert."""
    conn.execute(
        "INSERT INTO week_notes(week_iso, body_md, updated_at) "
        "VALUES(?, ?, datetime('now')) "
        "ON CONFLICT(week_iso) DO UPDATE SET "
        "  body_md = excluded.body_md, updated_at = datetime('now')",
        (week_iso, body_md),
    )
    conn.commit()


# ─── projects / mappings ───────────────────────────────


def create_project(
    conn: sqlite3.Connection, *, name: str, remote_id: str | None = None
) -> int:
    """프로젝트를 생성하고 id 반환. 이름 중복은 IntegrityError."""
    cur = conn.execute(
        "INSERT INTO projects(name, remote_id) VALUES(?, ?)",
        (name, remote_id),
    )
    conn.commit()
    return cur.lastrowid


def list_projects(
    conn: sqlite3.Connection, *, active_only: bool = False
) -> list[dict[str, Any]]:
    sql = "SELECT id, name, remote_id, active FROM projects"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY name"
    return [dict(r) for r in conn.execute(sql).fetchall()]


def set_mapping(
    conn: sqlite3.Connection,
    category: str,
    *,
    project_id: int | None,
    excluded: bool = False,
) -> None:
    """카테고리 매핑 upsert. project_id=None + excluded=True 면 의도적 미입력."""
    conn.execute(
        "INSERT INTO mappings(category, project_id, excluded) VALUES(?, ?, ?) "
        "ON CONFLICT(category) DO UPDATE SET "
        "  project_id = excluded.project_id, excluded = excluded.excluded",
        (category, project_id, 1 if excluded else 0),
    )
    conn.commit()


def get_mapping(
    conn: sqlite3.Connection, category: str
) -> dict[str, Any] | None:
    """카테고리 매핑 + 프로젝트명을 함께 반환. 없으면 None."""
    row = conn.execute(
        "SELECT m.category, m.project_id, m.excluded, p.name AS project_name "
        "FROM mappings m LEFT JOIN projects p ON p.id = m.project_id "
        "WHERE m.category = ?",
        (category,),
    ).fetchone()
    return dict(row) if row else None


def list_mappings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT m.category, m.project_id, m.excluded, p.name AS project_name "
        "FROM mappings m LEFT JOIN projects p ON p.id = m.project_id "
        "ORDER BY m.category"
    ).fetchall()
    return [dict(r) for r in rows]


# ─── action_logs ───────────────────────────────────────


def log_action(
    conn: sqlite3.Connection,
    action_type: str,
    target_range: str,
    status: str,
    message: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO action_logs(action_type, target_range, status, message) "
        "VALUES(?, ?, ?, ?)",
        (action_type, target_range, status, message),
    )
    conn.commit()


def recent_actions(
    conn: sqlite3.Connection, *, limit: int = 50
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, action_type, target_range, status, message, created_at "
        "FROM action_logs ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def cleanup_action_logs(conn: sqlite3.Connection, *, days: int = 90) -> int:
    """N일보다 오래된 action_logs 삭제. 삭제된 row 수 반환."""
    cur = conn.execute(
        "DELETE FROM action_logs WHERE created_at < datetime('now', ?)",
        (f"-{days} days",),
    )
    conn.commit()
    return cur.rowcount


# ─── settings ──────────────────────────────────────────


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_db.py -v
```

기대: 모든 테스트 통과

- [ ] **Step 6: Commit**

```bash
git add src/angeltime/db.py tests/test_db.py tests/conftest.py
git commit -m "feat: add SQLite schema and repository functions"
```

---

### Task 6: templates.py — 기본 출력 템플릿 상수

**Files:**
- Create: `src/angeltime/templates.py`
- Create: `tests/test_templates.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_templates.py`:

```python
"""기본 템플릿 상수가 정의되어 있는지 확인."""

from __future__ import annotations

from angeltime.templates import (
    DEFAULT_TEAM_REPORT,
    DEFAULT_UPNOTE_BODY,
    DEFAULT_UPNOTE_TITLE,
)


def test_defaults_are_non_empty_strings():
    for t in (DEFAULT_TEAM_REPORT, DEFAULT_UPNOTE_BODY, DEFAULT_UPNOTE_TITLE):
        assert isinstance(t, str)
        assert t.strip()


def test_team_report_template_uses_category():
    assert "{{ entry.category }}" in DEFAULT_TEAM_REPORT


def test_upnote_body_template_includes_week_notes_conditional():
    """메모가 비면 출력하지 않도록 조건 분기가 있어야 한다."""
    assert "if week_notes" in DEFAULT_UPNOTE_BODY


def test_upnote_title_template_uses_year_and_week():
    assert "{{ yy }}" in DEFAULT_UPNOTE_TITLE
    assert "{{ ww }}" in DEFAULT_UPNOTE_TITLE
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_templates.py -v
```

기대: `ModuleNotFoundError`

- [ ] **Step 3: templates.py 작성**

`src/angeltime/templates.py`:

```python
"""기본 출력 템플릿 (Jinja2 문자열).

사용자가 settings 에서 override 하지 않으면 이 값이 사용된다.
포맷은 사용자 본인의 기존 일일보고 스타일을 그대로 따른다.
"""

from __future__ import annotations

# 팀장 보고 — 단일 날짜 또는 평탄화된 entries 리스트 컨텍스트.
# 자유 메모(week_notes) 는 컨텍스트에 주지 않아 자동으로 포함되지 않는다.
DEFAULT_TEAM_REPORT = """\
{%- for entry in entries -%}
*) {{ entry.category }}
{{ entry.body }}
{% if not loop.last %}
{% endif -%}
{%- endfor %}"""


# UpNote 노트 제목 — 주 단위.
DEFAULT_UPNOTE_TITLE = "{{ yy }}년 W{{ ww }} ({{ week_start_mmdd }} ~ {{ week_end_mmdd }})"


# UpNote 노트 본문 — 그 주의 모든 날짜 + 자유 메모(있을 때).
DEFAULT_UPNOTE_BODY = """\
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
{%- endif %}"""
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_templates.py -v
```

기대: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/templates.py tests/test_templates.py
git commit -m "feat: add default output templates"
```

---

## Phase 3: Formatter & External Adapters (Tasks 7-9)

### Task 7: formatter.py — Jinja2 sandboxed env + context builder + renderer

**Files:**
- Create: `src/angeltime/formatter.py`
- Create: `tests/test_formatter.py`

이 task 는 spec 6.4 절의 전체 출력 템플릿 시스템을 구현한다. 컨텍스트 빌더(`build_week_context`, `build_team_report_context`) 와 렌더 함수들이 핵심.

- [ ] **Step 1: 실패하는 테스트 작성 — 기본 템플릿이 사용자 예시와 일치**

`tests/test_formatter.py`:

```python
"""formatter 의 컨텍스트 빌더와 템플릿 렌더링."""

from __future__ import annotations

import sqlite3

import pytest
from jinja2 import TemplateSyntaxError

from angeltime import db, formatter
from angeltime.templates import (
    DEFAULT_TEAM_REPORT,
    DEFAULT_UPNOTE_BODY,
    DEFAULT_UPNOTE_TITLE,
)


def _seed_user_sample(conn: sqlite3.Connection) -> None:
    """spec 의 사용자 제공 예시 데이터를 DB 에 넣는다."""
    db.upsert_entries(
        conn,
        date="2026-05-12",
        week_iso="2026-W19",
        entries=[
            {
                "category": "SKT SMSC 리빌딩",
                "hours": 4.0,
                "body_md": " - VM1.0.5 PKG 신규 통계(KCTHLR) 기능 개발\n   . 시험 및 패키지 배포",
            },
            {
                "category": "EM 고도화",
                "hours": 4.0,
                "body_md": (
                    " - 신규 OAM 서버 공통 패키지 개발\n"
                    "   . 코어 인프라 구현 (05/06 ~ 05/29)\n"
                    "     -> 공통 로깅/설정 모듈 구현"
                ),
            },
            {
                "category": "소스 Commit",
                "hours": 0.0,
                "body_md": " - 완료",
            },
        ],
    )


def test_render_team_report_matches_user_example(conn: sqlite3.Connection) -> None:
    """기본 템플릿 + 사용자 샘플 = spec 의 예시 문자열."""
    _seed_user_sample(conn)
    ctx = formatter.build_team_report_context(conn, date="2026-05-12")
    out = formatter.render_team_report(DEFAULT_TEAM_REPORT, ctx)
    expected = (
        "*) SKT SMSC 리빌딩\n"
        " - VM1.0.5 PKG 신규 통계(KCTHLR) 기능 개발\n"
        "   . 시험 및 패키지 배포\n"
        "\n"
        "*) EM 고도화\n"
        " - 신규 OAM 서버 공통 패키지 개발\n"
        "   . 코어 인프라 구현 (05/06 ~ 05/29)\n"
        "     -> 공통 로깅/설정 모듈 구현\n"
        "\n"
        "*) 소스 Commit\n"
        " - 완료"
    )
    assert out == expected


def test_render_team_report_week_range_flattens_all_days(
    conn: sqlite3.Connection,
) -> None:
    """date=None, week_iso='2026-W19' 로 호출하면 그 주의 모든 entries 가 평탄화된다."""
    _seed_user_sample(conn)
    db.upsert_entries(
        conn, date="2026-05-13", week_iso="2026-W19",
        entries=[{"category": "Z", "hours": 1.0, "body_md": "x"}],
    )
    ctx = formatter.build_team_report_context(conn, week_iso="2026-W19")
    cats = [e["category"] for e in ctx["entries"]]
    assert cats == [
        "SKT SMSC 리빌딩", "EM 고도화", "소스 Commit", "Z",
    ]


def test_render_upnote_body_matches_user_example(conn: sqlite3.Connection) -> None:
    """그 주의 모든 날짜 + 빈 메모 → 메모 헤더는 출력되지 않는다."""
    _seed_user_sample(conn)
    ctx = formatter.build_week_context(conn, week_iso="2026-W19")
    out = formatter.render_upnote_body(DEFAULT_UPNOTE_BODY, ctx)
    assert "📝 메모" not in out
    assert out.startswith("26년 < 05/12, 화 >")
    assert "*) 소스 Commit" in out


def test_render_upnote_body_with_week_note_includes_section(
    conn: sqlite3.Connection,
) -> None:
    """week_notes 가 비어있지 않으면 구분선 + 헤더 + 본문이 출력된다."""
    _seed_user_sample(conn)
    db.upsert_week_note(conn, "2026-W19", "강남에서…\n기계 : 젠틀맥스 프로")
    ctx = formatter.build_week_context(conn, week_iso="2026-W19")
    out = formatter.render_upnote_body(DEFAULT_UPNOTE_BODY, ctx)
    assert "📝 메모" in out
    assert "강남에서…" in out
    assert "기계 : 젠틀맥스 프로" in out
    # 메모 헤더는 마지막 날짜 블록 뒤에 와야 한다
    assert out.index("📝 메모") > out.index("*) 소스 Commit")


def test_render_upnote_body_blank_only_week_note_omits_section(
    conn: sqlite3.Connection,
) -> None:
    """공백만 있는 메모는 빈 것으로 처리되어 헤더가 출력되지 않는다."""
    _seed_user_sample(conn)
    db.upsert_week_note(conn, "2026-W19", "   \n\n  ")
    ctx = formatter.build_week_context(conn, week_iso="2026-W19")
    out = formatter.render_upnote_body(DEFAULT_UPNOTE_BODY, ctx)
    assert "📝 메모" not in out


def test_render_upnote_title_matches_format(conn: sqlite3.Connection) -> None:
    """기본 제목 템플릿 + 컨텍스트 → '26년 W19 (05/11 ~ 05/15)' 형식."""
    _seed_user_sample(conn)
    ctx = formatter.build_week_context(conn, week_iso="2026-W19")
    title = formatter.render_upnote_title(DEFAULT_UPNOTE_TITLE, ctx)
    assert title == "26년 W19 (05/11 ~ 05/15)"


def test_render_with_syntax_error_raises(conn: sqlite3.Connection) -> None:
    """잘못된 Jinja2 syntax 는 TemplateSyntaxError."""
    _seed_user_sample(conn)
    ctx = formatter.build_team_report_context(conn, date="2026-05-12")
    with pytest.raises(TemplateSyntaxError):
        formatter.render_team_report("{% bogus %}", ctx)


def test_sandbox_blocks_unsafe_attribute_access(
    conn: sqlite3.Connection,
) -> None:
    """샌드박스 환경에서 위험한 속성 접근은 차단된다."""
    _seed_user_sample(conn)
    ctx = formatter.build_team_report_context(conn, date="2026-05-12")
    with pytest.raises(Exception):  # SecurityError 또는 UndefinedError
        formatter.render_team_report(
            "{{ entries.__class__.__mro__ }}", ctx
        )


def test_entry_body_first_line_and_rest_in_context(
    conn: sqlite3.Connection,
) -> None:
    """컨텍스트 안 entry 객체에 body_first_line / body_rest 가 노출된다.

    스펙 6.4.2 에 명시된 변수.
    """
    db.upsert_entries(
        conn, date="2026-05-12", week_iso="2026-W19",
        entries=[{
            "category": "X",
            "hours": 1.0,
            "body_md": "first line\nsecond line\nthird",
        }],
    )
    ctx = formatter.build_team_report_context(conn, date="2026-05-12")
    out = formatter.render_team_report(
        "[{{ entry.category }}] {{ entry.body_first_line }}\n* {{ entry.body_rest }}",
        ctx,
        repeat_entries=False,  # 단일 entry 컨텍스트로 사용
    )
    # 단일 entry 헬퍼가 없으면 위 호출은 안 되니 대안: 본문 검증
    assert "[X] first line" in out
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_formatter.py -v
```

기대: `ModuleNotFoundError: No module named 'angeltime.formatter'`

- [ ] **Step 3: formatter.py 작성**

`src/angeltime/formatter.py`:

```python
"""Jinja2 SandboxedEnvironment + 출력 컨텍스트 빌더 + 렌더 함수.

스펙 6.4 참조. 모든 출력 (팀장 보고, UpNote 제목/본문) 은 이 모듈을 거친다.
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import Any

from jinja2 import Environment, TemplateSyntaxError, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

from . import db


_DAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
_DAY_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _env() -> Environment:
    """SandboxedEnvironment 인스턴스. 매 호출마다 새로 만들어 캐시 의도 없이 단순화."""
    env = SandboxedEnvironment(
        autoescape=select_autoescape(default_for_string=False),
        keep_trailing_newline=False,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    return env


def _entry_dict(row: dict[str, Any]) -> dict[str, Any]:
    """DB row → 템플릿에 노출할 entry 객체."""
    body = row.get("body_md", "")
    if body:
        first, _, rest = body.partition("\n")
        body_first_line = first
        body_rest = rest.rstrip()
    else:
        body_first_line = ""
        body_rest = ""
    return {
        "date": row.get("date"),
        "category": row["category"],
        "hours": row["hours"],
        "body": body,
        "body_first_line": body_first_line,
        "body_rest": body_rest,
    }


def _day_obj(date_str: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    """날짜 객체 + 그날 entries."""
    d = datetime.date.fromisoformat(date_str)
    return {
        "date": date_str,
        "yy": f"{d.year % 100:02d}",
        "yyyy": str(d.year),
        "mm": f"{d.month:02d}",
        "dd": f"{d.day:02d}",
        "day_kr": _DAY_KR[d.weekday()],
        "day_en": _DAY_EN[d.weekday()],
        "weekday": d.weekday(),
        "entries": [_entry_dict(e) for e in entries],
    }


def _week_globals(week_iso: str) -> dict[str, Any]:
    """{yy, ww, week_start, week_end, week_start_mmdd, week_end_mmdd, week_label}."""
    year_str, w_str = week_iso.split("-W")
    year = int(year_str)
    week = int(w_str)
    # ISO 주는 월요일~일요일, 우리는 월~금만 다룬다 (출력에 영향 없음)
    monday = datetime.date.fromisocalendar(year, week, 1)
    friday = monday + datetime.timedelta(days=4)
    return {
        "yy": f"{year % 100:02d}",
        "yyyy": str(year),
        "ww": f"{week:02d}",
        "week_iso": week_iso,
        "week_start": monday.isoformat(),
        "week_end": friday.isoformat(),
        "week_start_mmdd": f"{monday.month:02d}/{monday.day:02d}",
        "week_end_mmdd": f"{friday.month:02d}/{friday.day:02d}",
        "week_label": (
            f"{year % 100:02d}년 W{week:02d} "
            f"({monday.month:02d}/{monday.day:02d} ~ "
            f"{friday.month:02d}/{friday.day:02d})"
        ),
    }


# ─── 컨텍스트 빌더 ──────────────────────────────────────


def build_week_context(
    conn: sqlite3.Connection, *, week_iso: str
) -> dict[str, Any]:
    """UpNote 본문/제목용 컨텍스트.

    - days: 그 주의 entries 있는 날짜만
    - week_notes: 공백 트림 후 비면 None
    """
    week = db.get_week(conn, week_iso)
    days = [_day_obj(d["date"], d["entries"]) for d in week if d["entries"]]
    raw_note = db.get_week_note(conn, week_iso)
    note = raw_note.strip() or None
    return {
        **_week_globals(week_iso),
        "days": days,
        "week_notes": note,
    }


def build_team_report_context(
    conn: sqlite3.Connection,
    *,
    date: str | None = None,
    week_iso: str | None = None,
) -> dict[str, Any]:
    """팀장 보고용 컨텍스트.

    date 가 주어지면 그 날짜의 entries 만, week_iso 가 주어지면 그 주
    모든 날짜의 entries 를 날짜 오름차순 → order_index 순으로 평탄화.
    """
    if date is not None and week_iso is not None:
        raise ValueError("date 와 week_iso 는 동시에 줄 수 없다")
    if date is None and week_iso is None:
        raise ValueError("date 또는 week_iso 둘 중 하나는 필요하다")

    if date is not None:
        day = db.get_day(conn, date)
        entries = [_entry_dict({**e, "date": date}) for e in day["entries"]]
        target_label = date
        d = datetime.date.fromisoformat(date)
        globals_ = {
            "yy": f"{d.year % 100:02d}",
            "yyyy": str(d.year),
            "mm": f"{d.month:02d}",
            "dd": f"{d.day:02d}",
            "day_kr": _DAY_KR[d.weekday()],
            "day_en": _DAY_EN[d.weekday()],
        }
    else:
        week = db.get_week(conn, week_iso)
        entries: list[dict[str, Any]] = []
        for day in week:
            for e in day["entries"]:
                entries.append(_entry_dict({**e, "date": day["date"]}))
        target_label = "이번 주 전체"
        globals_ = _week_globals(week_iso)

    return {**globals_, "entries": entries, "target_label": target_label}


# ─── 렌더 함수 ──────────────────────────────────────────


def render_team_report(
    template: str, ctx: dict[str, Any], *, repeat_entries: bool = True
) -> str:
    """팀장 보고 텍스트 렌더. TemplateSyntaxError 는 그대로 raise.

    repeat_entries=False 인 경우 (테스트용) ctx['entries'] 의 첫 entry 를
    'entry' 단일 변수로도 노출한다.
    """
    env = _env()
    t = env.from_string(template)
    if not repeat_entries and ctx.get("entries"):
        ctx = {**ctx, "entry": ctx["entries"][0]}
    return t.render(**ctx)


def render_upnote_title(template: str, ctx: dict[str, Any]) -> str:
    """UpNote 제목 렌더."""
    return _env().from_string(template).render(**ctx)


def render_upnote_body(template: str, ctx: dict[str, Any]) -> str:
    """UpNote 본문 렌더."""
    return _env().from_string(template).render(**ctx)


def validate_template(template: str) -> None:
    """syntax 만 검증한다. TemplateSyntaxError 를 그대로 raise."""
    _env().from_string(template)


__all__ = [
    "build_week_context",
    "build_team_report_context",
    "render_team_report",
    "render_upnote_title",
    "render_upnote_body",
    "validate_template",
    "TemplateSyntaxError",
]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_formatter.py -v
```

기대: 모든 테스트 통과. 실패하면 템플릿의 공백/줄바꿈을 신중히 확인 (trailing newline, blank line 사이).

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/formatter.py tests/test_formatter.py
git commit -m "feat: add Jinja2 sandboxed formatter with context builders"
```

---

### Task 8: upnote.py — x-callback-url 빌더 + subprocess open

**Files:**
- Create: `src/angeltime/upnote.py`
- Create: `tests/test_upnote.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_upnote.py`:

```python
"""UpNote x-callback-url 빌더와 호출."""

from __future__ import annotations

import subprocess
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from angeltime import upnote


def test_build_url_uses_note_new_endpoint():
    url = upnote.build_new_note_url(
        title="26년 W19", text="hello", notebook_id="nb-uuid"
    )
    parts = urlsplit(url)
    assert parts.scheme == "upnote"
    assert parts.netloc == "x-callback-url"
    assert parts.path == "/note/new"


def test_build_url_includes_required_params():
    url = upnote.build_new_note_url(
        title="제목", text="본문 텍스트", notebook_id="abc-def"
    )
    qs = parse_qs(urlsplit(url).query)
    assert qs["title"] == ["제목"]
    assert qs["text"] == ["본문 텍스트"]
    assert qs["notebook"] == ["abc-def"]
    assert qs["markdown"] == ["true"]


def test_build_url_percent_encodes_special_chars():
    url = upnote.build_new_note_url(
        title="W19 (05/11 ~ 05/15)",
        text="line1\nline2 & line3",
        notebook_id="nb",
    )
    # urlencode 가 처리. 디코딩해서 원본 일치 확인
    qs = parse_qs(urlsplit(url).query)
    assert qs["title"] == ["W19 (05/11 ~ 05/15)"]
    assert qs["text"] == ["line1\nline2 & line3"]


def test_build_url_omits_notebook_when_empty():
    """notebook_id 가 비어있으면 notebook 파라미터를 생략 (UpNote 기본 노트북에 저장)."""
    url = upnote.build_new_note_url(title="t", text="b", notebook_id="")
    qs = parse_qs(urlsplit(url).query)
    assert "notebook" not in qs


def test_open_note_calls_subprocess_open_with_url():
    """open_new_note 는 subprocess.run(['open', url]) 을 호출."""
    with patch.object(subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        upnote.open_new_note(title="t", text="b", notebook_id="nb")
    called_with = run.call_args[0][0]
    assert called_with[0] == "open"
    assert called_with[1].startswith("upnote://x-callback-url/note/new")


def test_open_note_raises_on_nonzero_exit():
    with patch.object(subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="failed"
        )
        with pytest.raises(RuntimeError):
            upnote.open_new_note(title="t", text="b", notebook_id="nb")
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_upnote.py -v
```

기대: `ModuleNotFoundError`

- [ ] **Step 3: upnote.py 작성**

`src/angeltime/upnote.py`:

```python
"""UpNote x-callback-url 어댑터.

공식 문서: https://help.getupnote.com/resources/x-callback-url-endpoints

UpNote 의 모든 x-callback-url 은 외부 → UpNote 단방향. note 의 내용을 읽어오는
endpoint 는 제공되지 않는다. 본 도구는 'note/new' 만 사용해 노트 생성한다.
"""

from __future__ import annotations

import logging
import subprocess
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


def build_new_note_url(
    *, title: str, text: str, notebook_id: str = ""
) -> str:
    """upnote://x-callback-url/note/new URL 을 만든다.

    notebook_id 가 비어있으면 notebook 파라미터를 생략하여 UpNote 기본 노트북에 저장.
    """
    params: dict[str, str] = {
        "title": title,
        "text": text,
        "markdown": "true",
    }
    if notebook_id:
        params["notebook"] = notebook_id
    qs = urlencode(params)
    return f"upnote://x-callback-url/note/new?{qs}"


def open_new_note(
    *, title: str, text: str, notebook_id: str = ""
) -> str:
    """subprocess.run(['open', url]) 로 호출.

    `open` 은 macOS 의 빌트인. 호출 자체가 비동기로 UpNote 앱을 깨우므로,
    반환값으로는 단지 호출에 사용한 URL 을 돌려준다.
    실패 시 RuntimeError.
    """
    url = build_new_note_url(title=title, text=text, notebook_id=notebook_id)
    result = subprocess.run(
        ["open", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"open upnote url failed: rc={result.returncode} "
            f"stderr={result.stderr.strip()}"
        )
    logger.info("Opened UpNote new-note URL (title=%r)", title)
    return url
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_upnote.py -v
```

기대: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/upnote.py tests/test_upnote.py
git commit -m "feat: add UpNote x-callback-url adapter"
```

---

### Task 9: client.py — timesheet.uangel.com login (angelnet 복제)

**Files:**
- Create: `src/angeltime/client.py`
- Create: `tests/test_client.py`

이 task 에서는 **login 만** 구현한다. jobtime API 메서드는 Phase 7 에서 DevTools 캡처 후 추가.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_client.py`:

```python
"""TimesheetClient 의 login 만 우선 검증.

httpx 호출은 respx 로 mock 한다.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from angeltime.client import (
    SPRING_BASE,
    TS_LOGIN,
    TimesheetClient,
)
from angeltime.errors import AuthError, BotBlockedError


@pytest.fixture
def client() -> TimesheetClient:
    return TimesheetClient(user_id="alice")


@respx.mock
async def test_login_success_returns_user(client: TimesheetClient) -> None:
    respx.post(TS_LOGIN).mock(return_value=httpx.Response(200, json={"ok": True}))
    respx.get(f"{SPRING_BASE}/meeting-rooms/current-user").mock(
        return_value=httpx.Response(200, json={"userId": "alice"})
    )
    respx.get(f"{SPRING_BASE}/meeting-rooms/user-name").mock(
        return_value=httpx.Response(200, json={"name": "앨리스"})
    )
    user = await client.login("secret")
    await client.close()
    assert user.user_id == "alice"
    assert user.name == "앨리스"


@respx.mock
async def test_login_4xx_raises_auth_error(client: TimesheetClient) -> None:
    respx.post(TS_LOGIN).mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    with pytest.raises(AuthError):
        await client.login("badpass")
    await client.close()


@respx.mock
async def test_login_bot_block_raises(client: TimesheetClient) -> None:
    respx.post(TS_LOGIN).mock(
        return_value=httpx.Response(
            403, json={"error": "Automated requests are not allowed"}
        )
    )
    with pytest.raises(BotBlockedError):
        await client.login("secret")
    await client.close()


@respx.mock
async def test_login_cached_session_no_refetch(
    client: TimesheetClient,
) -> None:
    """세션 캐시가 살아있으면 두 번째 호출은 네트워크 호출 없이 같은 User 반환."""
    login_route = respx.post(TS_LOGIN).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    cu_route = respx.get(f"{SPRING_BASE}/meeting-rooms/current-user").mock(
        return_value=httpx.Response(200, json={"userId": "alice"})
    )
    respx.get(f"{SPRING_BASE}/meeting-rooms/user-name").mock(
        return_value=httpx.Response(200, json={"name": "앨리스"})
    )
    await client.login("secret")
    await client.login("secret")
    await client.close()
    assert login_route.call_count == 1
    assert cu_route.call_count == 1
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_client.py -v
```

기대: `ModuleNotFoundError: No module named 'angeltime.client'`

- [ ] **Step 3: client.py 작성 (angelnet client.py 의 login 부분만 복제 + 클래스명 변경)**

`src/angeltime/client.py`:

```python
"""timesheet.uangel.com Spring REST 클라이언트.

angelnet/src/angeldash/client.py 의 login() 흐름을 그대로 가져와 사용한다.
세션 쿠키(JSESSIONID) 는 httpx.AsyncClient 가 자동 보관해 후속 호출에 자동 포함.

jobtime API 메서드는 Phase 7 (DevTools 캡처 후) 에서 추가된다.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from .errors import ApiError, AuthError, BotBlockedError
from .models import User

logger = logging.getLogger(__name__)

# Timesheet 인증
TS_LOGIN = "https://timesheet.uangel.com/home/login.json"
TS_REDIRECT_PATH = "/times/timesheet/jobtime/create.htm"
TS_REDIRECT_PARAMS: dict[str, str] = {}

# Spring REST base (angelnet 과 같은 도메인)
SPRING_BASE = "https://timesheet.uangel.com/times/application/meeting_room/api"

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X)"
HTTP_TIMEOUT = 15.0
BOT_BLOCK_MARKER = "Automated requests are not allowed"
SESSION_TTL = 24 * 3600  # 24h


def _is_bot_blocked(payload: Any) -> bool:
    """응답 본문에 자동화 차단 메시지가 포함되어 있는지."""
    if isinstance(payload, dict):
        msg = payload.get("error") or payload.get("message") or ""
        return BOT_BLOCK_MARKER in str(msg)
    return False


class TimesheetClient:
    """timesheet.uangel.com Spring REST 호출 캡슐화.

    angelnet 의 AngelNetClient 와 같은 인증 흐름. 향후 두 도구를 통합하면
    공통 base class 로 추출 가능.
    """

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._user: User | None = None
        self._session_ready = False
        self._session_expires = 0.0
        self._http = httpx.AsyncClient(
            verify=False,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )

    async def close(self) -> None:
        await self._http.aclose()

    # ─── 인증 ────────────────────────────────────────

    async def login(self, password: str) -> User:
        """Timesheet 로그인 후 current-user 호출하여 User 반환.

        캐시된 세션이 살아있으면 네트워크 호출 없이 캐시를 반환한다.
        """
        if self._user and self._session_ready and time.time() < self._session_expires:
            return self._user

        # angelnet 과 동일한 redirectUrl 형식. params 가 비면 query 없이 path 만.
        if TS_REDIRECT_PARAMS:
            rq = urlencode(TS_REDIRECT_PARAMS)
            redirect = f"{TS_REDIRECT_PATH}?{rq}"
        else:
            redirect = TS_REDIRECT_PATH

        resp = await self._http.post(
            TS_LOGIN,
            data={
                "userId": self.user_id,
                "password": password,
                "redirectUrl": redirect,
            },
        )
        body = self._safe_json(resp)
        if _is_bot_blocked(body):
            raise BotBlockedError(body.get("error") or body.get("message"))
        if resp.status_code >= 500:
            raise ApiError(
                f"server error on login: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        if resp.status_code >= 400:
            raise AuthError(f"login failed: status={resp.status_code} body={body}")

        # current-user 로 사용자 정보 확보
        cu = await self._http.get(f"{SPRING_BASE}/meeting-rooms/current-user")
        cu_body = self._safe_json(cu)
        if _is_bot_blocked(cu_body):
            raise BotBlockedError(cu_body.get("error") or cu_body.get("message"))
        if cu.status_code >= 500:
            raise ApiError(
                f"server error on current-user: status={cu.status_code}",
                status_code=cu.status_code,
                payload=cu_body,
            )
        if cu.status_code >= 400:
            raise AuthError(
                f"current-user failed: status={cu.status_code} body={cu_body}"
            )
        if not (isinstance(cu_body, dict) and cu_body.get("userId")):
            raise AuthError(f"current-user missing userId: {cu_body}")

        # name 은 별도 endpoint. 실패는 fatal 아님 (userId fallback)
        name = cu_body["userId"]
        try:
            nu = await self._http.get(
                f"{SPRING_BASE}/meeting-rooms/user-name",
                params={"userId": cu_body["userId"]},
            )
            if nu.status_code == 200:
                nb = nu.json()
                if isinstance(nb, dict) and nb.get("name"):
                    name = nb["name"]
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("user-name fetch failed (non-fatal): %s", exc)

        self._user = User(user_id=cu_body["userId"], name=name)
        self._session_ready = True
        self._session_expires = time.time() + SESSION_TTL
        logger.info("Spring session established for user=%s", self.user_id)
        return self._user

    # ─── jobtime API (Phase 7 에서 추가) ───────────
    # submit_jobtime, list_remote_projects 는 DevTools 캡처 후 구현됨.

    # ─── 내부 헬퍼 ─────────────────────────────────

    @staticmethod
    def _safe_json(
        resp: httpx.Response,
        exc_type: type[Exception] = AuthError,
    ) -> Any:
        """JSON 파싱 실패 시 지정 예외로 변환."""
        try:
            return resp.json()
        except ValueError as exc:
            if exc_type is ApiError:
                raise ApiError(
                    f"non-json response: status={resp.status_code}",
                    status_code=resp.status_code,
                ) from exc
            raise exc_type(
                f"non-json response: status={resp.status_code}"
            ) from exc
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_client.py -v
```

기대: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/client.py tests/test_client.py
git commit -m "feat: add TimesheetClient.login (angelnet pattern)"
```

---

## Phase 4: FastAPI Server Skeleton + CRUD APIs (Tasks 10-13)

### Task 10: server.py — 앱 골격 + lifespan + /api/me

**Files:**
- Create: `src/angeltime/server.py`
- Modify: `tests/conftest.py` (FastAPI TestClient 픽스처 추가)

- [ ] **Step 1: conftest.py 에 TestClient 픽스처 추가**

`tests/conftest.py` 전체:

```python
"""공통 pytest 픽스처."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from angeltime import db as db_module
from angeltime.models import User


@pytest.fixture
def conn() -> Generator[sqlite3.Connection, None, None]:
    """인메모리 SQLite 연결 + 스키마 초기화."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db_module.init_schema(c)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def mock_client() -> AsyncMock:
    """TimesheetClient mock — login 만 stub. user_id 속성 미리 지정."""
    m = AsyncMock()
    m.user_id = "alice"
    m.login.return_value = User(user_id="alice", name="앨리스")
    return m


@pytest.fixture
def test_app(conn: sqlite3.Connection, mock_client: AsyncMock):
    """build_app 으로 만든 FastAPI 앱 + dependency override."""
    from angeltime.server import build_app, get_conn, get_client, get_password

    app = build_app(user_id="alice", skip_lifespan_login=True)
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_password] = lambda: "secret"
    return app


@pytest.fixture
def api(test_app):
    return TestClient(test_app)
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_server.py`:

```python
"""FastAPI 서버 라우트 테스트."""

from __future__ import annotations


def test_me_returns_logged_in_user(api):
    r = api.get("/api/me")
    assert r.status_code == 200
    assert r.json() == {"user_id": "alice", "name": "앨리스"}


def test_static_index_html_served(api):
    r = api.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
```

- [ ] **Step 3: server.py 작성 (최소 골격: lifespan + me + 정적 파일)**

`src/angeltime/server.py`:

```python
"""FastAPI 앱.

lifespan 에서 TimesheetClient login → 의존성 주입. 라우터는 phase 별로 추가된다.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db as db_module
from .auth import KeychainStore
from .client import TimesheetClient
from .models import User

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


# ─── 의존성 placeholder ────────────────────────────────


def get_conn() -> sqlite3.Connection:
    raise RuntimeError("db connection not initialized")


def get_client() -> TimesheetClient:
    raise RuntimeError("client not initialized")


def get_password() -> str:
    raise RuntimeError("password not initialized")


# ─── 앱 빌더 ───────────────────────────────────────────


def build_app(
    user_id: str,
    *,
    db_path: Path | str | None = None,
    skip_lifespan_login: bool = False,
) -> FastAPI:
    """FastAPI 앱 빌더.

    skip_lifespan_login=True 면 테스트에서 lifespan 의 네트워크 호출을 건너뛴다.
    """
    keychain = KeychainStore(account=user_id)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 테스트 모드: lifespan 안에서 자원 할당 없이 곧장 yield.
        # 테스트는 dependency_overrides 로 conn/client/password 를 직접 주입한다.
        if skip_lifespan_login:
            yield
            return

        conn = db_module.connect(db_path) if db_path else db_module.connect()
        app.dependency_overrides[get_conn] = lambda: conn

        password = os.environ.get("ANGELNET_PWD") or keychain.get()
        if not password:
            raise RuntimeError(
                "Password not found. Set ANGELNET_PWD env var or run angeldash once."
            )
        client = TimesheetClient(user_id=user_id)
        await client.login(password)
        app.dependency_overrides[get_client] = lambda: client
        app.dependency_overrides[get_password] = lambda: password

        try:
            yield
        finally:
            await client.close()
            conn.close()

    app = FastAPI(title="angeltime — 일일 업무 보고 통합 도구", lifespan=lifespan)

    # ─── 정적 파일 ─────────────────────────────────
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    # ─── /api/me ────────────────────────────────────
    @app.get("/api/me", response_model=User)
    async def me(
        client: TimesheetClient = Depends(get_client),
        password: str = Depends(get_password),
    ) -> User:
        return await client.login(password)

    return app
```

- [ ] **Step 4: 정적 파일 placeholder 생성 (server 가 인덱스 페이지를 찾을 수 있도록)**

`src/angeltime/static/index.html`:

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>angeltime</title>
</head>
<body>
  <h1>angeltime</h1>
  <p>아직 UI 가 구현되지 않았습니다.</p>
</body>
</html>
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_server.py -v
```

기대: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/angeltime/server.py src/angeltime/static/index.html tests/conftest.py tests/test_server.py
git commit -m "feat: add FastAPI app skeleton with /api/me and static serving"
```

---

### Task 11: server.py — Reports API (entries CRUD)

**Files:**
- Modify: `src/angeltime/server.py` (라우트 추가)
- Modify: `tests/test_server.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_server.py` 뒤에 추가:

```python
def test_get_week_empty(api):
    r = api.get("/api/weeks/2026-W19")
    assert r.status_code == 200
    body = r.json()
    assert body == {"week_iso": "2026-W19", "days": []}


def test_put_day_creates_entries(api):
    r = api.put(
        "/api/days/2026-05-12",
        json={
            "week_iso": "2026-W19",
            "entries": [
                {"category": "A", "hours": 4, "body_md": "x"},
                {"category": "B", "hours": 4, "body_md": "y"},
            ],
        },
    )
    assert r.status_code == 200
    g = api.get("/api/days/2026-05-12")
    cats = [e["category"] for e in g.json()["entries"]]
    assert cats == ["A", "B"]


def test_put_day_replaces_entries(api):
    api.put(
        "/api/days/2026-05-12",
        json={
            "week_iso": "2026-W19",
            "entries": [{"category": "A", "hours": 8, "body_md": ""}],
        },
    )
    api.put(
        "/api/days/2026-05-12",
        json={
            "week_iso": "2026-W19",
            "entries": [{"category": "B", "hours": 1, "body_md": ""}],
        },
    )
    g = api.get("/api/days/2026-05-12")
    cats = [e["category"] for e in g.json()["entries"]]
    assert cats == ["B"]


def test_put_day_rejects_invalid_category(api):
    r = api.put(
        "/api/days/2026-05-12",
        json={
            "week_iso": "2026-W19",
            "entries": [{"category": "   ", "hours": 4, "body_md": ""}],
        },
    )
    assert r.status_code == 422


def test_get_week_note_default_empty(api):
    r = api.get("/api/weeks/2026-W19/note")
    assert r.status_code == 200
    assert r.json() == {"week_iso": "2026-W19", "body_md": ""}


def test_put_week_note_persists(api):
    r = api.put(
        "/api/weeks/2026-W19/note",
        json={"body_md": "메모 본문"},
    )
    assert r.status_code == 200
    g = api.get("/api/weeks/2026-W19/note")
    assert g.json()["body_md"] == "메모 본문"
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_server.py -v -k "week or day or note"
```

기대: 404 또는 동일한 fail

- [ ] **Step 3: server.py 에 reports 라우트 추가**

`src/angeltime/server.py` 의 `build_app` 안 `/api/me` 다음에 추가:

```python
    # ─── Reports API ────────────────────────────────

    from pydantic import BaseModel  # (모듈 상단으로 옮겨도 됨)
    from .models import EntryInput, WeekNoteInput

    class DayInput(BaseModel):
        week_iso: str
        entries: list[EntryInput]

    @app.get("/api/weeks/{week_iso}")
    async def get_week_route(
        week_iso: str, conn=Depends(get_conn)
    ) -> dict:
        days = db_module.get_week(conn, week_iso)
        return {"week_iso": week_iso, "days": days}

    @app.get("/api/days/{date}")
    async def get_day_route(date: str, conn=Depends(get_conn)) -> dict:
        return db_module.get_day(conn, date)

    @app.put("/api/days/{date}")
    async def put_day_route(
        date: str, payload: DayInput, conn=Depends(get_conn)
    ) -> dict:
        db_module.upsert_entries(
            conn,
            date=date,
            week_iso=payload.week_iso,
            entries=[e.model_dump() for e in payload.entries],
        )
        return {"ok": True}

    @app.get("/api/weeks/{week_iso}/note")
    async def get_week_note_route(
        week_iso: str, conn=Depends(get_conn)
    ) -> dict:
        return {
            "week_iso": week_iso,
            "body_md": db_module.get_week_note(conn, week_iso),
        }

    @app.put("/api/weeks/{week_iso}/note")
    async def put_week_note_route(
        week_iso: str, payload: WeekNoteInput, conn=Depends(get_conn)
    ) -> dict:
        db_module.upsert_week_note(conn, week_iso, payload.body_md)
        return {"ok": True}
```

`import` 정리: `from pydantic import BaseModel` 와 `from .models import EntryInput, WeekNoteInput` 을 파일 상단으로 옮긴다.

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_server.py -v
```

기대: 모든 테스트 통과

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/server.py tests/test_server.py
git commit -m "feat: add reports/week-notes CRUD API"
```

---

### Task 12: server.py — Projects + Mappings API

**Files:**
- Modify: `src/angeltime/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_server.py` 뒤에 추가:

```python
def test_create_and_list_projects(api):
    r = api.post(
        "/api/projects",
        json={"name": "25년 SKT SMSC MAP 프로토콜 제거"},
    )
    assert r.status_code == 200
    pid = r.json()["id"]
    g = api.get("/api/projects")
    assert g.status_code == 200
    names = [p["name"] for p in g.json()]
    assert "25년 SKT SMSC MAP 프로토콜 제거" in names


def test_create_project_rejects_duplicate(api):
    api.post("/api/projects", json={"name": "X"})
    r = api.post("/api/projects", json={"name": "X"})
    assert r.status_code == 409


def test_put_mapping_and_list(api):
    p = api.post("/api/projects", json={"name": "P"}).json()
    api.put(
        "/api/mappings/SKT%20SMSC%20%EB%A6%AC%EB%B9%8C%EB%94%A9",
        json={"project_id": p["id"], "excluded": False},
    )
    g = api.get("/api/mappings")
    items = {m["category"]: m for m in g.json()}
    assert "SKT SMSC 리빌딩" in items
    assert items["SKT SMSC 리빌딩"]["project_name"] == "P"


def test_put_mapping_with_excluded_true_clears_project(api):
    api.put(
        "/api/mappings/%EC%86%8C%EC%8A%A4%20Commit",
        json={"project_id": None, "excluded": True},
    )
    g = api.get("/api/mappings")
    items = {m["category"]: m for m in g.json()}
    assert items["소스 Commit"]["excluded"] is True
    assert items["소스 Commit"]["project_id"] is None
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_server.py -v -k "project or mapping"
```

기대: 404

- [ ] **Step 3: server.py 에 라우트 추가**

`build_app` 안 reports 다음:

```python
    # ─── Projects + Mappings API ────────────────────

    from .models import Mapping, Project, ProjectInput

    class MappingInput(BaseModel):
        project_id: int | None = None
        excluded: bool = False

    @app.get("/api/projects")
    async def list_projects_route(conn=Depends(get_conn)) -> list[dict]:
        return db_module.list_projects(conn)

    @app.post("/api/projects")
    async def create_project_route(
        payload: ProjectInput, conn=Depends(get_conn)
    ) -> dict:
        import sqlite3 as _sqlite3
        try:
            pid = db_module.create_project(
                conn, name=payload.name, remote_id=payload.remote_id
            )
        except _sqlite3.IntegrityError as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail="duplicate name") from exc
        return {"id": pid, "name": payload.name}

    @app.get("/api/mappings")
    async def list_mappings_route(conn=Depends(get_conn)) -> list[dict]:
        return db_module.list_mappings(conn)

    @app.put("/api/mappings/{category}")
    async def put_mapping_route(
        category: str, payload: MappingInput, conn=Depends(get_conn)
    ) -> dict:
        db_module.set_mapping(
            conn,
            category,
            project_id=payload.project_id,
            excluded=payload.excluded,
        )
        return {"ok": True}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_server.py -v
```

기대: 모든 테스트 통과

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/server.py tests/test_server.py
git commit -m "feat: add projects/mappings CRUD API"
```

---

### Task 13: server.py — Settings + Action logs API

**Files:**
- Modify: `src/angeltime/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_server.py` 뒤에 추가:

```python
def test_get_settings_returns_defaults_for_unset(api):
    r = api.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    # 키 존재 보장 (값은 None 또는 default 템플릿 문자열)
    for key in (
        "upnote.notebook_id",
        "upnote.title_template",
        "upnote.body_template",
        "team_report.template",
    ):
        assert key in body


def test_put_settings_updates_values(api):
    api.put("/api/settings", json={"upnote.notebook_id": "abc-123"})
    r = api.get("/api/settings")
    assert r.json()["upnote.notebook_id"] == "abc-123"


def test_put_settings_rejects_invalid_jinja2(api):
    r = api.put(
        "/api/settings",
        json={"team_report.template": "{% bogus %}"},
    )
    assert r.status_code == 400


def test_post_settings_preview_renders_team_report(api):
    api.put(
        "/api/days/2026-05-12",
        json={
            "week_iso": "2026-W19",
            "entries": [{"category": "X", "hours": 1, "body_md": "- 어쩌고"}],
        },
    )
    r = api.post(
        "/api/settings/preview",
        json={
            "kind": "team_report",
            "template": "*) {{ entry.category }}\n{{ entry.body }}",
            "date": "2026-05-12",
        },
    )
    assert r.status_code == 200
    assert "*) X" in r.json()["text"]


def test_get_logs_empty(api):
    r = api.get("/api/logs")
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_server.py -v -k "settings or logs"
```

- [ ] **Step 3: server.py 에 라우트 추가**

`build_app` 안 추가:

```python
    # ─── Settings + Logs API ───────────────────────

    from . import formatter as fmt_module
    from .templates import (
        DEFAULT_TEAM_REPORT,
        DEFAULT_UPNOTE_BODY,
        DEFAULT_UPNOTE_TITLE,
    )

    SETTING_DEFAULTS: dict[str, str] = {
        "upnote.notebook_id": "",
        "upnote.title_template": DEFAULT_UPNOTE_TITLE,
        "upnote.body_template": DEFAULT_UPNOTE_BODY,
        "team_report.template": DEFAULT_TEAM_REPORT,
    }

    @app.get("/api/settings")
    async def get_settings_route(conn=Depends(get_conn)) -> dict:
        out: dict[str, str] = {}
        for k, default in SETTING_DEFAULTS.items():
            v = db_module.get_setting(conn, k)
            out[k] = v if v is not None else default
        return out

    @app.put("/api/settings")
    async def put_settings_route(
        payload: dict[str, str], conn=Depends(get_conn)
    ) -> dict:
        # Jinja2 syntax 검증: template 키들은 미리 컴파일 시도
        from fastapi import HTTPException

        template_keys = {
            "upnote.title_template",
            "upnote.body_template",
            "team_report.template",
        }
        for k, v in payload.items():
            if k in template_keys and v.strip():
                try:
                    fmt_module.validate_template(v)
                except fmt_module.TemplateSyntaxError as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"template syntax error in {k}: {exc.message}",
                    ) from exc
        for k, v in payload.items():
            db_module.set_setting(conn, k, v)
        return {"ok": True}

    class SettingsPreviewInput(BaseModel):
        kind: str  # 'team_report' | 'upnote_title' | 'upnote_body'
        template: str
        date: str | None = None
        week_iso: str | None = None

    @app.post("/api/settings/preview")
    async def preview_settings_route(
        payload: SettingsPreviewInput, conn=Depends(get_conn)
    ) -> dict:
        from fastapi import HTTPException

        try:
            if payload.kind == "team_report":
                if payload.date:
                    ctx = fmt_module.build_team_report_context(
                        conn, date=payload.date
                    )
                elif payload.week_iso:
                    ctx = fmt_module.build_team_report_context(
                        conn, week_iso=payload.week_iso
                    )
                else:
                    raise HTTPException(400, "date or week_iso required")
                text = fmt_module.render_team_report(payload.template, ctx)
            else:
                if not payload.week_iso:
                    raise HTTPException(400, "week_iso required")
                ctx = fmt_module.build_week_context(
                    conn, week_iso=payload.week_iso
                )
                if payload.kind == "upnote_title":
                    text = fmt_module.render_upnote_title(payload.template, ctx)
                elif payload.kind == "upnote_body":
                    text = fmt_module.render_upnote_body(payload.template, ctx)
                else:
                    raise HTTPException(400, f"unknown kind: {payload.kind}")
        except fmt_module.TemplateSyntaxError as exc:
            raise HTTPException(
                400, f"template syntax error: {exc.message}"
            ) from exc
        return {"text": text}

    @app.get("/api/logs")
    async def list_logs_route(conn=Depends(get_conn)) -> list[dict]:
        return db_module.recent_actions(conn, limit=200)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_server.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/server.py tests/test_server.py
git commit -m "feat: add settings + logs API with template validation/preview"
```

---

## Phase 5: Action APIs (Tasks 14-15)

### Task 14: server.py — Action: team-report (텍스트 생성)

**Files:**
- Modify: `src/angeltime/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: 실패하는 테스트 추가**

```python
def test_action_team_report_returns_text(api):
    api.put(
        "/api/days/2026-05-12",
        json={
            "week_iso": "2026-W19",
            "entries": [{
                "category": "X",
                "hours": 8,
                "body_md": " - 어쩌고",
            }],
        },
    )
    r = api.post(
        "/api/actions/team-report",
        json={"date": "2026-05-12"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "*) X" in body["text"]
    assert " - 어쩌고" in body["text"]


def test_action_team_report_logs(api):
    api.put(
        "/api/days/2026-05-12",
        json={"week_iso": "2026-W19", "entries": [
            {"category": "X", "hours": 8, "body_md": ""}
        ]},
    )
    api.post("/api/actions/team-report", json={"date": "2026-05-12"})
    logs = api.get("/api/logs").json()
    assert any(
        l["action_type"] == "report" and l["status"] == "ok" for l in logs
    )


def test_action_team_report_week_range(api):
    api.put("/api/days/2026-05-12", json={"week_iso": "2026-W19", "entries": [
        {"category": "X", "hours": 4, "body_md": ""}
    ]})
    api.put("/api/days/2026-05-13", json={"week_iso": "2026-W19", "entries": [
        {"category": "Y", "hours": 4, "body_md": ""}
    ]})
    r = api.post("/api/actions/team-report", json={"week_iso": "2026-W19"})
    text = r.json()["text"]
    assert "X" in text
    assert "Y" in text
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_server.py -v -k "team_report"
```

- [ ] **Step 3: server.py 에 action 라우트 추가**

```python
    # ─── Actions ────────────────────────────────────

    class TeamReportActionInput(BaseModel):
        date: str | None = None
        week_iso: str | None = None

    @app.post("/api/actions/team-report")
    async def action_team_report(
        payload: TeamReportActionInput, conn=Depends(get_conn)
    ) -> dict:
        from fastapi import HTTPException

        try:
            template = db_module.get_setting(conn, "team_report.template")
            if not template:
                template = SETTING_DEFAULTS["team_report.template"]
            if payload.date:
                ctx = fmt_module.build_team_report_context(
                    conn, date=payload.date
                )
                target_range = payload.date
            elif payload.week_iso:
                ctx = fmt_module.build_team_report_context(
                    conn, week_iso=payload.week_iso
                )
                target_range = payload.week_iso
            else:
                raise HTTPException(400, "date or week_iso required")
            text = fmt_module.render_team_report(template, ctx)
        except Exception as exc:
            db_module.log_action(
                conn, "report",
                payload.date or payload.week_iso or "?",
                "fail", str(exc),
            )
            raise
        db_module.log_action(conn, "report", target_range, "ok", None)
        return {"text": text}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_server.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/server.py tests/test_server.py
git commit -m "feat: add team-report action API"
```

---

### Task 15: server.py — Action: upnote-sync (subprocess open 호출)

**Files:**
- Modify: `src/angeltime/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: 실패하는 테스트 추가**

```python
def test_action_upnote_sync_calls_subprocess(api, monkeypatch):
    """upnote-sync 는 build_url 결과로 subprocess.run(['open', url]) 을 호출."""
    from angeltime import upnote
    calls = []

    def fake_open(*, title, text, notebook_id):
        calls.append({"title": title, "text": text, "notebook_id": notebook_id})
        return "upnote://fake"

    monkeypatch.setattr(upnote, "open_new_note", fake_open)

    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W19",
        "entries": [{"category": "X", "hours": 8, "body_md": " - 어쩌고"}],
    })
    api.put("/api/settings", json={"upnote.notebook_id": "nb-123"})

    r = api.post(
        "/api/actions/upnote-sync",
        json={"week_iso": "2026-W19"},
    )
    assert r.status_code == 200, r.text
    assert len(calls) == 1
    assert calls[0]["notebook_id"] == "nb-123"
    assert "26년" in calls[0]["title"]
    assert "*) X" in calls[0]["text"]


def test_action_upnote_dry_run_returns_payload_without_open(api, monkeypatch):
    """dry_run=True 면 subprocess 호출 없이 title/text 만 반환."""
    from angeltime import upnote

    def boom(**kwargs):
        raise AssertionError("should not be called in dry_run")

    monkeypatch.setattr(upnote, "open_new_note", boom)

    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W19",
        "entries": [{"category": "X", "hours": 8, "body_md": "x"}],
    })
    r = api.post(
        "/api/actions/upnote-sync",
        json={"week_iso": "2026-W19", "dry_run": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert "title" in body
    assert "text" in body
    assert body["opened"] is False
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_server.py -v -k "upnote"
```

- [ ] **Step 3: server.py 에 라우트 추가**

```python
    # 위 Actions 섹션 안에 추가:

    from . import upnote as upnote_module

    class UpNoteSyncInput(BaseModel):
        week_iso: str
        dry_run: bool = False

    @app.post("/api/actions/upnote-sync")
    async def action_upnote_sync(
        payload: UpNoteSyncInput, conn=Depends(get_conn)
    ) -> dict:
        from fastapi import HTTPException

        title_template = (
            db_module.get_setting(conn, "upnote.title_template")
            or SETTING_DEFAULTS["upnote.title_template"]
        )
        body_template = (
            db_module.get_setting(conn, "upnote.body_template")
            or SETTING_DEFAULTS["upnote.body_template"]
        )
        notebook_id = db_module.get_setting(conn, "upnote.notebook_id") or ""

        try:
            ctx = fmt_module.build_week_context(conn, week_iso=payload.week_iso)
            title = fmt_module.render_upnote_title(title_template, ctx)
            text = fmt_module.render_upnote_body(body_template, ctx)
        except Exception as exc:
            db_module.log_action(
                conn, "upnote", payload.week_iso, "fail", str(exc),
            )
            raise HTTPException(400, str(exc)) from exc

        if payload.dry_run:
            return {"title": title, "text": text, "opened": False}

        try:
            upnote_module.open_new_note(
                title=title, text=text, notebook_id=notebook_id
            )
        except Exception as exc:
            db_module.log_action(
                conn, "upnote", payload.week_iso, "fail", str(exc),
            )
            raise HTTPException(500, str(exc)) from exc

        db_module.log_action(
            conn, "upnote", payload.week_iso, "ok",
            f"title={title}",
        )
        return {"title": title, "text": text, "opened": True}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_server.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/server.py tests/test_server.py
git commit -m "feat: add upnote-sync action API with dry-run"
```

---

## Phase 6: Frontend (Tasks 16-20)

### Task 16: Static — API client + 공통 스타일

**Files:**
- Create: `src/angeltime/static/js/api.js`
- Create: `src/angeltime/static/css/main.css`

프론트엔드 변경은 단위 테스트 대상이 아니다. 수동 검증 단계에서 확인한다.

- [ ] **Step 1: api.js 작성**

`src/angeltime/static/js/api.js`:

```javascript
// 모든 API 호출 공통 래퍼.
// 에러는 throw, 성공은 응답 본문(JSON) 반환.

export async function apiGet(path) {
  const r = await fetch(path, { headers: { 'Accept': 'application/json' } });
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function apiPut(path, body) {
  const r = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`PUT ${path} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function apiPost(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${path} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

// ISO 주 계산: 어떤 Date 객체 -> 'YYYY-Www' 문자열.
export function isoWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

// ISO 주 -> 그 주의 월요일 ~ 금요일 날짜 5개 (YYYY-MM-DD).
export function weekDates(weekIso) {
  const [yearStr, wStr] = weekIso.split('-W');
  const year = parseInt(yearStr, 10);
  const week = parseInt(wStr, 10);
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const jan4Day = jan4.getUTCDay() || 7;
  const week1Mon = new Date(jan4);
  week1Mon.setUTCDate(jan4.getUTCDate() - (jan4Day - 1));
  const monday = new Date(week1Mon);
  monday.setUTCDate(week1Mon.getUTCDate() + (week - 1) * 7);
  return Array.from({ length: 5 }, (_, i) => {
    const d = new Date(monday);
    d.setUTCDate(monday.getUTCDate() + i);
    return d.toISOString().slice(0, 10);
  });
}

const DAY_KR = ['월', '화', '수', '목', '금', '토', '일'];
export function formatDateLabel(yyyyMmDd) {
  const [y, m, d] = yyyyMmDd.split('-').map((v) => parseInt(v, 10));
  const date = new Date(Date.UTC(y, m - 1, d));
  const day = (date.getUTCDay() || 7) - 1;
  return `${String(m).padStart(2, '0')}/${String(d).padStart(2, '0')} (${DAY_KR[day]})`;
}

// 디바운스 헬퍼.
export function debounce(fn, ms) {
  let t = null;
  return (...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// 토스트 알림.
export function toast(message, kind = 'ok') {
  const el = document.createElement('div');
  el.className = `toast toast--${kind}`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}
```

- [ ] **Step 2: main.css 작성 (전체 페이지 공통)**

`src/angeltime/static/css/main.css`:

```css
:root {
  --color-bg: #f7f7f9;
  --color-surface: #ffffff;
  --color-border: #e1e4e8;
  --color-text: #1f2328;
  --color-muted: #6e7681;
  --color-accent: #2563eb;
  --color-success: #16a34a;
  --color-warn: #ca8a04;
  --color-danger: #dc2626;
  --radius: 6px;
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
               "Segoe UI", Roboto, sans-serif;
  background: var(--color-bg);
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.5;
}

header {
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  padding: 12px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

header nav a {
  margin-right: 12px;
  color: var(--color-muted);
  text-decoration: none;
  font-weight: 500;
}

header nav a.active { color: var(--color-accent); }

main {
  max-width: 960px;
  margin: 0 auto;
  padding: 20px;
}

button {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  border-radius: var(--radius);
  padding: 8px 14px;
  font-size: 14px;
  cursor: pointer;
}

button.primary {
  background: var(--color-accent);
  color: white;
  border-color: var(--color-accent);
}

input, textarea, select {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 6px 10px;
  font: inherit;
  background: var(--color-surface);
}

textarea {
  resize: vertical;
  min-height: 80px;
  font-family: "SF Mono", Menlo, Consolas, monospace;
}

.day-block {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 12px 16px;
  margin-bottom: 16px;
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  margin-bottom: 8px;
}

.entry {
  border-top: 1px solid var(--color-border);
  padding: 8px 0;
}

.entry-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 4px;
}

.entry-header input.category {
  flex: 1;
}

.entry-header input.hours {
  width: 60px;
  text-align: right;
}

.entry-body {
  width: 100%;
}

.totals {
  font-size: 13px;
  color: var(--color-muted);
}

.totals.ok { color: var(--color-success); }
.totals.warn { color: var(--color-warn); }

.actions-bar {
  position: sticky;
  bottom: 0;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
  padding: 12px 16px;
  display: flex;
  gap: 12px;
  margin-top: 24px;
}

.toast {
  position: fixed;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  background: #1f2328;
  color: white;
  padding: 10px 16px;
  border-radius: var(--radius);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  z-index: 1000;
}

.toast--fail { background: var(--color-danger); }

.week-notes textarea {
  width: 100%;
  min-height: 200px;
}
```

- [ ] **Step 3: Commit**

```bash
git add src/angeltime/static/js/api.js src/angeltime/static/css/main.css
git commit -m "feat: add frontend API client and base styles"
```

---

### Task 17: Static — Main page (week report)

**Files:**
- Replace: `src/angeltime/static/index.html`
- Create: `src/angeltime/static/js/main.js`

- [ ] **Step 1: index.html 작성**

`src/angeltime/static/index.html`:

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>angeltime</title>
  <link rel="stylesheet" href="/static/css/main.css">
</head>
<body>
  <header>
    <nav>
      <a href="/" class="active">📅 보고서</a>
      <a href="/projects.html">🗂 프로젝트</a>
      <a href="/logs.html">📋 로그</a>
      <a href="/settings.html">⚙️ 설정</a>
    </nav>
    <span id="user-label" class="muted"></span>
  </header>
  <main>
    <section class="week-header">
      <button id="prev-week">◀ 이전 주</button>
      <span id="week-label">로딩…</span>
      <button id="this-week">이번 주</button>
      <button id="next-week">다음 주 ▶</button>
    </section>

    <section id="days"></section>

    <section class="week-notes">
      <h3>📝 이번 주 메모 (UpNote 동기화에만 포함)</h3>
      <textarea id="week-note" placeholder="자유 메모…"></textarea>
    </section>

    <section class="actions-bar">
      <span>대상:</span>
      <select id="target">
        <option value="week">이번 주 전체</option>
        <option value="today">오늘만</option>
      </select>
      <button class="primary" id="btn-report">📋 팀장 보고 복사</button>
      <button class="primary" id="btn-timesheet" disabled title="Phase 7 이후 활성">📤 타임시트 입력</button>
      <button class="primary" id="btn-upnote">🔄 UpNote 저장</button>
    </section>
  </main>
  <script type="module" src="/static/js/main.js"></script>
</body>
</html>
```

- [ ] **Step 2: main.js 작성**

`src/angeltime/static/js/main.js`:

```javascript
import {
  apiGet, apiPut, apiPost,
  isoWeek, weekDates, formatDateLabel,
  debounce, toast,
} from './api.js';

let currentWeek = isoWeek(new Date());
let currentData = { days: [], note: '' };

async function loadMe() {
  try {
    const me = await apiGet('/api/me');
    document.getElementById('user-label').textContent = `${me.name}(${me.user_id})`;
  } catch (e) {
    document.getElementById('user-label').textContent = '(로그인 실패)';
  }
}

async function loadWeek() {
  const [weekResp, noteResp] = await Promise.all([
    apiGet(`/api/weeks/${currentWeek}`),
    apiGet(`/api/weeks/${currentWeek}/note`),
  ]);
  currentData = {
    days: weekResp.days,  // [{date, entries}]
    note: noteResp.body_md,
  };
  render();
}

function render() {
  document.getElementById('week-label').textContent = currentWeek;
  const dates = weekDates(currentWeek);
  const byDate = Object.fromEntries(currentData.days.map((d) => [d.date, d]));
  const container = document.getElementById('days');
  container.innerHTML = '';
  for (const date of dates) {
    const day = byDate[date] || { date, entries: [] };
    container.appendChild(renderDay(day));
  }
  document.getElementById('week-note').value = currentData.note;
}

function renderDay(day) {
  const wrap = document.createElement('div');
  wrap.className = 'day-block';
  wrap.dataset.date = day.date;

  const header = document.createElement('div');
  header.className = 'day-header';
  header.innerHTML = `<span>${formatDateLabel(day.date)}</span>`;
  const totals = document.createElement('span');
  totals.className = 'totals';
  header.appendChild(totals);
  wrap.appendChild(header);

  for (const entry of day.entries) {
    wrap.appendChild(renderEntry(entry));
  }

  const addBtn = document.createElement('button');
  addBtn.textContent = '+ 카테고리 추가';
  addBtn.addEventListener('click', () => {
    wrap.insertBefore(renderEntry({ category: '', hours: 0, body_md: '' }), addBtn);
    saveDay(day.date);
  });
  wrap.appendChild(addBtn);

  updateDayTotals(wrap);
  return wrap;
}

function renderEntry(entry) {
  const row = document.createElement('div');
  row.className = 'entry';
  row.innerHTML = `
    <div class="entry-header">
      <input class="category" type="text" placeholder="카테고리"
             value="${escapeHtml(entry.category)}">
      <input class="hours" type="number" min="0" max="24" step="0.5"
             value="${entry.hours}">
      <span>h</span>
      <button class="remove">×</button>
    </div>
    <textarea class="entry-body" placeholder="본문 (markdown)">${escapeHtml(entry.body_md)}</textarea>
  `;
  const date = row.closest('.day-block')?.dataset.date;
  const debounced = debounce(() => {
    const d = row.closest('.day-block')?.dataset.date;
    if (d) { saveDay(d); updateDayTotals(row.closest('.day-block')); }
  }, 600);
  for (const el of row.querySelectorAll('input, textarea')) {
    el.addEventListener('input', debounced);
  }
  row.querySelector('.remove').addEventListener('click', () => {
    const block = row.closest('.day-block');
    row.remove();
    if (block) { saveDay(block.dataset.date); updateDayTotals(block); }
  });
  return row;
}

function escapeHtml(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function collectEntries(block) {
  const out = [];
  for (const row of block.querySelectorAll('.entry')) {
    const category = row.querySelector('.category').value.trim();
    if (!category) continue;
    out.push({
      category,
      hours: parseFloat(row.querySelector('.hours').value || '0'),
      body_md: row.querySelector('.entry-body').value,
    });
  }
  return out;
}

function updateDayTotals(block) {
  const sum = collectEntries(block).reduce((a, e) => a + (e.hours || 0), 0);
  const totals = block.querySelector('.totals');
  totals.textContent = `합계: ${sum}h`;
  totals.classList.remove('ok', 'warn');
  if (sum === 8) totals.classList.add('ok');
  else if (sum === 0 || sum < 8) totals.classList.add('warn');
}

async function saveDay(date) {
  const block = document.querySelector(`.day-block[data-date="${date}"]`);
  if (!block) return;
  const entries = collectEntries(block);
  try {
    await apiPut(`/api/days/${date}`, { week_iso: currentWeek, entries });
  } catch (e) {
    toast(`저장 실패: ${e.message}`, 'fail');
  }
}

async function saveNote() {
  try {
    await apiPut(`/api/weeks/${currentWeek}/note`, {
      body_md: document.getElementById('week-note').value,
    });
  } catch (e) {
    toast(`메모 저장 실패: ${e.message}`, 'fail');
  }
}

document.getElementById('week-note').addEventListener(
  'input', debounce(saveNote, 800)
);

document.getElementById('this-week').addEventListener('click', () => {
  currentWeek = isoWeek(new Date());
  loadWeek();
});
document.getElementById('prev-week').addEventListener('click', () => {
  currentWeek = shiftWeek(currentWeek, -1);
  loadWeek();
});
document.getElementById('next-week').addEventListener('click', () => {
  currentWeek = shiftWeek(currentWeek, +1);
  loadWeek();
});

function shiftWeek(weekIso, delta) {
  const [yearStr, wStr] = weekIso.split('-W');
  const monday = new Date(Date.UTC(parseInt(yearStr, 10), 0, 4));
  const day = monday.getUTCDay() || 7;
  monday.setUTCDate(monday.getUTCDate() - (day - 1) + (parseInt(wStr, 10) - 1 + delta) * 7);
  return isoWeek(monday);
}

document.getElementById('btn-report').addEventListener('click', async () => {
  const target = document.getElementById('target').value;
  try {
    const body = target === 'today'
      ? { date: new Date().toISOString().slice(0, 10) }
      : { week_iso: currentWeek };
    const r = await apiPost('/api/actions/team-report', body);
    await navigator.clipboard.writeText(r.text);
    toast('팀장 보고가 클립보드에 복사되었습니다');
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

document.getElementById('btn-upnote').addEventListener('click', async () => {
  try {
    if (!confirm(`이번 주(${currentWeek}) UpNote 노트를 생성합니다. 같은 주의 기존 노트는 자동 삭제되지 않습니다. 계속하시겠습니까?`)) return;
    await apiPost('/api/actions/upnote-sync', { week_iso: currentWeek });
    toast('UpNote 에 노트가 생성되었습니다');
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

(async () => {
  await loadMe();
  await loadWeek();
})();
```

- [ ] **Step 2: 수동 확인 (Phase 8 의 launcher 가 없으므로 임시로 uvicorn 직접 실행)**

```bash
cd ~/source/timesheet
ANGELNET_USER=youruserid .venv/bin/uvicorn angeltime.server:build_app --factory --reload --port 5174 &
```

브라우저로 `http://127.0.0.1:5174` 접속. 다음 항목 수동 확인:

- 헤더에 사용자 이름 표시
- `+ 카테고리 추가` 버튼으로 항목 추가 가능
- 카테고리/시간/본문 입력 시 600ms 후 자동 저장 (Network 탭에서 PUT 호출 확인)
- 합계 시간이 8h 일 때 녹색, 미만이면 노란색
- 페이지 새로고침 후 입력 내용이 유지됨
- 메모 textarea 에 입력 후 새로고침 → 유지됨
- 이전/다음 주 이동 정상
- `📋 팀장 보고 복사` 클릭 → 클립보드에 사용자 본인 포맷으로 복사됨

(타임시트 / UpNote 동작은 Phase 7 / 7 후 수동 검증)

- [ ] **Step 3: 임시 서버 종료**

```bash
kill %1 2>/dev/null
```

- [ ] **Step 4: Commit**

```bash
git add src/angeltime/static/index.html src/angeltime/static/js/main.js
git commit -m "feat: add main week-report page"
```

---

### Task 18: Static — Projects + Mappings page

**Files:**
- Create: `src/angeltime/static/projects.html`
- Create: `src/angeltime/static/js/projects.js`

- [ ] **Step 1: projects.html 작성**

`src/angeltime/static/projects.html`:

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>프로젝트 / 매핑 — angeltime</title>
  <link rel="stylesheet" href="/static/css/main.css">
</head>
<body>
  <header>
    <nav>
      <a href="/">📅 보고서</a>
      <a href="/projects.html" class="active">🗂 프로젝트</a>
      <a href="/logs.html">📋 로그</a>
      <a href="/settings.html">⚙️ 설정</a>
    </nav>
  </header>
  <main>
    <section>
      <h2>타임시트 프로젝트</h2>
      <div>
        <input id="new-project-name" type="text" placeholder="프로젝트 이름">
        <input id="new-project-remote-id" type="text" placeholder="remote_id (선택)">
        <button class="primary" id="add-project">추가</button>
      </div>
      <ul id="projects-list"></ul>
    </section>

    <section>
      <h2>카테고리 매핑</h2>
      <p class="muted">현재 보고서에 등장한 카테고리 → 타임시트 프로젝트 매핑.</p>
      <table id="mappings-table">
        <thead>
          <tr><th>카테고리</th><th>타임시트 프로젝트</th><th>타임시트 제외</th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </section>
  </main>
  <script type="module" src="/static/js/projects.js"></script>
</body>
</html>
```

- [ ] **Step 2: projects.js 작성**

`src/angeltime/static/js/projects.js`:

```javascript
import { apiGet, apiPost, apiPut, toast } from './api.js';

async function loadProjects() {
  const items = await apiGet('/api/projects');
  const ul = document.getElementById('projects-list');
  ul.innerHTML = '';
  for (const p of items) {
    const li = document.createElement('li');
    li.textContent = p.name + (p.active ? '' : ' (비활성)');
    ul.appendChild(li);
  }
  return items;
}

async function loadMappings(projects) {
  const items = await apiGet('/api/mappings');
  const tbody = document.querySelector('#mappings-table tbody');
  tbody.innerHTML = '';
  const opts = ['<option value="">(미매핑)</option>']
    .concat(projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`))
    .join('');
  for (const m of items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(m.category)}</td>
      <td><select class="project-select">${opts}</select></td>
      <td><input type="checkbox" class="excluded" ${m.excluded ? 'checked' : ''}></td>
    `;
    const sel = tr.querySelector('.project-select');
    if (m.project_id) sel.value = String(m.project_id);
    const exc = tr.querySelector('.excluded');
    const save = async () => {
      try {
        await apiPut(
          `/api/mappings/${encodeURIComponent(m.category)}`,
          {
            project_id: sel.value ? parseInt(sel.value, 10) : null,
            excluded: exc.checked,
          },
        );
        toast('매핑 저장됨');
      } catch (e) {
        toast(`실패: ${e.message}`, 'fail');
      }
    };
    sel.addEventListener('change', save);
    exc.addEventListener('change', save);
    tbody.appendChild(tr);
  }
}

function escapeHtml(s) {
  return String(s ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
}

document.getElementById('add-project').addEventListener('click', async () => {
  const nameInput = document.getElementById('new-project-name');
  const remoteInput = document.getElementById('new-project-remote-id');
  const name = nameInput.value.trim();
  const remote_id = remoteInput.value.trim() || null;
  if (!name) return;
  try {
    await apiPost('/api/projects', { name, remote_id });
    nameInput.value = '';
    remoteInput.value = '';
    const ps = await loadProjects();
    await loadMappings(ps);
    toast(`프로젝트 추가됨: ${name}`);
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});

(async () => {
  const ps = await loadProjects();
  await loadMappings(ps);
})();
```

- [ ] **Step 3: Commit**

```bash
git add src/angeltime/static/projects.html src/angeltime/static/js/projects.js
git commit -m "feat: add projects/mappings management page"
```

---

### Task 19: Static — Settings page (템플릿 편집)

**Files:**
- Create: `src/angeltime/static/settings.html`
- Create: `src/angeltime/static/js/settings.js`

- [ ] **Step 1: settings.html 작성**

`src/angeltime/static/settings.html`:

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>설정 — angeltime</title>
  <link rel="stylesheet" href="/static/css/main.css">
</head>
<body>
  <header>
    <nav>
      <a href="/">📅 보고서</a>
      <a href="/projects.html">🗂 프로젝트</a>
      <a href="/logs.html">📋 로그</a>
      <a href="/settings.html" class="active">⚙️ 설정</a>
    </nav>
  </header>
  <main>
    <section>
      <h2>UpNote</h2>
      <label>노트북 UUID
        <input id="notebook-id" type="text" placeholder="0889cff8-...">
      </label>
      <p class="muted">UpNote 사이드바에서 노트북 우클릭 → 링크 복사 → URL 의 notebookId 값.</p>
    </section>

    <section>
      <h2>출력 템플릿</h2>
      <p class="muted">Jinja2 문법. <code>{{ entry.category }}</code>, <code>{{ entry.body }}</code>, <code>{{ yy }}</code>, <code>{{ ww }}</code>, <code>{{ days }}</code>, <code>{{ week_notes }}</code> 등.</p>

      <h3>팀장 보고</h3>
      <textarea id="t-team-report" rows="10"></textarea>
      <div>
        <button data-preview="team_report">미리보기</button>
        <button data-reset="team_report.template">기본값 복원</button>
      </div>
      <pre id="preview-team-report" class="muted"></pre>

      <h3>UpNote 제목</h3>
      <textarea id="t-upnote-title" rows="2"></textarea>
      <div>
        <button data-preview="upnote_title">미리보기</button>
        <button data-reset="upnote.title_template">기본값 복원</button>
      </div>
      <pre id="preview-upnote-title" class="muted"></pre>

      <h3>UpNote 본문</h3>
      <textarea id="t-upnote-body" rows="20"></textarea>
      <div>
        <button data-preview="upnote_body">미리보기</button>
        <button data-reset="upnote.body_template">기본값 복원</button>
      </div>
      <pre id="preview-upnote-body" class="muted"></pre>
    </section>

    <section class="actions-bar">
      <button class="primary" id="save">저장</button>
    </section>
  </main>
  <script type="module" src="/static/js/settings.js"></script>
</body>
</html>
```

- [ ] **Step 2: settings.js 작성**

`src/angeltime/static/js/settings.js`:

```javascript
import { apiGet, apiPut, apiPost, isoWeek, toast } from './api.js';

const KEYS = {
  'notebook-id': 'upnote.notebook_id',
  't-team-report': 'team_report.template',
  't-upnote-title': 'upnote.title_template',
  't-upnote-body': 'upnote.body_template',
};

let defaults = {};

async function load() {
  const s = await apiGet('/api/settings');
  defaults = { ...s };
  for (const [elId, key] of Object.entries(KEYS)) {
    document.getElementById(elId).value = s[key] ?? '';
  }
}

document.getElementById('save').addEventListener('click', async () => {
  const payload = {};
  for (const [elId, key] of Object.entries(KEYS)) {
    payload[key] = document.getElementById(elId).value;
  }
  try {
    await apiPut('/api/settings', payload);
    toast('저장됨');
  } catch (e) {
    toast(`저장 실패: ${e.message}`, 'fail');
  }
});

for (const btn of document.querySelectorAll('button[data-preview]')) {
  btn.addEventListener('click', async () => {
    const kind = btn.dataset.preview;
    const elId = kind === 'team_report'
      ? 't-team-report'
      : kind === 'upnote_title' ? 't-upnote-title' : 't-upnote-body';
    const template = document.getElementById(elId).value;
    const previewEl = document.getElementById(
      kind === 'team_report' ? 'preview-team-report'
        : kind === 'upnote_title' ? 'preview-upnote-title'
          : 'preview-upnote-body',
    );
    try {
      const body = { kind, template, week_iso: isoWeek(new Date()) };
      if (kind === 'team_report') body.week_iso = isoWeek(new Date());
      const r = await apiPost('/api/settings/preview', body);
      previewEl.textContent = r.text;
    } catch (e) {
      previewEl.textContent = `[ERROR] ${e.message}`;
    }
  });
}

for (const btn of document.querySelectorAll('button[data-reset]')) {
  btn.addEventListener('click', () => {
    const key = btn.dataset.reset;
    const elId = Object.entries(KEYS).find(([, k]) => k === key)[0];
    document.getElementById(elId).value = defaults[key] ?? '';
    toast('기본값으로 복원 (저장 버튼을 눌러 적용)');
  });
});

load();
```

- [ ] **Step 3: 수동 확인**

브라우저에서 `/settings.html` 접속 후:
- 4개 입력란이 기본값으로 채워짐
- 팀장 보고 미리보기 클릭 → 현재 주 데이터로 렌더 결과 표시
- 잘못된 Jinja2 (예: `{% bogus %}`) 입력 후 저장 → 에러 토스트
- 기본값 복원 클릭 → 텍스트가 default 로 돌아옴

- [ ] **Step 4: Commit**

```bash
git add src/angeltime/static/settings.html src/angeltime/static/js/settings.js
git commit -m "feat: add settings page with template editing and preview"
```

---

### Task 20: Static — Logs page + cleanup on startup

**Files:**
- Create: `src/angeltime/static/logs.html`
- Create: `src/angeltime/static/js/logs.js`
- Modify: `src/angeltime/server.py` (lifespan 에 cleanup 호출 추가)

- [ ] **Step 1: logs.html 작성**

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>로그 — angeltime</title>
  <link rel="stylesheet" href="/static/css/main.css">
</head>
<body>
  <header>
    <nav>
      <a href="/">📅 보고서</a>
      <a href="/projects.html">🗂 프로젝트</a>
      <a href="/logs.html" class="active">📋 로그</a>
      <a href="/settings.html">⚙️ 설정</a>
    </nav>
  </header>
  <main>
    <h2>최근 동작 로그 (90일)</h2>
    <table>
      <thead>
        <tr>
          <th>시각</th><th>종류</th><th>대상</th><th>상태</th><th>메시지</th>
        </tr>
      </thead>
      <tbody id="logs-tbody"></tbody>
    </table>
  </main>
  <script type="module" src="/static/js/logs.js"></script>
</body>
</html>
```

- [ ] **Step 2: logs.js 작성**

```javascript
import { apiGet } from './api.js';

async function load() {
  const items = await apiGet('/api/logs');
  const tbody = document.getElementById('logs-tbody');
  tbody.innerHTML = '';
  for (const log of items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${log.created_at}</td>
      <td>${log.action_type}</td>
      <td>${log.target_range}</td>
      <td>${log.status === 'ok' ? '✓' : '✗'}</td>
      <td>${log.message ?? ''}</td>
    `;
    tbody.appendChild(tr);
  }
}

load();
```

- [ ] **Step 3: server.py lifespan 에 cleanup 추가**

`build_app` 의 lifespan 안, `conn = db_module.connect(...)` 다음 줄, `app.dependency_overrides[get_conn] = lambda: conn` 다음 줄에:

```python
        # 시작 시 90일 이전 로그 정리
        deleted = db_module.cleanup_action_logs(conn, days=90)
        if deleted:
            logger.info("Cleaned up %d old action_log rows", deleted)
```

위치는 skip_lifespan_login=False 분기 안. 테스트 모드에서는 호출되지 않는다.

- [ ] **Step 4: Commit**

```bash
git add src/angeltime/static/logs.html src/angeltime/static/js/logs.js src/angeltime/server.py
git commit -m "feat: add logs page and startup cleanup"
```

---

## Phase 7: Timesheet API discovery + integration (Tasks 21-23)

### Task 21: 타임시트 jobtime API DevTools 캡처 (사용자 수동 작업)

**Files:**
- Modify: `docs/superpowers/specs/2026-05-12-angeltime-design.md` (부록 추가)

이 task 는 코드 작성이 아니라 **사용자가 직접 수행하는 수동 작업** 이다. 결과를 spec 문서에 부록으로 기록한 뒤 Task 22 로 진행한다.

- [ ] **Step 1: Chrome 또는 Edge 로 timesheet.uangel.com 접속**

```
URL: https://timesheet.uangel.com/times/timesheet/jobtime/create.htm
```

ANGELNET_USER / 패스워드로 로그인.

- [ ] **Step 2: DevTools 열기 (Cmd+Option+I) → Network 탭 → Preserve log 체크**

- [ ] **Step 3: 페이지가 완전히 로드된 후 다음 호출을 캡처**

(a) **프로젝트 드롭다운 로드 호출**: 페이지 로드 시 자동 발생하는 GET 또는 POST. URL 패스에 `project`, `job`, `wbs` 등이 들어가는 호출.

(b) **저장(submit) 호출**: 폼에 1회 정상 입력 후 "저장" 클릭. 발생하는 XHR/Fetch 요청.

각 호출에 대해 다음을 메모:
- Request URL
- Method
- Request Headers (특히 `Content-Type`, `X-Requested-With`)
- Request Payload (Form Data 인지 JSON 인지, 정확한 키 이름과 값)
- Response Body (구조 + 성공/실패 마커)

- [ ] **Step 4: 결과를 spec 문서 부록으로 추가**

`docs/superpowers/specs/2026-05-12-angeltime-design.md` 끝에 추가:

```markdown
## 부록 A: Timesheet jobtime API 캡처 (2026-05-XX 수행)

### A.1 프로젝트 목록 조회

- URL: `https://timesheet.uangel.com/times/...` (실제 캡처 URL)
- Method: GET / POST
- Headers: ...
- Payload: ...
- Response 예시:
  ```json
  [{"projectId": "...", "projectName": "..."}]
  ```

### A.2 jobtime 저장

- URL: `https://timesheet.uangel.com/times/...`
- Method: POST
- Content-Type: application/json or application/x-www-form-urlencoded
- Payload 예시:
  ```json
  {
    "date": "2026-05-12",
    "projectId": "...",
    "hours": 4,
    "description": "..."
  }
  ```
- Response 성공 시: `{"success": true, ...}`
- Response 실패 시: 4xx/5xx 또는 `{"success": false, "message": "..."}`
```

- [ ] **Step 5: Commit spec 갱신**

```bash
git add docs/superpowers/specs/2026-05-12-angeltime-design.md
git commit -m "docs: capture jobtime API endpoints from DevTools"
```

---

### Task 22: client.py — jobtime API 메서드 (search.json + save.json)

Task 21 에서 발견한 실제 API 구조를 client 에 반영. 핵심:

- **search.json**: 그 달의 task 목록 + 일별 시간 매트릭스 조회 (form POST, dhtmlxGrid JSON 응답)
- **save.json**: 일괄 저장 — `rows` form field 에 JSON array 문자열, **응답은 text/plain** (`"error:"` prefix 가 실패 마커)

자세한 페이로드 명세는 spec 부록 A 참조.

**Files:**
- Modify: `src/angeltime/client.py`
- Modify: `tests/test_client.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_client.py` 뒤에 추가:

```python
import json as _json

import respx

JOBTIME_SEARCH_URL = "https://timesheet.uangel.com/times/timesheet/jobtime/search.json"
JOBTIME_SAVE_URL = "https://timesheet.uangel.com/times/timesheet/jobtime/save.json"


@respx.mock
async def test_list_jobtime_tasks_returns_named_tasks(
    client: TimesheetClient,
) -> None:
    """search.json 응답을 task_id/name/work_type 로 정규화한다."""
    respx.post(JOBTIME_SEARCH_URL).mock(
        return_value=httpx.Response(200, json={
            "rows": [
                {"id": "11113", "data": ["KT 2026년 LTE 구축", "개발", "0", "0", "0"]},
                {"id": "11114", "data": ["EM 고도화", "개발", "0", "0", "0"]},
            ],
        })
    )
    tasks = await client.list_jobtime_tasks(year_month="2026-05")
    await client.close()
    assert {t["name"] for t in tasks} == {"KT 2026년 LTE 구축", "EM 고도화"}
    assert all("task_id" in t and "work_type" in t for t in tasks)


@respx.mock
async def test_list_jobtime_tasks_filters_subtotal_rows(
    client: TimesheetClient,
) -> None:
    """id 가 음수인 합계/소계 행은 제외된다."""
    respx.post(JOBTIME_SEARCH_URL).mock(
        return_value=httpx.Response(200, json={
            "rows": [
                {"id": "11113", "data": ["X", "개발", "0"]},
                {"id": "-1000", "data": ["", "소계", "0"]},
                {"id": "-2000", "data": ["", "월합계", "0"]},
            ],
        })
    )
    tasks = await client.list_jobtime_tasks(year_month="2026-05")
    await client.close()
    assert [t["task_id"] for t in tasks] == ["11113"]


@respx.mock
async def test_submit_jobtimes_sends_form_encoded_rows(
    client: TimesheetClient,
) -> None:
    """save.json 은 form-encoded 의 rows 키에 JSON array 문자열을 담는다."""
    route = respx.post(JOBTIME_SAVE_URL).mock(
        return_value=httpx.Response(200, text="OK")
    )
    rows = [
        {"task_id": "11113", "work_hour": 4,
         "work_day": "20260512", "user_id": "alice"},
    ]
    result = await client.submit_jobtimes(rows)
    await client.close()
    assert "OK" in result
    # request body 확인
    req = route.calls[0].request
    body = req.content.decode()
    assert body.startswith("rows=")
    decoded = body[len("rows="):]
    from urllib.parse import unquote_plus
    parsed = _json.loads(unquote_plus(decoded))
    assert parsed == rows


@respx.mock
async def test_submit_jobtimes_error_prefix_raises_api_error(
    client: TimesheetClient,
) -> None:
    """응답이 'error:' 로 시작하면 ApiError 로 변환된다."""
    respx.post(JOBTIME_SAVE_URL).mock(
        return_value=httpx.Response(200, text="error:duplicate entry")
    )
    with pytest.raises(ApiError) as exc:
        await client.submit_jobtimes([{
            "task_id": "11113", "work_hour": 4,
            "work_day": "20260512", "user_id": "alice",
        }])
    await client.close()
    assert "duplicate entry" in str(exc.value)


@respx.mock
async def test_submit_jobtimes_4xx_raises(client: TimesheetClient) -> None:
    respx.post(JOBTIME_SAVE_URL).mock(
        return_value=httpx.Response(500, text="server error")
    )
    with pytest.raises(ApiError):
        await client.submit_jobtimes([{
            "task_id": "11113", "work_hour": 4,
            "work_day": "20260512", "user_id": "alice",
        }])
    await client.close()
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_client.py -v -k "jobtime"
```

기대: `AttributeError: 'TimesheetClient' object has no attribute 'list_jobtime_tasks'`

- [ ] **Step 3: client.py 에 메서드 추가**

`TimesheetClient` 클래스 안 (`# ─── jobtime API (Phase 7 에서 추가) ───` 주석 위치) 에 추가:

```python
    # ─── 타임시트 jobtime API ──────────────────────
    # spec 부록 A 참조. 시스템은 task × 날짜 매트릭스 모델.

    JOBTIME_SEARCH_URL = (
        "https://timesheet.uangel.com/times/timesheet/jobtime/search.json"
    )
    JOBTIME_SAVE_URL = (
        "https://timesheet.uangel.com/times/timesheet/jobtime/save.json"
    )

    async def list_jobtime_tasks(
        self, *, year_month: str, dept_code: str = ""
    ) -> list[dict[str, str]]:
        """그 달의 task 목록 조회 (search.json).

        Args:
            year_month: 'YYYY-MM' 형식.
            dept_code: 일반적으로 빈 문자열 — 서버가 세션의 user 로 결정.

        Returns:
            [{"task_id": "11113", "name": "...", "work_type": "개발"}, ...]
            합계/소계 행 (id 가 음수 또는 이름 비어있음) 은 제외.
        """
        resp = await self._http.post(
            self.JOBTIME_SEARCH_URL,
            data={"dept_code": dept_code, "year_month": year_month},
        )
        body = self._safe_json(resp, exc_type=ApiError)
        if _is_bot_blocked(body):
            raise BotBlockedError(str(body))
        if resp.status_code >= 400:
            raise ApiError(
                f"list_jobtime_tasks failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        rows = body.get("rows", []) if isinstance(body, dict) else []
        out: list[dict[str, str]] = []
        for r in rows:
            rid = str(r.get("id", ""))
            try:
                if int(rid) < 0:
                    continue
            except ValueError:
                continue
            data = r.get("data", [])
            if len(data) < 2:
                continue
            name = (data[0] or "").strip()
            if not name:
                continue
            out.append({
                "task_id": rid,
                "name": name,
                "work_type": (data[1] or "").strip(),
            })
        return out

    async def submit_jobtimes(self, rows: list[dict[str, Any]]) -> str:
        """jobtime 일괄 저장 (save.json).

        Args:
            rows: 각 element 는
                {"task_id": str, "work_hour": int|float,
                 "work_day": "YYYYMMDD", "user_id": str}.

        Returns:
            성공 시 응답 본문 (text).

        Raises:
            ApiError: 응답이 'error:' 로 시작하거나 4xx/5xx.
            BotBlockedError: 자동화 차단.
        """
        import json as _json

        resp = await self._http.post(
            self.JOBTIME_SAVE_URL,
            data={"rows": _json.dumps(rows, ensure_ascii=False)},
        )
        if resp.status_code >= 400:
            raise ApiError(
                f"submit_jobtimes failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=resp.text[:500],
            )
        text = resp.text
        # bot block 메시지가 text 로 올 가능성도 검사
        if BOT_BLOCK_MARKER in text:
            raise BotBlockedError(text[:300])
        if text.lstrip().startswith("error:"):
            msg = text.split(":", 1)[1].strip() if ":" in text else "save error"
            raise ApiError(f"jobtime save failed: {msg}", payload=text[:500])
        return text
```

이미 client.py 상단에 `from typing import Any` 가 있어야 한다. 없으면 추가.

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_client.py -v
```

기대: 모든 테스트 통과 (jobtime 테스트 5개 포함)

- [ ] **Step 5: Commit**

```bash
git add src/angeltime/client.py tests/test_client.py
git commit -m "feat: add jobtime search/save API based on real capture"
```

---

### Task 23: server.py — Action: timesheet-submit + UI 연결

핵심 흐름 (spec 부록 A 참조):

1. 대상 entries 수집 (일/주)
2. 각 entry 의 카테고리 → 매핑 → `projects.remote_id` (= task 정식 이름)
3. 매핑 누락 / excluded / remote_id 비어있음 분류 — dry_run 으로 미리보기, 실제 호출은 차단
4. 필요한 월별로 `client.list_jobtime_tasks(year_month=...)` 호출 → 이름 → task_id 맵
5. task 이름이 시스템에 등록 안 된 경우 `task_not_registered` 로 표시 (회사 페이지에서 먼저 추가 필요)
6. 등록된 항목으로 save 페이로드 빌드: `[{task_id, work_hour, work_day=YYYYMMDD, user_id}, ...]`
7. `client.submit_jobtimes(rows)` 한 번 호출로 일괄 저장

**Files:**
- Modify: `src/angeltime/server.py`
- Modify: `tests/test_server.py`
- Modify: `src/angeltime/static/js/main.js`
- Modify: `src/angeltime/static/index.html`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_server.py`:

```python
from unittest.mock import AsyncMock


def _setup_mapped_entry(
    api, *, category: str, task_name: str | None, hours: float = 4
):
    """헬퍼: 카테고리 → 프로젝트 → 매핑 일괄 셋업 + entry 등록."""
    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W19",
        "entries": [{"category": category, "hours": hours, "body_md": "x"}],
    })
    if task_name is not None:
        pid = api.post("/api/projects", json={
            "name": category + " (project)", "remote_id": task_name,
        }).json()["id"]
        api.put(f"/api/mappings/{category}",
                json={"project_id": pid, "excluded": False})


def test_timesheet_dry_run_classifies_items(api):
    """ready / missing_mapping / excluded 3가지 상태로 분류한다."""
    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W19",
        "entries": [
            {"category": "X", "hours": 4, "body_md": "x"},
            {"category": "Unmapped", "hours": 4, "body_md": ""},
            {"category": "Skip", "hours": 0, "body_md": ""},
        ],
    })
    pid = api.post("/api/projects", json={
        "name": "P-X", "remote_id": "EM 고도화",
    }).json()["id"]
    api.put("/api/mappings/X", json={"project_id": pid, "excluded": False})
    api.put("/api/mappings/Skip", json={"project_id": None, "excluded": True})

    r = api.post(
        "/api/actions/timesheet-submit",
        json={"date": "2026-05-12", "dry_run": True},
    )
    assert r.status_code == 200
    statuses = {it["category"]: it["status"] for it in r.json()["items"]}
    assert statuses == {"X": "ready", "Unmapped": "missing_mapping",
                        "Skip": "excluded"}


def test_timesheet_dry_run_does_not_call_remote(api, mock_client):
    """dry_run 은 list_jobtime_tasks / submit_jobtimes 를 호출하지 않는다."""
    mock_client.list_jobtime_tasks = AsyncMock(side_effect=AssertionError("no!"))
    mock_client.submit_jobtimes = AsyncMock(side_effect=AssertionError("no!"))
    _setup_mapped_entry(api, category="X", task_name="EM 고도화")
    r = api.post(
        "/api/actions/timesheet-submit",
        json={"date": "2026-05-12", "dry_run": True},
    )
    assert r.status_code == 200


def test_timesheet_actual_submit_calls_search_then_save(api, mock_client):
    """실제 호출은 search → save 순으로 1회씩 호출."""
    mock_client.user_id = "alice"
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "11113", "name": "EM 고도화", "work_type": "개발"},
    ])
    mock_client.submit_jobtimes = AsyncMock(return_value="OK")

    _setup_mapped_entry(api, category="X", task_name="EM 고도화")

    r = api.post(
        "/api/actions/timesheet-submit",
        json={"date": "2026-05-12", "dry_run": False},
    )
    assert r.status_code == 200, r.text
    mock_client.list_jobtime_tasks.assert_awaited_once_with(year_month="2026-05")
    mock_client.submit_jobtimes.assert_awaited_once()
    rows = mock_client.submit_jobtimes.await_args[0][0]
    assert rows == [{
        "task_id": "11113", "work_hour": 4,
        "work_day": "20260512", "user_id": "alice",
    }]


def test_timesheet_blocks_when_mapping_missing(api):
    """매핑 누락 항목이 있으면 실제 호출은 400."""
    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W19",
        "entries": [{"category": "Unmapped", "hours": 4, "body_md": ""}],
    })
    r = api.post(
        "/api/actions/timesheet-submit",
        json={"date": "2026-05-12", "dry_run": False},
    )
    assert r.status_code == 400
    assert "missing" in r.json()["detail"].lower()


def test_timesheet_task_not_registered_blocks_save(api, mock_client):
    """매핑은 있지만 search 결과에 task 가 없으면 save 호출 없이 400."""
    mock_client.user_id = "alice"
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "999", "name": "다른 task", "work_type": "개발"},
    ])
    mock_client.submit_jobtimes = AsyncMock(
        side_effect=AssertionError("should not be called")
    )

    _setup_mapped_entry(api, category="X", task_name="없는 task 이름")

    r = api.post(
        "/api/actions/timesheet-submit",
        json={"date": "2026-05-12", "dry_run": False},
    )
    assert r.status_code == 400
    assert "task" in r.json()["detail"].lower()


def test_timesheet_week_range_aggregates_months(api, mock_client):
    """주 단위 입력 시 그 주가 걸친 모든 달의 search 호출."""
    mock_client.user_id = "alice"
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "11113", "name": "EM 고도화", "work_type": "개발"},
    ])
    mock_client.submit_jobtimes = AsyncMock(return_value="OK")

    pid = api.post("/api/projects", json={
        "name": "P", "remote_id": "EM 고도화",
    }).json()["id"]
    api.put("/api/mappings/X", json={"project_id": pid, "excluded": False})
    api.put("/api/days/2026-04-30", json={
        "week_iso": "2026-W18",
        "entries": [{"category": "X", "hours": 4, "body_md": ""}],
    })
    api.put("/api/days/2026-05-01", json={
        "week_iso": "2026-W18",
        "entries": [{"category": "X", "hours": 4, "body_md": ""}],
    })

    r = api.post(
        "/api/actions/timesheet-submit",
        json={"week_iso": "2026-W18", "dry_run": False},
    )
    assert r.status_code == 200
    # 두 달에 걸친 entries 라서 list_jobtime_tasks 가 2회 호출됨
    calls = mock_client.list_jobtime_tasks.await_args_list
    months = {c.kwargs.get("year_month") for c in calls}
    assert months == {"2026-04", "2026-05"}
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
.venv/bin/pytest tests/test_server.py -v -k "timesheet"
```

- [ ] **Step 3: server.py 에 라우트 추가**

```python
    class TimesheetSubmitInput(BaseModel):
        date: str | None = None
        week_iso: str | None = None
        dry_run: bool = False

    @app.post("/api/actions/timesheet-submit")
    async def action_timesheet_submit(
        payload: TimesheetSubmitInput,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> dict:
        from fastapi import HTTPException

        if not (payload.date or payload.week_iso):
            raise HTTPException(400, "date or week_iso required")

        # 1) 대상 entries 수집
        if payload.date:
            day = db_module.get_day(conn, payload.date)
            rows = [{**e, "date": payload.date} for e in day["entries"]]
            target_range = payload.date
        else:
            week = db_module.get_week(conn, payload.week_iso)
            rows = []
            for d in week:
                for e in d["entries"]:
                    rows.append({**e, "date": d["date"]})
            target_range = payload.week_iso

        # 2) 매핑 분류
        items: list[dict] = []
        ready: list[dict] = []
        missing_categories: list[str] = []
        for e in rows:
            m = db_module.get_mapping(conn, e["category"])
            if m is None or (m["project_id"] is None and not m["excluded"]):
                items.append({**e, "status": "missing_mapping",
                              "project_name": None, "task_name": None})
                missing_categories.append(e["category"])
                continue
            if m["excluded"]:
                items.append({**e, "status": "excluded",
                              "project_name": None, "task_name": None})
                continue
            project = conn.execute(
                "SELECT name, remote_id FROM projects WHERE id = ?",
                (m["project_id"],),
            ).fetchone()
            task_name = (
                (project["remote_id"] or "").strip() if project else ""
            )
            if not task_name:
                items.append({**e, "status": "missing_remote_id",
                              "project_name": m["project_name"],
                              "task_name": None})
                missing_categories.append(e["category"])
                continue
            items.append({**e, "status": "ready",
                          "project_name": m["project_name"],
                          "task_name": task_name})
            ready.append({**e, "task_name": task_name})

        if payload.dry_run:
            return {"items": items, "missing": missing_categories}

        if missing_categories:
            raise HTTPException(
                400, f"missing mappings: {', '.join(missing_categories)}"
            )
        if not ready:
            return {"items": items, "results": [], "missing": []}

        # 3) 필요한 월별 search.json 호출 → name → task_id 맵
        months = sorted({e["date"][:7] for e in ready})
        task_id_by_month: dict[str, dict[str, str]] = {}
        for ym in months:
            try:
                tasks = await client.list_jobtime_tasks(year_month=ym)
            except Exception as exc:
                db_module.log_action(
                    conn, "timesheet", target_range, "fail",
                    f"list_jobtime_tasks({ym}): {exc}",
                )
                raise HTTPException(500, f"task 목록 조회 실패: {exc}") from exc
            task_id_by_month[ym] = {t["name"]: t["task_id"] for t in tasks}

        # 4) save 페이로드 빌드 (task 미등록은 분류)
        save_rows: list[dict] = []
        unregistered: list[str] = []
        for e in ready:
            ym = e["date"][:7]
            tid = task_id_by_month.get(ym, {}).get(e["task_name"])
            if not tid:
                unregistered.append(e["task_name"])
                continue
            save_rows.append({
                "task_id": tid,
                "work_hour": e["hours"],
                "work_day": e["date"].replace("-", ""),  # YYYYMMDD
                "user_id": client.user_id,
            })

        if unregistered:
            uniq = sorted(set(unregistered))
            db_module.log_action(
                conn, "timesheet", target_range, "fail",
                f"unregistered tasks: {', '.join(uniq)}",
            )
            raise HTTPException(
                400,
                f"타임시트에 미등록된 task: {', '.join(uniq)}. "
                "회사 페이지에서 먼저 task 를 추가하세요.",
            )

        if not save_rows:
            return {"items": items, "results": [], "missing": []}

        # 5) save.json 일괄 호출
        try:
            await client.submit_jobtimes(save_rows)
        except Exception as exc:
            db_module.log_action(
                conn, "timesheet", target_range, "fail", str(exc),
            )
            raise HTTPException(500, str(exc)) from exc

        db_module.log_action(
            conn, "timesheet", target_range, "ok",
            f"{len(save_rows)} rows",
        )
        return {
            "items": items,
            "results": [{**e, "status": "ok"} for e in ready],
            "missing": [],
        }
```

또한 `create_project_route` 가 `payload.remote_id` 도 함께 저장하는지 확인 (Task 12 의 코드에 이미 포함됨):

```python
        pid = db_module.create_project(
            conn, name=payload.name, remote_id=payload.remote_id
        )
```

추가로 Task 12 의 projects 페이지가 remote_id 도 받도록 이미 Task 18 에서 수정함. 확인.

- [ ] **Step 4: main.js 에 타임시트 버튼 활성화 + 흐름 추가**

`src/angeltime/static/index.html` 에서 `btn-timesheet` 의 `disabled title="Phase 7 이후 활성"` 부분을 제거.

`src/angeltime/static/js/main.js` 에 핸들러 추가:

```javascript
document.getElementById('btn-timesheet').addEventListener('click', async () => {
  const target = document.getElementById('target').value;
  const body = target === 'today'
    ? { date: new Date().toISOString().slice(0, 10), dry_run: true }
    : { week_iso: currentWeek, dry_run: true };
  try {
    const preview = await apiPost('/api/actions/timesheet-submit', body);
    const summary = preview.items.map(
      (it) => `${it.date} [${it.status}] ${it.category} ${it.hours}h`
        + (it.project_name ? ` → ${it.project_name}` : '')
        + (it.task_name ? ` (task: ${it.task_name})` : ''),
    ).join('\n');
    if (preview.missing && preview.missing.length) {
      toast(`매핑 누락: ${preview.missing.join(', ')}`, 'fail');
      console.warn('preview:', preview);
      return;
    }
    if (!confirm(`다음 항목을 타임시트에 입력합니다:\n\n${summary}\n\n계속?`)) return;
    const real = await apiPost('/api/actions/timesheet-submit',
      { ...body, dry_run: false });
    toast(`타임시트 입력 완료 (${(real.results || []).length}건)`);
  } catch (e) {
    toast(`실패: ${e.message}`, 'fail');
  }
});
```

응답 status 가 4xx 일 때 apiPost 는 throw 하므로 task 미등록/매핑 누락 같은 케이스는 catch 블록의 toast 가 사용자에게 알린다.

- [ ] **Step 5: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_server.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/angeltime/server.py tests/test_server.py src/angeltime/static/js/main.js src/angeltime/static/index.html
git commit -m "feat: add timesheet-submit action and UI flow"
```

---

## Phase 8: Launcher + 종합 검증 (Tasks 24-25)

### Task 24: `time` launcher + __main__.py

**Files:**
- Create: `src/angeltime/__main__.py`
- Create: `time` (실행 권한)

- [ ] **Step 1: __main__.py 작성**

`src/angeltime/__main__.py`:

```python
"""CLI 진입점: argparse → 패스워드 확보 → uvicorn 실행."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys

import uvicorn

from .auth import KeychainStore
from .server import build_app

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"  # 외부 노출 안 함
DEFAULT_PORT = 5174


def _ensure_password(user_id: str) -> str:
    """패스워드를 Keychain → env → prompt 순으로 확보."""
    keychain = KeychainStore(account=user_id)
    if pwd := keychain.get():
        logger.info("Loaded password from keychain (service=%s)", keychain.service)
        return pwd
    if pwd := os.environ.get("ANGELNET_PWD"):
        logger.info("Loaded password from env, persisting to keychain")
        keychain.save(pwd)
        return pwd
    pwd = getpass.getpass(f"AngelNet password for {user_id}: ")
    if not pwd:
        raise SystemExit("Password is required")
    keychain.save(pwd)
    print(f"Password saved to Keychain (service={keychain.service}).", file=sys.stderr)
    return pwd


def main() -> None:
    parser = argparse.ArgumentParser(description="angeltime 서버")
    parser.add_argument(
        "--user",
        default=os.environ.get("ANGELNET_USER"),
        help="사용자 ID (또는 환경변수 ANGELNET_USER)",
    )
    parser.add_argument("--host", default=os.environ.get("ANGELTIME_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port", type=int,
        default=int(os.environ.get("ANGELTIME_PORT", DEFAULT_PORT)),
    )
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    if not args.user:
        raise SystemExit(
            "사용자 ID 가 필요합니다. ANGELNET_USER 를 설정하거나 --user 옵션."
        )

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    pwd = _ensure_password(args.user)
    os.environ["ANGELNET_PWD"] = pwd  # build_app 의 lifespan 이 읽어감

    app = build_app(user_id=args.user)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: `time` launcher 작성**

`/Users/sondaegon/source/timesheet/time` (executable):

```bash
#!/bin/bash
set -euo pipefail

# angeltime launcher
# venv 활성화 → 백그라운드 기동 → 헬스체크 → 브라우저 자동 열기
# ⚠️ macOS 빌트인 'time' 과 동명이므로 항상 './time' 으로 명시 실행하거나
#    alias angeltime=~/source/timesheet/time 로 노출하라.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -z "${ANGELNET_USER:-}" ]]; then
    echo "Error: ANGELNET_USER 환경변수가 필요합니다." >&2
    echo "       예: export ANGELNET_USER=youruserid" >&2
    exit 1
fi

VENV="$SCRIPT_DIR/.venv"
HOST="${ANGELTIME_HOST:-127.0.0.1}"
PORT="${ANGELTIME_PORT:-5174}"
URL="http://127.0.0.1:${PORT}"
LOG_FILE="$SCRIPT_DIR/.angeltime.log"

if [[ ! -d "$VENV" ]]; then
    echo "Error: .venv 가 없습니다. 'python3 -m venv .venv && .venv/bin/pip install -e \".[dev]\"' 먼저 실행." >&2
    exit 1
fi

source "$VENV/bin/activate"

python -m angeltime --user "$ANGELNET_USER" --host "$HOST" --port "$PORT" \
    > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

cleanup() {
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "Stopping server (pid=$SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# 헬스체크 (최대 15초; lifespan 의 login 호출 때문에 angelnet 보다 약간 길게)
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if curl -sf "${URL}/api/me" > /dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "Error: server died during startup." >&2
        cat "$LOG_FILE" >&2
        exit 1
    fi
    sleep 1
done

if ! curl -sf "${URL}/api/me" > /dev/null 2>&1; then
    echo "Error: server health check failed after 15s." >&2
    tail -50 "$LOG_FILE" >&2
    exit 1
fi

echo "Server ready at $URL (pid=$SERVER_PID, log=$LOG_FILE)"
echo "Press Ctrl+C to stop."
open "$URL"
wait "$SERVER_PID"
```

- [ ] **Step 3: 실행 권한 + commit**

```bash
chmod +x time
git add src/angeltime/__main__.py time
git commit -m "feat: add CLI entry point and ./time launcher"
```

---

### Task 25: 수동 검증 + 최종 정리

**Files:**
- (수정 없음. 검증만)

- [ ] **Step 1: 전체 테스트 실행**

```bash
cd ~/source/timesheet
.venv/bin/pytest -v
```

기대: 모든 테스트 통과. 실패 있으면 그 모듈을 다시 확인.

- [ ] **Step 2: 린트 + 포맷 확인**

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

지적 사항 있으면 수정 후 한 번 더 실행.

- [ ] **Step 3: 실제 서버 기동 + 첫 실행 검증 체크리스트 수행**

```bash
export ANGELNET_USER=youruserid
./time
```

spec section 13 의 첫 실행 검증 체크리스트 수행:

```
[ ] ANGELNET_USER 환경변수 설정 후 ./time 실행 시 패스워드 prompt 또는 Keychain 자동 로드
[ ] 브라우저가 http://127.0.0.1:5174 으로 자동 열림
[ ] 헤더에 사용자 이름 표시
[ ] 빈 주차에 카테고리 추가 / 시간 입력 / 본문 입력이 정상 autosave
[ ] 📝 메모 textarea 에 자유 입력 후 다른 주로 이동했다 돌아와도 내용이 유지됨
[ ] /projects 에서 타임시트 프로젝트 등록 가능 (이름 + remote_id)
[ ] /projects 에서 카테고리 → 프로젝트 매핑 가능
[ ] /settings 에서 UpNote notebook UUID 입력 후 저장됨
[ ] /settings 에서 출력 템플릿 3종 편집 → 미리보기 정상 → 저장 후 동작에 반영됨
[ ] 잘못된 Jinja2 syntax 입력 시 저장이 거부되고 에러 토스트 표시
[ ] [기본값으로 복원] 클릭 시 default 템플릿으로 되돌아옴
[ ] [📋 팀장 보고 복사] 클릭 시 클립보드에 정확한 포맷으로 복사됨
[ ] [🔄 UpNote 저장] 클릭 시 UpNote 앱에 새 노트가 생성됨
[ ] 메모가 빈 주를 UpNote 동기화하면 구분선과 📝 헤더가 출력되지 않음
[ ] 같은 주를 두 번 동기화하면 새 노트가 추가됨
[ ] [📤 타임시트 입력] 클릭 시 미리보기 모달 표시 → 확인 후 실제 입력 성공
[ ] /logs 에 동작 이력 기록됨
[ ] Ctrl+C 로 서버 깔끔하게 종료됨
```

각 항목을 직접 확인 후 체크. 실패 있으면 해당 항목을 디버깅.

- [ ] **Step 4: README 마지막 정비 + 최종 commit**

```bash
git add -A
git status   # 변경 없는지 확인
```

깨끗하게 모든 변경이 commit 되어 있어야 한다.

```bash
git log --oneline | head
```

각 commit 이 한 단위 작업을 잘 반영하는지 확인.

---

## Self-review notes

스펙 커버리지 매핑:

| Spec 섹션 | 구현 Task |
|---|---|
| 4 아키텍처 | Task 10 (server skeleton), 17 (frontend) |
| 5 데이터 모델 | Task 5 (db.py) |
| 6.1 입력 모델 | Task 4 (models), 11 (CRUD) |
| 6.2 팀장 보고 (템플릿) | Task 6 (templates), 7 (formatter), 14 (action) |
| 6.3 UpNote 출력 (템플릿) | Task 6, 7, 15 (action) |
| 6.4 출력 템플릿 시스템 | Task 7 (sandbox), 13 (settings preview), 19 (settings UI) |
| 7.1 Timesheet REST | Task 9 (login), 21 (캡처), 22 (jobtime methods), 23 (action) |
| 7.2 UpNote x-callback-url | Task 8 (adapter) |
| 7.3 팀장 보고 클립보드 | Task 14 (action), 17 (clipboard JS) |
| 8 UI | Task 17, 18, 19, 20 |
| 9 디렉토리 구조 | Task 1 |
| 10 보안 | Task 3 (Keychain), 9 (verify=False, secret 미로그), 24 (HOST=127.0.0.1) |
| 11 에러 처리 | Task 2 (예외 계층) |
| 12 테스트 전략 | 각 Phase 의 TDD |
| 13 검증 체크리스트 | Task 25 |
| 14 단계적 구현 순서 | 본 plan 전체 |
| 15 angelnet 통합 경로 | Task 3 (KEYCHAIN_SERVICE 공유), 9 (코드 패턴 일치) |
