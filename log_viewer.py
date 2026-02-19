import time
import codecs
from pathlib import Path
import sys

LOG_FILE = Path("server.log")

def decode_unicode_escapes(text):
    try:
        return codecs.decode(text, 'unicode_escape')
    except:
        return text

def main():
    print("=" * 60)
    print("MangaLib Server - Real-time Log Viewer")
    print("Press Ctrl+C to close")
    print("=" * 60)
    print()
    
    if not LOG_FILE.exists():
        print("Waiting for server.log to be created...")
        while not LOG_FILE.exists():
            time.sleep(1)
    
    last_size = LOG_FILE.stat().st_size
    
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        f.seek(0, 2)
        
        while True:
            try:
                line = f.readline()
                if line:
                    decoded = decode_unicode_escapes(line.rstrip())
                    print(decoded, flush=True)
                else:
                    time.sleep(0.3)
                    try:
                        current_size = LOG_FILE.stat().st_size
                        if current_size < last_size:
                            f.seek(0)
                        last_size = current_size
                    except FileNotFoundError:
                        pass
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}", flush=True)
                time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
