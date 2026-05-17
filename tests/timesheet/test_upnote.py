"""UpNote x-callback-url 빌더와 호출."""

from __future__ import annotations

import subprocess
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from angeldash.timesheet import upnote


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
    # 기본은 false (plain text 보존)
    assert qs["markdown"] == ["false"]


def test_build_url_markdown_true_when_requested():
    url = upnote.build_new_note_url(
        title="t", text="b", notebook_id="nb", markdown=True,
    )
    qs = parse_qs(urlsplit(url).query)
    assert qs["markdown"] == ["true"]


def test_build_url_percent_encodes_special_chars():
    url = upnote.build_new_note_url(
        title="W19 (05/11 ~ 05/15)",
        text="line1\nline2 & line3",
        notebook_id="nb",
    )
    qs = parse_qs(urlsplit(url).query)
    assert qs["title"] == ["W19 (05/11 ~ 05/15)"]
    assert qs["text"] == ["line1\nline2 & line3"]


def test_build_url_omits_notebook_when_empty():
    """notebook_id 가 비어있으면 notebook 파라미터 생략 (UpNote 기본 노트북에 저장)."""
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
