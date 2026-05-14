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
    # 헤더 라인 bold 처리 + 그 다음에 <br>
    assert "<strong>*) EM 고도화</strong><br>" in html
    # 2-space 들여쓰기가 &nbsp;&nbsp; 로
    assert "&nbsp;&nbsp;- 신규 OAM" in html
    # 4-space 들여쓰기가 &nbsp;×4 로
    assert "&nbsp;&nbsp;&nbsp;&nbsp;. 코어 인프라 구현" in html


def test_render_html_table_bolds_category_headers() -> None:
    """'*) ' 로 시작하는 카테고리 헤더 라인은 <strong> 으로 강조."""
    rows = [{
        "project_name": "P1",
        "last_week": "",
        "this_week": "*) EM 고도화\n  - 신규 OAM 서버",
        "next_week": "", "note": "",
    }]
    html = weekly_table.render_html_table(rows)
    assert "<strong>*) EM 고도화</strong>" in html
    # bold 가 아닌 본문 라인은 strong 으로 감싸지지 않음
    assert "<strong>  - 신규" not in html
    assert "<strong>&nbsp;&nbsp;- 신규" not in html


def test_render_markdown_table_bolds_category_headers() -> None:
    """markdown 표에서도 '*) ' 헤더 라인은 `**\\*)...**` 로 (`*` escape 포함)."""
    rows = [{
        "project_name": "P1",
        "last_week": "",
        "this_week": "*) EM 고도화\n  - 신규 OAM 서버",
        "next_week": "", "note": "",
    }]
    md = weekly_table.render_markdown_table(rows)
    assert r"**\*) EM 고도화**" in md
    # 본문 라인은 escape/감싸기 영향 없음
    assert "- 신규 OAM 서버" in md


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


def test_render_weekly_upnote_table_basic_box_drawing() -> None:
    """UpNote 본문 — Unicode 박스 표. 헤더 + 행 + 행 사이 separator."""
    rows = [
        {
            "project_name": "OAM 개선",
            "last_week": "*) EM 고도화\n  - 코어 인프라",
            "this_week": "*) EM 고도화",
            "next_week": "", "note": "",
        },
    ]
    out = weekly_table.render_weekly_upnote_table(rows)
    # 박스 문자
    assert "┌" in out and "┐" in out
    assert "└" in out and "┘" in out
    assert "├" in out and "┤" in out
    assert "│" in out  # 셀 separator
    # 헤더 라벨
    assert "프로젝트" in out
    assert "지난주 한 일" in out
    assert "이번주 한 일/할 일" in out
    # 본문 내용
    assert "OAM 개선" in out
    assert "*) EM 고도화" in out
    assert "- 코어 인프라" in out


def test_render_weekly_upnote_table_multiline_cell_alignment() -> None:
    """셀 안 멀티라인이 행 안에서 같은 박스 안에 함께 들어간다."""
    rows = [
        {
            "project_name": "P",
            "last_week": "a\nb\nc",
            "this_week": "x",
            "next_week": "", "note": "",
        },
    ]
    out = weekly_table.render_weekly_upnote_table(rows)
    # 멀티라인 cell — 같은 행 안에 3 라인 모두 등장
    assert "a" in out and "b" in out and "c" in out
    # 모든 본문 행이 같은 폭 (정렬) — 표가 깨지지 않음을 확인하기 위해
    # 박스 line 들이 동일 길이인지 확인
    lines = out.split("\n")
    body_lines = [ln for ln in lines if ln.startswith("│")]
    # 행 안의 모든 라인은 셀 폭이 같아 동일 column 위치에 │가 옴
    widths = [
        sum(2 if 0xAC00 <= ord(c) <= 0xD7A3 else 1 for c in ln)
        for ln in body_lines
    ]
    assert len(set(widths)) <= 2  # 헤더 라인과 본문 라인 폭은 같아야 함


def test_render_weekly_upnote_table_korean_width_aligns_columns() -> None:
    """한글 셀이 들어가도 컬럼 정렬이 깨지지 않는다 (east_asian_width 폭 2)."""
    rows = [
        {
            "project_name": "한",  # 폭 2
            "last_week": "OK",     # 폭 2
            "this_week": "", "next_week": "", "note": "",
        },
    ]
    out = weekly_table.render_weekly_upnote_table(rows)
    # 헤더 '프로젝트' (폭 8) 와 본문 '한' (폭 2) 이 같은 컬럼 — column width 는
    # 헤더 기준 8 이 되어야 함. 본문 행은 '│ 한' 으로 시작
    lines = out.split("\n")
    body_lines = [ln for ln in lines if ln.startswith("│ 한 ")]
    assert body_lines, "본문 행이 있어야 함"
    # '한' 다음에 최소 6 칸 space 가 있어 다음 │ 까지 정렬 (헤더 폭 8 - 한 폭 2)
    assert "한      " in body_lines[0]


def test_render_email_plain_omits_empty_greeting_and_closing() -> None:
    rows = [{"project_name": "P1", "last_week": "", "this_week": "",
             "next_week": "", "note": ""}]
    out = weekly_table.render_email_plain(rows, greeting="", closing="")
    # 표만 남음
    assert out.startswith("| ")
    assert "\n\n" not in out  # 빈 줄로 구분되는 chunk 없음
