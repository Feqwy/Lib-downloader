import asyncio
import json
import logging
import os
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional

import aiohttp
from aiohttp import web, WSMsgType
from dotenv import load_dotenv

from api_parsing import (
    extract_items_from_response as _extract_api_items,
    get_chapter_index as _get_chapter_index,
)
from csv_contract import (
    CSV_FILE_NAME,
    format_missing_tokens as _format_missing_tokens,
    write_check_csv,
)
from sites import SITES


LOG_BUFFER_SIZE = 200
RETRY_DELAYS = [3, 7, 12, 17, 25]

CHAPTER_REGEX = re.compile(r"Chapter\s+([\d\.]+)", re.IGNORECASE)
VOLUME_REGEX = re.compile(r"Volume\s+(\d+)", re.IGNORECASE)


API_CONFIGS = {
    domain: {
        "api": site.api,
        "referer": site.referer,
    }
    for domain, site in SITES.items()
}


log_buffer = deque(maxlen=LOG_BUFFER_SIZE)


class MemoryLogHandler(logging.Handler):

    def emit(self, record):
        msg = self.format(record)
        log_buffer.append(msg)


logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[MemoryLogHandler()]
)
logger = logging.getLogger("MangaServer")


def get_local_chapters(manga_path: Path) -> Set[Tuple[int, str]]:
    try:
        if not manga_path.exists():
            return set()

        local_keys: Set[Tuple[int, str]] = set()

        volume_dirs = [
            p for p in manga_path.iterdir()
            if p.is_dir() and VOLUME_REGEX.search(p.name or "")
        ]
        
        if volume_dirs:
            return _scan_volume_structure(volume_dirs)

        return _scan_legacy_structure(manga_path)
        
    except Exception as e:
        logger.error(f"Ошибка диска: {e}")
        return set()


def _scan_volume_structure(volume_dirs: List[Path]) -> Set[Tuple[int, str]]:
    local_keys: Set[Tuple[int, str]] = set()
    
    for vol_dir in volume_dirs:
        m = VOLUME_REGEX.search(vol_dir.name or "")
        if not m:
            continue
            
        try:
            vol = int(m.group(1))
        except ValueError:
            continue

        for entry in vol_dir.iterdir():
            name = entry.name or ""

            if entry.is_dir():
                cm = CHAPTER_REGEX.search(name)
                if cm:
                    local_keys.add((vol, cm.group(1)))
                    
            elif entry.is_file():
                cm = CHAPTER_REGEX.search(Path(name).stem)
                if cm:
                    local_keys.add((vol, cm.group(1)))

    return local_keys


def _scan_legacy_structure(manga_path: Path) -> Set[Tuple[int, str]]:
    local_keys: Set[Tuple[int, str]] = set()
    
    for root, dirs, files in os.walk(manga_path):
        for dir_name in dirs:
            match = CHAPTER_REGEX.search(dir_name)
            if match:
                local_keys.add((0, match.group(1)))
                
        for file_name in files:
            match = CHAPTER_REGEX.search(Path(file_name).stem)
            if match:
                local_keys.add((0, match.group(1)))

    return local_keys


def _build_request_headers(domain: str, token: Optional[str]) -> Dict[str, str]:
    headers = {
        "accept": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Referer": API_CONFIGS.get(domain, {}).get("referer", "")
    }

    if token:
        headers["authorization"] = token

    return headers


def _extract_chapter_entries(items: List[Any]) -> List[Dict[str, Any]]:
    entries = []
    
    for pos, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            continue
            
        num = it.get("number")
        vol = it.get("volume")
        
        if num is None or vol is None:
            continue
            
        try:
            vol_int = int(vol)
        except (ValueError, TypeError):
            continue

        idx_int = _get_chapter_index(it, pos)
        entries.append({
            "index": idx_int,
            "volume": vol_int,
            "number_str": str(num),
        })

    return entries


def save_to_csv(results: List[Dict[str, Any]], mode: str, domain: str) -> None:
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    try:
        write_check_csv(CSV_FILE_NAME, results, mode, domain, timestamp=current_time)

        logger.info(f"Лог перезаписан: {CSV_FILE_NAME}")

    except Exception as e:
        logger.error(f"Ошибка CSV: {e}")


async def fetch_server_chapters(
    session: aiohttp.ClientSession,
    slug: str,
    config: Dict[str, str],
    token: Optional[str],
    domain: str
) -> Optional[List[Dict[str, Any]]]:
    url = f"{config['api']}/{slug}/chapters"
    headers = _build_request_headers(domain, token)

    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    raw_data = await response.json()
                    items = _extract_api_items(raw_data)
                    return _extract_chapter_entries(items)

                elif response.status == 429:
                    wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    await asyncio.sleep(wait_time)
                    continue
                    
                elif response.status == 404:
                    return None

                elif response.status in (401, 403):
                    logger.error(f"Доступ запрещен (401/403) для {slug} на {domain}")
                    return []

                return []
                
        except Exception:
            return []
            
    return []


async def handle_check(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        slugs = data.get('slugs', [])
        mode = data.get('mode', 'server_only')
        user_path = data.get('path', '')
        client_token = data.get('token')
        domain = data.get('domain', 'mangalib.me')

        if not slugs:
            return web.json_response([])

        current_config = API_CONFIGS.get(domain, API_CONFIGS["mangalib.me"])

        if not _validate_token(domain, client_token):
            return web.json_response(
                {"error": "Токен не найден. Обновите страницу (F5)!"},
                status=401
            )

        _log_mode_info(domain, client_token)
        logger.info(f"--- Старт: Обработка {len(slugs)} тайтлов ---")

        results = await _process_slugs(slugs, mode, user_path, current_config, client_token, domain)
        
        save_to_csv(results, mode, domain)
        return web.json_response(results)

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        return web.json_response({"error": str(e)}, status=500)


def _validate_token(domain: str, token: Optional[str]) -> bool:
    return True


def _log_mode_info(domain: str, token: Optional[str]) -> None:
    if "ranobelib.me" in domain:
        if token:
            logger.info(f"Режим: {domain.upper()} (Текстовые главы; токен получен)")
        else:
            logger.info(f"Режим: {domain.upper()} (Текстовые главы; без токена)")
    elif not token:
        logger.info(f"Режим: {domain.upper()} (Без токена)")
    else:
        logger.info(f"Режим: {domain.upper()} (Токен получен)")


async def _process_slugs(
    slugs: List[str],
    mode: str,
    user_path: str,
    config: Dict[str, str],
    token: Optional[str],
    domain: str
) -> List[Dict[str, Any]]:
    results = []
    base_path = Path(user_path) if user_path else None

    connector = aiohttp.TCPConnector(limit=3)
    async with aiohttp.ClientSession(connector=connector) as session:
        for i, slug in enumerate(slugs):
            if i > 0:
                await asyncio.sleep(0.4)

            result = await _process_single_slug(
                session, slug, mode, base_path, config, token, domain
            )
            results.append(result)
            logger.info(f"  [{result['status']}] {slug}")

    return results


async def _process_single_slug(
    session: aiohttp.ClientSession,
    slug: str,
    mode: str,
    base_path: Optional[Path],
    config: Dict[str, str],
    token: Optional[str],
    domain: str
) -> Dict[str, Any]:
    server_entries = await fetch_server_chapters(session, slug, config, token, domain)

    res = _create_initial_result(slug, server_entries)

    if server_entries is None:
        res["status"] = "404 Not Found"
    else:
        manga_path = base_path / slug if base_path else None
        await _analyze_local_chapters(manga_path, server_entries, res)

    missing_indices = sorted({
        e.get("index") for e in res["missing_entries"]
        if isinstance(e, dict) and isinstance(e.get("index"), int)
    })
    res["missing_indices"] = missing_indices
    res["missing"] = missing_indices

    if res["missing_entries"]:
        res["status"] = f"Не хватает {len(res['missing_entries'])}"
    else:
        res["status"] = "Актуально"

    return res


def _create_initial_result(slug: str, server_entries: Optional[List]) -> Dict[str, Any]:
    return {
        "slug": slug,
        "server_count": len(server_entries) if server_entries else 0,
        "local_count": 0,
        "missing": [],
        "missing_indices": [],
        "missing_entries": [],
        "status": "OK"
    }


async def _analyze_local_chapters(
    manga_path: Optional[Path],
    server_entries: List[Dict[str, Any]],
    res: Dict[str, Any]
) -> None:
    if manga_path and manga_path.exists():
        local_keys = get_local_chapters(manga_path)
        res["local_count"] = len(local_keys)

        server_keys = {
            (e["volume"], e["number_str"])
            for e in server_entries
            if isinstance(e, dict) and e.get("volume") is not None and e.get("number_str") is not None
        }
        missing_keys = server_keys - local_keys

        res["missing_entries"] = [
            e for e in server_entries
            if (e.get("volume"), e.get("number_str")) in missing_keys
        ]
    else:
        res["local_count"] = 0
        res["missing_entries"] = list(server_entries) if server_entries else []


async def handle_logs_ws(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    for msg in log_buffer:
        await ws.send_str(json.dumps({"type": "log", "message": msg}))

    last_pos = len(log_buffer)
    
    try:
        while True:
            while last_pos < len(log_buffer):
                await ws.send_str(json.dumps({"type": "log", "message": log_buffer[last_pos]}))
                last_pos += 1

            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                if msg.type == WSMsgType.ERROR:
                    break
            except asyncio.TimeoutError:
                pass
                
    except Exception:
        pass

    return ws


async def handle_logs(request: web.Request) -> web.Response:
    return web.json_response(
        {"logs": list(log_buffer)},
        headers={"X-Log-Endpoint": "true"}
    )


async def add_cors(app: web.Application, res: web.Response) -> web.Response:
    res.headers["Access-Control-Allow-Origin"] = "*"
    res.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    res.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return res


app = web.Application()
app.on_response_prepare.append(add_cors)
app.router.add_post('/check', handle_check)
app.router.add_get('/logs', handle_logs)
app.router.add_get('/logs/ws', handle_logs_ws)


if __name__ == "__main__":
    logger.info(
        "Сервер готов. Поддерживаются: "
        "v2.shlib.life, mangalib.me, mangalib.org, ranobelib.me и hentailib.me"
    )
    web.run_app(app, port=8080, access_log=None)