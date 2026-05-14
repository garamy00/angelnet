"""TimesheetClient 의 login 만 우선 검증.

httpx 호출은 respx 로 mock 한다.
"""

from __future__ import annotations

import json as _json

import httpx
import pytest
import respx

from angeldash.timesheet.client import (
    SPRING_BASE,
    TS_LOGIN,
    TimesheetClient,
)
from angeldash._common.errors import ApiError, AuthError, BotBlockedError

JOBTIME_SEARCH_URL = "https://timesheet.uangel.com/times/timesheet/jobtime/search.json"
JOBTIME_SAVE_URL = "https://timesheet.uangel.com/times/timesheet/jobtime/save.json"
VACATION_SEARCH_URL = (
    "https://timesheet.uangel.com/times/timesheet/jobtime/vacationSearch.json"
)


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


@respx.mock
async def test_list_jobtime_tasks_returns_named_tasks(
    client: TimesheetClient,
) -> None:
    """search.json 응답을 task_id/name/work_type 로 정규화한다."""
    respx.post(JOBTIME_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {
                        "id": "11113",
                        "data": ["KT 2026년 LTE 구축", "개발", "0", "0", "0"],
                    },
                    {"id": "11114", "data": ["EM 고도화", "개발", "0", "0", "0"]},
                ],
            },
        )
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
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {"id": "11113", "data": ["X", "개발", "0"]},
                    {"id": "-1000", "data": ["", "소계", "0"]},
                    {"id": "-2000", "data": ["", "월합계", "0"]},
                ],
            },
        )
    )
    tasks = await client.list_jobtime_tasks(year_month="2026-05")
    await client.close()
    assert [t["task_id"] for t in tasks] == ["11113"]


@respx.mock
async def test_fetch_jobtime_grid_detailed_auto_detects_text_columns(
    client: TimesheetClient,
) -> None:
    """텍스트 컬럼이 1~3개 가변이어도 첫 숫자 셀까지 자동 감지해 메타로 모은다."""
    respx.post(JOBTIME_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    # 2-column row (이전 형식): name + work_type
                    {"id": "11113", "data": ["OAM 개선", "개발",
                                              "8", "0", "0", "8"]},
                    # 3-column row (사용자 케이스): root + dept + leaf
                    {"id": "11114", "data": ["행정, 공통개발업무",
                                              "행정, 공통 개발",
                                              "세미나",
                                              "0", "2", "0", "2"]},
                    # 1-column row (단순 task)
                    {"id": "11115", "data": ["단순 task", "4", "4"]},
                ],
            },
        )
    )
    rows = await client.fetch_jobtime_grid_detailed(year_month="2026-05")
    await client.close()

    by_root = {r["task_name"]: r for r in rows}
    # 2-column: label = 'OAM 개선 [개발]'
    assert by_root["OAM 개선"]["label"] == "OAM 개선 [개발]"
    assert by_root["OAM 개선"]["work_type"] == "개발"
    # 3-column: label 의 work_type 자리에 leaf(세미나) 가 들어감 (dept 가 아님)
    assert by_root["행정, 공통개발업무"]["label"] == "행정, 공통개발업무 [세미나]"
    assert by_root["행정, 공통개발업무"]["work_type"] == "세미나"
    # 1-column: brackets 없음
    assert by_root["단순 task"]["label"] == "단순 task"
    assert by_root["단순 task"]["work_type"] == ""


@respx.mock
async def test_fetch_jobtime_grid_detailed_handles_all_zero_row(
    client: TimesheetClient,
) -> None:
    """일별 시간이 모두 0 인 row 도 정상 반환 (0-filter 는 호출자 책임)."""
    respx.post(JOBTIME_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {"id": "11113", "data": ["빈 task", "개발",
                                              "0", "0", "0", "0"]},
                ],
            },
        )
    )
    rows = await client.fetch_jobtime_grid_detailed(year_month="2026-05")
    await client.close()
    assert len(rows) == 1
    assert rows[0]["days"] == {}  # 모든 hours 가 0 이라 day_hours 비어있음
    assert rows[0]["label"] == "빈 task [개발]"


@respx.mock
async def test_fetch_jobtime_grid_detailed_skips_empty_first_text(
    client: TimesheetClient,
) -> None:
    """data[0] 이 빈 문자열인 row (합계/소계 등) 는 결과에서 제외."""
    respx.post(JOBTIME_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {"id": "11113", "data": ["정상 task", "개발",
                                              "4", "0", "4"]},
                    {"id": "11114", "data": ["", "월합계", "4", "0", "4"]},
                ],
            },
        )
    )
    rows = await client.fetch_jobtime_grid_detailed(year_month="2026-05")
    await client.close()
    names = [r["task_name"] for r in rows]
    assert names == ["정상 task"]  # 빈 텍스트 prefix row 는 skip


@respx.mock
async def test_submit_jobtimes_sends_form_encoded_rows(
    client: TimesheetClient,
) -> None:
    """save.json 은 form-encoded 의 rows 키에 JSON array 문자열을 담는다."""
    route = respx.post(JOBTIME_SAVE_URL).mock(
        return_value=httpx.Response(200, text="OK")
    )
    rows = [
        {
            "task_id": "11113",
            "work_hour": 4,
            "work_day": "20260512",
            "user_id": "alice",
        },
    ]
    result = await client.submit_jobtimes(rows)
    await client.close()
    assert "OK" in result
    # request body 확인
    req = route.calls[0].request
    body = req.content.decode()
    assert body.startswith("rows=")
    decoded = body[len("rows=") :]
    from urllib.parse import unquote_plus

    parsed = _json.loads(unquote_plus(decoded))
    assert parsed == rows


@respx.mock
async def test_submit_jobtimes_error_prefix_raises_api_error(
    client: TimesheetClient,
) -> None:
    """응답이 'error:' 로 시작하면 ApiError 로 변환된다."""
    from angeldash._common.errors import ApiError

    respx.post(JOBTIME_SAVE_URL).mock(
        return_value=httpx.Response(200, text="error:duplicate entry")
    )
    with pytest.raises(ApiError) as exc:
        await client.submit_jobtimes(
            [
                {
                    "task_id": "11113",
                    "work_hour": 4,
                    "work_day": "20260512",
                    "user_id": "alice",
                }
            ]
        )
    await client.close()
    assert "duplicate entry" in str(exc.value)


@respx.mock
async def test_submit_jobtimes_4xx_raises(client: TimesheetClient) -> None:
    from angeldash._common.errors import ApiError

    respx.post(JOBTIME_SAVE_URL).mock(
        return_value=httpx.Response(500, text="server error")
    )
    with pytest.raises(ApiError):
        await client.submit_jobtimes(
            [
                {
                    "task_id": "11113",
                    "work_hour": 4,
                    "work_day": "20260512",
                    "user_id": "alice",
                }
            ]
        )
    await client.close()


@respx.mock
async def test_list_vacations_parses_grid(client: TimesheetClient) -> None:
    """vacationSearch.json 의 dhtmlxGrid 응답을 (date, type, hours) 로 변환."""
    respx.post(VACATION_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    # 1409 = 연차. 5/4 = 8h, 마지막은 합계.
                    {
                        "id": "1409",
                        "data": ["연차"] + ["0"] * 3 + ["8"] + ["0"] * 27 + ["8"],
                    },
                    # 2145 = 반차(오후). 5/15 = 4h.
                    {
                        "id": "2145",
                        "data": ["반차(오후)"]
                        + ["0"] * 14
                        + ["4"]
                        + ["0"] * 16
                        + ["4"],
                    },
                    # 비어있는 종류는 결과에 안 나옴
                    {"id": "927", "data": ["공가"] + ["0"] * 31 + ["0"]},
                ],
            },
        )
    )
    items = await client.list_vacations(year_month="2026-05")
    await client.close()
    assert items == [
        {"date": "2026-05-04", "type": "연차", "hours": 8.0},
        {"date": "2026-05-15", "type": "반차(오후)", "hours": 4.0},
    ]


@respx.mock
async def test_fetch_jobtime_grid_parses_matrix(client: TimesheetClient) -> None:
    """실제 jobtime grid 응답: data = [task_name, work_type, 1일, 2일, ..., 말일, 월합계].

    work_type 컬럼 (data[1]) 을 day 1 로 잘못 읽으면 모든 day 가 1씩 shift 되어
    잘못된 비교 결과를 만든다. 회귀 방지 테스트.
    """
    respx.post(JOBTIME_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    # work_type="개발" + 5/4=8h, 5/12=4h, 월합계=12
                    {
                        "id": "11113",
                        "data": ["EM 고도화", "개발"]
                        + ["0"] * 3
                        + ["8"]
                        + ["0"] * 7
                        + ["4"]
                        + ["0"] * 19
                        + ["12"],
                    },
                    # 빈 task (work_type 만)
                    {"id": "11114", "data": ["다른", "개발"] + ["0"] * 31 + ["0"]},
                    # 합계 행
                    {"id": "-1000", "data": ["", "소계"] + ["0"] * 31 + ["0"]},
                ],
            },
        )
    )
    grid = await client.fetch_jobtime_grid(year_month="2026-05")
    await client.close()
    # work_type 컬럼을 건너뛰고 정확한 일자에 매핑되어야 한다
    assert grid["EM 고도화"] == {4: 8.0, 12: 4.0}
    assert grid.get("다른") == {}
    assert "" not in grid  # 합계 행 제외


@respx.mock
async def test_download_jobtime_excel_returns_bytes_and_filename(
    client: TimesheetClient,
) -> None:
    """excelbyday.json 응답을 (bytes, filename) 으로 정규화한다."""
    EXCEL_URL = "https://timesheet.uangel.com/times/timesheet/jobtime/excelbyday.json"
    # XLSX magic + dummy zip content
    xlsx_body = b"PK\x03\x04" + b"\x00" * 200
    respx.post(EXCEL_URL).mock(
        return_value=httpx.Response(
            200,
            content=xlsx_body,
            headers={
                "content-type": "application/octet-stream;charset=UTF-8",
                "content-disposition": (
                    "attachment;filename="
                    '"%EC%9E%91%EC%97%85%EC%8B%9C%EA%B0%84_%EB%A6%AC%ED%8F%AC%ED%8A%B8%282026-05%29.xlsx";'
                ),
            },
        )
    )
    body, filename = await client.download_jobtime_excel(year_month="2026-05")
    await client.close()
    assert body == xlsx_body
    assert filename == "작업시간_리포트(2026-05).xlsx"


@respx.mock
async def test_download_jobtime_excel_rejects_non_xlsx_response(
    client: TimesheetClient,
) -> None:
    """XLSX magic 이 아니면 ApiError."""
    from angeldash._common.errors import ApiError

    EXCEL_URL = "https://timesheet.uangel.com/times/timesheet/jobtime/excelbyday.json"
    respx.post(EXCEL_URL).mock(
        return_value=httpx.Response(
            200,
            content=b"<html>error</html>",
        )
    )
    with pytest.raises(ApiError):
        await client.download_jobtime_excel(year_month="2026-05")
    await client.close()


@respx.mock
async def test_list_vacations_handles_short_month(client: TimesheetClient) -> None:
    """4월 데이터의 31일 자리 → ValueError 로 자동 skip (그 달에 31일 없음)."""
    respx.post(VACATION_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    # 4월은 30일까지. 31일째 자리에 8 이 있어도 무시.
                    {"id": "1409", "data": ["연차"] + ["0"] * 30 + ["8"] + ["8"]},
                ],
            },
        )
    )
    items = await client.list_vacations(year_month="2026-04")
    await client.close()
    assert items == []  # 31일은 4월에 없으므로 skip


HOLIDAY_TAG_SEARCH_URL = (
    "https://timesheet.uangel.com/times/timesheet/jobtime/holidayTagSearch.json"
)

JOIN_PAGE_URL = "https://timesheet.uangel.com/times/timesheet/join/searchForm.htm"
JOIN_SEARCH_URL = "https://timesheet.uangel.com/times/timesheet/join/search.json"
JOIN_USER_MAP_SAVE_URL = (
    "https://timesheet.uangel.com/times/timesheet/join/UserMapJoinSave.json"
)


_JOIN_PAGE_HTML = """
<html><body>
<input type="hidden" name="user_id" id="user_id" value="alice"/>
<input type="hidden" name="position" value="J002006"/>
<input type="hidden" name="status" id="status" value="C002001">
<input type="hidden" id="dept_code" name="dept_code" value="DADABF">
<input type="hidden" id="group_id" name="group_id" value="USER">
</body></html>
"""


@respx.mock
async def test_search_joinable_projects_normalizes_rows(
    client: TimesheetClient,
) -> None:
    """실제 응답은 페이징 wrapper 안에 dhtmlxgrid {rows:[...]} 가 한 번 더 감싸진 구조.

    data[0] 이 정수일 수도 있고, data[3] 이 가입 여부.
    """
    respx.get(JOIN_PAGE_URL).mock(
        return_value=httpx.Response(200, text=_JOIN_PAGE_HTML)
    )
    respx.post(JOIN_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "pageSize": 50,
                "page": 1,
                "totalCount": 2,
                "rows": {  # 이중 wrapper
                    "rows": [
                        # data[0] 정수, data[3] 가입, data[4] status code
                        {
                            "id": "0",
                            "data": [
                                2074,
                                "yGHTRp2503",
                                "2025 김해경전철 LTE-R 구축",
                                "1",
                                "C002001",
                            ],
                        },
                        {
                            "id": "1",
                            "data": [
                                2184,
                                "nIIEVg2604",
                                "26년 IITP Evolved SBA 핵심기술개발",
                                "0",
                                "C002001",
                            ],
                        },
                    ],
                },
            },
        )
    )
    res = await client.search_joinable_projects(keyword="LTE")
    await client.close()
    assert res["total"] == 2
    assert res["rows"][0] == {
        "project_id": "2074",
        "code": "yGHTRp2503",
        "name": "2025 김해경전철 LTE-R 구축",
        "joined": True,
    }
    assert res["rows"][1]["joined"] is False


@respx.mock
async def test_join_project_sends_C002001(
    client: TimesheetClient,
) -> None:
    respx.get(JOIN_PAGE_URL).mock(
        return_value=httpx.Response(200, text=_JOIN_PAGE_HTML)
    )
    route = respx.post(JOIN_USER_MAP_SAVE_URL).mock(
        return_value=httpx.Response(200, text="success")
    )
    await client.join_project(project_id="2184")
    await client.close()
    body = route.calls[0].request.content.decode()
    assert body.startswith("rows=")
    from urllib.parse import unquote_plus
    import json as _json

    payload = _json.loads(unquote_plus(body[len("rows=") :]))
    assert payload == [
        {
            "project_id": "2184",
            "user_id": "alice",
            "status": "C002001",
        }
    ]


JOIN_TASKS_SEARCH_URL = (
    "https://timesheet.uangel.com/times/timesheet/join/tasks_search.json"
)
JOIN_TASKS_SAVE_URL = (
    "https://timesheet.uangel.com/times/timesheet/join/tasksMapJoinSave.json"
)


@respx.mock
async def test_list_project_tasks_normalizes(client: TimesheetClient) -> None:
    respx.get(JOIN_PAGE_URL).mock(
        return_value=httpx.Response(200, text=_JOIN_PAGE_HTML)
    )
    respx.post(JOIN_TASKS_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {"id": "0", "data": [11132, "시험/지원", 0]},
                    {"id": "1", "data": [11131, "개발", 1]},
                    {"id": "2", "data": [11130, "영업", 0]},
                ],
            },
        )
    )
    tasks = await client.list_project_tasks(project_id="2160")
    await client.close()
    assert {t["name"] for t in tasks} == {"시험/지원", "개발", "영업"}
    by_name = {t["name"]: t for t in tasks}
    assert by_name["개발"]["joined"] is True
    assert by_name["시험/지원"]["joined"] is False


@respx.mock
async def test_set_project_task_joined_sends_correct_row(
    client: TimesheetClient,
) -> None:
    respx.get(JOIN_PAGE_URL).mock(
        return_value=httpx.Response(200, text=_JOIN_PAGE_HTML)
    )
    route = respx.post(JOIN_TASKS_SAVE_URL).mock(
        return_value=httpx.Response(200, text="success")
    )
    await client.set_project_task_joined(project_id="2160", task_id="11131")
    await client.close()
    from urllib.parse import unquote_plus
    import json as _json

    body = route.calls[0].request.content.decode()
    payload = _json.loads(unquote_plus(body[len("rows=") :]))
    assert payload == [
        {
            "task_id": "11131",
            "user_id": "alice",
            "project_id": "2160",
            "status": "C0000001",
        }
    ]


JOIN_TASKS_DEL_ALL_URL = (
    "https://timesheet.uangel.com/times/timesheet/join/tasksMapDelAll.htm"
)


@respx.mock
async def test_unjoin_project_cascade_with_joined_task(
    client: TimesheetClient,
) -> None:
    """가입 task 가 있으면 tasksMapDelAll 만 호출 (임시 가입 불필요)."""
    respx.get(JOIN_PAGE_URL).mock(
        return_value=httpx.Response(200, text=_JOIN_PAGE_HTML)
    )
    respx.post(JOIN_TASKS_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {"id": "0", "data": [11132, "시험/지원", 0]},
                    {"id": "1", "data": [11131, "개발", 1]},
                ],
            },
        )
    )
    save_route = respx.post(JOIN_TASKS_SAVE_URL).mock(
        return_value=httpx.Response(200, text="success")
    )
    del_route = respx.post(JOIN_TASKS_DEL_ALL_URL).mock(
        return_value=httpx.Response(200, json={"result": 1, "success": True})
    )
    await client.unjoin_project(project_id="2160")
    await client.close()
    assert save_route.called is False  # 이미 가입된 task 있음
    assert del_route.called is True
    body = del_route.calls[0].request.content.decode()
    assert "user_id=alice" in body
    assert "project_id=2160" in body


@respx.mock
async def test_unjoin_project_cascade_no_joined_task(
    client: TimesheetClient,
) -> None:
    """가입 task 가 0개면 임시 task 1개 가입 → tasksMapDelAll cascade."""
    respx.get(JOIN_PAGE_URL).mock(
        return_value=httpx.Response(200, text=_JOIN_PAGE_HTML)
    )
    respx.post(JOIN_TASKS_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {"id": "0", "data": [11132, "시험/지원", 0]},
                    {"id": "1", "data": [11131, "개발", 0]},
                ],
            },
        )
    )
    save_route = respx.post(JOIN_TASKS_SAVE_URL).mock(
        return_value=httpx.Response(200, text="success")
    )
    del_route = respx.post(JOIN_TASKS_DEL_ALL_URL).mock(
        return_value=httpx.Response(200, json={"result": 1, "success": True})
    )
    await client.unjoin_project(project_id="2160")
    await client.close()
    assert save_route.called is True
    assert del_route.called is True
    from urllib.parse import unquote_plus
    import json as _json

    body = save_route.calls[0].request.content.decode()
    payload = _json.loads(unquote_plus(body[len("rows=") :]))
    # 첫 task 를 임시 가입 (C0000001)
    assert payload == [
        {
            "task_id": "11132",
            "user_id": "alice",
            "project_id": "2160",
            "status": "C0000001",
        }
    ]


@respx.mock
async def test_unjoin_project_raises_when_no_tasks(
    client: TimesheetClient,
) -> None:
    """프로젝트에 task 자체가 없으면 cascade 불가 → 명시적 에러."""
    respx.get(JOIN_PAGE_URL).mock(
        return_value=httpx.Response(200, text=_JOIN_PAGE_HTML)
    )
    respx.post(JOIN_TASKS_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [],
            },
        )
    )
    with pytest.raises(ApiError, match="no tasks"):
        await client.unjoin_project(project_id="2160")
    await client.close()


@respx.mock
async def test_unjoin_project_raises_when_server_rejects(
    client: TimesheetClient,
) -> None:
    """tasksMapDelAll 이 success=false 반환하면 에러."""
    respx.get(JOIN_PAGE_URL).mock(
        return_value=httpx.Response(200, text=_JOIN_PAGE_HTML)
    )
    respx.post(JOIN_TASKS_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [{"id": "0", "data": [11131, "개발", 1]}],
            },
        )
    )
    respx.post(JOIN_TASKS_DEL_ALL_URL).mock(
        return_value=httpx.Response(200, json={"result": 0, "success": False})
    )
    with pytest.raises(ApiError, match="server rejected"):
        await client.unjoin_project(project_id="2160")
    await client.close()


@respx.mock
async def test_list_holidays_parses_days(client: TimesheetClient) -> None:
    """holidayTagSearch.json 응답을 (date, label, types) 로 정규화."""
    respx.post(HOLIDAY_TAG_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "days": {
                    "20260501": {
                        "label": "노동절",
                        "labels": ["노동절"],
                        "types": ["public"],
                        "locked": True,
                    },
                    "20260505": {"label": "어린이날", "types": ["public"]},
                    "invalid": {"label": "skipped"},  # 잘못된 키 → skip
                },
            },
        )
    )
    items = await client.list_holidays(year_month="2026-05")
    await client.close()
    assert {(it["date"], it["label"]) for it in items} == {
        ("2026-05-01", "노동절"),
        ("2026-05-05", "어린이날"),
    }


# ─── 휴가계 조회 ─────────────────────────────────────────

VACATION_ANNUAL_URL = (
    "https://timesheet.uangel.com/times/application/vacation/getAnnualVacation.json"
)
VACATION_APP_SEARCH_URL = (
    "https://timesheet.uangel.com/times/application/vacation/search.htm"
)


@respx.mock
async def test_get_annual_vacation_summary_parses_quoted_url_encoded(
    client: TimesheetClient,
) -> None:
    """서버 응답 '"23.0+-+9.0+%3D+14.0+%EC%9D%BC"' → total/used/remaining."""
    respx.get(VACATION_ANNUAL_URL).mock(
        return_value=httpx.Response(
            200,
            text='"23.0+-+9.0+%3D+14.0+%EC%9D%BC"',
        )
    )
    r = await client.get_annual_vacation_summary(year=2026)
    await client.close()
    assert r["total"] == 23.0
    assert r["used"] == 9.0
    assert r["remaining"] == 14.0


@respx.mock
async def test_get_annual_vacation_summary_handles_unparseable(
    client: TimesheetClient,
) -> None:
    """예상 형식이 아니면 raw_text 만 채워 반환, total=None."""
    respx.get(VACATION_ANNUAL_URL).mock(
        return_value=httpx.Response(200, text='"-- 데이터 없음 --"'),
    )
    r = await client.get_annual_vacation_summary(year=2026)
    await client.close()
    assert r["total"] is None
    assert "데이터" in r["raw_text"]


_VACATION_SAMPLE_HTML = """
<html><body>
<table id="list">
<thead><tr><th>기안일</th></tr></thead>
<tbody>
<tr><td>2025-12-23</td><td>연차</td><td>&nbsp;&nbsp;징검다리</td>
    <td>2026-12-31 ~ 2026-12-31</td><td>1.0 일</td>
    <td>2025-12-23</td><td>손대곤</td><td>품의완료</td>
    <td><button onclick="goSubmit('detail','35115','detail');">조회</button></td></tr>
<tr><td>2026-05-11</td><td>반차(오후)</td><td>개인 사유</td>
    <td>2026-05-15 ~ 2026-05-15</td><td>0.5 일</td>
    <td>2026-05-11</td><td>손대곤</td><td>품의완료</td>
    <td><button onclick="goSubmit('detail','36425','detail');">조회</button></td></tr>
</tbody>
</table>
</body></html>
"""


@respx.mock
async def test_list_vacation_applications_parses_table(
    client: TimesheetClient,
) -> None:
    """search.htm HTML 응답에서 9컬럼 + vacation_id 추출."""
    respx.post(VACATION_APP_SEARCH_URL).mock(
        return_value=httpx.Response(200, text=_VACATION_SAMPLE_HTML),
    )
    rows = await client.list_vacation_applications(year=2026)
    await client.close()
    assert len(rows) == 2

    r0 = rows[0]
    assert r0["draft_date"] == "2025-12-23"
    assert r0["vacation_type"] == "연차"
    assert r0["from_date"] == "2026-12-31"
    assert r0["to_date"] == "2026-12-31"
    assert r0["days"] == "1.0 일"
    assert r0["status"] == "품의완료"
    assert r0["vacation_id"] == "35115"
    # &nbsp; 는 공백으로 정규화돼 잡힘
    assert "징검다리" in r0["reason"]

    r1 = rows[1]
    assert r1["vacation_type"] == "반차(오후)"
    assert r1["vacation_id"] == "36425"


@respx.mock
async def test_list_vacation_applications_empty_table(
    client: TimesheetClient,
) -> None:
    """결과가 없으면 빈 리스트."""
    html = '<table id="list"><thead><tr><th>X</th></tr></thead><tbody></tbody></table>'
    respx.post(VACATION_APP_SEARCH_URL).mock(
        return_value=httpx.Response(200, text=html),
    )
    rows = await client.list_vacation_applications(year=2026)
    await client.close()
    assert rows == []
