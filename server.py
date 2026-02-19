import os
import re
import asyncio
import aiohttp
import logging
import csv
from datetime import datetime
from aiohttp import web
from pathlib import Path
from dotenv import load_dotenv

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("MangaServer")

load_dotenv()

CHAPTER_REGEX = re.compile(r"Chapter\s+([\d\.]+)", re.IGNORECASE)
VOLUME_REGEX = re.compile(r"Volume\s+(\d+)", re.IGNORECASE)
RETRY_DELAYS = [3, 7, 12, 17, 25] 
CSV_FILE_NAME = "chapter_checker_log.csv"

# API
CONFIGS = {
    "v2.shlib.life": {
        "api": "https://hapi.hentaicdn.org/api/manga",
        "referer": "https://v2.shlib.life/"
    },
    "mangalib.me": {
        "api": "https://api.cdnlibs.org/api/manga",
        "referer": "https://mangalib.me/"
    },
    "mangalib.org": {
        "api": "https://api.cdnlibs.org/api/manga",
        "referer": "https://mangalib.org/"
    },
    "ranobelib.me": {
        "api": "https://api.cdnlibs.org/api/manga",
        "referer": "https://ranobelib.me/"
    }
}

def get_local_chapters(manga_path):
    try:
        if not manga_path.exists():
            return set()

        local_keys: set[tuple[int, str]] = set()

        # Основной сценарий: downloads/<slug>/Volume 01/Chapter 1[/...]
        volume_dirs = [p for p in manga_path.iterdir() if p.is_dir() and VOLUME_REGEX.search(p.name or "")]
        if volume_dirs:
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

                    # Папка "Chapter X"
                    if entry.is_dir():
                        cm = CHAPTER_REGEX.search(name)
                        if cm:
                            local_keys.add((vol, cm.group(1)))
                        continue

                    # Файл "Chapter X.cbz" (режим pack_cbz)
                    if entry.is_file():
                        cm = CHAPTER_REGEX.search(Path(name).stem)
                        if cm:
                            local_keys.add((vol, cm.group(1)))

            return local_keys

        # Fallback: старый формат без Volume-папок (обратная совместимость)
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
    except Exception as e:
        logger.error(f"Ошибка диска: {e}")
        return set()

async def fetch_server_chapters(session, slug, config, token, domain):
    url = f"{config['api']}/{slug}/chapters"
    
    headers = {
        "accept": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Referer": config['referer']
    }

    # Добавляем токен
    if "shlib.life" in domain and token:
        headers["authorization"] = f"{token}"
        #logger.info(f"  [Auth] Использую токен для Shlib: {slug}")
    #else:
        #logger.info(f"  [Public] Запрос без токена для {domain}: {slug}")

    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    raw_data = await response.json()
                    if isinstance(raw_data, list):
                        items = raw_data
                    else:
                        items = (
                            raw_data.get('data') or
                            raw_data.get('items') or
                            raw_data.get('chapters') or
                            []
                        )

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

                        idx_raw = it.get("index", None)
                        if idx_raw is None:
                            idx_raw = it.get("item_number", None)
                        try:
                            idx_int = int(idx_raw) if idx_raw is not None else None
                        except (ValueError, TypeError):
                            idx_int = None
                        # Если API не дает индекс — используем позицию в массиве как fallback,
                        # чтобы формат был единым и пригодным для batch-загрузки.
                        if idx_int is None:
                            idx_int = pos

                        entries.append({
                            "index": idx_int,
                            "volume": vol_int,
                            "number_str": str(num),
                        })

                    return entries
                
                elif response.status == 429:
                    # Логика ожидания при лимите запросов
                    wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)]
                    await asyncio.sleep(wait_time)
                    continue
                elif response.status == 404:
                    return None
                
                elif response.status == 401 or response.status == 403:
                    logger.error(f"Доступ запрещен (401/403) для {slug} на {domain}")
                    return []
                
                return []
        except Exception:
            return []
    return []

def save_to_csv(results, mode: str, domain: str):
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    try:
        # Один простой формат, 1 строка = 1 манга:
        # MISSING = список токенов "index:volume:number" через запятую.
        summary_header = ["TIME", "SLUG", "DOMAIN", "MODE", "STATUS", "LOCAL", "SERVER", "MISSING_COUNT", "MISSING"]

        # Пользовательский запрос: лог перезаписывается каждый раз и по одной манге на строку.
        with open(CSV_FILE_NAME, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(summary_header)

            for res in results:
                missing_entries = res.get("missing_entries") or []
                # Всегда единый токен: "index:volume:number"
                tokens = []
                for e in sorted(missing_entries, key=lambda x: (x.get("index") is None, x.get("index") or 0)):
                    if not isinstance(e, dict):
                        continue
                    i = e.get("index")
                    v = e.get("volume")
                    n = e.get("number_str")
                    if i is None or v is None or n is None:
                        continue
                    tokens.append(f"{i}:{v}:{n}")
                missing_str = ", ".join(tokens)

                writer.writerow([
                    current_time,
                    res.get("slug", ""),
                    domain,
                    "CHECK_LOCAL" if mode == "check_local" else "ONLY_SERVER",
                    res.get("status", ""),
                    str(res.get("local_count", 0)),
                    str(res.get("server_count", 0)),
                    str(len(tokens)),
                    missing_str,
                ])

        logger.info(f"Лог перезаписан: {CSV_FILE_NAME}")
    except Exception as e:
        logger.error(f"Ошибка CSV: {e}")

async def handle_check(request):
    try:
        data = await request.json()
        slugs = data.get('slugs', [])
        mode = data.get('mode', 'server_only')
        user_path = data.get('path', '')
        client_token = data.get('token')
        domain = data.get('domain', 'mangalib.me')

        if not slugs: 
            return web.json_response([])

        current_config = CONFIGS.get(domain, CONFIGS["mangalib.me"])
        
        is_shlib = "shlib.life" in domain
        is_ranobelib = "ranobelib.me" in domain
        
        # Блокируем запрос если токена нет
        if is_shlib and not client_token:
            logger.error(f"Ошибка: Для домена {domain} обязателен токен!")
            return web.json_response({"error": "Токен не найден. Обновите страницу Shlib (F5)!"}, status=401)
        
        if is_ranobelib:
            logger.info(f"Режим: {domain.upper()} (Текстовые главы; без токена)")
        elif not client_token:
            logger.info(f"Режим: {domain.upper()} (Без токена)")
        else:
            logger.info(f"Режим: {domain.upper()} (Токен получен)")

        logger.info(f"--- Старт: Обработка {len(slugs)} тайтлов ---")

        results = []
        base_path = Path(user_path) if user_path else None

        connector = aiohttp.TCPConnector(limit=3) 
        async with aiohttp.ClientSession(connector=connector) as session:
            for i, slug in enumerate(slugs):
                if i > 0: await asyncio.sleep(0.4)

                server_entries = await fetch_server_chapters(session, slug, current_config, client_token, domain)
                
                res = {
                    "slug": slug,
                    "server_count": len(server_entries) if server_entries else 0,
                    "local_count": 0,
                    # missing: индексы (чтобы можно было напрямую докачать диапазоном индексов)
                    "missing": [],
                    "missing_indices": [],
                    "missing_entries": [],
                    "status": "OK"
                }

                if server_entries is None:
                    res["status"] = "404 Not Found"
                else:
                    manga_path = base_path / slug if base_path else None
    
                    if manga_path and manga_path.exists():
                        local_keys = get_local_chapters(manga_path)
                        res["local_count"] = len(local_keys)

                        server_keys = {
                            (e["volume"], e["number_str"])
                            for e in server_entries
                            if isinstance(e, dict) and e.get("volume") is not None and e.get("number_str") is not None
                        }
                        missing_keys = server_keys - local_keys

                        missing_entries = [
                            e for e in server_entries
                            if (e.get("volume"), e.get("number_str")) in missing_keys
                        ]
                    else:
                        res["local_count"] = 0
                        missing_entries = list(server_entries) if server_entries else []
    
                    # Стабильный набор индексов для UI/CSV. Если индекс не пришёл — пропускаем.
                    missing_indices = sorted({e.get("index") for e in missing_entries if isinstance(e, dict) and isinstance(e.get("index"), int)})
                    res["missing_indices"] = missing_indices
                    res["missing_entries"] = missing_entries
                    res["missing"] = missing_indices
    
                    if missing_entries:
                        res["status"] = f"Не хватает {len(missing_entries)}"
                    else:
                        res["status"] = "Актуально"

                results.append(res)
                logger.info(f"  [{res['status']}] {slug}")

        save_to_csv(results, mode, domain)
        return web.json_response(results)

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        return web.json_response({"error": str(e)}, status=500)

app = web.Application()

async def add_cors(app, res):
    res.headers["Access-Control-Allow-Origin"] = "*"
    res.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    res.headers["Access-Control-Allow-Headers"] = "Content-Type"

app.on_response_prepare.append(add_cors)
app.router.add_post('/check', handle_check)

if __name__ == "__main__":
    logger.info("Сервер готов. Поддерживаются: v2.shlib.life, mangalib.me, mangalib.org и ranobelib.me")
    web.run_app(app, port=8080)