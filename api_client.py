import asyncio
import aiohttp
import random
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple

from config import Config
from colors import Colors
from models import ChapterInfo


class MangaAPIClient:

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._session: Optional[aiohttp.ClientSession] = None
        # Кэшированные структуры
        self._chapters_map: Dict[str, Dict[float, int | float]] = {}
        self._series_cache: Dict[str, Dict[str, Any]] = {}
        self._full_pool_cache: Dict[str, List[Dict[str, Any]]] = {} # Кэш для всех сырых данных глав
        self._headers = {
            "User-Agent": "Mozilla/5.0 (iPad; CPU OS 18_6_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/142.0.7444.46 Mobile/15E148 Safari/604.1",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.cfg.referer, # Используем реферер из конфига
            "Origin": self.cfg.referer.rstrip("/")
        }

        # Добавляем Bearer Token, если он есть
        if self.cfg.auth_token:
            self._headers["Authorization"] = f"Bearer {self.cfg.auth_token}"

    async def __aenter__(self):
        conn = aiohttp.TCPConnector(limit=self.cfg.max_concurrent_images * 2)
        # Создаем сессию сразу с нужными хедерами
        self._session = aiohttp.ClientSession(connector=conn, headers=self._headers)
        await self._warm_up_session()
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def _warm_up_session(self):
        # Делаем легкий запрос к рефереру, чтобы прогреть соединение
        try:
            async with self._session.get(self.cfg.referer, timeout=6):
                pass
        except Exception:
            pass

    @staticmethod
    def _parse_chapter_number(number: Any) -> Optional[Union[int, float]]:
        if number is None:
            return None
        try:
            return int(number)
        except ValueError:
            try:
                return float(str(number).replace(',', '.'))
            except (ValueError, TypeError):
                return None

    async def fetch_full_chapter_pool(self, slug: str) -> List[Dict[str, Any]]:
        if slug in self._full_pool_cache:
            return self._full_pool_cache[slug]

        # Используем api_base из конфига
        url = f"{self.cfg.api_base}/{slug}/chapters"
        try:
            data = await self._get_json(url, retries=4)
            # API может вернуть:
            # - dict { "data": [...] } (cdnlibs)
            # - dict { "items"/"chapters": [...] } (варианты)
            # - list [...] (некоторые реализации)
            items: List[Dict[str, Any]] = []
            if isinstance(data, list):
                items = [x for x in data if isinstance(x, dict)]
            elif isinstance(data, dict):
                for key in ("data", "items", "chapters"):
                    val = data.get(key)
                    if isinstance(val, list):
                        items = [x for x in val if isinstance(x, dict)]
                        break
            self._full_pool_cache[slug] = items
            return items
        except Exception as e:
            print(Colors.error(f"Не удалось получить список глав: {e}"))
            return []

    async def to_chapter_info_list(
        self,
        slug: str,
        start_num: float,
        end_num: float,
        extra: List[float]
    ) -> List[ChapterInfo]:
        full_data = await self.fetch_full_chapter_pool(slug)
        
        chapter_info_list: List[ChapterInfo] = []
        # Диапазон в конфиге трактуем как ГЛОБАЛЬНЫЕ индексы глав из API (`item["index"]`),
        # потому что `number` может сбрасываться между томами.
        start_idx = int(start_num)
        end_idx = int(end_num)
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        # extra: поддерживаем оба сценария:
        # - целые значения => индекс главы
        # - дробные => номер главы (например 10.1)
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
        
        seen_keys: set[tuple[int, str]] = set()

        for fallback_idx, item in enumerate(full_data):
            raw_number = item.get("number") # Получаем сырое значение
            number = self._parse_chapter_number(raw_number) # Преобразуем во float
            
            volume_raw = item.get("volume")
            volume = 0
            try:
                volume = int(volume_raw)
            except (ValueError, TypeError):
                pass

            # Реальный индекс главы в серии — именно он нужен для сортировки/диапазона.
            api_index_raw = item.get("index")
            if api_index_raw is None:
                api_index_raw = item.get("item_number")
            try:
                api_index = int(api_index_raw)
            except (ValueError, TypeError):
                # fallback: стабильный, но менее точный
                api_index = fallback_idx + 1

            if number is None:
                continue

            # Основной критерий: попадаем в диапазон по глобальному индексу
            in_index_range = start_idx <= api_index <= end_idx
            # Доп. критерий: явное добавление по номеру (дробные extras)
            in_extra_numbers = number in extra_numbers
            # Доп. критерий: явное добавление по индексу (целые extras)
            in_extra_indices = api_index in extra_indices

            if in_index_range or in_extra_numbers or in_extra_indices:
                info = ChapterInfo(
                    number=number,     # Число (для сортировки)
                    number_str=str(raw_number), # Сохраняем строку для запроса
                    index=api_index,
                    volume=volume, 
                    name=item.get("name") or "",
                    pages_count=item.get("pages_count", 0),
                    series_title=None,
                    teams=item.get("teams", []),
                    chapter_id=item.get("id"),
                )

                # номер может повторяться (Volume 2: 1-3), и мы потеряем главы.
                key = (info.volume, info.number_str)
                if key not in seen_keys:
                    chapter_info_list.append(info)
                    seen_keys.add(key)

        # Сортируем по глобальному индексу: корректно склеивает тома в правильном порядке.
        return sorted(chapter_info_list, key=lambda ch: (ch.index, ch.volume, ch.number))

    async def download_image_raw(self, url: str, retries: int = 5) -> tuple[bytes, str]:
        if not self._session:
            raise RuntimeError("Client session is not initialized. Use 'async with MangaAPIClient(...) as api:'")

        headers = {
            **self._headers,
            "Referer": self.cfg.referer,
            "Origin": self.cfg.referer.rstrip("/")
        }

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

    async def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None, 
                       retries: int = 5) -> Dict[str, Any]:
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
        retry_after = headers.get("Retry-After")
        if retry_after:
            # Retry-After может быть числом секунд или HTTP-date — в простом случае пытаемся int
            try:
                # если в заголовке число — используем его
                sec = int(float(retry_after))
                return float(sec) + 1.0
            except Exception:
                # если не число — fallback на экспоненцию
                pass

        # базовый backoff
        base = min(2 ** attempt, 60)
        jitter = random.uniform(0.3, 1.3)
        return base + 0.1 * attempt + jitter

    @staticmethod
    def _parse_float(value: str) -> Optional[float]:
        try:
            return float(value)
        except ValueError:
            try:
                return float(value.replace(",", "."))
            except ValueError:
                return None

    async def fetch_chapters_list(self, slug: str) -> Dict[float, int]:
        if slug in self._chapters_map:
            return self._chapters_map[slug]

        url = f"{self.cfg.api_base}/{slug}/chapters"
        mapping: Dict[float, int] = {}

        try:
            data = await self._get_json(url, retries=4)
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                for key in ("data", "items", "chapters"):
                    val = data.get(key)
                    if isinstance(val, list):
                        items = val
                        break

            for item in items:
                chapter_num = item.get("number")
                volume_num = item.get("volume")

                if chapter_num is None or volume_num is None:
                    continue

                chapter_float = self._parse_float(str(chapter_num))
                try:
                    volume_int = int(volume_num)
                except (ValueError, TypeError):
                    continue

                if chapter_float is not None:
                    mapping[chapter_float] = volume_int
        except Exception:
            mapping = {}

        self._chapters_map[slug] = mapping
        return mapping

    async def fetch_series_info(self, slug: str) -> Dict[str, Any]:
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

    # Тип chapter_num теперь включает str
    async def fetch_chapter_data(self, slug: str, chapter_num: Union[int, float, str],
                                 volume: int) -> Dict[str, Any]:
        url = f"{self.cfg.api_base}/{slug}/chapter"
        # API получит string, если мы его передадим
        return await self._get_json(
            url,
            params={"number": chapter_num, "volume": volume},
            retries=4
        )

    async def resolve_volume(self, slug: str, chapter_num: int) -> int:
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

    def _search_volume_in_metadata(self, metadata: Dict[str, Any], 
                                   target_chapter: float) -> Optional[int]:
        def search(obj) -> Optional[int]:
            if isinstance(obj, dict):
                num = obj.get("number") or obj.get("chapter_number")
                vol = obj.get("volume")

                if num is not None and vol is not None:
                    chapter_float = self._parse_float(str(num))
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
        start, end = self.cfg.fallback_volume_range

        for volume in range(start, end + 1):
            try:
                await asyncio.sleep(0.12)
                await self.fetch_chapter_data(slug, chapter_num, volume)
                return volume
            except Exception:
                continue

        raise ValueError(f"Could not determine volume for chapter {chapter_num}")

    async def download_image(self, url: str, dest: Path, retries: int = 10):
        headers = {
            **self._headers,
            "Referer": self.cfg.referer,
            "Origin": self.cfg.referer.rstrip("/")
        }

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
                # Если ошибка HTTP и последний заход — пробрасываем
                if attempt == retries - 1:
                    print(Colors.error(f"Image download failed after {retries} attempts: {e}"))
                    raise
                await asyncio.sleep(0.2 * (attempt + 1))

            except Exception as e:
                if attempt == retries - 1:
                    print(Colors.error(f"Image download failed after {retries} attempts: {e}"))
                    raise
                await asyncio.sleep(0.2 * (attempt + 1))