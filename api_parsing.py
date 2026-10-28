from typing import Any, Dict, List


def extract_items_from_response(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if isinstance(data, dict):
        for key in ("data", "items", "chapters"):
            val = data.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]

    return []


def get_chapter_index(item: dict, fallback: int) -> int:
    idx_raw = item.get("index") or item.get("item_number")

    try:
        return int(idx_raw) if idx_raw is not None else fallback
    except (ValueError, TypeError):
        return fallback
