import os
import re
import sys
from pathlib import Path
from typing import Optional, Union, List


def parse_float(value: str) -> Optional[float]:
    # Преобразует строку в float, поддерживая запятую как разделитель.
    try:
        return float(value)
    except ValueError:
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None


def parse_chapter_number(number: Union[int, float, str, None]) -> Optional[Union[int, float]]:
    # Преобразует значение номера главы в число (int или float).
    if number is None:
        return None
    
    if isinstance(number, (int, float)):
        return number
    
    try:
        return int(number)
    except ValueError:
        try:
            return float(str(number).replace(",", "."))
        except (ValueError, TypeError):
            return None


def format_chapter_number(num: Union[int, float, str]) -> str:
    # Форматирует номер главы для отображения.
    if isinstance(num, str):
        return num
    
    try:
        f = float(num)
        if f.is_integer():
            return str(int(f))
        s = str(f).rstrip("0").rstrip(".")
        return s
    except Exception:
        return str(num)


def sanitize_filename(text: str) -> str:
    # Очищает строку для использования в имени файла.
    text = (text or "").strip()
    text = re.sub(r'[\\/*?:"<>|]', "_", text)
    return text[:200]


def build_image_url(path: str, host: str) -> str:
    # Строит полный URL изображения из пути и хоста.
    if not path:
        raise ValueError("Empty image path")
    
    if path.startswith("//"):
        path = path[1:]
    
    if path.startswith("http"):
        return path
    
    if not path.startswith("/"):
        path = "/" + path
    
    return host + path


def clean_chapter_name(name: str) -> str:
    # Очищает название главы от номеров и служебной информации.
    if not name:
        return ""
    
    name = re.sub(r'\s*\([^)]*\d[^)]*\)', '', name).strip()
    name = re.sub(r'\d+', '', name).strip()
    return name


def clear_console() -> None:
    # Очищает консоль в зависимости от ОС.
    os.system('cls' if os.name == 'nt' else 'clear')


def configure_utf8_console() -> None:
    # Настраивает UTF-8 кодировку для консоли (актуально на Windows).
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_yes_no(value: str, default: str = "n") -> bool:
    # Преобразует строку в булево значение.
    value = value.strip().lower()
    
    if not value:
        value = default
    
    first_char = value[0] if value else ''
    
    if first_char in ('y', 'н'):
        return True
    if first_char in ('n', 'т'):
        return False
    
    return default == 'y'


def extract_slug_from_url(url: str) -> str:
    # Извлекает slug манги из URL.
    try:
        slug = url.split("/")[-1].split("?")[0]
        if not slug:
            slug = url.split("/")[-2]
        return slug
    except IndexError:
        return "unknown"


def get_api_config_for_domain(domain: str) -> dict:
    # Возвращает конфигурацию API для домена.
    configs = {
        "v2.shlib.life": {
            "api": "https://hapi.hentaicdn.org/api/manga",
            "referer": "https://v2.shlib.life/",
            "image_host": "https://img3.mixlib.me",
            "site_type": "shlib"
        },
        "mangalib.me": {
            "api": "https://api.cdnlibs.org/api/manga",
            "referer": "https://mangalib.me/",
            "image_host": "https://img3.mixlib.me",
            "site_type": "mangalib"
        },
        "mangalib.org": {
            "api": "https://api.cdnlibs.org/api/manga",
            "referer": "https://mangalib.org/",
            "image_host": "https://img3.mixlib.me",
            "site_type": "mangalib"
        },
        "ranobelib.me": {
            "api": "https://api.cdnlibs.org/api/manga",
            "referer": "https://ranobelib.me/",
            "image_host": "https://img3.mixlib.me",
            "site_type": "ranobelib"
        },
        "hentailib.me": {
            "api": "https://hapi.hentaicdn.org/api/manga",
            "referer": "https://hentailib.me/",
            "image_host": "https://img3.hentaicdn.org",
            "site_type": "hentailib"
        }
    }
    
    return configs.get(domain, configs["mangalib.me"])


def is_token_required(domain: str) -> bool:
    return "shlib.life" in domain or "hentailib.me" in domain or "mangalib.me" in domain or "mangalib.org" in domain or "ranobelib.me" in domain


def is_ranobelib(domain: str) -> bool:
    # Проверяет, является ли домен RanobeLib.
    return "ranobelib.me" in domain
