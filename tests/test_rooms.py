"""rooms 모듈 단위 테스트."""

from angeldash.rooms.registry import ROOMS, get_room_name, list_rooms_on_floor


def test_get_room_name_known_id_returns_korean_name():
    assert get_room_name("11") == "8층 3번 LAB"
    assert get_room_name("1") == "10층 대회의실"


def test_get_room_name_unknown_id_returns_unknown_label():
    assert get_room_name("999") == "알 수 없는 회의실(999)"


def test_list_rooms_on_floor_8_returns_six_rooms_in_id_order():
    rooms = list_rooms_on_floor(8)
    assert [r.id for r in rooms] == ["6", "7", "8", "9", "10", "11"]
    assert rooms[0].name == "8층 대회의실"


def test_rooms_dict_uses_string_keys():
    # GraphQL 응답이 ID 타입(string)이라 키도 string 으로 통일
    assert all(isinstance(k, str) for k in ROOMS)


def test_list_rooms_on_floor_12_returns_three_rooms_in_id_order():
    rooms = list_rooms_on_floor(12)
    assert [r.id for r in rooms] == ["12", "13", "14"]


def test_rooms_total_count_is_14():
    assert len(ROOMS) == 14
