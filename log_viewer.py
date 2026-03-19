import asyncio
from typing import Set

import aiohttp

from utils import configure_utf8_console

SERVER_URL = "http://127.0.0.1:8080/logs"


def print_header() -> None:
    # Выводит заголовок просмотрщика логов.
    print("=" * 60)
    print("MangaLib Server - Real-time Log Viewer")
    print("Press Ctrl+C to close")
    print("=" * 60)
    print()
    print("Connecting to server...")


async def run_log_viewer() -> None:
    # Запускает цикл просмотра логов.
    configure_utf8_console()
    print_header()

    last_logs: Set[str] = set()

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(SERVER_URL, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        logs = data.get("logs", [])
                        await _process_logs(logs, last_logs)
                    else:
                        print(f"Server returned status: {response.status}", flush=True)

            except aiohttp.ClientError as e:
                print(f"Waiting for server... ({type(e).__name__})", flush=True)
            except Exception as e:
                print(f"Error: {e}", flush=True)

            await asyncio.sleep(1)


async def _process_logs(logs: list, last_logs: Set[str]) -> None:
    # Обрабатывает и выводит новые логи.
    current_logs = set(logs)
    new_logs = [log for log in logs if log not in last_logs]

    for log in new_logs:
        print(log, flush=True)

    last_logs.clear()
    last_logs.update(current_logs)


def main() -> None:
    # Точка входа просмотрщика логов.
    try:
        asyncio.run(run_log_viewer())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nLog viewer error: {e}")


if __name__ == "__main__":
    main()
