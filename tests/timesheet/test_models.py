"""Pydantic 모델 검증."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from angeldash.timesheet.models import (
    Entry,
    EntryInput,
    Project,
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
