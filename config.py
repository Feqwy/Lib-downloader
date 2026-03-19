from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List


# Конфигурация загрузки манги.
@dataclass
class Config:
    
    manga_slug: str
    chapter_range: Tuple[int, int]
    extra_chapters: Optional[List[float]] = None
    series_title_override: Optional[str] = None
    volume_override: Optional[int] = None
    
    output_dir: Path = field(default_factory=lambda: Path("downloads"))
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
        # Проверяет, является ли источник RanobeLib.
        return self.site_type == "ranobelib"

    @property
    def is_hentailib(self) -> bool:
        # Проверяет, является ли источник HentaiLib.
        return self.site_type == "hentailib"

    @property
    def is_slashlib(self) -> bool:
        # Проверяет, является ли источник SlashLib.
        return self.site_type == "shlib"

    def validate(self) -> List[str]:
        # Проверяет корректность конфигурации.
        # Список ошибок валидации (пустой, если всё корректно).
        errors = []
        
        if not self.manga_slug:
            errors.append("manga_slug не может быть пустым")
        
        start, end = self.chapter_range
        if start > end and start != 0 and end != 0:
            errors.append(f"Некорректный диапазон глав: {start}-{end}")
        
        if self.max_concurrent_chapters < 1:
            errors.append("max_concurrent_chapters должен быть >= 1")
        
        if self.max_concurrent_images < 1:
            errors.append("max_concurrent_images должен быть >= 1")
        
        if self.request_delay < 0:
            errors.append("request_delay не может быть отрицательным")
        
        vol_start, vol_end = self.fallback_volume_range
        if vol_start > vol_end:
            errors.append(f"Некорректный диапазон томов: {vol_start}-{vol_end}")
        
        return errors