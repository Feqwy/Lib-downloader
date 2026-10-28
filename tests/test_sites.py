import pytest

import server
from sites import (
    DEFAULT_SITE,
    SITES,
    SOURCE_CHOICES,
    detect_cli_site,
    detect_domain,
    detect_site_from_url,
    get_api_config_for_domain,
    get_site,
    is_ranobelib,
    is_token_required,
)


EXPECTED_DOMAINS = {
    "v2.shlib.life",
    "mangalib.me",
    "mangalib.org",
    "ranobelib.me",
    "hentailib.me",
}


def test_registry_contains_all_supported_domains():
    assert set(SITES) == EXPECTED_DOMAINS
    assert DEFAULT_SITE.domain == "mangalib.me"


def test_api_dict_shape_is_unchanged():
    config = get_api_config_for_domain("ranobelib.me")

    assert config == {
        "api": "https://api.cdnlibs.org/api/manga",
        "referer": "https://ranobelib.me/",
        "image_host": "https://img3.mixlib.me",
        "site_type": "ranobelib",
    }


def test_unknown_domain_falls_back_to_mangalib():
    assert get_site("unknown.example") is DEFAULT_SITE
    assert get_api_config_for_domain("unknown.example") == get_api_config_for_domain(
        "mangalib.me"
    )


@pytest.mark.parametrize("domain", ["mangalib.me", "mangalib.org"])
def test_mangalib_image_host(domain):
    # img3.mixlib.me answers with a certificate error; MangaLib images are
    # served from img3.cdnlibs.org.
    assert get_api_config_for_domain(domain)["image_host"] == (
        "https://img3.cdnlibs.org"
    )


def test_server_api_configs_are_built_from_registry():
    expected = {
        domain: {"api": site.api, "referer": site.referer}
        for domain, site in SITES.items()
    }

    assert server.API_CONFIGS == expected


def test_source_choices_order_and_labels():
    assert SOURCE_CHOICES == (
        ("mangalib.me", "MangaLib"),
        ("v2.shlib.life", "SlashLib"),
        ("ranobelib.me", "RanobeLib"),
        ("hentailib.me", "HentaiLib"),
    )


def test_detect_domain():
    assert detect_domain("https://v2.shlib.life/manga/1") == "v2.shlib.life"
    assert detect_domain("https://shlib.life/manga/1") == "v2.shlib.life"
    assert detect_domain("https://hentailib.me/manga/1") == "hentailib.me"
    assert detect_domain("https://ranobelib.me/manga/1") == "ranobelib.me"
    assert detect_domain("https://mangalib.me/manga/1") == "mangalib.me"
    assert detect_domain("https://mangalib.org/manga/1") == "mangalib.org"
    assert detect_domain("https://example.com/manga/1") is None


def test_detect_site_from_url_includes_all_registry_domains():
    assert detect_site_from_url("https://v2.shlib.life/x").site_type == "shlib"
    assert detect_site_from_url("https://hentailib.me/x").site_type == "hentailib"
    assert detect_site_from_url("https://ranobelib.me/x").site_type == "ranobelib"
    assert detect_site_from_url("https://mangalib.org/x").site_type == "mangalib"
    assert detect_site_from_url("https://example.com/x") is DEFAULT_SITE


def test_detect_cli_site_preserves_old_fallback_for_mangalib_org():
    assert detect_cli_site("https://v2.shlib.life/x").domain == "v2.shlib.life"
    assert detect_cli_site("https://hentailib.me/x").domain == "hentailib.me"
    assert detect_cli_site("https://ranobelib.me/x").domain == "ranobelib.me"
    assert detect_cli_site("https://mangalib.me/x") is DEFAULT_SITE
    # The CLI never had a mangalib.org branch and used mangalib.me instead.
    assert detect_cli_site("https://mangalib.org/x") is DEFAULT_SITE
    assert detect_cli_site("https://example.com/x") is DEFAULT_SITE


def test_predicates_are_backed_by_registry():
    assert is_token_required("v2.shlib.life") is True
    assert is_token_required("shlib.life") is True
    assert is_token_required("mangalib.me") is True
    assert is_token_required("mangalib.org") is True
    assert is_token_required("ranobelib.me") is True
    assert is_token_required("hentailib.me") is True
    assert is_token_required("example.com") is False

    assert is_ranobelib("ranobelib.me") is True
    assert is_ranobelib("https://ranobelib.me/x") is True
    assert is_ranobelib("mangalib.me") is False
    assert is_ranobelib("example.com") is False
