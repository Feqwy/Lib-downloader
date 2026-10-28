from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class SiteConfig:
    domain: str
    label: str
    api: str
    referer: str
    image_host: str
    site_type: str
    token_hints: Tuple[str, ...]

    def as_api_dict(self) -> dict:
        return {
            "api": self.api,
            "referer": self.referer,
            "image_host": self.image_host,
            "site_type": self.site_type,
        }


_SHARED_TOKEN_HINT = "Требуется Bearer Token (можно получить через расширение)"
_MANGA_TOKEN_HINT = "Для доступа к 18+ контенту требуется Bearer Token"
_RANOBE_TOKEN_HINTS = (
    "Текстовые главы, без изображений",
    "Для доступа к 18+ контенту требуется Bearer Token",
)


SITES: Dict[str, SiteConfig] = {
    "v2.shlib.life": SiteConfig(
        domain="v2.shlib.life",
        label="SlashLib",
        api="https://hapi.hentaicdn.org/api/manga",
        referer="https://v2.shlib.life/",
        image_host="https://img3.hentaicdn.org",
        site_type="shlib",
        token_hints=(_SHARED_TOKEN_HINT,),
    ),
    "hentailib.me": SiteConfig(
        domain="hentailib.me",
        label="HentaiLib",
        api="https://hapi.hentaicdn.org/api/manga",
        referer="https://hentailib.me/",
        image_host="https://img3.hentaicdn.org",
        site_type="hentailib",
        token_hints=(_SHARED_TOKEN_HINT,),
    ),
    "ranobelib.me": SiteConfig(
        domain="ranobelib.me",
        label="RanobeLib",
        api="https://api.cdnlibs.org/api/manga",
        referer="https://ranobelib.me/",
        image_host="https://img3.mixlib.me",
        site_type="ranobelib",
        token_hints=_RANOBE_TOKEN_HINTS,
    ),
    "mangalib.org": SiteConfig(
        domain="mangalib.org",
        label="MangaLib",
        api="https://api.cdnlibs.org/api/manga",
        referer="https://mangalib.org/",
        image_host="https://img3.cdnlibs.org",
        site_type="mangalib",
        token_hints=(_MANGA_TOKEN_HINT,),
    ),
    "mangalib.me": SiteConfig(
        domain="mangalib.me",
        label="MangaLib",
        api="https://api.cdnlibs.org/api/manga",
        referer="https://mangalib.me/",
        image_host="https://img3.cdnlibs.org",
        site_type="mangalib",
        token_hints=(_MANGA_TOKEN_HINT,),
    ),
}

DEFAULT_SITE = SITES["mangalib.me"]

SOURCE_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("mangalib.me", "MangaLib"),
    ("v2.shlib.life", "SlashLib"),
    ("ranobelib.me", "RanobeLib"),
    ("hentailib.me", "HentaiLib"),
)

CLI_DETECT_ORDER: Tuple[str, ...] = (
    "v2.shlib.life",
    "hentailib.me",
    "ranobelib.me",
)


def get_site(domain: str) -> SiteConfig:
    return SITES.get(domain, DEFAULT_SITE)


def get_api_config_for_domain(domain: str) -> dict:
    return get_site(domain).as_api_dict()


def detect_domain(value: str) -> Optional[str]:
    for domain in SITES:
        needle = "shlib.life" if domain == "v2.shlib.life" else domain
        if needle in value:
            return domain
    return None


def detect_site_from_url(url: str) -> SiteConfig:
    return SITES.get(detect_domain(url) or "", DEFAULT_SITE)


def detect_cli_site(url: str) -> SiteConfig:
    for domain in CLI_DETECT_ORDER:
        if domain in url:
            return SITES[domain]
    return DEFAULT_SITE


def is_token_required(value: str) -> bool:
    return detect_domain(value) is not None


def is_ranobelib(value: str) -> bool:
    return detect_domain(value) == "ranobelib.me"
