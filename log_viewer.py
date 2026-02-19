import asyncio
import aiohttp
from pathlib import Path
import sys

SERVER_URL = "http://127.0.0.1:8080/logs"

def _configure_utf8_console():
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

async def run_log_viewer():
    _configure_utf8_console()
    
    print("=" * 60)
    print("MangaLib Server - Real-time Log Viewer")
    print("Press Ctrl+C to close")
    print("=" * 60)
    print()
    print("Connecting to server...")

    last_logs = set()

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(SERVER_URL, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        logs = data.get("logs", [])

                        current_logs = set(logs)
                        new_logs = [log for log in logs if log not in last_logs]

                        for log in new_logs:
                            print(log, flush=True)

                        last_logs = current_logs
                    else:
                        print(f"Server returned status: {response.status}", flush=True)

            except aiohttp.ClientError as e:
                print(f"Waiting for server... ({type(e).__name__})", flush=True)
            except Exception as e:
                print(f"Error: {e}", flush=True)

            await asyncio.sleep(1)

def main():
    try:
        asyncio.run(run_log_viewer())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nLog viewer error: {e}")

if __name__ == "__main__":
    main()
