import json
import xml.etree.ElementTree as ET

import pytest

from config import Config
from metadata import MetadataGenerator
from models import ChapterInfo


def _generator() -> MetadataGenerator:
    return MetadataGenerator(Config(manga_slug="test-series", chapter_range=(1, 1)))


def _xml_field(root: ET.Element, tag: str):
    node = root.find(tag)
    return None if node is None else node.text


def test_create_chapter_comicinfo():
    info = ChapterInfo(
        number=5,
        number_str="5",
        index=1,
        volume=2,
        name="Глава 5",
        pages_count=10,
        series_title="Series",
        teams=["Team A", "Team B"],
        chapter_id="chapter-id",
    )

    root = ET.fromstring(_generator().create_chapter_comicinfo(info))

    assert _xml_field(root, "Title") == "Глава 5"
    assert _xml_field(root, "Series") == "Series"
    assert _xml_field(root, "Number") == "5"
    assert _xml_field(root, "Volume") == "2"
    assert _xml_field(root, "PageCount") == "10"
    assert _xml_field(root, "Summary") == "Chapter 5 of Series"
    assert _xml_field(root, "Writer") == "Team A, Team B"


def test_create_series_comicinfo_maps_metadata():
    series_info = {
        "summary": "Description",
        "authors": [{"name": "Author"}],
        "publisher": [{"name": "Publisher"}],
        "genres": [{"name": "Action"}, "Drama"],
        "type": {"label": "Манхва"},
        "ageRestriction": {"label": "18+"},
        "releaseDate": "2020-05-01",
    }

    root = ET.fromstring(_generator().create_series_comicinfo("Series", series_info))

    assert _xml_field(root, "Title") == "Series"
    assert _xml_field(root, "Series") == "Series"
    assert _xml_field(root, "Summary") == "Description"
    assert _xml_field(root, "Writer") == "Author"
    assert _xml_field(root, "Publisher") == "Publisher"
    assert _xml_field(root, "Genre") == "Action; Drama"
    assert _xml_field(root, "LanguageISO") == "ko"
    assert _xml_field(root, "Country") == "KR"
    assert _xml_field(root, "AgeRating") == "MATURE"
    # Current behavior writes releaseDate as-is, not just the year.
    assert _xml_field(root, "Year") == "2020-05-01"


def test_create_volume_comicinfo():
    series_info = {
        "authors": [{"name": "Author"}],
        "publisher": [{"name": "Publisher"}],
        "releaseDate": "2020",
        "type": {"label": "Манга"},
    }

    root = ET.fromstring(
        _generator().create_volume_comicinfo(3, "Series", 12, series_info)
    )

    assert _xml_field(root, "Title") == "Volume 03"
    assert _xml_field(root, "Volume") == "3"
    assert _xml_field(root, "Number") == "3"
    assert _xml_field(root, "Count") == "12"
    assert _xml_field(root, "Series") == "Series"
    assert _xml_field(root, "Summary") == "Volume 3 of Series"
    assert _xml_field(root, "Writer") == "Author"
    assert _xml_field(root, "Publisher") == "Publisher"
    assert _xml_field(root, "Year") == "2020"
    assert _xml_field(root, "LanguageISO") == "ja"


def test_create_series_json():
    series_info = {
        "id": "series-id",
        "name": "Series Name",
        "summary": "Description",
        "genres": [{"name": "Action"}],
        "tags": [{"name": "Drama"}],
        "authors": [{"name": "Author"}],
        "artists": [{"name": "Artist"}],
        "publisher": [{"name": "Publisher"}],
        "releaseDate": "2020-05-01",
        "type": {"label": "Манга"},
        "ageRestriction": {"label": "16+"},
        "status": {"id": 2},
    }

    result = json.loads(_generator().create_series_json("", series_info))

    assert result["name"] == "Series Name"
    assert result["title"] == "Series Name"
    assert result["comicid"] == "series-id"
    assert result["summary"] == "Description"
    assert result["description_text"] == "Description"
    assert result["description_formatted"] == "Description"
    assert result["status"] == "Completed"
    assert result["publisher"] == "Publisher"
    assert result["year"] == "2020"
    assert result["releaseDate"] == "2020-05-01"
    assert result["age_rating"] == "16+"
    assert result["language"] == "ja"
    assert result["genres"] == ["Action"]
    assert result["tags"] == ["Drama"]
    assert result["authors"] == [
        {"name": "Author", "role": "Writer"},
        {"name": "Artist", "role": "Artist"},
    ]


def test_create_series_json_uses_slug_and_defaults():
    result = json.loads(_generator().create_series_json("", {}))

    assert result["name"] == ""
    assert result["comicid"] == "test-series"
    assert result["status"] == "Hiatus"
    assert result["year"] == ""
    assert result["releaseDate"] == ""
    assert result["language"] == "en"
    assert result["genres"] == []
    assert result["tags"] == []
    assert result["authors"] == []


@pytest.mark.parametrize(
    ("series_info", "expected"),
    [
        ({"releaseDate": "2020-05-01"}, ("2020", "2020-05-01")),
        ({"releaseDate": "2020"}, ("2020", "2020-01-01")),
        ({"releaseDate": 2020}, ("2020", "2020-01-01")),
        ({"year": "2019"}, ("2019", "2019-01-01")),
        ({"startYear": 2019}, ("2019", "2019-01-01")),
        ({}, ("", "")),
    ],
)
def test_extract_year_info(series_info, expected):
    assert _generator()._extract_year_info(series_info) == expected


@pytest.mark.parametrize(
    ("type_label", "language", "country"),
    [
        ("Манхва", "ko", "KR"),
        ("Манга", "ja", "JP"),
        ("Manhua", "en", "US"),
    ],
)
def test_language_and_country_mapping(type_label, language, country):
    series_info = {"type": {"label": type_label}}

    assert _generator()._get_language(series_info) == language
    assert _generator()._get_country(series_info) == country


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("18", "18+"),
        ("Mature", "18+"),
        ("18+", "18+"),
        ("16", "16+"),
        ("Teen", "16+"),
        ("12+", "12+"),
    ],
)
def test_extract_age_rating(label, expected):
    assert _generator()._extract_age_rating({"ageRestriction": {"label": label}}) == expected


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("16+", "TEEN"),
        ("18+", "MATURE"),
        ("TEEN", "TEEN"),
        ("MATURE", "MATURE"),
        ("unknown", "EVERYONE"),
    ],
)
def test_comic_age_rating(label, expected):
    series_info = {"ageRestriction": {"label": label}}

    assert _generator()._get_comic_age_rating(series_info) == expected


def test_extract_names_accepts_dicts_strings_and_scalars():
    generator = _generator()

    assert generator._extract_names(
        [{"name": "A"}, {"label": "B"}, {"title": "C"}, "D", None]
    ) == ["A", "B", "C", "D"]
    assert generator._extract_names({"name": "Only"}) == ["Only"]
    assert generator._extract_names("Single") == ["Single"]
    assert generator._extract_names(None) == []


def test_get_first_string():
    generator = _generator()

    assert generator._get_first_string([{"name": "A"}]) == "A"
    assert generator._get_first_string(["B"]) == "B"
    assert generator._get_first_string({"label": "C"}) == "C"
    assert generator._get_first_string("D") == "D"
    assert generator._get_first_string([]) == ""
    assert generator._get_first_string(None) == ""


@pytest.mark.parametrize(
    ("status_id", "expected"),
    [(1, "Continuing"), (2, "Completed"), (0, "Hiatus"), (99, "Hiatus")],
)
def test_readable_status(status_id, expected):
    assert _generator()._get_readable_status({"status": {"id": status_id}}) == expected
