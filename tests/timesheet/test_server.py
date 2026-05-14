"""FastAPI 서버 라우트 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock


def test_me_returns_logged_in_user(api):
    r = api.get("/api/me")
    assert r.status_code == 200
    body = r.json()
    # 통합 User 모델은 email optional 포함. 핵심 필드만 검증.
    assert body["user_id"] == "alice"
    assert body["name"] == "앨리스"


def test_static_index_html_served(api):
    r = api.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_vacation_page_served(api):
    """/vacation.html 페이지가 정상 응답하고 nav 가 active 로 표시된다."""
    r = api.get("/vacation.html")
    assert r.status_code == 200
    assert "휴가조회" in r.text
    assert 'href="/vacation.html" class="active"' in r.text


def test_vacation_page_has_external_new_vacation_button(api):
    """회사 타임시트 휴가 등록 페이지를 새 탭으로 여는 버튼이 있어야 한다."""
    r = api.get("/vacation.html")
    assert r.status_code == 200
    # 새 탭 + 안전한 rel + 회사 create.htm URL
    assert (
        'href="https://timesheet.uangel.com/times/application/vacation/create.htm"'
        in r.text
    )
    assert 'target="_blank"' in r.text
    assert "noopener" in r.text


def test_vacation_annual_route(api, mock_client):
    """/api/vacation/annual 이 client.get_annual_vacation_summary 결과 전달."""
    mock_client.get_annual_vacation_summary = AsyncMock(return_value={
        "total": 23.0, "used": 9.0, "remaining": 14.0, "raw_text": "23.0 - 9.0 = 14.0 일",
    })
    r = api.get("/api/vacation/annual?year=2026")
    assert r.status_code == 200
    assert r.json()["remaining"] == 14.0
    mock_client.get_annual_vacation_summary.assert_awaited_once_with(year=2026)


def test_vacation_applications_route(api, mock_client):
    """/api/vacation/applications 가 client.list_vacation_applications 결과 전달."""
    mock_client.list_vacation_applications = AsyncMock(return_value=[
        {"draft_date": "2026-05-11", "vacation_type": "반차(오후)",
         "reason": "개인 사유", "from_date": "2026-05-15", "to_date": "2026-05-15",
         "days": "0.5 일", "registered_date": "2026-05-11", "name": "손대곤",
         "status": "품의완료", "vacation_id": "36425"},
    ])
    r = api.get("/api/vacation/applications?year=2026")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["vacation_id"] == "36425"
    mock_client.list_vacation_applications.assert_awaited_once_with(year=2026)


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


def test_create_and_list_projects(api):
    r = api.post(
        "/api/projects",
        json={"name": "25년 SKT SMSC MAP 프로토콜 제거"},
    )
    assert r.status_code == 200
    g = api.get("/api/projects")
    assert g.status_code == 200
    names = [p["name"] for p in g.json()]
    assert "25년 SKT SMSC MAP 프로토콜 제거" in names


def test_create_project_rejects_duplicate(api):
    api.post("/api/projects", json={"name": "X"})
    r = api.post("/api/projects", json={"name": "X"})
    assert r.status_code == 409


def test_delete_project_removes_unmapped(api):
    """매핑/패턴에서 사용 안 되면 정상 삭제."""
    p = api.post("/api/projects", json={"name": "DEL-OK"}).json()
    r = api.delete(f"/api/projects/{p['id']}")
    assert r.status_code == 200
    names = [x["name"] for x in api.get("/api/projects").json()]
    assert "DEL-OK" not in names


def test_delete_project_blocked_by_category_mapping(api):
    """카테고리 매핑에 사용 중인 프로젝트는 409 차단."""
    p = api.post("/api/projects", json={"name": "MAPPED"}).json()
    api.put("/api/mappings/cat-a", json={"project_id": p["id"], "excluded": False})
    r = api.delete(f"/api/projects/{p['id']}")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["reason"] == "in_use"
    assert detail["category_mappings"] == 1


def test_delete_project_blocked_by_pattern_mapping(api):
    """패턴 매핑에 사용 중인 프로젝트도 409 차단."""
    p = api.post("/api/projects", json={"name": "PMAPPED"}).json()
    api.post(
        "/api/pattern-mappings",
        json={"pattern": "VM1.0", "project_id": p["id"], "excluded": False},
    )
    r = api.delete(f"/api/projects/{p['id']}")
    assert r.status_code == 409
    assert r.json()["detail"]["pattern_mappings"] == 1


def test_delete_mapping_removes_row(api):
    """매핑 행 삭제 후 다시 list 했을 때 그 카테고리가 없거나 placeholder 로만 나타남."""
    p = api.post("/api/projects", json={"name": "Q"}).json()
    api.put("/api/mappings/cat-x", json={"project_id": p["id"], "excluded": False})
    r = api.delete("/api/mappings/cat-x")
    assert r.status_code == 200
    # entries 에 없으므로 목록에서 사라져야 함
    items = {m["category"]: m for m in api.get("/api/mappings").json()}
    assert "cat-x" not in items


def test_list_mappings_filters_old_entry_categories(api):
    """오래된 entries 카테고리는 placeholder 로 안 나타난다 (지난달 이전)."""
    import datetime
    old = (datetime.date.today() - datetime.timedelta(days=180)).isoformat()
    week = "2024-W01"  # week_iso 는 검증 안 함, 형식만 맞추면 됨
    api.put(f"/api/days/{old}", json={
        "week_iso": week,
        "entries": [{"category": "old-only-cat", "hours": 1, "body_md": "x"}],
    })
    items = {m["category"]: m for m in api.get("/api/mappings").json()}
    assert "old-only-cat" not in items


def test_list_mappings_keeps_recent_entry_categories(api):
    """이번달 entries 카테고리는 placeholder 로 자동 노출."""
    import datetime
    today = datetime.date.today().isoformat()
    api.put(f"/api/days/{today}", json={
        "week_iso": "2026-W19",
        "entries": [{"category": "fresh-cat", "hours": 1, "body_md": "x"}],
    })
    items = {m["category"]: m for m in api.get("/api/mappings").json()}
    assert "fresh-cat" in items


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


def test_get_settings_returns_defaults_for_unset(api):
    r = api.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "upnote.notebook_id",
        "upnote.title_template",
        "upnote.body_template",
        "team_report.template",
        "ongoing_schedule",
        "upnote.weekly_notebook_id",
    ):
        assert key in body


def test_put_settings_updates_values(api):
    api.put("/api/settings", json={"upnote.notebook_id": "abc-123"})
    r = api.get("/api/settings")
    assert r.json()["upnote.notebook_id"] == "abc-123"


def test_put_settings_ongoing_schedule_round_trip(api):
    """ongoing_schedule key 가 PUT → DB → GET round-trip 으로 보존되는지."""
    payload = "<< 5월 월간 계획 >>\n*) EM 고도화 (05/06 ~ 05/29)"
    api.put("/api/settings", json={"ongoing_schedule": payload})
    r = api.get("/api/settings")
    assert r.json()["ongoing_schedule"] == payload


def test_put_settings_weekly_notebook_id_round_trip(api):
    """upnote.weekly_notebook_id key 가 PUT → GET 으로 보존되는지."""
    api.put("/api/settings", json={"upnote.weekly_notebook_id": "주간업무보고-노트북"})
    r = api.get("/api/settings")
    assert r.json()["upnote.weekly_notebook_id"] == "주간업무보고-노트북"


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
    tmpl = (
        "{% for entry in entries %}"
        "*) {{ entry.category }}\n{{ entry.body }}"
        "{% endfor %}"
    )
    r = api.post(
        "/api/settings/preview",
        json={"kind": "team_report", "template": tmpl, "date": "2026-05-12"},
    )
    assert r.status_code == 200
    assert "*) X" in r.json()["text"]


def test_get_logs_empty(api):
    r = api.get("/api/logs")
    assert r.status_code == 200
    assert r.json() == []


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
        log["action_type"] == "report" and log["status"] == "ok" for log in logs
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


def test_action_upnote_sync_calls_subprocess(api, monkeypatch):
    """upnote-sync 는 build_url 결과로 subprocess.run(['open', url]) 을 호출."""
    from angeldash.timesheet import upnote
    calls = []

    def fake_open(*, title, text, notebook_id, markdown=False):
        calls.append({
            "title": title, "text": text,
            "notebook_id": notebook_id, "markdown": markdown,
        })
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
    from angeldash.timesheet import upnote

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
    calls = mock_client.list_jobtime_tasks.await_args_list
    months = {c.kwargs.get("year_month") for c in calls}
    assert months == {"2026-04", "2026-05"}


def test_remote_tasks_lists_year_month(api, mock_client):
    """list_remote_tasks 는 year_month 를 그대로 전달한다."""
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "11113", "name": "EM 고도화", "work_type": "개발"},
        {"task_id": "11114", "name": "다른 task", "work_type": "개발"},
    ])
    r = api.get("/api/timesheet/tasks?year_month=2026-05")
    assert r.status_code == 200
    tasks = r.json()
    names = [t["name"] for t in tasks]
    assert names == ["EM 고도화", "다른 task"]
    mock_client.list_jobtime_tasks.assert_awaited_once_with(year_month="2026-05")


def test_remote_tasks_marks_already_registered(api, mock_client):
    """projects 에 이미 등록된 (remote_id, work_type) 조합은 already_registered=True."""
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "11113", "name": "EM 고도화", "work_type": "개발"},
        {"task_id": "11114", "name": "신규 task", "work_type": "개발"},
    ])
    # 'EM 고도화 [개발]' 은 이미 등록
    api.post("/api/projects", json={
        "name": "EM 고도화", "remote_id": "EM 고도화", "work_type": "개발",
    })

    r = api.get("/api/timesheet/tasks?year_month=2026-05")
    tasks = {t["name"]: t for t in r.json()}
    assert tasks["EM 고도화"]["already_registered"] is True
    assert tasks["EM 고도화"]["project_id"] is not None
    assert tasks["신규 task"]["already_registered"] is False
    assert tasks["신규 task"]["project_id"] is None


def test_remote_tasks_different_work_type_not_registered(api, mock_client):
    """같은 name 이라도 work_type 이 다르면 already_registered=False."""
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "20001", "name": "행정, 공통개발업무", "work_type": "개발"},
        {"task_id": "20002", "name": "행정, 공통개발업무", "work_type": "세미나"},
    ])
    # 개발만 등록
    api.post("/api/projects", json={
        "name": "행정, 공통개발업무", "remote_id": "행정, 공통개발업무",
        "work_type": "개발",
    })

    r = api.get("/api/timesheet/tasks?year_month=2026-05")
    by_wt = {(t["name"], t["work_type"]): t for t in r.json()}
    assert by_wt[("행정, 공통개발업무", "개발")]["already_registered"] is True
    assert by_wt[("행정, 공통개발업무", "세미나")]["already_registered"] is False


def test_create_project_allows_same_name_different_work_type(api):
    """동일 이름 + 다른 work_type 은 2개 등록 가능 (UNIQUE(name, work_type))."""
    r1 = api.post("/api/projects", json={
        "name": "행정", "remote_id": "행정", "work_type": "개발",
    })
    r2 = api.post("/api/projects", json={
        "name": "행정", "remote_id": "행정", "work_type": "세미나",
    })
    assert r1.status_code == 200
    assert r2.status_code == 200

    g = api.get("/api/projects")
    items = g.json()
    work_types = sorted([p["work_type"] for p in items if p["name"] == "행정"])
    assert work_types == ["개발", "세미나"]


def test_create_project_rejects_same_name_same_work_type(api):
    """동일 (name, work_type) 은 409."""
    api.post("/api/projects", json={
        "name": "X", "remote_id": "X", "work_type": "개발",
    })
    r = api.post("/api/projects", json={
        "name": "X", "remote_id": "X", "work_type": "개발",
    })
    assert r.status_code == 409


def test_remote_tasks_backfills_legacy_empty_work_type(api, mock_client):
    """work_type 이 비어 있는 레거시 행은 처음 매칭되는 remote task 의 work_type 으로 backfill."""
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "11113", "name": "행정", "work_type": "개발"},
        {"task_id": "11114", "name": "행정", "work_type": "세미나"},
    ])
    # 레거시: work_type 미지정으로 등록 (마이그레이션 직후 상태 시뮬레이션)
    api.post("/api/projects", json={"name": "행정", "remote_id": "행정"})

    r = api.get("/api/timesheet/tasks?year_month=2026-05")
    by_wt = {(t["name"], t["work_type"]): t for t in r.json()}
    # 첫번째 매칭 ('개발') 이 legacy 행을 흡수 → already_registered=True
    assert by_wt[("행정", "개발")]["already_registered"] is True
    # 두번째 ('세미나') 는 새 row 이므로 미등록 상태
    assert by_wt[("행정", "세미나")]["already_registered"] is False

    # backfill 확인: 로컬 행의 work_type 이 '개발' 로 채워졌어야 한다
    items = api.get("/api/projects").json()
    legacy = [p for p in items if p["name"] == "행정"]
    assert len(legacy) == 1
    assert legacy[0]["work_type"] == "개발"


def test_remote_tasks_default_year_month(api, mock_client):
    """year_month 미지정 시 현재 달이 사용된다."""
    import datetime as _dt
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[])
    r = api.get("/api/timesheet/tasks")
    assert r.status_code == 200
    expected_ym = _dt.date.today().strftime("%Y-%m")
    mock_client.list_jobtime_tasks.assert_awaited_once_with(year_month=expected_ym)


def test_pattern_mapping_crud(api):
    pid = api.post("/api/projects", json={"name": "P1"}).json()["id"]
    r = api.post(
        "/api/pattern-mappings",
        json={"pattern": "KCTHLR", "project_id": pid, "excluded": False},
    )
    assert r.status_code == 200
    pmid = r.json()["id"]
    g = api.get("/api/pattern-mappings")
    assert any(x["pattern"] == "KCTHLR" for x in g.json())
    d = api.delete(f"/api/pattern-mappings/{pmid}")
    assert d.status_code == 200
    assert api.get("/api/pattern-mappings").json() == []


def test_timesheet_uses_pattern_mapping_when_body_matches(api, mock_client):
    """본문에 패턴이 있으면 카테고리 매핑보다 패턴 매핑이 우선."""
    from unittest.mock import AsyncMock
    mock_client.user_id = "alice"
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "999", "name": "패턴_프로젝트_task", "work_type": "개발"},
        {"task_id": "111", "name": "카테고리_프로젝트_task", "work_type": "개발"},
    ])
    mock_client.submit_jobtimes = AsyncMock(return_value="OK")

    # 카테고리 매핑
    cat_pid = api.post("/api/projects", json={
        "name": "카테고리 프로젝트", "remote_id": "카테고리_프로젝트_task",
    }).json()["id"]
    api.put("/api/mappings/SKT SMSC 리빌딩",
            json={"project_id": cat_pid, "excluded": False})

    # 패턴 매핑 (더 구체적)
    pat_pid = api.post("/api/projects", json={
        "name": "패턴 프로젝트", "remote_id": "패턴_프로젝트_task",
    }).json()["id"]
    api.post("/api/pattern-mappings", json={
        "pattern": "KCTHLR", "project_id": pat_pid, "excluded": False,
    })

    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W19",
        "entries": [{
            "category": "SKT SMSC 리빌딩",
            "hours": 4,
            "body_md": "- VM1.0.5 PKG 신규 통계(KCTHLR) 기능 개발",
        }],
    })

    r = api.post(
        "/api/actions/timesheet-submit",
        json={"date": "2026-05-12", "dry_run": False},
    )
    assert r.status_code == 200, r.text
    rows = mock_client.submit_jobtimes.await_args[0][0]
    assert rows[0]["task_id"] == "999"  # 패턴 매핑의 task


def test_vacations_route_calls_client(api, mock_client):
    from unittest.mock import AsyncMock
    mock_client.list_vacations = AsyncMock(return_value=[
        {"date": "2026-05-04", "type": "연차", "hours": 8.0},
    ])
    r = api.get("/api/vacations?year_month=2026-05")
    assert r.status_code == 200
    assert r.json() == [{"date": "2026-05-04", "type": "연차", "hours": 8.0}]
    mock_client.list_vacations.assert_awaited_once_with(year_month="2026-05")


def test_vacations_route_default_year_month(api, mock_client):
    import datetime as _dt
    from unittest.mock import AsyncMock
    mock_client.list_vacations = AsyncMock(return_value=[])
    api.get("/api/vacations")
    expected = _dt.date.today().strftime("%Y-%m")
    mock_client.list_vacations.assert_awaited_once_with(year_month=expected)


def test_verify_marks_synced_and_mismatch(api, mock_client):
    from unittest.mock import AsyncMock
    mock_client.user_id = "alice"
    # 회사 시스템: 5/12 EM 고도화 = 4h, 5/13 = 0h
    mock_client.fetch_jobtime_grid = AsyncMock(return_value={
        "EM 고도화 task": {12: 4.0},
    })

    pid = api.post("/api/projects", json={
        "name": "EM 고도화", "remote_id": "EM 고도화 task",
    }).json()["id"]
    api.put("/api/mappings/EM 고도화", json={
        "project_id": pid, "excluded": False,
    })

    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W20",
        "entries": [{"category": "EM 고도화", "hours": 4, "body_md": ""}],
    })
    api.put("/api/days/2026-05-13", json={
        "week_iso": "2026-W20",
        "entries": [{"category": "EM 고도화", "hours": 4, "body_md": ""}],
    })

    r = api.get("/api/timesheet/verify?week_iso=2026-W20")
    assert r.status_code == 200
    items = {(it["date"], it["category"]): it for it in r.json()["items"]}
    assert items[("2026-05-12", "EM 고도화")]["sync_status"] == "synced"
    assert items[("2026-05-13", "EM 고도화")]["sync_status"] == "not_submitted"


def test_verify_marks_no_mapping(api, mock_client):
    from unittest.mock import AsyncMock
    mock_client.fetch_jobtime_grid = AsyncMock(return_value={})
    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W20",
        "entries": [{"category": "Unmapped", "hours": 4, "body_md": ""}],
    })
    r = api.get("/api/timesheet/verify?week_iso=2026-W20")
    items = r.json()["items"]
    assert items[0]["sync_status"] == "no_mapping"


def test_timesheet_longer_pattern_wins(api, mock_client):
    """긴 패턴이 짧은 패턴보다 우선."""
    from unittest.mock import AsyncMock
    mock_client.user_id = "alice"
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "AAA", "name": "긴_task", "work_type": "개발"},
        {"task_id": "BBB", "name": "짧은_task", "work_type": "개발"},
    ])
    mock_client.submit_jobtimes = AsyncMock(return_value="OK")

    long_pid = api.post("/api/projects", json={
        "name": "긴 프로젝트", "remote_id": "긴_task",
    }).json()["id"]
    short_pid = api.post("/api/projects", json={
        "name": "짧은 프로젝트", "remote_id": "짧은_task",
    }).json()["id"]
    api.post("/api/pattern-mappings",
             json={"pattern": "VM1.0.5 PKG", "project_id": long_pid})
    api.post("/api/pattern-mappings",
             json={"pattern": "VM", "project_id": short_pid})

    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W19",
        "entries": [{
            "category": "X",
            "hours": 4,
            "body_md": "VM1.0.5 PKG 신규 작업",
        }],
    })
    r = api.post(
        "/api/actions/timesheet-submit",
        json={"date": "2026-05-12", "dry_run": False},
    )
    assert r.status_code == 200
    rows = mock_client.submit_jobtimes.await_args[0][0]
    assert rows[0]["task_id"] == "AAA"  # 긴 패턴의 task


def test_verify_aggregates_same_task_on_same_day(api, mock_client):
    """같은 task 로 매핑된 entries 가 한 날에 여러 개 있으면 합산해서 비교."""
    from unittest.mock import AsyncMock
    mock_client.user_id = "alice"
    # 회사 시스템: EM 고도화 task 의 5/7 = 8h
    mock_client.fetch_jobtime_grid = AsyncMock(return_value={
        "EM 고도화 task": {7: 8.0},
    })

    # 두 카테고리 모두 같은 task 로 매핑
    pid = api.post("/api/projects", json={
        "name": "EM", "remote_id": "EM 고도화 task",
    }).json()["id"]
    api.put("/api/mappings/SKT SMSC 리빌딩",
            json={"project_id": pid, "excluded": False})
    api.put("/api/mappings/EM 고도화",
            json={"project_id": pid, "excluded": False})

    # 5/7 에 두 entry — 3h + 5h = 8h (회사와 일치)
    api.put("/api/days/2026-05-07", json={
        "week_iso": "2026-W19",
        "entries": [
            {"category": "SKT SMSC 리빌딩", "hours": 3, "body_md": ""},
            {"category": "EM 고도화", "hours": 5, "body_md": ""},
        ],
    })

    r = api.get("/api/timesheet/verify?week_iso=2026-W19")
    assert r.status_code == 200
    items = r.json()["items"]
    # 둘 다 task 합산이 회사와 일치 → 둘 다 synced
    for it in items:
        assert it["sync_status"] == "synced"
        assert it["local_task_total"] == 8.0
        assert it["remote_hours"] == 8.0


def test_excel_download_streams_binary(api, mock_client):
    from unittest.mock import AsyncMock
    xlsx = b"PK\x03\x04" + b"X" * 100
    mock_client.download_jobtime_excel = AsyncMock(
        return_value=(xlsx, "작업시간_리포트(2026-05).xlsx")
    )
    r = api.get("/api/timesheet/excel?year_month=2026-05")
    assert r.status_code == 200
    assert r.content == xlsx
    cd = r.headers.get("content-disposition", "")
    assert "filename=" in cd
    assert "UTF-8" in cd  # RFC 5987 한글 filename
    mock_client.download_jobtime_excel.assert_awaited_once_with(year_month="2026-05")


def test_verify_uses_pattern_mapping_when_body_matches(api, mock_client):
    """본문 패턴 매핑으로 라우팅된 entry 도 sync 검증에서 같이 비교한다."""
    from unittest.mock import AsyncMock
    mock_client.user_id = "alice"
    # 회사 시스템: 패턴_프로젝트_task 의 5/7 = 4h
    mock_client.fetch_jobtime_grid = AsyncMock(return_value={
        "패턴_프로젝트_task": {7: 4.0},
    })

    # 카테고리 매핑은 다른 task. 패턴 매핑이 우선이어야 함.
    cat_pid = api.post("/api/projects", json={
        "name": "카테고리 프로젝트", "remote_id": "카테고리_task",
    }).json()["id"]
    api.put("/api/mappings/SKT SMSC 리빌딩", json={
        "project_id": cat_pid, "excluded": False,
    })
    # 패턴 매핑
    pat_pid = api.post("/api/projects", json={
        "name": "패턴 프로젝트", "remote_id": "패턴_프로젝트_task",
    }).json()["id"]
    api.post("/api/pattern-mappings", json={
        "pattern": "KCTHLR", "project_id": pat_pid, "excluded": False,
    })

    # 본문에 KCTHLR 포함 → 패턴 매핑 우선 → 패턴_프로젝트_task 와 비교
    api.put("/api/days/2026-05-07", json={
        "week_iso": "2026-W19",
        "entries": [{
            "category": "SKT SMSC 리빌딩",
            "hours": 4,
            "body_md": "- VM1.0.5 PKG 신규 통계(KCTHLR) 기능 개발",
        }],
    })

    r = api.get("/api/timesheet/verify?week_iso=2026-W19")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["sync_status"] == "synced"  # 4h == 4h
    assert items[0].get("matched_pattern") == "KCTHLR"
    assert items[0]["remote_hours"] == 4.0


def test_verify_reports_orphan_entries(api, mock_client):
    """회사 시스템에는 있지만 도구에는 없는 (date, task) 를 orphan 으로 표시."""
    from unittest.mock import AsyncMock
    mock_client.user_id = "alice"
    # 회사 시스템: 5/12 에 두 task 시간이 있음
    mock_client.fetch_jobtime_grid = AsyncMock(return_value={
        "EM 고도화 task": {12: 4.0},     # 도구에도 있음
        "다른 잡일 task": {12: 2.0},      # 도구에 없음 (orphan)
        "또 다른 task": {15: 1.0},        # 그 주 아니면 무시 (W20=5/11~5/17 이므로 포함)
    })

    pid = api.post("/api/projects", json={
        "name": "EM 고도화", "remote_id": "EM 고도화 task",
    }).json()["id"]
    api.put("/api/mappings/EM 고도화",
            json={"project_id": pid, "excluded": False})

    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W20",
        "entries": [{"category": "EM 고도화", "hours": 4, "body_md": ""}],
    })

    r = api.get("/api/timesheet/verify?week_iso=2026-W20")
    assert r.status_code == 200
    items = r.json()["items"]
    orphans = [it for it in items if it["sync_status"] == "orphan"]
    orphan_keys = {(it["date"], it["task_name"]) for it in orphans}
    # 다른 잡일 task 와 또 다른 task 둘 다 orphan
    assert ("2026-05-12", "다른 잡일 task") in orphan_keys
    assert ("2026-05-15", "또 다른 task") in orphan_keys


def test_push_one_submits_single_row(api, mock_client):
    """push-one 은 search → 단일 row save 호출."""
    from unittest.mock import AsyncMock
    mock_client.user_id = "alice"
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "999", "name": "EM 고도화 task", "work_type": "개발"},
    ])
    mock_client.submit_jobtimes = AsyncMock(return_value="OK")

    r = api.post("/api/actions/timesheet-push-one", json={
        "date": "2026-05-12",
        "task_name": "EM 고도화 task",
        "hours": 5,
    })
    assert r.status_code == 200
    rows = mock_client.submit_jobtimes.await_args[0][0]
    assert rows == [{
        "task_id": "999", "work_hour": 5,
        "work_day": "20260512", "user_id": "alice",
    }]


def test_push_one_with_zero_hours_deletes(api, mock_client):
    """hours=0 으로 push 하면 사실상 삭제 (회사 시스템이 그 셀을 0 으로 update)."""
    from unittest.mock import AsyncMock
    mock_client.user_id = "alice"
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[
        {"task_id": "777", "name": "잘못 등록된 task", "work_type": "개발"},
    ])
    mock_client.submit_jobtimes = AsyncMock(return_value="OK")

    r = api.post("/api/actions/timesheet-push-one", json={
        "date": "2026-05-12",
        "task_name": "잘못 등록된 task",
        "hours": 0,
    })
    assert r.status_code == 200
    rows = mock_client.submit_jobtimes.await_args[0][0]
    assert rows[0]["work_hour"] == 0


def test_push_one_rejects_unknown_task(api, mock_client):
    """search 결과에 없는 task 면 400."""
    from unittest.mock import AsyncMock
    mock_client.list_jobtime_tasks = AsyncMock(return_value=[])
    r = api.post("/api/actions/timesheet-push-one", json={
        "date": "2026-05-12",
        "task_name": "없는 task",
        "hours": 4,
    })
    assert r.status_code == 400


def test_holidays_route_calls_client(api, mock_client):
    from unittest.mock import AsyncMock
    mock_client.list_holidays = AsyncMock(return_value=[
        {"date": "2026-05-05", "label": "어린이날", "types": ["public"]},
    ])
    r = api.get("/api/holidays?year_month=2026-05")
    assert r.status_code == 200
    assert r.json()[0]["label"] == "어린이날"
    mock_client.list_holidays.assert_awaited_once_with(year_month="2026-05")


def test_get_daily_meta_default(api):
    r = api.get("/api/days/2026-05-12/meta")
    assert r.status_code == 200
    assert r.json() == {"date": "2026-05-12", "source_commit": "done", "misc_note": ""}


def test_put_daily_meta_round_trip(api):
    r = api.put(
        "/api/days/2026-05-12/meta",
        json={"source_commit": "local_backup", "misc_note": "오늘 오후 반차"},
    )
    assert r.status_code == 200
    g = api.get("/api/days/2026-05-12/meta")
    assert g.json()["source_commit"] == "local_backup"
    assert g.json()["misc_note"] == "오늘 오후 반차"


def test_put_daily_meta_rejects_invalid(api):
    r = api.put(
        "/api/days/2026-05-12/meta",
        json={"source_commit": "bogus", "misc_note": ""},
    )
    assert r.status_code == 400


def test_team_report_includes_source_commit_and_misc(api):
    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W20",
        "entries": [{"category": "X", "hours": 8, "body_md": " - 작업"}],
    })
    api.put("/api/days/2026-05-12/meta", json={
        "source_commit": "done", "misc_note": "내일 연차입니다",
    })
    r = api.post("/api/actions/team-report", json={"date": "2026-05-12"})
    text = r.json()["text"]
    assert "*) 소스 Commit" in text
    assert " - 완료" in text
    assert "*) 기타" in text
    assert "내일 연차입니다" in text


def test_team_report_omits_misc_when_empty(api):
    api.put("/api/days/2026-05-12", json={
        "week_iso": "2026-W20",
        "entries": [{"category": "X", "hours": 8, "body_md": " - 작업"}],
    })
    # source_commit 만 설정, misc 는 빈 채로
    api.put("/api/days/2026-05-12/meta", json={
        "source_commit": "later", "misc_note": "",
    })
    r = api.post("/api/actions/team-report", json={"date": "2026-05-12"})
    text = r.json()["text"]
    assert "*) 소스 Commit" in text
    assert "- 추후" in text
    assert "*) 기타" not in text


def test_misc_auto_route_basic(api, mock_client):
    """기본: 휴가 없으면 빈 문자열."""
    mock_client.list_vacations = AsyncMock(return_value=[])
    mock_client.list_holidays = AsyncMock(return_value=[])

    r = api.get("/api/days/2026-05-12/misc-auto")
    assert r.status_code == 200
    assert r.json() == {"date": "2026-05-12", "text": ""}


def test_projects_search_route(api, mock_client):
    from unittest.mock import AsyncMock
    mock_client.search_joinable_projects = AsyncMock(return_value={
        "rows": [
            {"project_id": "2184", "code": "X", "name": "NEW",
             "joined": False},
        ],
        "total": 1, "page": 1, "page_size": 50,
    })
    r = api.get("/api/timesheet/projects/search?keyword=LTE")
    assert r.status_code == 200
    assert r.json()["rows"][0]["name"] == "NEW"
    mock_client.search_joinable_projects.assert_awaited_once_with(
        keyword="LTE", page=1, page_size=50,
    )


def test_projects_join_route_auto_joins_task(api, mock_client):
    """프로젝트 가입 시 settings.join.auto_task_name 의 task 도 자동 가입."""
    from unittest.mock import AsyncMock
    mock_client.join_project = AsyncMock(return_value=None)
    mock_client.list_project_tasks = AsyncMock(return_value=[
        {"task_id": "11132", "name": "시험/지원", "joined": False},
        {"task_id": "11131", "name": "개발", "joined": False},
    ])
    mock_client.set_project_task_joined = AsyncMock(return_value=None)
    # 기본값 "개발" 사용
    r = api.post(
        "/api/timesheet/projects/join",
        json={"project_id": "2166", "joined": True},
    )
    assert r.status_code == 200
    assert r.json()["joined_task"] == "개발"
    mock_client.set_project_task_joined.assert_awaited_once_with(
        project_id="2166", task_id="11131",
    )


def test_projects_join_route_skips_task_if_already_joined(api, mock_client):
    """이미 그 task 에 가입되어 있으면 set_project_task_joined 안 호출."""
    from unittest.mock import AsyncMock
    mock_client.join_project = AsyncMock(return_value=None)
    mock_client.list_project_tasks = AsyncMock(return_value=[
        {"task_id": "11131", "name": "개발", "joined": True},
    ])
    mock_client.set_project_task_joined = AsyncMock(return_value=None)
    r = api.post(
        "/api/timesheet/projects/join",
        json={"project_id": "2160", "joined": True},
    )
    assert r.status_code == 200
    mock_client.set_project_task_joined.assert_not_awaited()


def test_projects_join_route_uses_custom_team_task(api, mock_client):
    """다른 팀: settings 의 auto_task_name 변경 시 그 task 가입."""
    from unittest.mock import AsyncMock
    api.put("/api/settings", json={"join.auto_task_name": "영업"})
    mock_client.join_project = AsyncMock(return_value=None)
    mock_client.list_project_tasks = AsyncMock(return_value=[
        {"task_id": "11131", "name": "개발", "joined": False},
        {"task_id": "11130", "name": "영업", "joined": False},
    ])
    mock_client.set_project_task_joined = AsyncMock(return_value=None)
    r = api.post(
        "/api/timesheet/projects/join",
        json={"project_id": "2166", "joined": True},
    )
    assert r.status_code == 200
    assert r.json()["joined_task"] == "영업"
    mock_client.set_project_task_joined.assert_awaited_once_with(
        project_id="2166", task_id="11130",
    )


def test_projects_unjoin_uses_cascade(api, mock_client):
    """탈퇴 시 unjoin_project (tasksMapDelAll cascade) 한 번만 호출."""
    from unittest.mock import AsyncMock
    mock_client.unjoin_project = AsyncMock(return_value=None)
    r = api.post(
        "/api/timesheet/projects/join",
        json={"project_id": "2160", "joined": False},
    )
    assert r.status_code == 200
    mock_client.unjoin_project.assert_awaited_once_with(project_id="2160")


def test_misc_auto_route_uses_exclude_labels(api, mock_client):
    """settings.misc.holiday_exclude_labels 를 반영."""
    mock_client.list_vacations = AsyncMock(side_effect=[
        [{"date": "2026-05-22", "type": "연차", "hours": 8}],  # 5월
        [],  # 6월
    ])
    mock_client.list_holidays = AsyncMock(side_effect=[
        [{"date": "2026-05-22", "label": "가정의날", "types": ["public"]}],
        [],
    ])
    # 가정의날을 출근일로 처리
    api.put("/api/settings", json={"misc.holiday_exclude_labels": "가정의날"})

    r = api.get("/api/days/2026-05-21/misc-auto")
    assert r.status_code == 200
    # 5/22 가 영업일 → 연차 → "내일 연차"
    assert r.json()["text"] == "내일 연차입니다"


# ─── 주간업무보고 API 회귀 ─────────────────────────────


def test_get_weekly_report_returns_empty_for_unset(api):
    r = api.get("/api/weekly-reports/2026-W20")
    assert r.status_code == 200
    body = r.json()
    assert body["week_iso"] == "2026-W20"
    assert body["rows"] == []


def test_put_weekly_report_round_trip(api):
    rows = [
        {"project_name": "OAM", "last_week": "a", "this_week": "b",
         "next_week": "c", "note": "d"},
    ]
    r = api.put("/api/weekly-reports/2026-W20", json={"rows": rows})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r2 = api.get("/api/weekly-reports/2026-W20")
    assert r2.json()["rows"] == rows


def test_generate_weekly_report_preserves_manual(api):
    # 수동 입력
    rows = [
        {"project_name": "OAM", "last_week": "", "this_week": "",
         "next_week": "차주 작업", "note": "비고"},
    ]
    api.put("/api/weekly-reports/2026-W20", json={"rows": rows})
    # generate 호출 — daily entries 가 없어도 200 응답이어야 함
    r = api.post(
        "/api/weekly-reports/2026-W20/generate",
        json={"preserve_manual": True},
    )
    assert r.status_code == 200
    assert "rows" in r.json()


def test_weekly_report_upnote_requires_notebook_id(api):
    api.put("/api/weekly-reports/2026-W20", json={"rows": [
        {"project_name": "X", "last_week": "a", "this_week": "b",
         "next_week": "", "note": ""},
    ]})
    r = api.post(
        "/api/actions/weekly-report-upnote",
        json={"week_iso": "2026-W20"},
    )
    assert r.status_code == 400
    assert "weekly_notebook_id" in r.json()["detail"]


def test_weekly_report_upnote_requires_non_empty_rows(api):
    api.put("/api/settings", json={"upnote.weekly_notebook_id": "test-nb"})
    r = api.post(
        "/api/actions/weekly-report-upnote",
        json={"week_iso": "2026-W20"},
    )
    assert r.status_code == 400
    assert "비어" in r.json()["detail"]
