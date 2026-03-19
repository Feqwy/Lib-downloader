from dataclasses import dataclass
from typing import Optional, List, Union


@dataclass
class ChapterInfo:
    number: Union[int, float]
    number_str: str
    index: int
    volume: int
    name: str
    pages_count: int
    series_title: Optional[str]
    teams: List[str]
    chapter_id: Optional[str] = None