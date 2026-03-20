import asyncio
import random
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

import aiohttp

from config import Config
from colors import Colors
from models import ChapterInfo
from utils import parse_chapter_number, parse_float


# Асинхронный клиент для работы с API Lib-сайтов.
# Поддерживает: MangaLib, SlashLib, RanobeLib, HentaiLib.
class MangaAPIClient:
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (iPad; CPU OS 18_6_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/142.0.7444.46 Mobile/15E148 Safari/604.1",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, cfg: Config):
        # Инициализирует клиент.
        # cfg
        self.cfg = cfg
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Кэш данных
        self._chapters_map: Dict[str, Dict[float, int]] = {}
        self._series_cache: Dict[str, Dict[str, Any]] = {}
        self._full_pool_cache: Dict[str, List[Dict[str, Any]]] = {}
        
        # Заголовки
        self._headers = {
            **self.DEFAULT_HEADERS,
            "Referer": self.cfg.referer,
            "Origin": self.cfg.referer.rstrip("/")
        }

        if self.cfg.auth_token:
            # Добавляем префикс Bearer, если его ещё нет
            token = self.cfg.auth_token.strip()
            if not token.lower().startswith('bearer '):
                self._headers["Authorization"] = f"Bearer {token}"
            else:
                self._headers["Authorization"] = token

    async def __aenter__(self):
        conn = aiohttp.TCPConnector(limit=self.cfg.max_concurrent_images * 2)
        self._session = aiohttp.ClientSession(connector=conn, headers=self._headers)
        await self._warm_up_session()
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def _warm_up_session(self) -> None:
        # Прогревает сессию легким запросом к рефереру.
        try:
            async with self._session.get(self.cfg.referer, timeout=6):
                pass
        except Exception:
            pass

    async def fetch_full_chapter_pool(self, slug: str) -> List[Dict[str, Any]]:
        # Получает полный список глав для тайтла.
        if slug in self._full_pool_cache:
            return self._full_pool_cache[slug]

        url = f"{self.cfg.api_base}/{slug}/chapters"
        
        try:
            data = await self._get_json(url, retries=4)
            items = self._extract_items_from_response(data)
            self._full_pool_cache[slug] = items
            return items
        except Exception as e:
            print(Colors.error(f"Не удалось получить список глав: {e}"))
            return []

    def _extract_items_from_response(self, data: Any) -> List[Dict[str, Any]]:
        # Извлекает список элементов из ответа API.
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        
        if isinstance(data, dict):
            for key in ("data", "items", "chapters"):
                val = data.get(key)
                if isinstance(val, list):
                    return [x for x in val if isinstance(x, dict)]
        
        return []

    def _build_chapters_map_from_items(
        self,
        items: List[Dict[str, Any]],
    ) -> Dict[float, int]:
        # Преобразует список элементов /chapters в карту {chapter_number: volume}.
        mapping: Dict[float, int] = {}

        for item in items:
            chapter_num = item.get("number")
            volume_num = item.get("volume")

            if chapter_num is None or volume_num is None:
                continue

            chapter_float = parse_float(str(chapter_num))
            if chapter_float is None:
                continue

            try:
                volume_int = int(volume_num)
            except (ValueError, TypeError):
                continue

            mapping[chapter_float] = volume_int

        return mapping

    async def to_chapter_info_list(
        self,
        slug: str,
        start_num: float,
        end_num: float,
        extra: List[float]
    ) -> List[ChapterInfo]:
        full_data = await self.fetch_full_chapter_pool(slug)

        chapter_info_list: List[ChapterInfo] = []
        start_idx = int(start_num)
        end_idx = int(end_num)
        
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        extra_indices, extra_numbers = self._parse_extra_chapters(extra)
        seen_keys: set[tuple[int, str]] = set()

        for fallback_idx, item in enumerate(full_data):
            info = self._create_chapter_info_from_item(item, fallback_idx)
            if info is None:
                continue

            if self._should_include_chapter(info, start_idx, end_idx, extra_indices, extra_numbers):
                key = (info.volume, info.number_str)
                if key not in seen_keys:
                    chapter_info_list.append(info)
                    seen_keys.add(key)

        return sorted(chapter_info_list, key=lambda ch: (ch.index, ch.volume, ch.number))

    def _parse_extra_chapters(self, extra: List[float]) -> tuple[set[int], set[float]]:
        # Разделяет дополнительные главы на индексы и номера.
        extra_indices = set()
        extra_numbers = set()
        
        for x in (extra or []):
            try:
                xf = float(x)
                if xf.is_integer():
                    extra_indices.add(int(xf))
                else:
                    extra_numbers.add(xf)
            except Exception:
                pass
        
        return extra_indices, extra_numbers

    def _create_chapter_info_from_item(self, item: Dict[str, Any], fallback_idx: int) -> Optional[ChapterInfo]:
        # Создает ChapterInfo из элемента данных API.
        raw_number = item.get("number")
        number = parse_chapter_number(raw_number)
        
        volume_raw = item.get("volume")
        volume = 0
        try:
            volume = int(volume_raw)
        except (ValueError, TypeError):
            pass

        api_index_raw = item.get("index") or item.get("item_number")
        try:
            api_index = int(api_index_raw)
        except (ValueError, TypeError):
            api_index = fallback_idx + 1

        if number is None:
            return None

        return ChapterInfo(
            number=number,
            number_str=str(raw_number),
            index=api_index,
            volume=volume,
            name=item.get("name") or "",
            pages_count=item.get("pages_count", 0),
            series_title=None,
            teams=item.get("teams", []),
            chapter_id=item.get("id"),
        )

    def _should_include_chapter(
        self,
        info: ChapterInfo,
        start_idx: int,
        end_idx: int,
        extra_indices: set[int],
        extra_numbers: set[float]
    ) -> bool:
        # Определяет, должна ли глава быть включена в загрузку.
        in_index_range = start_idx <= info.index <= end_idx
        in_extra_numbers = info.number in extra_numbers
        in_extra_indices = info.index in extra_indices
        
        return in_index_range or in_extra_numbers or in_extra_indices

    async def download_image_raw(self, url: str, retries: int = 5) -> tuple[bytes, str]:
        # Загружает изображение как байты.
        if not self._session:
            raise RuntimeError("Client session is not initialized")

        # Используем заголовки сессии (в т.ч. Referer/Origin и Authorization при необходимости).
        headers = self._headers

        for attempt in range(retries):
            try:
                async with self._session.get(url, headers=headers, timeout=60) as resp:
                    if resp.status == 429:
                        wait = self._calculate_retry_delay(resp.headers, attempt)
                        await asyncio.sleep(wait)
                        continue
                    
                    resp.raise_for_status()
                    data = await resp.read()
                    
                    if not data:
                        raise RuntimeError("Empty response")
                    
                    ctype = resp.headers.get("Content-Type", "")
                    return data, ctype
                    
            except Exception:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(0.25 * (attempt + 1))
        
        raise RuntimeError("Retries exhausted")

    async def _get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        retries: int = 5
    ) -> Dict[str, Any]:
        # Выполняет GET запрос и возвращает JSON.
        for attempt in range(retries):
            try:
                async with self._session.get(url, params=params, timeout=30) as resp:
                    if resp.status == 429:
                        wait = self._calculate_retry_delay(resp.headers, attempt)
                        print(Colors.warning(
                            f"Rate limit (429). Retry in {wait:.2f}s... "
                            f"(Attempt {attempt + 1}/{retries})"
                        ))
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()
                    data = await resp.json()
                    await asyncio.sleep(self.cfg.request_delay)
                    return data

            except aiohttp.ClientResponseError as e:
                if getattr(e, "status", None) == 429:
                    wait = self._calculate_retry_delay({}, attempt)
                    print(Colors.warning(
                        f"Rate limit (429) via exception. Retry in {wait:.2f}s... "
                        f"(Attempt {attempt + 1}/{retries})"
                    ))
                    await asyncio.sleep(wait)
                    continue
                    
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(0.2 * (attempt + 1))

            except Exception as e:
                if attempt == retries - 1:
                    print(Colors.error(f"Request failed after {retries} attempts: {e}"))
                    raise
                await asyncio.sleep(0.2 * (attempt + 1))

        raise RuntimeError("Retries exhausted")

    @staticmethod
    def _calculate_retry_delay(headers: Dict[str, str], attempt: int) -> float:
        # Вычисляет задержку перед повторной попыткой.
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                sec = int(float(retry_after))
                return float(sec) + 1.0
            except Exception:
                pass

        base = min(2 ** attempt, 60)
        jitter = random.uniform(0.3, 1.3)
        return base + 0.1 * attempt + jitter

    async def fetch_chapters_list(self, slug: str) -> Dict[float, int]:
        # Получает список глав с номерами и томами.
        if slug in self._chapters_map:
            return self._chapters_map[slug]

        # Если уже загружен полный пул глав, строим карту томов из кэша (уменьшаем количество HTTP запросов в рамках одного сеанса).
        if slug in self._full_pool_cache:
            mapping = self._build_chapters_map_from_items(self._full_pool_cache[slug])
            self._chapters_map[slug] = mapping
            return mapping

        url = f"{self.cfg.api_base}/{slug}/chapters"
        mapping: Dict[float, int] = {}

        try:
            data = await self._get_json(url, retries=4)
            items = self._extract_items_from_response(data)
            mapping = self._build_chapters_map_from_items(items)
                    
        except Exception:
            mapping = {}

        self._chapters_map[slug] = mapping
        return mapping

    async def fetch_series_info(self, slug: str) -> Dict[str, Any]:
        # Получает информацию о серии.
        if slug in self._series_cache:
            return self._series_cache[slug]

        url = f"{self.cfg.api_base}/{slug}"
        fields = [
            "background", "eng_name", "otherNames", "summary", "releaseDate",
            "type_id", "caution", "views", "close_view", "rate_avg", "rate",
            "genres", "tags", "teams", "user", "franchise", "authors", "publisher",
            "userRating", "moderated", "metadata", "metadata.count",
            "metadata.close_comments", "manga_status_id", "chap_count",
            "status_id", "artists", "format"
        ]
        params = {f"fields[]": field for field in fields}

        try:
            data = await self._get_json(url, params=params, retries=3)
            result = data.get("data", {}) if isinstance(data, dict) else {}
        except Exception:
            result = {}

        self._series_cache[slug] = result
        return result

    async def fetch_chapter_data(
        self,
        slug: str,
        chapter_num: Union[int, float, str],
        volume: int
    ) -> Dict[str, Any]:
        # Получает данные главы.
        url = f"{self.cfg.api_base}/{slug}/chapter"
        return await self._get_json(
            url,
            params={"number": chapter_num, "volume": volume},
            retries=4
        )

    async def resolve_volume(self, slug: str, chapter_num: int) -> int:
        # Определяет том для главы.
        if self.cfg.volume_override is not None:
            return self.cfg.volume_override

        chapters_map = await self.fetch_chapters_list(slug)
        target_chapter = float(chapter_num)

        if chapters_map and target_chapter in chapters_map:
            return chapters_map[target_chapter]

        series_info = await self.fetch_series_info(slug)
        detected_volume = self._search_volume_in_metadata(series_info, target_chapter)

        if detected_volume is not None:
            try:
                await self.fetch_chapter_data(slug, chapter_num, detected_volume)
                return detected_volume
            except Exception:
                pass

        return await self._bruteforce_volume(slug, chapter_num)

    def _search_volume_in_metadata(
        self,
        metadata: Dict[str, Any],
        target_chapter: float
    ) -> Optional[int]:
        # Ищет том для главы в метаданных.
        def search(obj) -> Optional[int]:
            if isinstance(obj, dict):
                num = obj.get("number") or obj.get("chapter_number")
                vol = obj.get("volume")

                if num is not None and vol is not None:
                    chapter_float = parse_float(str(num))
                    if chapter_float == target_chapter:
                        try:
                            return int(vol)
                        except (ValueError, TypeError):
                            pass

                for value in obj.values():
                    result = search(value)
                    if result is not None:
                        return result
                        
            elif isinstance(obj, list):
                for item in obj:
                    result = search(item)
                    if result is not None:
                        return result
                        
            return None

        return search(metadata)

    async def _bruteforce_volume(self, slug: str, chapter_num: int) -> int:
        # Перебирает тома для нахождения нужного.
        start, end = self.cfg.fallback_volume_range

        for volume in range(start, end + 1):
            try:
                await asyncio.sleep(0.12)
                await self.fetch_chapter_data(slug, chapter_num, volume)
                return volume
            except Exception:
                continue

        raise ValueError(f"Could not determine volume for chapter {chapter_num}")

    async def download_image(self, url: str, dest: Path, retries: int = 10) -> None:
        # Загружает изображение и сохраняет в файл.
        # URL
        # Dest
        # Retries
        # Используем заголовки сессии (в т.ч. Referer/Origin и Authorization при необходимости).
        headers = self._headers

        for attempt in range(retries):
            try:
                async with self._session.get(url, headers=headers, timeout=60) as resp:
                    if resp.status == 429:
                        wait = self._calculate_retry_delay(resp.headers, attempt)
                        print(Colors.warning(
                            f"Rate limit (429) for image. Retry in {wait:.2f}s... "
                            f"(Attempt {attempt + 1}/{retries})"
                        ))
                        await asyncio.sleep(wait)
                        continue

                    if resp.status == 403 and attempt < retries - 1:
                        print(Colors.warning(
                            f"403 Forbidden. Warming up and retrying... "
                            f"(Attempt {attempt + 1}/{retries})"
                        ))
                        await self._warm_up_session()
                        await asyncio.sleep(0.3 * (attempt + 1))
                        continue

                    resp.raise_for_status()
                    data = await resp.read()

                    if not data:
                        raise RuntimeError("Empty response")

                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                    await asyncio.sleep(self.cfg.request_delay)
                    return

            except aiohttp.ClientResponseError as e:
                if attempt == retries - 1:
                    print(Colors.error(f"Image download failed after {retries} attempts: {e}"))
                    raise
                await asyncio.sleep(0.2 * (attempt + 1))

            except Exception as e:
                if attempt == retries - 1:
                    print(Colors.error(f"Image download failed after {retries} attempts: {e}"))
                    raise
                await asyncio.sleep(0.2 * (attempt + 1))