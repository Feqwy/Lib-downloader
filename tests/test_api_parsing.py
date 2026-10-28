import pytest

import server
from api_client import MangaAPIClient
from api_parsing import extract_items_from_response, get_chapter_index
from config import Config


def _client() -> MangaAPIClient:
    return MangaAPIClient(Config(manga_slug="series", chapter_range=(1, 1)))


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ([{"number": "1"}], [{"number": "1"}]),
        ([{"number": "1"}, "junk", None], [{"number": "1"}]),
        ({"data": [{"number": "1"}, "junk"]}, [{"number": "1"}]),
        ({"items": [{"number": "1"}]}, [{"number": "1"}]),
        ({"chapters": [{"number": "1"}]}, [{"number": "1"}]),
        ({"data": None, "items": [{"number": "1"}]}, [{"number": "1"}]),
        ({"data": "not-a-list", "chapters": [{"number": "1"}]}, [{"number": "1"}]),
        ({"data": "not-a-list"}, []),
        ({}, []),
        (None, []),
        ("string", []),
        (123, []),
    ],
)
def test_extract_items_from_response(data, expected):
    assert extract_items_from_response(data) == expected


@pytest.mark.parametrize(
    ("item", "fallback", "expected"),
    [
        ({"index": 5}, 1, 5),
        ({"index": "5"}, 1, 5),
        ({"item_number": 7}, 1, 7),
        ({"index": None, "item_number": 8}, 1, 8),
        # index == 0 is falsy, so item_number wins (current behavior).
        ({"index": 0, "item_number": 9}, 1, 9),
        ({}, 3, 3),
        ({"index": "x", "item_number": 4}, 3, 3),
        ({"index": ""}, 4, 4),
        ({"index": None}, 2, 2),
    ],
)
def test_get_chapter_index(item, fallback, expected):
    assert get_chapter_index(item, fallback) == expected


def test_server_and_client_share_response_parser():
    data = {"data": [{"number": "1"}, "junk", None]}

    assert server._extract_api_items(data) == [{"number": "1"}]
    assert _client()._extract_items_from_response(data) == [{"number": "1"}]
    assert server._extract_api_items("not-a-container") == []
