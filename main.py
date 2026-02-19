import asyncio
import sys
import socket
import subprocess
import time
import signal
import threading
from pathlib import Path
from config import Config
from downloader import ChapterDownloader
import csv
from typing import List, Tuple, Dict, Any, Optional

_server_process: Optional[subprocess.Popen] = None
_server_thread: Optional[threading.Thread] = None
_server_started = threading.Event()


def _parse_yes_no(value: str, default: str = "n") -> bool:
    value = value.strip().lower()
    
    if not value:
        value = default
    
    first_char = value[0] if value else ''
    
    if first_char in ('y', 'н'):
        return True
    if first_char in ('n', 'т'):
        return False
    
    return default == 'y'


def _configure_utf8_console() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _is_server_running(host: str = "127.0.0.1", port: int = 8080) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _run_server_thread(server_log_path: str):
    import logging
    from aiohttp import web
    
    file_handler = logging.FileHandler(server_log_path, mode='a', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
    
    from server import app, logger as server_logger
    
    server_logger.addHandler(file_handler)
    server_logger.setLevel(logging.INFO)
    
    async def run_app():
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 8080)
        await site.start()
        server_logger.info("Server ready. Supports: v2.shlib.life, mangalib.me, mangalib.org, ranobelib.me")
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
    finally:
        file_handler.close()


def _start_background_server() -> Optional[subprocess.Popen]:
    global _server_thread
    
    server_log = Path("server.log")
    script_dir = Path(__file__).parent

    _server_started.clear()

    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        try:
            with open(server_log, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n{'='*50}\n")
                log_file.write(f"Server started at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.write(f"{'='*50}\n")

            _server_thread = threading.Thread(target=_run_server_thread, args=(str(server_log),), daemon=True)
            _server_thread.start()
            
            if _server_started.wait(timeout=10):
                print("Server started successfully in background thread")
                return None
            else:
                print("Warning: Server thread failed to start within timeout. Check server.log")
                return None
                
        except Exception as e:
            print(f"Error starting server thread: {e}")
            return None
    
    server_script = script_dir / "server.py"
    
    if not server_script.exists():
        print(f"Warning: server.py not found at {server_script}")
        return None
    
    try:
        CREATE_NO_WINDOW = 0x08000000
        with open(server_log, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n{'='*50}\n")
            log_file.write(f"Server started at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write(f"{'='*50}\n")
        
        process = subprocess.Popen(
            [sys.executable, str(server_script)],
            stdout=open(server_log, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
            cwd=str(script_dir)
        )
        
        time.sleep(2)
        
        if _is_server_running():
            print(f"Server started successfully (PID: {process.pid})")
            return process
        else:
            print("Warning: Server may have failed to start. Check server.log")
            return None
            
    except Exception as e:
        print(f"Error starting server: {e}")
        return None


def _stop_background_server():
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


def _open_log_viewer():
    script_dir = Path(__file__).parent
    
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        viewer_script = Path(sys._MEIPASS) / "log_viewer.py"
    else:
        viewer_script = script_dir / "log_viewer.py"

    if not viewer_script.exists():
        print(f"Error: log_viewer.py not found at {viewer_script}")
        return
    
    try:
        import subprocess
        subprocess.Popen(
            ["python", str(viewer_script.absolute())],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=str(script_dir)
        )
        print("Log viewer opened in new window.")
        
    except Exception as e:
        print(f"Error opening log viewer: {e}")


def _signal_handler(signum, frame):
    print("\nShutting down...")
    _stop_background_server()
    sys.exit(0)

def read_csv_tasks(csv_path: Path) -> List[Dict[str, Any]]:
    tasks = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                slug = (row.get('SLUG') or row.get('slug') or "").strip()
                if not slug:
                    continue

                # Новый простой формат (server.py):
                # MISSING = "index:volume:number, index:volume:number, ..."
                missing_str = (row.get('MISSING') or "").strip()
                if missing_str:
                    indices: List[float] = []
                    for token in missing_str.split(','):
                        token = token.strip()
                        if not token:
                            continue
                        # token => "index:volume:number"
                        parts = token.split(':')
                        if not parts:
                            continue
                        try:
                            idx = int(parts[0].strip())
                            indices.append(float(idx))
                        except ValueError:
                            continue

                    if indices:
                        tasks.append({'slug': slug, 'chapters': indices})
                    continue

                status = row.get('СТАТУС', '') or ""
                missing_chapters_str = (row.get('ПРОПУЩЕННЫЕ_ГЛАВЫ', '') or '').strip()
                if "Не хватает" in status and missing_chapters_str:
                    try:
                        missing_chapters = [float(c.strip()) for c in missing_chapters_str.split(',') if c.strip()]
                        if missing_chapters:
                            tasks.append({'slug': slug, 'chapters': missing_chapters})
                    except ValueError:
                        print(f"Warning: Could not parse chapter numbers for {slug}. Skipping.")

    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_path}")
    except Exception as e:
        print(f"Error reading CSV: {e}")
        import traceback
        traceback.print_exc()
        
    print(f"\nTotal tasks extracted from CSV: {len(tasks)}")
    return tasks

def _clear_console():
    import os
    os.system('cls' if os.name == 'nt' else 'clear')


def _print_launcher_header():
    print("=" * 50)
    print("       MangaLib Downloader Launcher")
    print("=" * 50)
    print()
    print("Starting MangaLib Downloader...")
    print()


def _print_header():
    print()
    print("=" * 50)


def _print_section(title: str):
    print()
    print(title)


def _print_info(message: str):
    print(f"  → {message}")


def prompt_batch_config() -> Config:
    _print_header()
    _print_section("Настройки пакетной загрузки")
    _print_header()

    print(f"\nВыберите источник API:")
    print(f"  1. MangaLib (mangalib.me)")
    print(f"  2. SlashLib (v2.shlib.life)")
    print(f"  3. RanobeLib (ranobelib.me)")
    
    api_choice = input(f"\nВаш выбор [1-3, по умолчанию 1]: ").strip() or "1"

    auth_token: Optional[str] = None
    site_type = "mangalib"

    if api_choice == "2":
        _print_info("Выбран API SlashLib")
        default_api = "https://hapi.hentaicdn.org/api/manga"
        default_image_host = "https://img3.mixlib.me"
        default_referer = "https://v2.shlib.life/"
        site_type = "shlib"
        _print_info("Требуется Bearer Token (можно получить через расширение)")
        auth_token = input(f"Токен [Enter — без токена]: ").strip() or None

    elif api_choice == "3":
        _print_info("Выбран API RanobeLib")
        default_api = "https://api.cdnlibs.org/api/manga"
        default_image_host = "https://img3.mixlib.me"
        default_referer = "https://ranobelib.me/"
        site_type = "ranobelib"
        _print_info("Текстовые главы, без изображений")

    else:
        _print_info("Выбран API MangaLib")
        default_api = "https://api.cdnlibs.org/api/manga"
        default_image_host = "https://img3.mixlib.me"
        default_referer = "https://mangalib.me/"

    try:
        max_chapters = int(input(f"\nМакс. глав одновременно [по умолчанию 1]: ").strip() or "1")
        max_images = int(input(f"Макс. изображений одновременно [по умолчанию 5]: ").strip() or "5")
        delay = float(input(f"Задержка между запросами (сек) [по умолчанию 0.5]: ").strip() or "0.5")
    except ValueError:
        print(f"\nНеверное число, используются значения по умолчанию")
        max_chapters, max_images, delay = 1, 5, 0.5

    output_dir_input = input(f"\nДиректория для загрузки [по умолчанию downloads]: ").strip()
    output_dir = Path(output_dir_input) if output_dir_input else Path("downloads")

    pack_cbz_input = input(f"Собирать CBZ архивы (y/n, по умолчанию n): ").strip().lower() or "n"
    pack_cbz = _parse_yes_no(pack_cbz_input, "n")

    generate_metadata_input = input(f"Создавать метаданные (ComicInfo) (y/n, по умолчанию n): ").strip().lower() or "n"
    generate_metadata = _parse_yes_no(generate_metadata_input, "n")

    # Создаем фиктивную конфигурацию.
    cfg = Config(
        manga_slug="dummy-batch-slug",
        chapter_range=(0, 0),
        extra_chapters=[],
        series_title_override=None,
        max_concurrent_chapters=max_chapters,
        max_concurrent_images=max_images,
        request_delay=delay,
        output_dir=output_dir,
        cleanup_temp=True,
        pack_cbz=pack_cbz,
        generate_metadata=generate_metadata,
        # Динамические параметры API
        api_base=default_api,
        image_host=default_image_host,
        referer=default_referer,
        auth_token=auth_token,
        site_type=site_type,
    )
    return cfg

def prompt_user_config() -> Config:
    _print_header()
    _print_section("Настройки ручной загрузки")
    _print_header()

    manga_url = input(f"\nСсылка на мангу: ").strip()

    # Извлекаем slug из ссылки
    try:
        manga_slug = manga_url.split("/")[-1].split("?")[0]
        if not manga_slug:
            manga_slug = manga_url.split("/")[-2]
    except IndexError:
        print(f"\nНекорректная ссылка, используется slug по умолчанию")
        manga_slug = "unknown"

    is_slash = "v2.shlib.life" in manga_url
    is_ranobelib = "ranobelib.me" in manga_url

    auth_token: Optional[str] = None
    site_type = "mangalib"

    if is_slash:
        _print_info("Обнаружена ссылка на SlashLib")
        default_api = "https://hapi.hentaicdn.org/api/manga"
        default_image_host = "https://img3.mixlib.me"
        default_referer = "https://v2.shlib.life/"
        site_type = "shlib"
        _print_info("Требуется Bearer Token (можно получить через расширение)")
        auth_token = input(f"Токен [Enter — без токена]: ").strip() or None

    elif is_ranobelib:
        _print_info("Обнаружена ссылка на RanobeLib")
        default_api = "https://api.cdnlibs.org/api/manga"
        default_image_host = "https://img3.mixlib.me"
        default_referer = "https://ranobelib.me/"
        site_type = "ranobelib"
        _print_info("Текстовые главы, без изображений")

    else:
        _print_info("Используется API MangaLib")
        default_api = "https://api.cdnlibs.org/api/manga"
        default_image_host = "https://img3.mixlib.me"
        default_referer = "https://mangalib.me/"

    print(f"\n  → Slug: {manga_slug}")

    try:
        start = int(input(f"\nНачальный индекс главы: "))
        end = int(input(f"Конечный индекс главы: "))
    except ValueError:
        print(f"\nНеверный ввод, используется диапазон 1-1")
        start, end = 1, 1

    extra_chapters_input = input(f"Дополнительные главы [например 0.5, 10.1, Enter — пропустить]: ").strip()
    extra_chapters: Optional[List[float]] = None
    if extra_chapters_input:
        try:
            extra_chapters = [float(c.strip()) for c in extra_chapters_input.split(',') if c.strip()]
        except ValueError:
            print(f"Не удалось распознать номера глав")
            extra_chapters = None

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

    pack_cbz_input = input(f"Собирать CBZ архивы (y/n, по умолчанию n): ").strip().lower() or "n"
    pack_cbz = _parse_yes_no(pack_cbz_input, "n")

    generate_metadata_input = input(f"Создавать метаданные (ComicInfo) (y/n, по умолчанию n): ").strip().lower() or "n"
    generate_metadata = _parse_yes_no(generate_metadata_input, "n")

    cfg = Config(
        manga_slug=manga_slug,
        chapter_range=(start, end),
        extra_chapters=extra_chapters,
        series_title_override=title_override,
        max_concurrent_chapters=max_chapters,
        max_concurrent_images=max_images,
        request_delay=delay,
        output_dir=output_dir,
        cleanup_temp=True,
        pack_cbz=pack_cbz,
        generate_metadata=generate_metadata,
        # Динамические параметры API
        api_base=default_api,
        image_host=default_image_host,
        referer=default_referer,
        auth_token=auth_token,
        site_type=site_type,
    )
    return cfg

async def update_from_csv(csv_path: Path):
    tasks = read_csv_tasks(csv_path)

    if not tasks:
        print("Не найдено тайтлов для обновления в CSV. Выход.")
        return

    _clear_console()
    
    # Получаем общие настройки (API, токен, лимиты и опции)
    try:
        base_cfg = prompt_batch_config()
    except Exception as e:
        print(f"Ошибка при получении базовой конфигурации: {e}. Невозможно продолжить.")
        return

    _clear_console()
    print(f"Найдено {len(tasks)} тайтлов для обновления. Начинаем загрузку по очереди...")

    # Итерация и запуск скачивания для каждого тайтла
    for i, task in enumerate(tasks, 1):
        slug = task['slug']
        chapters = task['chapters']
        
        if chapters:
            print(f"\n[Задача {i}/{len(tasks)}] >>> Начинаем обновление тайтла: {slug} (Индексы: {', '.join(map(lambda x: str(int(x)) if float(x).is_integer() else str(x), chapters))})")
        else:
            print(f"\n[Задача {i}/{len(tasks)}] >>> Начинаем загрузку тайтла: {slug} (Все доступные главы)")
        
        # Создаем новый Config, используя базовые настройки, но переопределяя slug и главы.
        cfg_update = Config(
            manga_slug=slug,
            chapter_range=(0, 0), # Фиктивный диапазон
            # В новом формате server.py — это индексы глав (API index).
            # Они попадут в extra_indices внутри MangaAPIClient.to_chapter_info_list.
            extra_chapters=chapters,
            # Копируем остальные настройки из базовой конфигурации
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

async def main_loop():
    while True:
        _clear_console()
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

        mode = input("\nВаш выбор [1-5, по умолчанию 1]: ").strip() or "1"

        if mode == "2":
            # Режим пакетного обновления
            csv_file_name = "chapter_checker_log.csv"
            csv_path = Path(csv_file_name)
            await update_from_csv(csv_path)
        elif mode == "3":
            _open_log_viewer()
            continue
        elif mode == "4":
            print()
            _stop_background_server()
            input("Нажмите Enter для продолжения...")
            continue
        elif mode == "5":
            print()
            break
        else:
            # Режим ручного скачивания
            cfg = prompt_user_config()
            downloader = ChapterDownloader(cfg)
            await downloader.download_chapters()


async def main():
    _configure_utf8_console()
    
    _print_launcher_header()

    global _server_process
    server_running = _is_server_running()

    if server_running:
        print("✓ Сервер уже запущен на порту 8080")
    else:
        print("Запуск фонового сервера...")
        _server_process = _start_background_server()
    
    await asyncio.sleep(0.5)
    _clear_console()

    try:
        await main_loop()
    finally:
        _stop_background_server()


if __name__ == '__main__':
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОперация отменена пользователем.")
        _stop_background_server()
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        _stop_background_server()