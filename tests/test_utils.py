import pytest

from utils import (
    build_image_url,
    clean_chapter_name,
    extract_slug_from_url,
    format_chapter_number,
    get_api_config_for_domain,
    is_ranobelib,
    is_token_required,
    parse_chapter_number,
    parse_float,
    parse_yes_no,
    sanitize_filename,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.5", 1.5),
        ("1,5", 1.5),
        (" 2 ", 2.0),
        ("0", 0.0),
        ("abc", None),
        ("", None),
        ("1,2,3", None),
    ],
)
def test_parse_float(value, expected):
    assert parse_float(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (5, 5),
        (5.5, 5.5),
        ("5", 5),
        ("5.5", 5.5),
        ("5,5", 5.5),
        ("abc", None),
        ("", None),
    ],
)
def test_parse_chapter_number(value, expected):
    assert parse_chapter_number(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5, "5"),
        (5.0, "5"),
        (5.5, "5.5"),
        (0.5, "0.5"),
        (10.25, "10.25"),
        (1.2300, "1.23"),
        (100.0, "100"),
        ("5.5", "5.5"),
        ("abc", "abc"),
    ],
)
def test_format_chapter_number(value, expected):
    assert format_chapter_number(value) == expected


def test_sanitize_filename_replaces_forbidden_characters():
    result = sanitize_filename('a/b:c*?"<>|')

    assert not any(ch in result for ch in '\\/*?:"<>|')
    assert result.startswith("a_b_c")


def test_sanitize_filename_strips_and_truncates():
    assert sanitize_filename("  name  ") == "name"
    assert sanitize_filename("") == ""
    assert len(sanitize_filename("x" * 300)) == 200


def test_clean_chapter_name_removes_numbers_and_numbered_parentheses():
    assert clean_chapter_name("") == ""
    assert clean_chapter_name("Chapter 12") == "Chapter"
    assert clean_chapter_name("Chapter 12 (том 3)") == "Chapter"
    assert clean_chapter_name("Special (no digits)") == "Special (no digits)"


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        ("y", "n", True),
        ("Y", "n", True),
        ("yes", "n", True),
        ("н", "n", True),
        ("n", "y", False),
        ("N", "y", False),
        ("no", "y", False),
        ("т", "y", False),
        ("", "y", True),
        ("", "n", False),
        ("maybe", "n", False),
        ("maybe", "y", True),
    ],
)
def test_parse_yes_no(value, default, expected):
    assert parse_yes_no(value, default) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://mangalib.me/solo-leveling", "solo-leveling"),
        ("https://mangalib.me/solo-leveling/", "solo-leveling"),
        ("https://mangalib.me/solo-leveling?foo=1", "solo-leveling"),
        ("https://mangalib.me/solo-leveling/?foo=1", "solo-leveling"),
        ("slug", "slug"),
        # Current fallback: a URL without a path yields the host as the slug.
        ("https://mangalib.me", "mangalib.me"),
        ("", "unknown"),
    ],
)
def test_extract_slug_from_url(url, expected):
    assert extract_slug_from_url(url) == expected


@pytest.mark.parametrize(
    ("path", "host", "expected"),
    [
        ("//img/1.jpg", "https://host", "https://host/img/1.jpg"),
        ("img/1.jpg", "https://host", "https://host/img/1.jpg"),
        ("/img/1.jpg", "https://host", "https://host/img/1.jpg"),
        ("https://cdn/1.jpg", "https://host", "https://cdn/1.jpg"),
    ],
)
def test_build_image_url(path, host, expected):
    assert build_image_url(path, host) == expected


@pytest.mark.parametrize("path", ["", None])
def test_build_image_url_rejects_empty_path(path):
    with pytest.raises(ValueError):
        build_image_url(path, "https://host")


EXPECTED_SITE_CONFIGS = {
    "v2.shlib.life": {
        "api": "https://hapi.hentaicdn.org/api/manga",
        "referer": "https://v2.shlib.life/",
        "image_host": "https://img3.hentaicdn.org",
        "site_type": "shlib",
    },
    "mangalib.me": {
        "api": "https://api.cdnlibs.org/api/manga",
        "referer": "https://mangalib.me/",
        "image_host": "https://img3.cdnlibs.org",
        "site_type": "mangalib",
    },
    "mangalib.org": {
        "api": "https://api.cdnlibs.org/api/manga",
        "referer": "https://mangalib.org/",
        "image_host": "https://img3.cdnlibs.org",
        "site_type": "mangalib",
    },
    "ranobelib.me": {
        "api": "https://api.cdnlibs.org/api/manga",
        "referer": "https://ranobelib.me/",
        "image_host": "https://img3.mixlib.me",
        "site_type": "ranobelib",
    },
    "hentailib.me": {
        "api": "https://hapi.hentaicdn.org/api/manga",
        "referer": "https://hentailib.me/",
        "image_host": "https://img3.hentaicdn.org",
        "site_type": "hentailib",
    },
}


@pytest.mark.parametrize(("domain", "expected"), EXPECTED_SITE_CONFIGS.items())
def test_get_api_config_for_known_domain(domain, expected):
    assert get_api_config_for_domain(domain) == expected


def test_get_api_config_falls_back_to_mangalib():
    assert get_api_config_for_domain("unknown.example") == EXPECTED_SITE_CONFIGS["mangalib.me"]


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("v2.shlib.life", True),
        ("mangalib.me", True),
        ("mangalib.org", True),
        ("ranobelib.me", True),
        ("hentailib.me", True),
        ("unknown.example", False),
    ],
)
def test_is_token_required(domain, expected):
    assert is_token_required(domain) is expected


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("ranobelib.me", True),
        ("https://ranobelib.me/foo", True),
        ("mangalib.me", False),
        ("unknown.example", False),
    ],
)
def test_is_ranobelib(domain, expected):
    assert is_ranobelib(domain) is expected
