import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Protocol

from tqdm import tqdm

from colors import Colors


class Reporter(Protocol):

    def line(self, text: str = "") -> None:
        """Print a raw line without decoration."""

    def info(self, message: str) -> None:
        """Print an info message."""

    def success(self, message: str) -> None:
        """Print a success message."""

    def warning(self, message: str) -> None:
        """Print a warning message."""

    def error(self, message: str) -> None:
        """Print an error message."""

    def bold(self, message: str) -> None:
        """Print a bold message."""

    def progress_start(self, total: int, desc: str, unit: str = "img") -> Any:
        """Start a progress bar and return its handle."""

    def progress_update(self, progress: Any) -> None:
        """Advance the progress bar by one step."""

    def progress_finish(self, progress: Any) -> None:
        """Close the progress bar."""

    def series_header(
        self,
        series_title: str,
        start: int,
        end: int,
        extra_chapters: Optional[List[float]] = None,
        is_ranobelib: bool = False,
        max_chapters: int = 1,
        max_images: int = 5,
    ) -> None:
        """Print the series header."""

    def chapters_total(self, total: int) -> None:
        """Report how many chapters are going to be downloaded."""

    def chapter_started(self, number: Any) -> None:
        """Report that a chapter download has started."""

    def chapter_finished(self, number: Any) -> None:
        """Report that a chapter download has finished."""

    def rate_limited(
        self,
        wait: float,
        kind: str = "json",
        attempt: int = 0,
        retries: int = 0,
    ) -> None:
        """Report a 429 wait before the next attempt."""

    def summary(
        self,
        successful: int,
        total: int,
        failed: int,
        output_dir: Path,
    ) -> None:
        """Print the final summary."""

    def batch_started(self, total: int) -> None:
        """Report the start of a CSV batch run."""

    def batch_task_started(
        self,
        index: int,
        total: int,
        slug: str,
        chapters: Optional[List[float]],
    ) -> None:
        """Report the start of a single batch task."""

    def batch_task_finished(self, index: int, total: int, slug: str) -> None:
        """Report the end of a single batch task."""


class ConsoleReporter:
    """Reporter that reproduces the historical console output byte for byte."""

    _RATE_LIMIT_MESSAGES = {
        "json": (
            "Rate limit (429). Retry in {wait:.2f}s... "
            "(Attempt {attempt}/{retries})"
        ),
        "json_exception": (
            "Rate limit (429) via exception. Retry in {wait:.2f}s... "
            "(Attempt {attempt}/{retries})"
        ),
        "image": (
            "Rate limit (429) for image. Retry in {wait:.2f}s... "
            "(Attempt {attempt}/{retries})"
        ),
    }

    def line(self, text: str = "") -> None:
        print(text)

    def info(self, message: str) -> None:
        print(Colors.info(message))

    def success(self, message: str) -> None:
        print(Colors.success(message))

    def warning(self, message: str) -> None:
        print(Colors.warning(message))

    def error(self, message: str) -> None:
        print(Colors.error(message))

    def bold(self, message: str) -> None:
        print(f"{Colors.BOLD}{message}{Colors.RESET}")

    def progress_start(self, total: int, desc: str, unit: str = "img") -> Any:
        return tqdm(total=total, desc=desc, unit=unit)

    def progress_update(self, progress: Any) -> None:
        if progress is not None:
            progress.update(1)

    def progress_finish(self, progress: Any) -> None:
        if progress is not None:
            progress.close()

    def series_header(
        self,
        series_title: str,
        start: int,
        end: int,
        extra_chapters: Optional[List[float]] = None,
        is_ranobelib: bool = False,
        max_chapters: int = 1,
        max_images: int = 5,
    ) -> None:
        self.line()
        self.bold("╔══════════════════════════════════════════╗")
        self.bold("║            Lib Downloader v2.0.0         ║")
        self.bold("╚══════════════════════════════════════════╝")
        self.line()

        self.info(f"Series: {series_title}")
        self.info(f"Запрошенные индексы глав (API index): {start}-{end}")

        if extra_chapters:
            self.info(f"Дополнительные главы: {extra_chapters}")

        if is_ranobelib:
            self.info("Режим: Текстовые главы (RanobeLib)")

        self.info(
            f"Параллельность: {max_chapters} глав, "
            f"{max_images} изображений"
        )
        self.line()

    def chapters_total(self, total: int) -> None:
        self.info(f"Найдено глав для загрузки (после проверки API): {total}")

    def chapter_started(self, number: Any) -> None:
        self.info(f"Загрузка главы {number}...")

    def chapter_finished(self, number: Any) -> None:
        self.success(f"Глава {number} загружена")

    def rate_limited(
        self,
        wait: float,
        kind: str = "json",
        attempt: int = 0,
        retries: int = 0,
    ) -> None:
        template = self._RATE_LIMIT_MESSAGES.get(
            kind, self._RATE_LIMIT_MESSAGES["json"]
        )
        self.warning(
            template.format(wait=wait, attempt=attempt, retries=retries)
        )

    def summary(
        self,
        successful: int,
        total: int,
        failed: int,
        output_dir: Path,
    ) -> None:
        self.line()
        self.bold("═" * 50)
        self.success(f"Завершено: {successful}/{total} глав")

        if failed:
            self.info(f"Ошибок: {failed} глав")

        self.info(f"Директория вывода: {Path(output_dir).absolute()}")
        self.bold("═" * 50)
        self.line()

    def batch_started(self, total: int) -> None:
        self.line(
            f"Найдено {total} тайтлов для обновления. "
            f"Начинаем загрузку по очереди..."
        )

    def batch_task_started(
        self,
        index: int,
        total: int,
        slug: str,
        chapters: Optional[List[float]],
    ) -> None:
        self.line()

        if chapters:
            chapters_str = ', '.join(
                str(int(x)) if float(x).is_integer() else str(x)
                for x in chapters
            )
            self.line(
                f"[Задача {index}/{total}] >>> Начинаем обновление тайтла: "
                f"{slug} (Индексы: {chapters_str})"
            )
        else:
            self.line(
                f"[Задача {index}/{total}] >>> Начинаем загрузку тайтла: "
                f"{slug} (Все доступные главы)"
            )

    def batch_task_finished(self, index: int, total: int, slug: str) -> None:
        self.line(
            f"[Задача {index}/{total}] <<< Завершено обновление тайтла: {slug}"
        )


class NullReporter:
    """Reporter that discards everything (tests, quiet mode)."""

    def line(self, text: str = "") -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def success(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass

    def bold(self, message: str) -> None:
        pass

    def progress_start(self, total: int, desc: str, unit: str = "img") -> Any:
        return None

    def progress_update(self, progress: Any) -> None:
        pass

    def progress_finish(self, progress: Any) -> None:
        pass

    def series_header(
        self,
        series_title: str,
        start: int,
        end: int,
        extra_chapters: Optional[List[float]] = None,
        is_ranobelib: bool = False,
        max_chapters: int = 1,
        max_images: int = 5,
    ) -> None:
        pass

    def chapters_total(self, total: int) -> None:
        pass

    def chapter_started(self, number: Any) -> None:
        pass

    def chapter_finished(self, number: Any) -> None:
        pass

    def rate_limited(
        self,
        wait: float,
        kind: str = "json",
        attempt: int = 0,
        retries: int = 0,
    ) -> None:
        pass

    def summary(
        self,
        successful: int,
        total: int,
        failed: int,
        output_dir: Path,
    ) -> None:
        pass

    def batch_started(self, total: int) -> None:
        pass

    def batch_task_started(
        self,
        index: int,
        total: int,
        slug: str,
        chapters: Optional[List[float]],
    ) -> None:
        pass

    def batch_task_finished(self, index: int, total: int, slug: str) -> None:
        pass


_default_reporter: Reporter = ConsoleReporter()


def get_reporter() -> Reporter:
    return _default_reporter


def set_reporter(reporter: Reporter) -> None:
    global _default_reporter
    _default_reporter = reporter


def create_reporter() -> Reporter:
    """Pick the richest reporter available for the current output."""

    if os.environ.get("LIB_DOWNLOADER_UI", "").strip().lower() == "console":
        return ConsoleReporter()

    if not sys.stdout.isatty():
        return ConsoleReporter()

    try:
        from reporting_rich import RichReporter

        return RichReporter()
    except Exception:
        return ConsoleReporter()
