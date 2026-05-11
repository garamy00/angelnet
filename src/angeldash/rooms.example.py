"""회의실 ID-이름 정적 매핑 및 층별 조회 헬퍼.

NOTE: 이 파일은 example template. 실제 사용 시 `rooms.py` 로 복사하고
본인 환경의 회의실 데이터로 교체하라.
`rooms.py` 는 .gitignore 에 등록되어 git 추적되지 않는다.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Room:
    """회의실 한 건을 나타내는 불변 데이터 객체."""

    id: str
    name: str
    floor: int


# 예시 데이터 — 실제 사용 시 본인 환경의 회의실로 교체
_ROOM_TABLE: list[tuple[str, str, int]] = [
    ("1", "Floor 10 Conference Room A", 10),
    ("2", "Floor 10 Conference Room 1", 10),
    ("3", "Floor 10 Conference Room 2", 10),
    ("6", "Floor 8 Conference Room A", 8),
    ("7", "Floor 8 Conference Room 1", 8),
    ("8", "Floor 8 Conference Room 2", 8),
    ("10", "Floor 8 LAB 1", 8),
    ("11", "Floor 8 LAB 2", 8),
]

ROOMS: dict[str, Room] = {
    rid: Room(id=rid, name=name, floor=floor) for rid, name, floor in _ROOM_TABLE
}


def get_room_name(room_id: str) -> str:
    """회의실 ID 로 한글 이름을 반환한다. 없으면 fallback 라벨."""
    room = ROOMS.get(room_id)
    return room.name if room else f"Unknown Room ({room_id})"


def list_rooms_on_floor(floor: int) -> list[Room]:
    """특정 층의 회의실을 ID 숫자 순으로 반환한다. 없는 층이면 빈 리스트를 반환한다."""
    rooms = [r for r in ROOMS.values() if r.floor == floor]
    return sorted(rooms, key=lambda r: int(r.id))
