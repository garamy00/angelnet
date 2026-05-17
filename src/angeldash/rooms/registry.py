"""회의실 ID-이름 정적 매핑 및 층별 조회 헬퍼."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Room:
    """회의실 한 건을 나타내는 불변 데이터 객체."""

    id: str
    name: str
    floor: int


# 기존 archive/angel_add 의 get_room_name 케이스를 그대로 옮김
_ROOM_TABLE: list[tuple[str, str, int]] = [
    ("1", "10층 대회의실", 10),
    ("2", "10층 1번 회의실", 10),
    ("3", "10층 2번 회의실", 10),
    ("4", "10층 3번 회의실", 10),
    ("5", "10층 4번 회의실", 10),
    ("6", "8층 대회의실", 8),
    ("7", "8층 1번 회의실", 8),
    ("8", "8층 2번 회의실", 8),
    ("9", "8층 3번 회의실", 8),
    ("10", "8층 2번 LAB", 8),
    ("11", "8층 3번 LAB", 8),
    ("12", "12층 2번 회의실", 12),
    ("13", "12층 3번 회의실", 12),
    ("14", "12층 4번 회의실", 12),
]

ROOMS: dict[str, Room] = {
    rid: Room(id=rid, name=name, floor=floor) for rid, name, floor in _ROOM_TABLE
}


def get_room_name(room_id: str) -> str:
    """회의실 ID 로 한글 이름을 반환한다. 없으면 fallback 라벨."""
    room = ROOMS.get(room_id)
    return room.name if room else f"알 수 없는 회의실({room_id})"


def list_rooms_on_floor(floor: int) -> list[Room]:
    """특정 층의 회의실을 ID 숫자 순으로 반환한다. 없는 층이면 빈 리스트를 반환한다."""
    rooms = [r for r in ROOMS.values() if r.floor == floor]
    return sorted(rooms, key=lambda r: int(r.id))
