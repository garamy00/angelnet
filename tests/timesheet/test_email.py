"""이메일 빌더 + SMTP 헬퍼 unit 테스트.

SMTP 실제 발송은 외부 의존이라 검증하지 않는다. 메시지 빌드/주소 파싱 등
순수 함수만 검증.
"""

from __future__ import annotations

from angeldash.timesheet import email_smtp, weekly_table


def test_parse_recipients_splits_commas_and_trims() -> None:
    to, cc = email_smtp.parse_recipients(
        "a@x.com, b@y.com,  c@z.com",
        "manager@x.com",
    )
    assert to == ["a@x.com", "b@y.com", "c@z.com"]
    assert cc == ["manager@x.com"]


def test_parse_recipients_empty_string_returns_empty() -> None:
    to, cc = email_smtp.parse_recipients("", "")
    assert to == []
    assert cc == []


def test_parse_recipients_handles_semicolons() -> None:
    to, _cc = email_smtp.parse_recipients("a@x.com; b@y.com", "")
    assert to == ["a@x.com", "b@y.com"]


def test_build_message_includes_to_cc_subject() -> None:
    spec = email_smtp.EmailMessageSpec(
        from_addr="me@x.com",
        to=["t1@x.com", "t2@x.com"],
        cc=["c1@x.com"],
        subject="hi",
        html_body="<p>html</p>",
        plain_body="hello",
    )
    msg = email_smtp._build_message(spec)
    assert msg["From"] == "me@x.com"
    assert msg["To"] == "t1@x.com, t2@x.com"
    assert msg["Cc"] == "c1@x.com"
    assert msg["Subject"] == "hi"
    # multipart 안의 두 part 가 plain + html
    payloads = [p.get_content_type() for p in msg.iter_parts()]
    assert "text/plain" in payloads
    assert "text/html" in payloads


def test_render_email_html_wraps_greeting_table_closing_signature() -> None:
    rows = [
        {"project_name": "P1", "last_week": "a", "this_week": "b",
         "next_week": "", "note": ""},
    ]
    out = weekly_table.render_email_html(
        rows, greeting="안녕\n\n보고 드립니다",
        closing="감사합니다", signature_html="<p>sig</p>",
    )
    assert "<p>안녕</p>" in out
    assert "<p>보고 드립니다</p>" in out
    assert "<p>감사합니다</p>" in out
    assert "<p>sig</p>" in out
    # 표 영역 포함
    assert "<table" in out
    assert "P1" in out


def test_render_email_html_skips_blank_signature() -> None:
    rows = [{"project_name": "P1", "last_week": "", "this_week": "",
             "next_week": "", "note": ""}]
    out = weekly_table.render_email_html(
        rows, greeting="", closing="",
        signature_html="   ",  # whitespace 만 → 첨부 안 됨
    )
    assert "<br>" not in out  # 서명용 <br> prefix 도 안 들어감


def test_render_email_plain_concatenates_with_blank_lines() -> None:
    rows = [{"project_name": "P1", "last_week": "", "this_week": "",
             "next_week": "", "note": ""}]
    out = weekly_table.render_email_plain(
        rows, greeting="hello", closing="thanks",
    )
    # 세 chunk (인사말, 표, 마무리) 가 빈 줄로 구분
    assert out.startswith("hello\n\n")
    assert out.endswith("\n\nthanks")
    assert "| P1 |" in out


def test_render_html_table_preserves_newlines_and_indent() -> None:
    """Outlook 호환 — \\n 은 <br>, 줄 시작 spaces 는 &nbsp; 로 명시적 변환."""
    rows = [{
        "project_name": "P1",
        "last_week": "",
        "this_week": "*) EM 고도화\n  - 신규 OAM 서버\n    . 코어 인프라 구현",
        "next_week": "",
        "note": "",
    }]
    html = weekly_table.render_html_table(rows)
    # 줄바꿈이 <br> 로
    assert "*) EM 고도화<br>" in html
    # 2-space 들여쓰기가 &nbsp;&nbsp; 로
    assert "&nbsp;&nbsp;- 신규 OAM" in html
    # 4-space 들여쓰기가 &nbsp;×4 로
    assert "&nbsp;&nbsp;&nbsp;&nbsp;. 코어 인프라 구현" in html


def test_render_html_table_escapes_html_chars_in_cells() -> None:
    """셀에 < > & 가 있어도 안전하게 escape."""
    rows = [{
        "project_name": "P&Q",
        "last_week": "<script>alert(1)</script>",
        "this_week": "", "next_week": "", "note": "",
    }]
    html = weekly_table.render_html_table(rows)
    assert "P&amp;Q" in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_render_email_plain_omits_empty_greeting_and_closing() -> None:
    rows = [{"project_name": "P1", "last_week": "", "this_week": "",
             "next_week": "", "note": ""}]
    out = weekly_table.render_email_plain(rows, greeting="", closing="")
    # 표만 남음
    assert out.startswith("| ")
    assert "\n\n" not in out  # 빈 줄로 구분되는 chunk 없음
