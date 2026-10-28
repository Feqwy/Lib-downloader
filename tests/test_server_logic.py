import asyncio

import pytest

import server


@pytest.mark.parametrize(
    ("item", "fallback", "expected"),
    [
        ({"index": 5}, 1, 5),
        ({"index": "5"}, 1, 5),
        ({"item_number": 7}, 1, 7),
        ({"index": None, "item_number": 8}, 1, 8),
        # Current behavior: index == 0 is falsy, so item_number wins.
        ({"index": 0, "item_number": 9}, 1, 9),
        ({}, 3, 3),
        # Current behavior: a truthy invalid index does not fall back to item_number.
        ({"index": "x", "item_number": 4}, 3, 3),
        ({"index": ""}, 4, 4),
    ],
)
def test_get_chapter_index(item, fallback, expected):
    assert server._get_chapter_index(item, fallback) == expected


def test_extract_chapter_entries():
    items = [
        {"number": "1", "volume": "1", "index": 10},
        {"number": 2, "volume": 2, "item_number": 20},
        {"number": "3", "volume": "3"},
        {"number": None, "volume": "1"},
        {"number": "4", "volume": None},
        {"number": "5", "volume": "x"},
        "junk",
    ]

    assert server._extract_chapter_entries(items) == [
        {"index": 10, "volume": 1, "number_str": "1"},
        {"index": 20, "volume": 2, "number_str": "2"},
        {"index": 3, "volume": 3, "number_str": "3"},
    ]


@pytest.mark.parametrize(
    ("raw_data", "expected"),
    [
        ([{"number": "1"}], [{"number": "1"}]),
        ({"data": [{"number": "1"}]}, [{"number": "1"}]),
        ({"items": [{"number": "1"}]}, [{"number": "1"}]),
        ({"chapters": [{"number": "1"}]}, [{"number": "1"}]),
        ({"data": None, "items": [{"number": "1"}]}, [{"number": "1"}]),
        ({}, []),
        ("not-a-container", []),
        (123, []),
    ],
)
def test_extract_api_items(raw_data, expected):
    assert server._extract_api_items(raw_data) == expected


def test_get_local_chapters_volume_layout(tmp_path):
    (tmp_path / "Volume 01" / "Chapter 1").mkdir(parents=True)
    (tmp_path / "Volume 01" / "Chapter 2.cbz").write_bytes(b"cbz")
    (tmp_path / "Volume 02" / "Chapter 3").mkdir(parents=True)
    (tmp_path / "Volume 02" / "Chapter 3" / "001.jpg").write_bytes(b"jpg")

    assert server.get_local_chapters(tmp_path) == {(1, "1"), (1, "2"), (2, "3")}


def test_get_local_chapters_legacy_layout(tmp_path):
    (tmp_path / "Chapter 1").mkdir()
    (tmp_path / "Chapter 2.cbz").write_bytes(b"cbz")
    (tmp_path / "nested" / "Chapter 3").mkdir(parents=True)

    assert server.get_local_chapters(tmp_path) == {(0, "1"), (0, "2"), (0, "3")}


def test_get_local_chapters_missing_path(tmp_path):
    assert server.get_local_chapters(tmp_path / "missing") == set()


def test_create_initial_result():
    assert server._create_initial_result("slug", None) == {
        "slug": "slug",
        "server_count": 0,
        "local_count": 0,
        "missing": [],
        "missing_indices": [],
        "missing_entries": [],
        "status": "OK",
    }

    entries = [{"index": 1, "volume": 1, "number_str": "1"}]
    assert server._create_initial_result("slug", entries)["server_count"] == 1


def test_analyze_local_chapters_finds_missing_entries(tmp_path):
    (tmp_path / "Volume 01" / "Chapter 1").mkdir(parents=True)
    entries = [
        {"index": 1, "volume": 1, "number_str": "1"},
        {"index": 2, "volume": 1, "number_str": "2"},
    ]
    result = server._create_initial_result("slug", entries)

    asyncio.run(server._analyze_local_chapters(tmp_path, entries, result))

    assert result["local_count"] == 1
    assert result["missing_entries"] == [entries[1]]


def test_analyze_local_chapters_without_local_path():
    entries = [
        {"index": 1, "volume": 1, "number_str": "1"},
        {"index": 2, "volume": 1, "number_str": "2"},
    ]
    result = server._create_initial_result("slug", entries)

    asyncio.run(server._analyze_local_chapters(None, entries, result))

    assert result["local_count"] == 0
    assert result["missing_entries"] == entries


def test_analyze_local_chapters_with_empty_library(tmp_path):
    entries = [{"index": 1, "volume": 1, "number_str": "1"}]
    result = server._create_initial_result("slug", entries)

    asyncio.run(server._analyze_local_chapters(tmp_path, entries, result))

    assert result["local_count"] == 0
    assert result["missing_entries"] == entries


def test_token_validation_is_currently_disabled():
    # Known issue from AGENTS.md: token enforcement in the HTTP API is off.
    assert server._validate_token("hentailib.me", None) is True
    assert server._validate_token("mangalib.me", "bad-token") is True
