# AngelDash — 사내 통합 대시보드

> Internal-network unified dashboard. Single-port local web app combining
> meeting room reservations and daily-report/timesheet/UpNote workflows.
> Credentials in macOS Keychain. Spring REST against `timesheet.uangel.com`.

---

# AngelDash — 사내 통합 대시보드

회의실 예약(구 angelnet) + 일일 업무 보고/타임시트/UpNote 분배(구 angeltime) 를
하나의 1인용 로컬 웹 대시보드로 통합. 단일 포트 (5173), 단일 상단 nav.

**참고:** 2026-05 AngelNet 시스템이 Boan PHP/GraphQL 에서 Spring Java REST 로 전면 마이그레이션됨. 이 도구는 새 Spring API (`https://timesheet.uangel.com/times/...`) 만 호출한다.

## 페이지

| 경로 | 기능 |
|---|---|
| `/` | 🗓 회의실 — 예약 현황 그리드 / 등록 / 취소 |
| `/reports.html` | 📅 보고서 — 주간 일일보고 입력, 팀장 보고/UpNote 동기화 |
| `/projects.html` | 🗂 프로젝트 — 회사 프로젝트 검색/가입, 카테고리/패턴 매핑 |
| `/logs.html` | 📋 로그 — UpNote/타임시트/팀장보고 액션 이력 |
| `/settings.html` | ⚙️ 설정 — 출력 템플릿, UpNote 노트북, 자동 '기타' 문구 등 |

## 요구사항

- macOS (Keychain `security` CLI 사용)
- Python 3.11+
- 사내 네트워크 또는 VPN 으로 `timesheet.uangel.com` 접근 가능 (Spring REST). archive/ 의 bash 스크립트는 `boan.uangel.com` 도 필요했으나 현재 도구는 사용하지 않음
- AngelNet 계정. **환경변수 `ANGELNET_USER` 로 사용자 ID 지정** (예: `export ANGELNET_USER=youruserid`)

## 설치

```bash
cd /path/to/angelnet
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 실행

```bash
export ANGELNET_USER=youruserid   # 첫 실행 전 1회 (~/.zshrc 등에 영구 저장 권장)
./angel
```

처음 실행 시 패스워드를 한 번 입력하면 macOS Keychain (`service=angeldash`) 에
저장되고, 이후 실행에서는 자동으로 로드된다.

브라우저가 자동으로 `http://127.0.0.1:5173` 을 연다. Ctrl+C 로 종료.

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `ANGELNET_USER` | (없음, 필수) | AngelNet 사용자 ID |
| `ANGELNET_PWD` | (없음) | 패스워드 (있으면 Keychain 보다 우선) |
| `ANGELDASH_HOST` | `127.0.0.1` | 서버 바인딩 호스트 (로컬 전용). 사내 다른 사람도 접근시키려면 `0.0.0.0` |
| `ANGELDASH_PORT` | `5173` | 서버 포트 |

## 보안

- 서버는 기본 `0.0.0.0` 으로 모든 인터페이스에 listen — **외부(사내 네트워크) 접근 허용**.
  로컬 전용으로 회귀하려면 `export ANGELDASH_HOST=127.0.0.1`
- ⚠️ 외부에서 접속하는 사람은 **호스트 본인의 AngelNet 권한** 으로 예약/조회/삭제 가능.
  공용 와이파이/공유기·VPN 미접속 환경에서 노출하지 말 것
- 패스워드는 Keychain 또는 환경변수로만 보관, 코드/로그에 평문 출력 없음
- HTTPS 인증서 검증은 비활성(기존 bash 동작과 동일). 운영 환경 인증서가 적절히 갱신되면
  `client.py` 의 `verify=False` 를 제거할 것 (TODO)

### macOS 방화벽

기본적으로 macOS 방화벽이 켜져 있으면 첫 `./angel` 실행 시 시스템 대화상자
"Python.app 이 들어오는 네트워크 연결을 수락하시겠습니까?" 가 한 번 뜬다. **허용** 을
누르면 그 다음부터 자동으로 외부 접근 가능.

방화벽이 꺼져 있거나 이미 허용한 경우 별도 작업 불필요. 수동 확인:

```bash
# 방화벽 상태
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# 들어오는 연결 허용 (필요한 경우)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add "$(which python3)"
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp "$(which python3)"
```

### 외부 접근 URL

`./angel` 실행 시 출력되는 `External access: http://<IP>:5173` 의 IP 로 동일
네트워크 사용자가 접속 가능. IP 가 비어 있으면 `ipconfig getifaddr en0` (Wi-Fi)
또는 `ipconfig getifaddr en1` (이더넷) 으로 직접 확인.

## 개발

```bash
# 테스트
.venv/bin/pytest -v

# Lint / Format
.venv/bin/ruff check src tests
.venv/bin/ruff format src tests
```

## 트러블슈팅

| 증상 | 원인/대처 |
|---|---|
| `bot_blocked` 토스트 | 서버가 자동화 호출로 차단. 5분 후 재시도, 잦으면 호출 빈도 점검 |
| `auth` 401 | 패스워드 변경됨. Keychain Access 앱에서 angeldash 항목 삭제 후 재실행 |
| `api` 401 in POST/DELETE /api/reservations | Timesheet 세션 만료 또는 서버 측 권한 변경. 프로세스 재시작으로 신선한 로그인 |
| `boan` 또는 `php` 관련 메시지 | 기존 시스템 흔적. archive/ 의 bash 만 영향. 새 대시보드는 Spring REST 로 동작 |

## 면책 / Disclaimer

이 도구는 특정 회사 사내 시스템 (`timesheet.uangel.com`) 의 회의실 예약 API 를
호출하도록 만들어졌다. 외부 환경에서는 동작하지 않는다. 회의실 데이터
(`src/angeldash/rooms.py`) 는 본인 환경의 실제 회의실 ID 와 이름으로 직접
작성해야 한다 — `rooms.example.py` 를 복사해서 사용하라.

This tool targets a specific company's internal reservation system. It will not
work outside that network. You must populate `src/angeldash/rooms.py` with your
own room mappings (copy from `rooms.example.py`).

## 통합 수동 검증 (첫 실행)

`./angel` 직접 실행 후 다음을 체크:

- [ ] 패스워드 prompt 또는 자동 로드 (Keychain) 정상
- [ ] 브라우저가 `http://127.0.0.1:5173` 으로 자동 열림
- [ ] 헤더에 사용자 이름이 `Your Name(youruserid)` 으로 표시됨
- [ ] 8층 회의실 6개가 컬럼으로 표시됨
- [ ] 오늘 날짜 예약 블록이 시간대 위치에 정확히 그려짐
- [ ] 빈 셀 hover 시 강조됨
- [ ] 빈 셀 클릭 → 예약 모달 열림 (취소 시 정상 닫힘)
- [ ] 타인 예약 클릭 → 상세 모달 (삭제 버튼 없음)
- [ ] 본인 예약 클릭 → 상세 + 삭제 버튼
- [ ] 날짜 prev/next 버튼이 그리드 + 내 예약 리스트 모두 갱신
- [ ] 층 드롭다운 변경 시 그리드 재렌더
- [ ] Ctrl+C 시 서버가 깔끔하게 종료됨

⚠️ **실제 예약 생성/삭제는 본인 회의실로 1회만 검증**:
- [ ] 본인 회의실 빈 셀 클릭 → 예약 생성 → 토스트 "예약 완료" → 그리드에 본인 색상으로 표시
- [ ] 방금 만든 예약 클릭 → 삭제 → 토스트 "삭제 완료" → 그리드에서 사라짐
