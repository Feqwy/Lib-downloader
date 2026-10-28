import pytest

import api_client
from api_client import MangaAPIClient
from config import Config
from models import ChapterInfo


def _client() -> MangaAPIClient:
    return MangaAPIClient(Config(manga_slug="series", chapter_range=(1, 1)))


def _chapter_info(number=5.5, index=10, volume=1) -> ChapterInfo:
    return ChapterInfo(
        number=number,
        number_str=str(number),
        index=index,
        volume=volume,
        name="",
        pages_count=0,
        series_title=None,
        teams=[],
    )


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ([{"number": "1"}, "junk"], [{"number": "1"}]),
        ({"data": [{"number": "1"}, "junk"]}, [{"number": "1"}]),
        ({"items": [{"number": "1"}]}, [{"number": "1"}]),
        ({"chapters": [{"number": "1"}]}, [{"number": "1"}]),
        ({"data": None, "items": [{"number": "1"}]}, [{"number": "1"}]),
        ({"data": "not-a-list"}, []),
        ({}, []),
        (None, []),
        ("string", []),
    ],
)
def test_extract_items_from_response(data, expected):
    assert _client()._extract_items_from_response(data) == expected


def test_build_chapters_map_from_items():
    items = [
        {"number": "1", "volume": "2"},
        {"number": "1.5", "volume": 3},
        {"number": None, "volume": 1},
        {"number": "x", "volume": 1},
        {"number": "2", "volume": "bad"},
        {"number": "1", "volume": 5},
    ]

    assert _client()._build_chapters_map_from_items(items) == {1.0: 5, 1.5: 3}


def test_create_chapter_info_from_item():
    item = {
        "number": "5",
        "volume": "2",
        "index": 10,
        "name": "Name",
        "pages_count": 7,
        "teams": [{"name": "Team"}],
        "id": "chapter-id",
    }

    info = _client()._create_chapter_info_from_item(item, fallback_idx=0)

    assert info == ChapterInfo(
        number=5,
        number_str="5",
        index=10,
        volume=2,
        name="Name",
        pages_count=7,
        series_title=None,
        teams=[{"name": "Team"}],
        chapter_id="chapter-id",
    )


def test_create_chapter_info_uses_fallback_index_and_volume_zero():
    info = _client()._create_chapter_info_from_item(
        {"number": "5.5", "volume": "bad"}, fallback_idx=4
    )

    assert info.number == 5.5
    assert info.number_str == "5.5"
    assert info.index == 5
    assert info.volume == 0
    assert info.name == ""
    assert info.pages_count == 0
    assert info.teams == []
    assert info.chapter_id is None


def test_create_chapter_info_skips_missing_number():
    assert _client()._create_chapter_info_from_item({"number": None}, fallback_idx=0) is None


def test_create_chapter_info_invalid_index_falls_back():
    info = _client()._create_chapter_info_from_item(
        {"number": "5", "volume": "2", "index": "bad"}, fallback_idx=1
    )

    assert info.index == 2


def test_create_chapter_info_zero_index_uses_item_number():
    info = _client()._create_chapter_info_from_item(
        {"number": "5", "volume": "2", "index": 0, "item_number": 7}, fallback_idx=0
    )

    assert info.index == 7


@pytest.mark.parametrize(
    ("extra", "indices", "numbers"),
    [
        ([1, 2.0, 1.5, "3.0", "bad"], {1, 2, 3}, {1.5}),
        ([], set(), set()),
        (None, set(), set()),
    ],
)
def test_parse_extra_chapters(extra, indices, numbers):
    assert _client()._parse_extra_chapters(extra) == (indices, numbers)


def test_should_include_chapter():
    client = _client()
    info = _chapter_info(number=5.5, index=10)

    assert client._should_include_chapter(info, 1, 3, set(), set()) is False
    assert client._should_include_chapter(info, 10, 10, set(), set()) is True
    assert client._should_include_chapter(info, 1, 3, {10}, set()) is True
    assert client._should_include_chapter(info, 1, 3, set(), {5.5}) is True


def test_calculate_retry_delay(monkeypatch):
    monkeypatch.setattr(api_client.random, "uniform", lambda a, b: 0.5)
    client = _client()

    assert client._calculate_retry_delay({}, 0) == pytest.approx(1.5)
    assert client._calculate_retry_delay({}, 3) == pytest.approx(8.8)
    assert client._calculate_retry_delay({}, 10) == pytest.approx(61.5)


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Retry-After": "5"}, 6.0),
        ({"Retry-After": "5.7"}, 6.0),
        ({"Retry-After": "bad"}, 1.5),
    ],
)
def test_calculate_retry_delay_uses_retry_after(monkeypatch, headers, expected):
    monkeypatch.setattr(api_client.random, "uniform", lambda a, b: 0.5)
    client = _client()

    assert client._calculate_retry_delay(headers, 0) == pytest.approx(expected)


def test_search_volume_in_metadata():
    client = _client()
    metadata = {
        "nested": [
            {"unrelated": True},
            {"chapter_number": "5", "volume": "3"},
            {"number": "5", "volume": 4},
        ]
    }

    assert client._search_volume_in_metadata(metadata, 5.0) == 3
    assert client._search_volume_in_metadata(metadata, 6.0) is None
