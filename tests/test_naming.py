import pytest

from config import Config
from downloader import ChapterDownloader
from models import ChapterInfo
from naming import chapter_dir_name, series_title_from_meta, volume_dir_name


def _downloader(tmp_path, **config_overrides) -> ChapterDownloader:
    cfg = Config(
        manga_slug="test-series",
        chapter_range=(1, 1),
        output_dir=tmp_path,
        **config_overrides,
    )
    return ChapterDownloader(cfg)


def _chapter(volume=2, number=5, number_str="5") -> ChapterInfo:
    return ChapterInfo(
        number=number,
        number_str=number_str,
        index=1,
        volume=volume,
        name="",
        pages_count=1,
        series_title=None,
        teams=[],
    )


@pytest.mark.parametrize(
    ("volume", "expected"),
    [(1, "Volume 01"), (2, "Volume 02"), (12, "Volume 12"), (100, "Volume 100")],
)
def test_volume_dir_name(volume, expected):
    assert volume_dir_name(volume) == expected


@pytest.mark.parametrize(
    ("chapter", "expected"),
    [
        (1, "Chapter 1"),
        (5, "Chapter 5"),
        ("1.5", "Chapter 1.5"),
        (2.0, "Chapter 2"),
        ("05", "Chapter 05"),
    ],
)
def test_chapter_dir_name(chapter, expected):
    assert chapter_dir_name(chapter) == expected


@pytest.mark.parametrize(
    ("series_meta", "fallback", "override", "expected"),
    [
        ({"name": "Name", "rus_name": "Rus"}, "slug", None, "Name"),
        ({"rus_name": "Rus", "eng_name": "Eng"}, "slug", None, "Rus"),
        ({"eng_name": "Eng"}, "slug", None, "Eng"),
        ({}, "slug", None, "slug"),
        ({"name": "Name"}, "slug", "Override", "Override"),
    ],
)
def test_series_title_from_meta(series_meta, fallback, override, expected):
    assert series_title_from_meta(series_meta, fallback, override) == expected


def test_volume_folder_and_cbz_names_match_previous_layout(tmp_path):
    downloader = _downloader(tmp_path, pack_cbz=True, generate_metadata=False)
    info = _chapter()
    series_folder = tmp_path / "Series"
    series_folder.mkdir()
    src_dir = tmp_path / "_tmp_ch5"
    src_dir.mkdir()
    (src_dir / "001.jpg").write_bytes(b"jpg")

    downloader._process_volumes({2: [(src_dir, info)]}, series_folder, "Series", {})

    assert sorted(p.name for p in series_folder.iterdir()) == ["Volume 02"]
    vol_folder = series_folder / "Volume 02"
    assert sorted(p.name for p in vol_folder.iterdir()) == ["Chapter 5.cbz"]


def test_volume_folder_and_chapter_folder_names_match_previous_layout(tmp_path):
    downloader = _downloader(tmp_path, pack_cbz=False, generate_metadata=False)
    info = _chapter(volume=12, number=3, number_str="3")
    series_folder = tmp_path / "Series"
    series_folder.mkdir()
    src_dir = tmp_path / "_tmp_ch3"
    src_dir.mkdir()
    (src_dir / "001.jpg").write_bytes(b"jpg")

    downloader._process_volumes({12: [(src_dir, info)]}, series_folder, "Series", {})

    assert sorted(p.name for p in series_folder.iterdir()) == ["Volume 12"]
    vol_folder = series_folder / "Volume 12"
    assert sorted(p.name for p in vol_folder.iterdir()) == ["Chapter 3"]
    assert (vol_folder / "Chapter 3" / "001.jpg").read_bytes() == b"jpg"
