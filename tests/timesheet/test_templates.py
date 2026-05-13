"""기본 템플릿 상수가 정의되어 있는지 확인."""

from __future__ import annotations

from angeldash.timesheet.templates import (
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


def _render(template: str, ctx: dict) -> str:
    from jinja2.sandbox import SandboxedEnvironment
    return SandboxedEnvironment().from_string(template).render(**ctx)


def test_team_report_empty_body_single_blank_line_between_entries():
    """body 가 빈 entry 가 있어도 entry 사이 빈 줄은 정확히 1개."""
    out = _render(DEFAULT_TEAM_REPORT, {
        "entries": [
            {"category": "EM 고도화", "body": " - 코어 인프라"},
            {"category": "AI 세미나", "body": ""},
            {"category": "운영", "body": " - X"},
        ],
        "source_commit_label": "",
        "misc_note": "",
    })
    # 'AI 세미나' (빈 body) 와 다음 entry 사이에 '\n\n\n' (빈 줄 2개) 가 나오면 안 됨
    assert "\n\n\n" not in out
    # 'AI 세미나' 다음에 정확히 한 줄 띄고 '운영' 이 와야 한다
    assert "AI 세미나\n\n*) 운영" in out


def test_upnote_body_empty_entry_body_no_double_blank_line():
    """UpNote 본문도 동일하게 entry 사이 빈 줄 1개."""
    out = _render(DEFAULT_UPNOTE_BODY, {
        "yy": 26, "ww": "19",
        "week_start_mmdd": "05/11", "week_end_mmdd": "05/15",
        "days": [{
            "mm": "05", "dd": "13", "day_kr": "수",
            "entries": [
                {"category": "EM", "body": " - X"},
                {"category": "세미나", "body": ""},
                {"category": "운영", "body": " - Y"},
            ],
            "source_commit_label": "",
            "misc_note": "",
        }],
        "week_notes": "",
    })
    assert "\n\n\n" not in out
    assert "세미나\n\n*) 운영" in out
