from typing import Any, Dict, Optional, Union

from utils import format_chapter_number


def volume_dir_name(volume: int) -> str:
    return f"Volume {int(volume):02d}"


def chapter_dir_name(chapter_num: Union[int, float, str]) -> str:
    return f"Chapter {format_chapter_number(chapter_num)}"


def series_title_from_meta(
    series_meta: Dict[str, Any],
    fallback: str,
    override: Optional[str] = None,
) -> str:
    return (
        override or
        series_meta.get("name") or
        series_meta.get("rus_name") or
        series_meta.get("eng_name") or
        fallback
    )
