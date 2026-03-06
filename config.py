from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List


@dataclass
class Config:
    manga_slug: str
    chapter_range: Tuple[int, int]
    extra_chapters: Optional[List[float]] = None  # поддержка дробных / дополнительных глав
    series_title_override: Optional[str] = None
    volume_override: Optional[int] = None
    output_dir: Path = Path("downloads")
    max_concurrent_chapters: int = 3
    max_concurrent_images: int = 8
    request_delay: float = 0.03
    fallback_volume_range: Tuple[int, int] = (1, 15)
    cleanup_temp: bool = True
    pack_cbz: bool = True
    generate_metadata: bool = True
    api_base: str = "https://api.cdnlibs.org/api/manga"
    image_host: str = "https://img3.mixlib.me"
    referer: str = "https://mangalib.me/"
    auth_token: Optional[str] = None
    site_type: str = "mangalib"

    @property
    def is_ranobelib(self) -> bool:
        return self.site_type == "ranobelib"

    @property
    def is_hentailib(self) -> bool:
        return self.site_type == "hentailib"