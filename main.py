import asyncio
import csv
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

from config import Config
from downloader import ChapterDownloader
from utils import parse_yes_no, clear_console, extract_slug_from_url, get_api_config_for_domain, is_token_required

# Глобальные переменные сервера

_server_process: Optional[subprocess.Popen] = None
_server_thread: Optional[threading.Thread] = None
_server_started = threading.Event()

# Утилиты консоли

def configure_utf8_console() -> None:
    # Настраивает UTF-8 кодировку для консоли.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def print_header() -> None:
    # Выводит основной заголовок.
    print()
    print("=" * 50)


def print_section(title: str) -> None:
    # Выводит заголовок секции.
    print()
    print(title)


def print_info(message: str) -> None:
    # Выводит информационное сообщение.
    print(f"  → {message}")


def print_launcher_header() -> None:
    # Выводит заголовок лаунчера.
    print("=" * 50)
    print("       MangaLib Downloader Launcher")
    print("=" * 50)
    print()
    print("Starting MangaLib Downloader...")
    print()


def print_main_menu() -> None:
    # Выводит главное меню.
    clear_console()
    print(f"╔══════════════════════════════════════════╗")
    print(f"║         MangaLib Downloader v1.0         ║")
    print(f"╚══════════════════════════════════════════╝")
    print()
    print("Выберите режим:")
    print("  1. Ручная загрузка (URL)")
    print("  2. Пакетное обновление из CSV")
    print("  3. Логи сервера (real-time)")
    print("  4. Остановить сервер")
    print("  5. Выход")

# Управление сервером

def is_server_running(host: str = "127.0.0.1", port: int = 8080) -> bool:
    # Проверяет, запущен ли сервер на указанном порту.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def run_server_thread(server_log_path: str) -> None:
    # Запускает сервер в потоке.
    import logging
    from aiohttp import web
    from server import app, logger as server_logger

    async def run_app():
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 8080)
        await site.start()
        server_logger.info(
            "Server ready. Supports: v2.shlib.life, mangalib.me, "
            "mangalib.org, ranobelib.me, hentailib.me"
        )
        _server_started.set()
        
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()

    try:
        asyncio.run(run_app())
    except Exception as e:
        logging.error(f"Server thread error: {e}")
        _server_started.set()


def start_background_server() -> Optional[subprocess.Popen]:
    # Запускает сервер в фоновом режиме.
    global _server_thread

    script_dir = Path(__file__).parent
    _server_started.clear()

    # Запуск в потоке для frozen executable
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return _start_server_in_thread()

    # Запуск как отдельный процесс
    return _start_server_as_process(script_dir)


def _start_server_in_thread() -> Optional[subprocess.Popen]:
    # Запускает сервер в потоке.
    global _server_thread

    try:
        _server_thread = threading.Thread(
            target=run_server_thread,
            args=("",),
            daemon=True
        )
        _server_thread.start()

        if _server_started.wait(timeout=10):
            print("Server started successfully in background thread")
            return None
        else:
            print("Warning: Server thread failed to start within timeout")
            return None

    except Exception as e:
        print(f"Error starting server thread: {e}")
        return None


def _start_server_as_process(script_dir: Path) -> Optional[subprocess.Popen]:
    # Запускает сервер как отдельный процесс.
    server_script = script_dir / "server.py"

    if not server_script.exists():
        print(f"Warning: server.py not found at {server_script}")
        return None

    try:
        CREATE_NO_WINDOW = 0x08000000
        process = subprocess.Popen(
            [sys.executable, str(server_script)],
            creationflags=CREATE_NO_WINDOW,
            cwd=str(script_dir)
        )

        time.sleep(2)

        if is_server_running():
            print(f"Server started successfully (PID: {process.pid})")
            return process
        else:
            print("Warning: Server may have failed to start")
            return None

    except Exception as e:
        print(f"Error starting server: {e}")
        return None


def stop_background_server() -> None:
    # Останавливает фоновый сервер.
    global _server_process, _server_thread

    if _server_process is not None:
        try:
            _server_process.terminate()
            _server_process.wait(timeout=3)
            print("Background server stopped.")
        except Exception:
            try:
                _server_process.kill()
            except Exception:
                pass
        _server_process = None

    _server_thread = None


def open_log_viewer() -> None:
    # Открывает просмотрщик логов в новом окне.
    script_dir = Path(__file__).parent

    try:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            subprocess.Popen(
                [sys.executable, "--log-viewer"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=str(script_dir)
            )
        else:
            viewer_script = script_dir / "log_viewer.py"
            subprocess.Popen(
                ["python", str(viewer_script.absolute())],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=str(script_dir)
            )
        print("Log viewer opened in new window.")

    except Exception as e:
        print(f"Error opening log viewer: {e}")


def signal_handler(signum, frame) -> None:
    # Обработчик сигналов завершения.
    print("\nShutting down...")
    stop_background_server()
    sys.exit(0)

# Конфигурация

def prompt_batch_config() -> Config:
    # Запрашивает настройки для пакетной загрузки.
    print_header()
    print_section("Настройки пакетной загрузки")
    print_header()

    api_config = _prompt_api_selection()
    
    try:
        max_chapters = int(input(f"\nМакс. глав одновременно [по умолчанию 1]: ").strip() or "1")
        max_images = int(input(f"Макс. изображений одновременно [по умолчанию 5]: ").strip() or "5")
        delay = float(input(f"Задержка между запросами (сек) [по умолчанию 0.5]: ").strip() or "0.5")
    except ValueError:
        print(f"\nНеверное число, используются значения по умолчанию")
        max_chapters, max_images, delay = 1, 5, 0.5

    output_dir_input = input(f"\nДиректория для загрузки [по умолчанию downloads]: ").strip()
    output_dir = Path(output_dir_input) if output_dir_input else Path("downloads")

    pack_cbz = _prompt_yes_no("Собирать CBZ архивы", "n")
    generate_metadata = _prompt_yes_no("Создавать метаданные (ComicInfo)", "n")

    return _create_config(
        manga_slug="dummy-batch-slug",
        chapter_range=(0, 0),
        extra_chapters=[],
        max_chapters=max_chapters,
        max_images=max_images,
        delay=delay,
        output_dir=output_dir,
        pack_cbz=pack_cbz,
        generate_metadata=generate_metadata,
        api_config=api_config
    )


def prompt_user_config() -> Config:
    # Запрашивает настройки для ручной загрузки.
    print_header()
    print_section("Настройки ручной загрузки")
    print_header()

    manga_url = input(f"\nСсылка на мангу: ").strip()
    manga_slug = extract_slug_from_url(manga_url)
    
    api_config = _detect_api_config_from_url(manga_url)
    
    print(f"\n  → Slug: {manga_slug}")

    try:
        start = int(input(f"\nНачальный индекс главы: "))
        end = int(input(f"Конечный индекс главы: "))
    except ValueError:
        print(f"\nНеверный ввод, используется диапазон 1-1")
        start, end = 1, 1

    extra_chapters = _prompt_extra_chapters()
    
    try:
        title_override = input(f"Название манги [Enter — по умолчанию]: ").strip() or None
        max_chapters = int(input(f"Макс. глав одновременно [по умолчанию 1]: ").strip() or "1")
        max_images = int(input(f"Макс. изображений одновременно [по умолчанию 5]: ").strip() or "5")
        delay = float(input(f"Задержка между запросами (сек) [по умолчанию 0.5]: ").strip() or "0.5")
    except ValueError:
        print(f"\nНеверное число, используются значения по умолчанию")
        title_override, max_chapters, max_images, delay = None, 1, 5, 0.5

    output_dir_input = input(f"\nДиректория для загрузки [по умолчанию downloads]: ").strip()
    output_dir = Path(output_dir_input) if output_dir_input else Path("downloads")

    pack_cbz = _prompt_yes_no("Собирать CBZ архивы", "n")
    generate_metadata = _prompt_yes_no("Создавать метаданные (ComicInfo)", "n")

    return _create_config(
        manga_slug=manga_slug,
        chapter_range=(start, end),
        extra_chapters=extra_chapters,
        series_title_override=title_override,
        max_chapters=max_chapters,
        max_images=max_images,
        delay=delay,
        output_dir=output_dir,
        pack_cbz=pack_cbz,
        generate_metadata=generate_metadata,
        api_config=api_config
    )


def _prompt_api_selection() -> Dict[str, Any]:
    # Запрашивает выбор API у пользователя.
    print(f"\nВыберите источник API:")
    print(f"  1. MangaLib (mangalib.me)")
    print(f"  2. SlashLib (v2.shlib.life)")
    print(f"  3. RanobeLib (ranobelib.me)")
    print(f"  4. HentaiLib (hentailib.me)")

    api_choice = input(f"\nВаш выбор [1-4, по умолчанию 1]: ").strip() or "1"

    if api_choice == "2":
        print_info("Выбран API SlashLib")
        config = get_api_config_for_domain("v2.shlib.life")
        print_info("Требуется Bearer Token (можно получить через расширение)")
        config["auth_token"] = input(f"Токен [Enter — без токена]: ").strip() or None

    elif api_choice == "3":
        print_info("Выбран API RanobeLib")
        config = get_api_config_for_domain("ranobelib.me")
        print_info("Текстовые главы, без изображений")
        print_info("Для доступа к 18+ контенту требуется Bearer Token")
        config["auth_token"] = input(f"Токен [Enter — без токена]: ").strip() or None

    elif api_choice == "4":
        print_info("Выбран API HentaiLib")
        config = get_api_config_for_domain("hentailib.me")
        print_info("Требуется Bearer Token (можно получить через расширение)")
        config["auth_token"] = input(f"Токен [Enter — без токена]: ").strip() or None

    else:
        print_info("Выбран API MangaLib")
        config = get_api_config_for_domain("mangalib.me")
        print_info("Для доступа к 18+ контенту требуется Bearer Token")
        config["auth_token"] = input(f"Токен [Enter — без токена]: ").strip() or None

    return config


def _detect_api_config_from_url(manga_url: str) -> Dict[str, Any]:
    # Определяет конфигурацию API из URL.
    if "v2.shlib.life" in manga_url:
        print_info("Обнаружена ссылка на SlashLib")
        config = get_api_config_for_domain("v2.shlib.life")
        print_info("Требуется Bearer Token (можно получить через расширение)")
        config["auth_token"] = input(f"Токен [Enter — без токена]: ").strip() or None

    elif "hentailib.me" in manga_url:
        print_info("Обнаружена ссылка на HentaiLib")
        config = get_api_config_for_domain("hentailib.me")
        print_info("Требуется Bearer Token (можно получить через расширение)")
        config["auth_token"] = input(f"Токен [Enter — без токена]: ").strip() or None

    elif "ranobelib.me" in manga_url:
        print_info("Обнаружена ссылка на RanobeLib")
        config = get_api_config_for_domain("ranobelib.me")
        print_info("Текстовые главы, без изображений")
        print_info("Для доступа к 18+ контенту требуется Bearer Token")
        config["auth_token"] = input(f"Токен [Enter — без токена]: ").strip() or None

    else:
        print_info("Используется API MangaLib")
        config = get_api_config_for_domain("mangalib.me")
        print_info("Для доступа к 18+ контенту требуется Bearer Token")
        config["auth_token"] = input(f"Токен [Enter — без токена]: ").strip() or None

    return config


def _prompt_extra_chapters() -> Optional[List[float]]:
    # Запрашивает дополнительные главы.
    extra_chapters_input = input(
        f"Дополнительные главы [например 0.5, 10.1, Enter — пропустить]: "
    ).strip()
    
    if extra_chapters_input:
        try:
            return [
                float(c.strip())
                for c in extra_chapters_input.split(',')
                if c.strip()
            ]
        except ValueError:
            print(f"Не удалось распознать номера глав")
    
    return None


def _prompt_yes_no(prompt: str, default: str = "n") -> bool:
    # Запрашивает ответ y/n.
    response = input(f"{prompt} (y/n, по умолчанию {default}): ").strip().lower() or default
    return parse_yes_no(response, default)


def _create_config(
    manga_slug: str,
    chapter_range: Tuple[int, int],
    extra_chapters: Optional[List[float]],
    series_title_override: Optional[str] = None,
    max_chapters: int = 1,
    max_images: int = 5,
    delay: float = 0.5,
    output_dir: Path = Path("downloads"),
    pack_cbz: bool = False,
    generate_metadata: bool = False,
    api_config: Optional[Dict[str, Any]] = None
) -> Config:
    # Создает конфигурацию.
    if api_config is None:
        api_config = get_api_config_for_domain("mangalib.me")
    
    return Config(
        manga_slug=manga_slug,
        chapter_range=chapter_range,
        extra_chapters=extra_chapters,
        series_title_override=series_title_override,
        max_concurrent_chapters=max_chapters,
        max_concurrent_images=max_images,
        request_delay=delay,
        output_dir=output_dir,
        cleanup_temp=True,
        pack_cbz=pack_cbz,
        generate_metadata=generate_metadata,
        api_base=api_config["api"],
        image_host=api_config["image_host"],
        referer=api_config["referer"],
        auth_token=api_config.get("auth_token"),
        site_type=api_config["site_type"],
    )

# CSV

def read_csv_tasks(csv_path: Path) -> List[Dict[str, Any]]:
    # Читает задачи из CSV файла.
    tasks = []

    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                task = _parse_csv_row(row)
                if task:
                    tasks.append(task)

    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_path}")
    except Exception as e:
        print(f"Error reading CSV: {e}")
        import traceback
        traceback.print_exc()

    print(f"\nTotal tasks extracted from CSV: {len(tasks)}")
    return tasks


def _parse_csv_row(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
    # Парсит одну строку CSV.
    slug = (row.get('SLUG') or row.get('slug') or "").strip()
    if not slug:
        return None

    # Новый формат: MISSING = "index:volume:number, ..."
    missing_str = (row.get('MISSING') or "").strip()
    if missing_str:
        indices = _parse_missing_indices(missing_str)
        if indices:
            return {'slug': slug, 'chapters': indices}

    # Старый формат
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
            print(f"Warning: Could not parse chapter numbers for {slug}. Skipping.")

    return None


def _parse_missing_indices(missing_str: str) -> List[float]:
    # Парсит строку недостающих индексов.
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

# Основная логика

async def update_from_csv(csv_path: Path) -> None:
    # Выполняет пакетное обновление из CSV.
    tasks = read_csv_tasks(csv_path)

    if not tasks:
        print("Не найдено тайтлов для обновления в CSV. Выход.")
        return

    clear_console()

    try:
        base_cfg = prompt_batch_config()
    except Exception as e:
        print(f"Ошибка при получении базовой конфигурации: {e}. Невозможно продолжить.")
        return

    clear_console()
    print(f"Найдено {len(tasks)} тайтлов для обновления. Начинаем загрузку по очереди...")

    for i, task in enumerate(tasks, 1):
        slug = task['slug']
        chapters = task['chapters']

        if chapters:
            chapters_str = ', '.join(
                str(int(x)) if float(x).is_integer() else str(x)
                for x in chapters
            )
            print(f"\n[Задача {i}/{len(tasks)}] >>> Начинаем обновление тайтла: {slug} (Индексы: {chapters_str})")
        else:
            print(f"\n[Задача {i}/{len(tasks)}] >>> Начинаем загрузку тайтла: {slug} (Все доступные главы)")

        cfg_update = Config(
            manga_slug=slug,
            chapter_range=(0, 0),
            extra_chapters=chapters,
            series_title_override=base_cfg.series_title_override,
            volume_override=base_cfg.volume_override,
            output_dir=base_cfg.output_dir,
            max_concurrent_chapters=base_cfg.max_concurrent_chapters,
            max_concurrent_images=base_cfg.max_concurrent_images,
            request_delay=base_cfg.request_delay,
            fallback_volume_range=base_cfg.fallback_volume_range,
            cleanup_temp=base_cfg.cleanup_temp,
            pack_cbz=base_cfg.pack_cbz,
            generate_metadata=base_cfg.generate_metadata,
            api_base=base_cfg.api_base,
            image_host=base_cfg.image_host,
            referer=base_cfg.referer,
            auth_token=base_cfg.auth_token,
        )

        downloader = ChapterDownloader(cfg_update)
        await downloader.download_chapters()

        print(f"[Задача {i}/{len(tasks)}] <<< Завершено обновление тайтла: {slug}")


async def main_loop() -> None:
    # Основной цикл приложения.
    while True:
        print_main_menu()

        mode = input("\nВаш выбор [1-5, по умолчанию 1]: ").strip() or "1"

        if mode == "2":
            csv_path = Path("chapter_checker_log.csv")
            await update_from_csv(csv_path)
            
        elif mode == "3":
            open_log_viewer()
            continue
            
        elif mode == "4":
            print()
            stop_background_server()
            input("Нажмите Enter для продолжения...")
            continue
            
        elif mode == "5":
            print()
            break
            
        else:
            cfg = prompt_user_config()
            downloader = ChapterDownloader(cfg)
            await downloader.download_chapters()


async def main() -> None:
    # Точка входа приложения.
    configure_utf8_console()
    print_launcher_header()

    global _server_process
    server_running = is_server_running()

    if server_running:
        print("✓ Сервер уже запущен на порту 8080")
    else:
        print("Запуск фонового сервера...")
        _server_process = start_background_server()

    await asyncio.sleep(0.5)
    clear_console()

    try:
        await main_loop()
    finally:
        stop_background_server()

# Запуск

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Запуск в режиме просмотра логов
    if "--log-viewer" in sys.argv:
        from log_viewer import main as log_viewer_main
        log_viewer_main()
        sys.exit(0)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОперация отменена пользователем.")
        stop_background_server()
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        stop_background_server()
