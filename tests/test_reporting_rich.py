import asyncio
import io
import sys
import types

import pytest

pytest.importorskip("rich")

from rich.console import Console

import main
import reporting
from reporting import ConsoleReporter, NullReporter, get_reporter, set_reporter
from reporting_rich import RichReporter, get_console


def _console(width=120):
    return Console(
        file=io.StringIO(),
        force_terminal=False,
        width=width,
        no_color=True,
    )


def _reporter():
    console = _console()
    return RichReporter(console=console), console


def _output(console):
    return console.file.getvalue()


def test_messages_keep_prefixes_and_text():
    reporter, console = _reporter()

    reporter.line("plain line")
    reporter.info("info text")
    reporter.success("ok text")
    reporter.warning("careful")
    reporter.error("bad")
    reporter.bold("BOLD")

    out = _output(console)
    assert "plain line" in out
    assert "Info: info text" in out
    assert "Success: ok text" in out
    assert "Warning: careful" in out
    assert "Error: bad" in out
    assert "BOLD" in out


def test_series_header_panel():
    reporter, console = _reporter()

    reporter.series_header(
        "Series Title",
        1,
        3,
        extra_chapters=[0.5, 10.1],
        is_ranobelib=True,
        max_chapters=2,
        max_images=4,
    )

    out = _output(console)
    assert "Lib Downloader v2.0.0" in out
    assert "Series: Series Title" in out
    assert "Запрошенные индексы глав (API index): 1-3" in out
    assert "Дополнительные главы: [0.5, 10.1]" in out
    assert "Режим: Текстовые главы (RanobeLib)" in out
    assert "Параллельность: 2 глав, 4 изображений" in out


def test_pages_bar_rendered_below_chapters_bar():
    reporter, console = _reporter()

    reporter.chapters_total(2)
    assert reporter.live_active

    handle = reporter.progress_start(3, "  Downloading Ch1", unit="img")

    assert reporter.live_active
    assert [task.description for task in reporter._progress.tasks] == [
        "Главы",
        "  Downloading Ch1",
    ]

    reporter.progress_update(handle)
    assert reporter._progress.tasks[1].completed == 1


def test_progress_finish_keeps_live_and_bar_at_full():
    reporter, console = _reporter()
    reporter.chapters_total(1)

    handle = reporter.progress_start(2, "  Downloading Ch1")
    assert reporter.live_active

    reporter.progress_update(handle)
    reporter.progress_finish(handle)

    assert reporter.live_active
    assert [task.description for task in reporter._progress.tasks] == [
        "Главы",
        "  Downloading Ch1",
    ]
    assert reporter._progress.tasks[1].completed == 2


def test_progress_finish_keeps_live_while_other_pages_active():
    reporter, console = _reporter()
    reporter.chapters_total(2)

    first = reporter.progress_start(2, "  Downloading Ch1")
    second = reporter.progress_start(2, "  Downloading Ch2")
    reporter.progress_finish(first)

    assert reporter.live_active

    reporter.progress_finish(second)
    assert reporter.live_active


def test_chapter_lifecycle_updates_chapters_bar():
    reporter, console = _reporter()
    reporter.chapters_total(2)

    reporter.chapter_started(1)
    assert reporter.live_active

    reporter.chapter_finished(1)

    assert reporter.live_active
    assert reporter._progress.tasks[0].completed == 1
    assert reporter._progress.tasks[1].description == "Глава 1"


def _run_chapter(reporter, number, pages):
    reporter.chapter_started(number)
    handle = reporter.progress_start(pages, f"  Downloading Ch{number}")
    for _ in range(pages):
        reporter.progress_update(handle)
    reporter.progress_finish(handle)
    reporter.chapter_finished(number)


def test_single_live_for_three_sequential_chapters():
    reporter, console = _reporter()
    reporter.chapters_total(3)
    live = reporter._live
    assert live is not None

    async def scenario():
        for number, pages in ((1, 2), (2, 1), (3, 3)):
            _run_chapter(reporter, number, pages)

    asyncio.run(scenario())

    assert reporter._live is live
    chapter_bars = [
        task for task in reporter._progress.tasks
        if task.description.startswith("Глава ")
    ]
    assert [bar.description for bar in chapter_bars] == [
        "Глава 1",
        "Глава 2",
        "Глава 3",
    ]
    assert all(bar.completed == bar.total for bar in chapter_bars)

    chapters_task = reporter._progress.tasks[0]
    assert chapters_task.description == "Главы"
    assert chapters_task.completed == 3


def test_parallel_chapters_keep_separate_bars():
    reporter, console = _reporter()

    async def scenario():
        reporter.chapters_total(2)
        first_ready = asyncio.Event()
        second_ready = asyncio.Event()

        async def worker(number, pages, ready, wait_for):
            reporter.chapter_started(number)
            handle = reporter.progress_start(pages, f"  Downloading Ch{number}")
            ready.set()
            await wait_for.wait()
            for _ in range(pages):
                reporter.progress_update(handle)
            reporter.progress_finish(handle)
            reporter.chapter_finished(number)

        first = asyncio.create_task(
            worker(1, 2, first_ready, second_ready)
        )
        second = asyncio.create_task(
            worker(2, 3, second_ready, first_ready)
        )

        await first_ready.wait()
        await second_ready.wait()

        chapter_bars = [
            task for task in reporter._progress.tasks
            if task.description.startswith("Глава ")
        ]
        assert [bar.description for bar in chapter_bars] == [
            "Глава 1",
            "Глава 2",
        ]
        assert chapter_bars[0].total == 2
        assert chapter_bars[1].total == 3
        assert reporter.live_active
        assert reporter._progress.tasks[0].description == "Главы"

        await asyncio.gather(first, second)

    asyncio.run(scenario())

    assert reporter.live_active
    assert reporter._progress.tasks[0].completed == 2


def test_height_limit_keeps_last_eight_completed_bars():
    reporter, console = _reporter()

    async def scenario():
        reporter.chapters_total(12)
        for number in range(1, 13):
            _run_chapter(reporter, number, 1)

    asyncio.run(scenario())

    chapter_bars = [
        task.description for task in reporter._progress.tasks
        if task.description.startswith("Глава ")
    ]
    assert chapter_bars == [f"Глава {number}" for number in range(5, 13)]

    out = _output(console)
    for number in range(1, 5):
        assert f"Глава {number} загружена" in out
    assert out.count("загружена") == 4

    assert reporter._progress.tasks[0].completed == 12


def _run_download(reporter, chapters):
    async def scenario():
        reporter.chapters_total(len(chapters))
        for number, pages in chapters:
            _run_chapter(reporter, number, pages)

    asyncio.run(scenario())


def test_state_is_reset_between_downloads(tmp_path):
    reporter, console = _reporter()

    _run_download(reporter, [(1, 2), (2, 3)])
    reporter.summary(2, 2, 0, tmp_path)

    async def second_download():
        reporter.chapters_total(2)

        chapters_task = reporter._progress.tasks[0]
        assert chapters_task.description == "Главы"
        assert chapters_task.total == 2
        assert chapters_task.completed == 0

        reporter.chapter_started(1)
        handle = reporter.progress_start(5, "  Downloading Ch1")
        bar = reporter._progress.tasks[handle]
        assert bar.description == "Глава 1"
        assert bar.total == 5
        assert bar.completed == 0

        reporter.progress_update(handle)
        reporter.progress_update(handle)
        assert bar.completed == 2

        reporter.progress_finish(handle)
        reporter.chapter_finished(1)

        reporter.chapter_started(2)
        second_handle = reporter.progress_start(1, "  Downloading Ch2")
        reporter.progress_update(second_handle)
        reporter.progress_finish(second_handle)
        reporter.chapter_finished(2)

    asyncio.run(second_download())

    chapter_bars = [
        task for task in reporter._progress.tasks
        if task.description.startswith("Глава ")
    ]
    assert [bar.description for bar in chapter_bars] == ["Глава 1", "Глава 2"]
    assert [(bar.completed, bar.total) for bar in chapter_bars] == [(5, 5), (1, 1)]
    assert reporter._progress.tasks[0].completed == 2


def test_error_keeps_and_marks_chapter_bar():
    reporter, console = _reporter()

    async def scenario():
        reporter.chapters_total(2)
        reporter.chapter_started(3)
        reporter.progress_start(2, "  Downloading Ch3")
        reporter.error("Глава 3: boom")

    asyncio.run(scenario())

    out = _output(console)
    assert "Error: Глава 3: boom" in out

    chapter_bars = [
        task for task in reporter._progress.tasks
        if str(task.description).startswith("Глава 3")
    ]
    assert len(chapter_bars) == 1
    assert "ошибка" in chapter_bars[0].description


def test_rate_limited_shows_wait_status():
    reporter, console = _reporter()

    reporter.rate_limited(1.2, kind="image", attempt=2, retries=5)

    out = _output(console)
    assert "Ожидание 429, повтор через 1.2 с" in out


def test_summary_prints_table_and_stops_live(tmp_path):
    reporter, console = _reporter()
    reporter.chapter_started(1)
    assert reporter.live_active

    reporter.summary(2, 3, 1, tmp_path)

    out = _output(console)
    assert not reporter.live_active
    assert "Завершено" in out
    assert "2/3 глав" in out
    assert "Ошибок" in out
    assert "Директория вывода" in out
    assert str(tmp_path) in out


def test_summary_without_failures_omits_error_row(tmp_path):
    reporter, console = _reporter()

    reporter.summary(3, 3, 0, tmp_path)

    assert "Ошибок" not in _output(console)


def test_batch_events_show_task_progress():
    reporter, console = _reporter()

    reporter.batch_started(2)
    reporter.batch_task_started(1, 2, "first", [1.0, 2.5])
    reporter.batch_task_finished(1, 2, "first")
    reporter.batch_task_started(2, 2, "second", [])

    out = _output(console)
    assert "Найдено 2 тайтлов для обновления" in out
    assert "Задача 1 из 2" in out
    assert "(Индексы: 1, 2.5)" in out
    assert "завершена: first" in out
    assert "Задача 2 из 2" in out
    assert "(Все доступные главы)" in out


def test_close_stops_live_and_restores_cursor():
    reporter, console = _reporter()
    cursor_calls = []
    console.show_cursor = lambda visible=True: cursor_calls.append(visible)

    reporter.chapters_total(1)
    reporter.chapter_started(1)
    assert reporter.live_active

    reporter.close()
    assert not reporter.live_active
    assert cursor_calls[-1] is True

    reporter.close()
    assert not reporter.live_active


def test_single_console_per_application():
    assert get_console() is get_console()
    assert RichReporter().console is get_console()


def _fake_stdout(isatty):
    return types.SimpleNamespace(
        stdout=types.SimpleNamespace(isatty=lambda: isatty)
    )


def test_create_reporter_falls_back_when_not_tty(monkeypatch):
    monkeypatch.setattr(reporting, "sys", _fake_stdout(False))
    monkeypatch.delenv("LIB_DOWNLOADER_UI", raising=False)

    assert isinstance(reporting.create_reporter(), ConsoleReporter)


def test_create_reporter_uses_rich_on_tty(monkeypatch):
    monkeypatch.setattr(reporting, "sys", _fake_stdout(True))
    monkeypatch.delenv("LIB_DOWNLOADER_UI", raising=False)

    reporter = reporting.create_reporter()

    assert isinstance(reporter, RichReporter)
    assert not isinstance(reporter, ConsoleReporter)


@pytest.mark.parametrize("value", ["console", "CONSOLE", " console "])
def test_create_reporter_env_forces_console(monkeypatch, value):
    monkeypatch.setattr(reporting, "sys", _fake_stdout(True))
    monkeypatch.setenv("LIB_DOWNLOADER_UI", value)

    assert isinstance(reporting.create_reporter(), ConsoleReporter)


def test_create_reporter_falls_back_without_rich(monkeypatch):
    monkeypatch.setattr(reporting, "sys", _fake_stdout(True))
    monkeypatch.delenv("LIB_DOWNLOADER_UI", raising=False)
    monkeypatch.setitem(sys.modules, "reporting_rich", None)

    assert isinstance(reporting.create_reporter(), ConsoleReporter)


def test_read_input_stops_live_before_prompt(monkeypatch):
    calls = []

    class _CloseReporter(NullReporter):
        def close(self):
            calls.append(True)

    original = get_reporter()
    set_reporter(_CloseReporter())
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    try:
        assert main._read_input("prompt") == ""
    finally:
        set_reporter(original)

    assert calls == [True]


def test_main_installs_created_reporter(monkeypatch):
    async def _empty_loop():
        return None

    created = NullReporter()
    original = get_reporter()
    monkeypatch.setattr(main, "create_reporter", lambda: created)
    monkeypatch.setattr(main, "configure_utf8_console", lambda: None)
    monkeypatch.setattr(main, "print_launcher_header", lambda: None)
    monkeypatch.setattr(main, "clear_console", lambda: None)
    monkeypatch.setattr(main, "is_server_running", lambda: True)
    monkeypatch.setattr(main, "main_loop", _empty_loop)
    monkeypatch.setattr(main, "stop_background_server", lambda: None)

    try:
        asyncio.run(main.main())
        assert get_reporter() is created
    finally:
        set_reporter(original)
