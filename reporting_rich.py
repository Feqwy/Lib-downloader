import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table


MAX_FINISHED_BARS = 8

_CHAPTER_ERROR_RE = re.compile(r"(?:Глава|для главы)\s+([^\s:]+)\s*:")

_console: Optional[Console] = None


def get_console() -> Console:

    global _console
    if _console is None:
        _console = Console(highlight=False, soft_wrap=True)
    return _console


class RichReporter:

    max_finished_bars = MAX_FINISHED_BARS

    def __init__(self, console: Optional[Console] = None):
        self.console = console or get_console()
        self._progress: Optional[Progress] = None
        self._live: Optional[Live] = None
        self._chapters_task: Optional[TaskID] = None
        self._chapters_total = 0
        self._chapter_tasks: Dict[Any, TaskID] = {}
        self._task_chapters: Dict[Any, Any] = {}
        self._finished: List[Any] = []
        self._counted: Set[Any] = set()
        self._download_started = False

    @property
    def live_active(self) -> bool:
        return self._live is not None

    def line(self, text: str = "") -> None:
        self.console.print(text)

    def info(self, message: str) -> None:
        self.console.print(f"Info: {message}", style="cyan")

    def success(self, message: str) -> None:
        self.console.print(f"Success: {message}", style="green")

    def warning(self, message: str) -> None:
        self.console.print(f"Warning: {message}", style="yellow")

    def error(self, message: str) -> None:
        self.console.print(f"Error: {message}", style="red")
        self._mark_failed_from_message(message)

    def bold(self, message: str) -> None:
        self.console.print(message, style="bold")

    def _ensure_progress(self) -> Progress:
        if self._progress is None:
            self._progress = Progress(
                TextColumn("{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=self.console,
            )
        return self._progress

    def _ensure_chapters_task(self) -> TaskID:
        progress = self._ensure_progress()
        if self._chapters_task is None:
            total = self._chapters_total or None
            self._chapters_task = progress.add_task("Главы", total=total)
        return self._chapters_task

    def _ensure_live(self) -> None:
        if self._live is None:
            self._live = Live(
                self._ensure_progress(),
                console=self.console,
                refresh_per_second=10,
            )
            self._live.start()

    def close(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
        self.console.show_cursor(True)
        self._reset_state()

    def _reset_state(self) -> None:
        self._progress = None
        self._chapters_task = None
        self._chapters_total = 0
        self._chapter_tasks.clear()
        self._task_chapters.clear()
        self._finished.clear()
        self._counted.clear()
        self._download_started = False

    def _begin_download(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._reset_state()
        self._download_started = True

    def _ensure_download(self) -> None:
        if not self._download_started:
            self._begin_download()

    @staticmethod
    def _current_task() -> Any:
        try:
            return asyncio.current_task()
        except RuntimeError:
            return None

    def _create_chapter_task(
        self,
        key: Any,
        description: str,
        total: Optional[float],
    ) -> TaskID:
        progress = self._ensure_progress()
        self._ensure_chapters_task()
        task = progress.add_task(description, total=total)
        self._chapter_tasks[key] = task
        return task

    def _find_chapter_key(self, token: str) -> Any:
        for key in self._chapter_tasks:
            if str(key) == token:
                return key
        return None

    def _mark_failed_from_message(self, message: str) -> None:
        match = _CHAPTER_ERROR_RE.search(message)
        if match is None or self._progress is None:
            return

        key = self._find_chapter_key(match.group(1))
        if key is None:
            return

        task = self._chapter_tasks[key]
        try:
            self._progress.update(
                task,
                description=f"Глава {key} [red]ошибка[/red]",
            )
        except KeyError:
            pass

    def progress_start(self, total: int, desc: str, unit: str = "img") -> Any:
        self._ensure_download()
        current = self._current_task()
        key = self._task_chapters.get(current) if current is not None else None

        if key is None:
            key = desc

        task = self._chapter_tasks.get(key)

        if task is None:
            description = desc if isinstance(key, str) else f"Глава {key}"
            task = self._create_chapter_task(key, description, total)
        else:
            try:
                self._progress.update(task, total=total)
            except KeyError:
                pass

        self._ensure_live()
        return task

    def progress_update(self, progress: Any) -> None:
        if progress is None or self._progress is None:
            return

        try:
            self._progress.advance(progress, 1)
        except KeyError:
            pass

    def progress_finish(self, progress: Any) -> None:
        if progress is None or self._progress is None:
            return

        try:
            total = self._progress.tasks[progress].total
        except IndexError:
            return

        if total is not None:
            try:
                self._progress.update(progress, completed=total)
            except KeyError:
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
        self._begin_download()

        lines = [
            f"Series: {series_title}",
            f"Запрошенные индексы глав (API index): {start}-{end}",
        ]

        if extra_chapters:
            lines.append(f"Дополнительные главы: {extra_chapters}")

        if is_ranobelib:
            lines.append("Режим: Текстовые главы (RanobeLib)")

        lines.append(
            f"Параллельность: {max_chapters} глав, {max_images} изображений"
        )

        self.console.print(
            Panel(
                "\n".join(lines),
                title="Lib Downloader v2.0.0",
                border_style="blue",
            )
        )

    def chapters_total(self, total: int) -> None:
        self._ensure_download()
        self._chapters_total = total
        progress = self._ensure_progress()

        if self._chapters_task is None:
            self._chapters_task = progress.add_task("Главы", total=total)
        else:
            progress.update(self._chapters_task, total=total)

        self._ensure_live()

    def chapter_started(self, number: Any) -> None:
        self._ensure_download()
        task = self._chapter_tasks.get(number)

        if task is None:
            self._create_chapter_task(
                number,
                f"Глава {number}",
                total=None,
            )

        current = self._current_task()
        if current is not None:
            self._task_chapters[current] = number

        self._ensure_live()

    def chapter_finished(self, number: Any) -> None:
        progress = self._ensure_progress()
        task = self._chapter_tasks.get(number)

        if task is not None:
            try:
                total = progress.tasks[task].total
                if total is None:
                    progress.update(task, total=1, completed=1)
                else:
                    progress.update(task, completed=total)
            except (IndexError, KeyError):
                pass

        if number not in self._counted:
            self._counted.add(number)
            progress.advance(self._ensure_chapters_task(), 1)
            self._finished.append(number)
            self._enforce_height_limit()

        current = self._current_task()
        if current is not None:
            self._task_chapters.pop(current, None)

    def _enforce_height_limit(self) -> None:
        while len(self._finished) > self.max_finished_bars:
            oldest = self._finished.pop(0)
            task = self._chapter_tasks.pop(oldest, None)

            if task is not None and self._progress is not None:
                try:
                    self._progress.remove_task(task)
                except KeyError:
                    pass

            self.console.print(f"Глава {oldest} загружена", style="green")

    def rate_limited(
        self,
        wait: float,
        kind: str = "json",
        attempt: int = 0,
        retries: int = 0,
    ) -> None:
        self.console.print(
            f"Ожидание 429, повтор через {wait:.1f} с",
            style="yellow",
        )

    def summary(
        self,
        successful: int,
        total: int,
        failed: int,
        output_dir: Path,
    ) -> None:
        self.close()

        table = Table(title="Итог")
        table.add_column("Показатель")
        table.add_column("Значение", justify="right")
        table.add_row("Завершено", f"{successful}/{total} глав")

        if failed:
            table.add_row("Ошибок", f"{failed} глав")

        table.add_row("Директория вывода", str(Path(output_dir).absolute()))

        self.console.print(table)

    def batch_started(self, total: int) -> None:
        self.console.print(
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
        self.console.print()

        if chapters:
            chapters_str = ', '.join(
                str(int(x)) if float(x).is_integer() else str(x)
                for x in chapters
            )
            self.console.print(
                f"[bold]Задача {index} из {total}[/bold] — {slug} "
                f"(Индексы: {chapters_str})"
            )
        else:
            self.console.print(
                f"[bold]Задача {index} из {total}[/bold] — {slug} "
                f"(Все доступные главы)"
            )

    def batch_task_finished(self, index: int, total: int, slug: str) -> None:
        self.console.print(
            f"Задача {index} из {total} завершена: {slug}"
        )
