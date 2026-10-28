import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


CSV_FILE_NAME = "chapter_checker_log.csv"

CSV_HEADER = [
    "TIME", "SLUG", "DOMAIN", "MODE", "STATUS",
    "LOCAL", "SERVER", "MISSING_COUNT", "MISSING"
]

CSV_TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"
CSV_MODE_CHECK_LOCAL = "CHECK_LOCAL"
CSV_MODE_ONLY_SERVER = "ONLY_SERVER"


def format_missing_tokens(missing_entries: List[Dict[str, Any]]) -> str:
    tokens = []

    for e in sorted(
        (entry for entry in missing_entries if isinstance(entry, dict)),
        key=lambda x: (x.get("index") is None, x.get("index") or 0),
    ):
        i = e.get("index")
        v = e.get("volume")
        n = e.get("number_str")

        if i is None or v is None or n is None:
            continue

        tokens.append(f"{i}:{v}:{n}")

    return ", ".join(tokens)


def parse_missing_indices(missing_str: str) -> List[float]:
    indices: List[float] = []

    for token in missing_str.split(','):
        token = token.strip()
        if not token:
            continue

        parts = token.split(':')
        if not parts:
            continue

        try:
            idx = int(parts[0].strip())
            indices.append(float(idx))
        except ValueError:
            continue

    return indices


def parse_task_row(
    row: Dict[str, str],
    on_warning: Optional[Callable[[str], None]] = None,
) -> Optional[Dict[str, Any]]:
    slug = (row.get('SLUG') or row.get('slug') or "").strip()
    if not slug:
        return None

    missing_str = (row.get('MISSING') or "").strip()
    if missing_str:
        indices = parse_missing_indices(missing_str)
        if indices:
            return {'slug': slug, 'chapters': indices}

    status = row.get('СТАТУС', '') or ""
    missing_chapters_str = (row.get('ПРОПУЩЕННЫЕ_ГЛАВЫ', '') or '').strip()

    if "Не хватает" in status and missing_chapters_str:
        try:
            missing_chapters = [
                float(c.strip())
                for c in missing_chapters_str.split(',')
                if c.strip()
            ]
            if missing_chapters:
                return {'slug': slug, 'chapters': missing_chapters}
        except ValueError:
            if on_warning is not None:
                on_warning(
                    f"Could not parse chapter numbers for {slug}. Skipping."
                )

    return None


def write_check_csv(
    path: Union[str, Path],
    results: List[Dict[str, Any]],
    mode: str,
    domain: str,
    timestamp: Optional[str] = None,
) -> None:
    current_time = timestamp or datetime.now().strftime(CSV_TIME_FORMAT)

    with open(path, mode='w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(CSV_HEADER)

        for res in results:
            missing_entries = res.get("missing_entries") or []
            missing_str = format_missing_tokens(missing_entries)

            writer.writerow([
                current_time,
                res.get("slug", ""),
                domain,
                CSV_MODE_CHECK_LOCAL if mode == "check_local" else CSV_MODE_ONLY_SERVER,
                res.get("status", ""),
                str(res.get("local_count", 0)),
                str(res.get("server_count", 0)),
                str(len(missing_entries)),
                missing_str,
            ])
