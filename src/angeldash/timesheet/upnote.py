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
    *, title: str, text: str, notebook_id: str = "", markdown: bool = False
) -> str:
    """upnote://x-callback-url/note/new URL 을 만든다.

    notebook_id 가 비어있으면 notebook 파라미터를 생략하여 UpNote 기본 노트북에 저장.
    markdown=True 면 UpNote 가 본문을 마크다운으로 렌더 (들여쓰기 제거, '-' → bullet 변환).
    plain text 그대로 보존하려면 markdown=False (기본).
    """
    params: dict[str, str] = {
        "title": title,
        "text": text,
        "markdown": "true" if markdown else "false",
    }
    if notebook_id:
        params["notebook"] = notebook_id
    qs = urlencode(params)
    return f"upnote://x-callback-url/note/new?{qs}"


def open_new_note(
    *, title: str, text: str, notebook_id: str = "", markdown: bool = False
) -> str:
    """subprocess.run(['open', url]) 로 호출.

    `open` 은 macOS 의 빌트인. 호출 자체가 비동기로 UpNote 앱을 깨우므로,
    반환값으로는 단지 호출에 사용한 URL 을 돌려준다.
    실패 시 RuntimeError.
    """
    url = build_new_note_url(
        title=title, text=text, notebook_id=notebook_id, markdown=markdown,
    )
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
