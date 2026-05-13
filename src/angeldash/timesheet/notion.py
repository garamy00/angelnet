"""Notion REST API 어댑터.

Internal Integration Token 으로 인증한다.
공식 문서: https://developers.notion.com/reference/intro

엔트리 단위(1행 = 1 entry) 동기화. 동일 (Date, Project, Category) 가 있으면
기존 page 를 업데이트, 없으면 새로 생성한다.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.notion.com/v1"
API_VERSION = "2022-06-28"
HTTP_TIMEOUT = 15.0
# Notion 의 text content 한 chunk 최대 길이 (2000 자)
TEXT_CHUNK_MAX = 1900


class NotionError(Exception):
    """Notion API 호출 실패."""


class NotionClient:
    """최소 필요 endpoint 만 노출: query_database / create_page / update_page."""

    def __init__(self, token: str) -> None:
        if not token:
            raise NotionError("notion token is empty")
        self._http = httpx.AsyncClient(
            base_url=API_BASE,
            timeout=HTTP_TIMEOUT,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": API_VERSION,
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "NotionClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def query_database(
        self, database_id: str, *, filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Database 행 조회. filter 가 None 이면 전체."""
        body: dict[str, Any] = {}
        if filter is not None:
            body["filter"] = filter
        resp = await self._http.post(
            f"/databases/{database_id}/query", json=body,
        )
        self._raise_for_status(resp)
        return resp.json().get("results", [])

    async def create_page(
        self,
        *,
        database_id: str,
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> str:
        """새 page 생성. 반환: page_id."""
        body: dict[str, Any] = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        if children:
            body["children"] = children
        resp = await self._http.post("/pages", json=body)
        self._raise_for_status(resp)
        return resp.json()["id"]

    async def update_page(
        self, page_id: str, *, properties: dict[str, Any],
    ) -> None:
        """기존 page 의 properties 만 업데이트 (children 미포함)."""
        resp = await self._http.patch(
            f"/pages/{page_id}", json={"properties": properties},
        )
        self._raise_for_status(resp)

    async def replace_page_children(
        self, page_id: str, *, children: list[dict[str, Any]],
    ) -> None:
        """page 의 본문 블록을 통째로 교체.

        Notion API 가 "children 통째 교체" 를 직접 제공하지 않으므로,
        기존 children 을 모두 삭제 후 새로 append.
        """
        existing = await self._http.get(f"/blocks/{page_id}/children")
        self._raise_for_status(existing)
        for block in existing.json().get("results", []):
            del_resp = await self._http.delete(f"/blocks/{block['id']}")
            self._raise_for_status(del_resp)
        if children:
            append_resp = await self._http.patch(
                f"/blocks/{page_id}/children", json={"children": children},
            )
            self._raise_for_status(append_resp)

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = {"message": resp.text[:300]}
            raise NotionError(
                f"notion api {resp.status_code}: {body.get('message', body)}",
            )


# ─── 프로퍼티 / 블록 빌더 ───────────────────────────────


def text_prop(value: str) -> dict[str, Any]:
    """rich_text property 페이로드."""
    return {"rich_text": [{"text": {"content": value[:TEXT_CHUNK_MAX]}}]}


def title_prop(value: str) -> dict[str, Any]:
    """title property 페이로드."""
    return {"title": [{"text": {"content": value[:TEXT_CHUNK_MAX]}}]}


def select_prop(name: str) -> dict[str, Any]:
    """select property — 값이 비면 null 로 클리어.

    Notion Select 옵션 이름은 콤마(,) 사용 불가 → '·' 로 치환.
    """
    if not name:
        return {"select": None}
    safe = name.replace(",", "·")
    return {"select": {"name": safe}}


def date_prop(iso_date: str) -> dict[str, Any]:
    """date property — YYYY-MM-DD."""
    return {"date": {"start": iso_date}}


def number_prop(n: float) -> dict[str, Any]:
    return {"number": n}


def code_block(text: str) -> dict[str, Any]:
    """plain text 블록 (코드 블록으로 감싸 들여쓰기/포맷 보존)."""
    return {
        "object": "block",
        "type": "code",
        "code": {
            "language": "plain text",
            "rich_text": _split_rich_text(text),
        },
    }


def _split_rich_text(text: str) -> list[dict[str, Any]]:
    """2000자 제한 회피: 여러 rich_text 청크로 분할."""
    if not text:
        return []
    return [
        {"text": {"content": text[i : i + TEXT_CHUNK_MAX]}}
        for i in range(0, len(text), TEXT_CHUNK_MAX)
    ]


# ─── 필터 헬퍼 ────────────────────────────────────────


def filter_by_date_and_category(
    *, date_prop_name: str, date_iso: str,
    category_prop_name: str, category: str,
) -> dict[str, Any]:
    """(Date == date) AND (Category contains category) 필터."""
    return {
        "and": [
            {"property": date_prop_name, "date": {"equals": date_iso}},
            {
                "property": category_prop_name,
                "rich_text": {"equals": category},
            },
        ],
    }


def filter_by_title(
    *, title_prop_name: str, value: str,
) -> dict[str, Any]:
    """(Title == value) 필터 — Week Summary DB 같이 title 이 식별자 역할일 때."""
    return {
        "property": title_prop_name,
        "title": {"equals": value},
    }
