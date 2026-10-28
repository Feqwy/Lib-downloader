"""Golden tests for the ranobelib chapter files.

These pin the exact bytes of ``chapter.html`` and ``chapter.txt`` produced by
the current code, so later refactoring of the text output cannot change the
default result silently.
"""

import asyncio
from pathlib import Path

import pytest

from config import Config
from downloader import ChapterDownloader
from text_render import parse_text_output, resolve_text_output


EXPECTED_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Глава 1</title>
    <style>
        body {
            font-family: 'Georgia', 'Times New Roman', serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.8;
            color: #333;
        }
        h1, h2, h3 {
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }
        p {
            margin-bottom: 1em;
            text-align: justify;
        }
    </style>
</head>
<body>
    <h1>Глава 1</h1>
    <p>Hello</p>
<h2>Title</h2>
</body>
</html>"""

EXPECTED_TXT = "Глава 1\n=======\n\nHello\n\nTitle"


def _downloader(tmp_path: Path, **overrides) -> ChapterDownloader:
    cfg = Config(
        manga_slug="test-series",
        chapter_range=(1, 1),
        output_dir=tmp_path,
        site_type="ranobelib",
        **overrides,
    )
    return ChapterDownloader(cfg)


def _sample_content() -> dict:
    return {
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Hello", "marks": []},
                ],
            },
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Title"}],
            },
        ]
    }


def test_chapter_files_golden(tmp_path):
    downloader = _downloader(tmp_path)

    downloader._write_ranobelib_files(
        tmp_path,
        "<p>Hello</p>\n<h2>Title</h2>",
        "Hello\n\nTitle",
        "Глава 1",
        1.5,
    )

    assert (tmp_path / "chapter.html").read_text(encoding="utf-8") == EXPECTED_HTML
    assert (tmp_path / "chapter.txt").read_text(encoding="utf-8") == EXPECTED_TXT


def test_save_ranobelib_content_golden(tmp_path):
    downloader = _downloader(tmp_path)

    asyncio.run(
        downloader._save_ranobelib_content(
            tmp_path, {"content": _sample_content()}, "Глава 1", 1.5
        )
    )

    assert (tmp_path / "chapter.html").read_text(encoding="utf-8") == EXPECTED_HTML
    # The heading item adds its own leading newline on top of the paragraph
    # separator; this is the current converter behavior and is pinned here.
    assert (tmp_path / "chapter.txt").read_text(encoding="utf-8") == (
        "Глава 1\n=======\n\nHello\n\n\nTitle"
    )


def test_chapter_files_use_fallback_title(tmp_path):
    downloader = _downloader(tmp_path)

    downloader._write_ranobelib_files(tmp_path, "<p>Body</p>", "Body", "", 3)

    html = (tmp_path / "chapter.html").read_text(encoding="utf-8")
    txt = (tmp_path / "chapter.txt").read_text(encoding="utf-8")

    assert "<title>Chapter 3</title>" in html
    assert "<h1>Chapter 3</h1>" in html
    assert txt.startswith("Chapter 3\n=========\n\nBody")


@pytest.mark.parametrize(
    ("text_output", "expect_html", "expect_txt"),
    [
        ("both", True, True),
        ("txt", False, True),
        ("html", True, False),
    ],
)
def test_text_output_writes_selected_files(
    tmp_path, text_output, expect_html, expect_txt
):
    downloader = _downloader(tmp_path, text_output=text_output)

    downloader._write_ranobelib_files(
        tmp_path,
        "<p>Hello</p>\n<h2>Title</h2>",
        "Hello\n\nTitle",
        "Глава 1",
        1.5,
    )

    html_path = tmp_path / "chapter.html"
    txt_path = tmp_path / "chapter.txt"

    assert html_path.exists() is expect_html
    assert txt_path.exists() is expect_txt
    if expect_html:
        assert html_path.read_text(encoding="utf-8") == EXPECTED_HTML
    if expect_txt:
        assert txt_path.read_text(encoding="utf-8") == EXPECTED_TXT


def test_unknown_text_output_falls_back_to_both(tmp_path, capsys):
    downloader = _downloader(tmp_path, text_output="pdf")

    downloader._write_ranobelib_files(tmp_path, "<p>Hello</p>", "Hello", "Глава 1", 1)

    assert downloader.text_output == "both"
    assert (tmp_path / "chapter.html").exists()
    assert (tmp_path / "chapter.txt").exists()
    assert "Неизвестный формат текста 'pdf', используется both" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("both", "both"),
        ("txt", "txt"),
        ("html", "html"),
        ("", "both"),
        ("pdf", "both"),
        (None, "both"),
    ],
)
def test_resolve_text_output(value, expected):
    assert resolve_text_output(value) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", "both"),
        ("2", "txt"),
        ("3", "html"),
        ("", "both"),
        (" 2 ", "txt"),
        ("9", "both"),
        ("txt", "both"),
        (None, "both"),
    ],
)
def test_parse_text_output(raw, expected):
    assert parse_text_output(raw) == expected
