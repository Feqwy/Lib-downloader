import json
import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional

from models import ChapterInfo
from config import Config


# Генерирует метаданные в форматах ComicInfo.xml и JSON.
class MetadataGenerator:
    
    STATUS_MAP = {
        1: "Continuing",
        2: "Completed",
    }
    
    AGE_RATING_MAP = {
        "18": "18+",
        "Mature": "18+",
        "18+": "18+",
        "16": "16+",
        "Teen": "16+",
        "16+": "16+",
    }
    
    COMIC_AGE_RATING_MAP = {
        "16+": "TEEN",
        "18+": "MATURE",
        "TEEN": "TEEN",
        "MATURE": "MATURE",
    }

    def __init__(self, cfg: Config):
        # Инициализирует генератор.
        self.cfg = cfg

    def create_chapter_comicinfo(self, info: ChapterInfo) -> bytes:
        # Создает ComicInfo.xml для главы.
        root = ET.Element("ComicInfo")

        ET.SubElement(root, "Title").text = info.name or f"Chapter {info.number}"
        ET.SubElement(root, "Series").text = info.series_title or self.cfg.manga_slug
        ET.SubElement(root, "Number").text = str(info.number)
        ET.SubElement(root, "Volume").text = str(info.volume)
        ET.SubElement(root, "PageCount").text = str(info.pages_count)
        ET.SubElement(root, "Summary").text = (
            f"Chapter {info.number} of {info.series_title or self.cfg.manga_slug}"
        )

        if info.teams:
            ET.SubElement(root, "Writer").text = ", ".join(info.teams)

        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def create_series_comicinfo(self, series_title: str, series_info: Dict[str, Any]) -> bytes:
        # Создает ComicInfo.xml для серии.
        root = ET.Element("ComicInfo")

        ET.SubElement(root, "Title").text = series_title
        ET.SubElement(root, "Series").text = series_title
        ET.SubElement(root, "Summary").text = series_info.get("summary") or ""

        writers = self._extract_names(series_info.get("authors", []))
        if writers:
            ET.SubElement(root, "Writer").text = ", ".join(writers)

        publishers = self._extract_names(series_info.get("publisher", []))
        if publishers:
            ET.SubElement(root, "Publisher").text = publishers[0]

        genres = self._extract_names(series_info.get("genres", []))
        if genres:
            ET.SubElement(root, "Genre").text = "; ".join(genres)

        language = self._get_language(series_info)
        if language:
            ET.SubElement(root, "LanguageISO").text = language

        age_rating = self._get_comic_age_rating(series_info)
        if age_rating:
            ET.SubElement(root, "AgeRating").text = age_rating

        year = series_info.get("releaseDate")
        if year:
            ET.SubElement(root, "Year").text = str(year)

        country = self._get_country(series_info)
        if country:
            ET.SubElement(root, "Country").text = country

        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def create_volume_comicinfo(
        self,
        volume: int,
        series_title: str,
        chapter_count: int,
        series_info: Dict[str, Any]
    ) -> bytes:
        # Создает ComicInfo.xml для тома.
        root = ET.Element("ComicInfo")

        ET.SubElement(root, "Title").text = f"Volume {volume:02d}"
        ET.SubElement(root, "Volume").text = str(volume)
        ET.SubElement(root, "Number").text = str(volume)
        ET.SubElement(root, "Count").text = str(chapter_count)
        ET.SubElement(root, "Series").text = series_title
        ET.SubElement(root, "Summary").text = f"Volume {volume} of {series_title}"

        writers = self._extract_names(series_info.get("authors", []))
        if writers:
            ET.SubElement(root, "Writer").text = ", ".join(writers)

        publishers = self._extract_names(series_info.get("publisher", []))
        if publishers:
            ET.SubElement(root, "Publisher").text = publishers[0]

        year = series_info.get("releaseDate")
        if year:
            ET.SubElement(root, "Year").text = str(year)

        language = self._get_language(series_info)
        if language:
            ET.SubElement(root, "LanguageISO").text = language

        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def create_series_json(self, series_title: str, series_info: Dict[str, Any]) -> str:
        # Создает JSON метаданные для серии.
        name = self._get_series_name(series_title, series_info)
        comicid = self._get_series_comicid(series_info)
        summary = self._get_series_summary(series_info)
        genres = self._extract_names(series_info.get("genres") or series_info.get("genre"))
        tags = self._extract_names(
            series_info.get("tags") or
            series_info.get("themes") or
            series_info.get("otherNames")
        )
        authors_list = self._extract_authors(series_info)
        publisher = self._get_first_string(
            series_info.get("publisher") or series_info.get("publishers")
        )
        year_val, release_date = self._extract_year_info(series_info)
        language = self._get_language(series_info)
        age_rating = self._extract_age_rating(series_info)
        status = self._get_readable_status(series_info)

        series_dict = {
            "name": name,
            "comicid": comicid,
            "title": name,
            "summary": summary,
            "description_text": summary,
            "description_formatted": summary.replace("\n", "<br/>") if summary else "",
            "status": status,
            "publisher": publisher,
            "year": year_val or "",
            "releaseDate": release_date or "",
            "age_rating": age_rating,
            "language": language or "",
            "genres": genres,
            "tags": tags,
            "authors": authors_list
        }

        return json.dumps(series_dict, ensure_ascii=False, indent=2)

    def _get_series_name(self, series_title: str, series_info: Dict[str, Any]) -> str:
        # Получает название серии.
        if series_title:
            return series_title

        return self._get_first_string(
            series_info.get("name") or
            series_info.get("title") or
            series_info.get("eng_name")
        )

    def _get_series_comicid(self, series_info: Dict[str, Any]) -> str:
        # Получает ID серии.
        return str(
            series_info.get("id") or
            series_info.get("manga_id") or
            self.cfg.manga_slug
        )

    def _get_series_summary(self, series_info: Dict[str, Any]) -> str:
        # Получает описание серии.
        return (
            series_info.get("summary") or
            series_info.get("description") or
            series_info.get("shortDescription") or
            ""
        )

    def _extract_names(self, items: Any) -> List[str]:
        # Извлекает имена из списка объектов или строк.
        if items is None:
            return []
            
        if not isinstance(items, list):
            items = [items]
            
        names = []
        for item in items:
            if isinstance(item, dict):
                name = (
                    item.get("name") or
                    item.get("label") or
                    item.get("title") or
                    ""
                )
                if name:
                    names.append(str(name))
            elif isinstance(item, str):
                names.append(item)
                
        return names

    def _get_first_string(self, obj: Any) -> str:
        # Получает первую строку из объекта (список, dict, скаляр).
        if not obj:
            return ""

        if isinstance(obj, list):
            if obj and isinstance(obj[0], (str, dict)):
                if isinstance(obj[0], dict):
                    return obj[0].get("name", "") or obj[0].get("label", "") or ""
                return str(obj[0])
            return ""
            
        if isinstance(obj, dict):
            return obj.get("name", "") or obj.get("label", "") or ""
            
        return str(obj)

    def _extract_authors(self, series_info: Dict[str, Any]) -> List[Dict[str, str]]:
        # Извлекает авторов и художников.
        authors_list = []

        # Авторы
        for author in self._ensure_list(series_info.get("authors") or series_info.get("author")):
            if isinstance(author, dict):
                authors_list.append({
                    "name": author.get("name", ""),
                    "role": author.get("role", "Writer") or "Writer"
                })
            else:
                authors_list.append({"name": str(author), "role": "Writer"})

        # Художники
        for artist in self._ensure_list(series_info.get("artists") or series_info.get("artist")):
            if isinstance(artist, dict):
                authors_list.append({
                    "name": artist.get("name", ""),
                    "role": artist.get("role", "Artist") or "Artist"
                })
            else:
                authors_list.append({"name": str(artist), "role": "Artist"})

        return authors_list

    def _ensure_list(self, value: Any) -> List[Any]:
        # Гарантирует, что значение является списком.
        return value if isinstance(value, list) else [value] if value else []

    def _extract_year_info(self, series_info: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        # Извлекает год и дату релиза.
        year = series_info.get("releaseDate") or series_info.get("year") or ""

        if isinstance(year, str) and re.match(r"^\d{4}-\d{2}-\d{2}", year):
            return year[:4], year
        elif isinstance(year, str) and re.match(r"^\d{4}$", year):
            return year, f"{year}-01-01"
        elif isinstance(year, (int, float)):
            year_str = str(int(year))
            return year_str, f"{year_str}-01-01"
        else:
            year_val = str(series_info.get("year") or series_info.get("startYear") or "")
            return year_val, f"{year_val}-01-01" if year_val else ""

    def _extract_age_rating(self, series_info: Dict[str, Any]) -> str:
        # Извлекает возрастной рейтинг.
        # series_info: Данные серии.
        # Returns: Возрастной рейтинг.
        age = series_info.get("ageRestriction", {})
        age_label = age.get("label") if isinstance(age, dict) else age
        age_label = age_label or series_info.get("age_rating") or ""

        if not age_label:
            return ""

        age_str = str(age_label)
        
        # Проверяем по ключевым словам
        for key, rating in self.AGE_RATING_MAP.items():
            if key in age_str:
                return rating

        return age_str

    def _get_language(self, series_info: Dict[str, Any]) -> str:
        # Определяет язык по типу манги.
        type_info = series_info.get("type", {})
        type_label = type_info.get("label", "") if isinstance(type_info, dict) else ""

        if "Манхва" in type_label:
            return "ko"
        elif "Манга" in type_label:
            return "ja"
        return "en"

    def _get_country(self, series_info: Dict[str, Any]) -> str:
        # Определяет страну происхождения.
        type_info = series_info.get("type", {})
        type_label = type_info.get("label", "") if isinstance(type_info, dict) else ""

        if "Манхва" in type_label:
            return "KR"
        elif "Манга" in type_label:
            return "JP"
        return "US"

    def _get_comic_age_rating(self, series_info: Dict[str, Any]) -> str:
        # Получает рейтинг в формате ComicInfo.
        age = series_info.get("ageRestriction", {})
        age_label = age.get("label", "") if isinstance(age, dict) else ""

        return self.COMIC_AGE_RATING_MAP.get(age_label, "EVERYONE")

    def _get_readable_status(self, series_info: Dict[str, Any]) -> str:
        # Получает читаемый статус серии.
        status_id = series_info.get("status", {}).get("id", 0)
        return self.STATUS_MAP.get(status_id, "Hiatus")
