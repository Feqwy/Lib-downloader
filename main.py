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
from csv_contract import (
    parse_missing_indices as _parse_missing_indices,
    parse_task_row as _parse_csv_row,
)
from downloader import ChapterDownloader
from reporting import create_reporter, get_reporter, set_reporter
from sites import DEFAULT_SITE, SOURCE_CHOICES, detect_cli_site, get_site
from text_render import parse_text_output
from utils import (
    configure_utf8_console,
    parse_yes_no,
    clear_console,
    extract_slug_from_url,
    get_api_config_for_domain,
    is_token_required,
)


_server_process: Optional[subprocess.Popen] = None
_server_thread: Optional[threading.Thread] = None
_server_started = threading.Event()


def _close_reporter() -> None:
    close = getattr(get_reporter(), "close", None)
    if callable(close):
        close()


def _read_input(prompt: str = "") -> str:
    _close_reporter()
    return input(prompt)


def print_header() -> None:
    print()
    print("=" * 50)


def print_section(title: str) -> None:
    print()
    print(title)


def print_info(message: str) -> None:
    print(f"  → {message}")


def print_launcher_header() -> None:
    print("=" * 50)
    print("       MangaLib Downloader Launcher")
    print("=" * 50)
    print()
    print("Starting MangaLib Downloader...")
    print()


def print_main_menu() -> None:
    clear_console()
    print(f"╔══════════════════════════════════════════╗")
    print(f"║         MangaLib Downloader v2.0.0       ║")
    print(f"╚══════════════════════════════════════════╝")
    print()
    print("Выберите режим:")
    print("  1. Ручная загрузка (URL)")
    print("  2. Пакетное обновление из CSV")
    print("  3. Логи сервера (real-time)")
    print("  4. Остановить сервер")
    print("  5. Выход")


def is_server_running(host: str = "127.0.0.1", port: int = 8080) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def run_server_thread(server_log_path: str) -> None:
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
    global _server_thread

    script_dir = Path(__file__).parent
    _server_started.clear()

    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return _start_server_in_thread()

    return _start_server_as_process(script_dir)


def _start_server_in_thread() -> Optional[subprocess.Popen]:
    global _server_thread

    try:
        _server_thread = threading.Thread(
            target=run_server_thread,
            args=("",),
            daemon=True
        )
        _server_thread.start()

        if _server_started.wait(timeout=10):
            get_reporter().line("Server started successfully in background thread")
            return None
        else:
            get_reporter().warning("Server thread failed to start within timeout")
            return None

    except Exception as e:
        get_reporter().line(f"Error starting server thread: {e}")
        return None


def _start_server_as_process(script_dir: Path) -> Optional[subprocess.Popen]:
    server_script = script_dir / "server.py"

    if not server_script.exists():
        get_reporter().warning(f"server.py not found at {server_script}")
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
            get_reporter().line(f"Server started successfully (PID: {process.pid})")
            return process
        else:
            get_reporter().warning("Server may have failed to start")
            return None

    except Exception as e:
        get_reporter().line(f"Error starting server: {e}")
        return None


def stop_background_server() -> None:
    global _server_process, _server_thread

    if _server_process is not None:
        try:
            _server_process.terminate()
            _server_process.wait(timeout=3)
            get_reporter().line("Background server stopped.")
        except Exception:
            try:
                _server_process.kill()
            except Exception:
                pass
        _server_process = None

    _server_thread = None


def open_log_viewer() -> None:
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
        get_reporter().line("Log viewer opened in new window.")

    except Exception as e:
        get_reporter().line(f"Error opening log viewer: {e}")


def signal_handler(signum, frame) -> None:
    get_reporter().line()
    get_reporter().line("Shutting down...")
    stop_background_server()
    sys.exit(0)


def _prompt_download_options(
    include_title: bool = False,
    text_site: bool = False,
) -> Dict[str, Any]:
    title_override = None

    try:
        if include_title:
            title_override = _read_input(f"Название манги [Enter — по умолчанию]: ").strip() or None
        max_chapters = int(_read_input(f"\nМакс. глав одновременно [по умолчанию 1]: ").strip() or "1")
        max_images = int(_read_input(f"Макс. изображений одновременно [по умолчанию 5]: ").strip() or "5")
        delay = float(_read_input(f"Задержка между запросами (сек) [по умолчанию 0.5]: ").strip() or "0.5")
    except ValueError:
        print(f"\nНеверное число, используются значения по умолчанию")
        if include_title:
            title_override = None
        max_chapters, max_images, delay = 1, 5, 0.5

    output_dir_input = _read_input(f"\nДиректория для загрузки [по умолчанию downloads]: ").strip()
    output_dir = Path(output_dir_input) if output_dir_input else Path("downloads")

    pack_cbz = _prompt_yes_no("Собирать CBZ архивы", "n")
    generate_metadata = _prompt_yes_no("Создавать метаданные (ComicInfo)", "n")

    text_output = "both"
    if text_site:
        text_output = parse_text_output(
            _read_input(
                "Формат текстовых глав [1 — оба файла (по умолчанию), "
                "2 — только TXT, 3 — только HTML]: "
            )
        )

    return {
        "series_title_override": title_override,
        "max_chapters": max_chapters,
        "max_images": max_images,
        "delay": delay,
        "output_dir": output_dir,
        "pack_cbz": pack_cbz,
        "generate_metadata": generate_metadata,
        "text_output": text_output,
    }


def prompt_batch_config() -> Config:
    print_header()
    print_section("Настройки пакетной загрузки")
    print_header()

    api_config = _prompt_api_selection()
    options = _prompt_download_options(
        text_site=api_config.get("site_type") == "ranobelib"
    )

    return _create_config(
        manga_slug="dummy-batch-slug",
        chapter_range=(0, 0),
        extra_chapters=[],
        api_config=api_config,
        **options
    )


def prompt_user_config() -> Config:
    print_header()
    print_section("Настройки ручной загрузки")
    print_header()

    manga_url = _read_input(f"\nСсылка на мангу: ").strip()
    manga_slug = extract_slug_from_url(manga_url)
    
    api_config = _detect_api_config_from_url(manga_url)
    
    print(f"\n  → Slug: {manga_slug}")

    try:
        start = int(_read_input(f"\nНачальный индекс главы: "))
        end = int(_read_input(f"Конечный индекс главы: "))
    except ValueError:
        print(f"\nНеверный ввод, используется диапазон 1-1")
        start, end = 1, 1

    extra_chapters = _prompt_extra_chapters()
    options = _prompt_download_options(
        include_title=True,
        text_site=api_config.get("site_type") == "ranobelib",
    )

    return _create_config(
        manga_slug=manga_slug,
        chapter_range=(start, end),
        extra_chapters=extra_chapters,
        api_config=api_config,
        **options
    )


def _prompt_token_for_site(site) -> Optional[str]:
    for hint in site.token_hints:
        print_info(hint)
    return _read_input(f"Токен [Enter — без токена]: ").strip() or None


def _api_config_for_site(site) -> Dict[str, Any]:
    config = site.as_api_dict()
    config["auth_token"] = _prompt_token_for_site(site)
    return config


def _prompt_api_selection() -> Dict[str, Any]:
    print(f"\nВыберите источник API:")
    for index, (domain, label) in enumerate(SOURCE_CHOICES, start=1):
        print(f"  {index}. {label} ({domain})")

    api_choice = _read_input(f"\nВаш выбор [1-4, по умолчанию 1]: ").strip() or "1"

    try:
        choice_index = int(api_choice)
    except ValueError:
        choice_index = 1

    if not 1 <= choice_index <= len(SOURCE_CHOICES):
        choice_index = 1

    site = get_site(SOURCE_CHOICES[choice_index - 1][0])
    print_info(f"Выбран API {site.label}")
    return _api_config_for_site(site)


def _detect_api_config_from_url(manga_url: str) -> Dict[str, Any]:
    site = detect_cli_site(manga_url)

    if site is DEFAULT_SITE:
        print_info("Используется API MangaLib")
    else:
        print_info(f"Обнаружена ссылка на {site.label}")

    return _api_config_for_site(site)


def _prompt_extra_chapters() -> Optional[List[float]]:
    extra_chapters_input = _read_input(
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
    response = _read_input(f"{prompt} (y/n, по умолчанию {default}): ").strip().lower() or default
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
    text_output: str = "both",
    api_config: Optional[Dict[str, Any]] = None
) -> Config:
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
        text_output=text_output,
        api_base=api_config["api"],
        image_host=api_config["image_host"],
        referer=api_config["referer"],
        auth_token=api_config.get("auth_token"),
        site_type=api_config["site_type"],
    )


def read_csv_tasks(csv_path: Path) -> List[Dict[str, Any]]:
    tasks = []

    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                task = _parse_csv_row(row, on_warning=get_reporter().warning)
                if task:
                    tasks.append(task)

    except FileNotFoundError:
        get_reporter().error(f"CSV file not found at {csv_path}")
    except Exception as e:
        get_reporter().line(f"Error reading CSV: {e}")
        import traceback
        traceback.print_exc()

    get_reporter().line()
    get_reporter().line(f"Total tasks extracted from CSV: {len(tasks)}")
    return tasks


async def update_from_csv(csv_path: Path) -> None:
    tasks = read_csv_tasks(csv_path)

    if not tasks:
        get_reporter().line("Не найдено тайтлов для обновления в CSV. Выход.")
        return

    clear_console()

    try:
        base_cfg = prompt_batch_config()
    except Exception as e:
        get_reporter().line(
            f"Ошибка при получении базовой конфигурации: {e}. "
            f"Невозможно продолжить."
        )
        return

    clear_console()
    get_reporter().batch_started(len(tasks))

    for i, task in enumerate(tasks, 1):
        slug = task['slug']
        chapters = task['chapters']

        get_reporter().batch_task_started(i, len(tasks), slug, chapters)

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
            text_output=base_cfg.text_output,
            api_base=base_cfg.api_base,
            image_host=base_cfg.image_host,
            referer=base_cfg.referer,
            auth_token=base_cfg.auth_token,
            site_type=base_cfg.site_type,
        )

        downloader = ChapterDownloader(cfg_update, get_reporter())
        await downloader.download_chapters()

        get_reporter().batch_task_finished(i, len(tasks), slug)


async def main_loop() -> None:
    while True:
        print_main_menu()

        mode = _read_input("\nВаш выбор [1-5, по умолчанию 1]: ").strip() or "1"

        if mode == "2":
            csv_path = Path("chapter_checker_log.csv")
            await update_from_csv(csv_path)
            
        elif mode == "3":
            open_log_viewer()
            continue
            
        elif mode == "4":
            get_reporter().line()
            stop_background_server()
            _read_input("Нажмите Enter для продолжения...")
            continue
            
        elif mode == "5":
            get_reporter().line()
            break
            
        else:
            cfg = prompt_user_config()
            downloader = ChapterDownloader(cfg, get_reporter())
            await downloader.download_chapters()


async def main() -> None:
    configure_utf8_console()
    set_reporter(create_reporter())
    print_launcher_header()

    global _server_process
    server_running = is_server_running()

    if server_running:
        get_reporter().line("✓ Сервер уже запущен на порту 8080")
    else:
        get_reporter().line("Запуск фонового сервера...")
        _server_process = start_background_server()

    await asyncio.sleep(0.5)
    clear_console()

    try:
        await main_loop()
    finally:
        _close_reporter()
        stop_background_server()


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if "--log-viewer" in sys.argv:
        from log_viewer import main as log_viewer_main
        log_viewer_main()
        sys.exit(0)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _close_reporter()
        get_reporter().line()
        get_reporter().line("Операция отменена пользователем.")
        stop_background_server()
    except Exception as e:
        _close_reporter()
        get_reporter().line(f"Произошла непредвиденная ошибка: {e}")
        stop_background_server()
