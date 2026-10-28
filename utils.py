import os
import re
import sys
from pathlib import Path
from typing import Optional, Union, List

from sites import get_site, is_ranobelib as _is_ranobelib, is_token_required as _is_token_required


def parse_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None


def parse_chapter_number(number: Union[int, float, str, None]) -> Optional[Union[int, float]]:
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
    text = (text or "").strip()
    text = re.sub(r'[\\/*?:"<>|]', "_", text)
    return text[:200]


def build_image_url(path: str, host: str) -> str:
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
    if not name:
        return ""
    
    name = re.sub(r'\s*\([^)]*\d[^)]*\)', '', name).strip()
    name = re.sub(r'\d+', '', name).strip()
    return name


def clear_console() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')


def configure_utf8_console() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_yes_no(value: str, default: str = "n") -> bool:
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
    try:
        slug = url.split("/")[-1].split("?")[0]
        if not slug:
            slug = url.split("/")[-2]
        return slug
    except IndexError:
        return "unknown"


def get_api_config_for_domain(domain: str) -> dict:
    return get_site(domain).as_api_dict()


def is_token_required(domain: str) -> bool:
    return _is_token_required(domain)


def is_ranobelib(domain: str) -> bool:
    return _is_ranobelib(domain)
