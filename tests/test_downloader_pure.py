import pytest

from config import Config
from downloader import (
    ChapterDownloader,
    _apply_text_marks,
    _extract_heading_text,
    convert_ranobelib_content_to_html,
    convert_ranobelib_content_to_text,
)
from models import ChapterInfo


def _downloader(tmp_path, **config_overrides) -> ChapterDownloader:
    cfg = Config(
        manga_slug="test-series",
        chapter_range=(1, 1),
        output_dir=tmp_path,
        **config_overrides,
    )
    return ChapterDownloader(cfg)


def _sample_content() -> dict:
    return {
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Hello", "marks": []},
                    {
                        "type": "text",
                        "text": " world",
                        "marks": [{"type": "bold"}],
                    },
                    {"type": "text", "text": "!", "marks": [{"type": "italic"}]},
                ],
            },
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Title"}],
            },
            {"type": "hardBreak"},
        ]
    }


def test_convert_ranobelib_content_to_html():
    assert convert_ranobelib_content_to_html(_sample_content()) == (
        "<p>Hello<strong> world</strong><em>!</em></p>\n"
        "<h2>Title</h2>\n"
        "<br/>"
    )


def test_convert_ranobelib_content_to_text():
    assert convert_ranobelib_content_to_text(_sample_content()) == (
        "Hello world!\n\n\nTitle"
    )


@pytest.mark.parametrize("content", [None, {}, {"content": []}, "text"])
def test_ranobelib_converters_handle_empty_content(content):
    assert convert_ranobelib_content_to_html(content) == ""
    assert convert_ranobelib_content_to_text(content) == ""


def test_apply_text_marks_order():
    marks = [
        {"type": "bold"},
        {"type": "italic"},
        {"type": "underline"},
        {"type": "unknown"},
    ]

    assert _apply_text_marks("text", marks) == "<u><em><strong>text</strong></em></u>"


def test_extract_heading_text():
    item = {
        "content": [
            {"type": "text", "text": "A"},
            {"type": "mention", "text": "ignored"},
            {"type": "text", "text": "B"},
        ]
    }

    assert _extract_heading_text(item) == "AB"


def test_count_ranobelib_pages(tmp_path):
    downloader = _downloader(tmp_path)
    data = {
        "content": {
            "content": [
                {"type": "paragraph"},
                {"type": "paragraph"},
                {"type": "heading"},
            ]
        }
    }

    assert downloader._count_ranobelib_pages(data) == 2
    assert downloader._count_ranobelib_pages({"content": {}}) == 1


@pytest.mark.parametrize(
    ("series_meta", "expected"),
    [
        ({"name": "Name", "rus_name": "Rus", "eng_name": "Eng"}, "Name"),
        ({"rus_name": "Rus", "eng_name": "Eng"}, "Rus"),
        ({"eng_name": "Eng"}, "Eng"),
        ({}, "test-series"),
    ],
)
def test_determine_series_title(tmp_path, series_meta, expected):
    assert _downloader(tmp_path)._determine_series_title(series_meta) == expected


def test_determine_series_title_override(tmp_path):
    downloader = _downloader(tmp_path, series_title_override="Override")

    assert downloader._determine_series_title({"name": "Name"}) == "Override"


@pytest.mark.parametrize(
    ("volume", "chapter", "expected"),
    [
        (1, "1.5", ("Series", "Volume 01", "Chapter 1.5")),
        (12, 3, ("Series", "Volume 12", "Chapter 3")),
        (1, "5", ("A_B", "Volume 01", "Chapter 5")),
    ],
)
def test_build_final_chapter_dir_layout(tmp_path, volume, chapter, expected):
    series_title = "A/B" if expected[0] == "A_B" else "Series"
    downloader = _downloader(tmp_path)

    result = downloader._build_final_chapter_dir(series_title, volume, chapter)

    assert result == tmp_path.joinpath(*expected)
    assert result.is_dir()


def test_extract_chapter_data_from_chapter_info(tmp_path):
    info = ChapterInfo(
        number=5,
        number_str="5.5",
        index=10,
        volume=2,
        name="",
        pages_count=0,
        series_title=None,
        teams=[],
    )

    assert _downloader(tmp_path)._extract_chapter_data(info) == (5, "5.5", 2, 10)


def test_extract_chapter_data_from_number(tmp_path):
    assert _downloader(tmp_path)._extract_chapter_data(5.5) == (5.5, 5.5, None, 0)


def test_get_chapter_number_for_error(tmp_path):
    downloader = _downloader(tmp_path)
    info = ChapterInfo(
        number=5,
        number_str="5.5",
        index=1,
        volume=1,
        name="",
        pages_count=0,
        series_title=None,
        teams=[],
    )

    assert downloader._get_chapter_number_for_error(info) == "5.5"
    assert downloader._get_chapter_number_for_error(7) == 7
