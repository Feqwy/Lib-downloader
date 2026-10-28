import re
from pathlib import Path

import pytest

from reporting import ConsoleReporter, NullReporter, get_reporter, set_reporter


ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _strip(text):
    return ANSI_RE.sub("", text)


def _lines(capsys):
    return [_strip(line) for line in capsys.readouterr().out.splitlines()]


def test_series_header_full(capsys):
    reporter = ConsoleReporter()

    reporter.series_header(
        "Solo Leveling",
        1,
        2,
        extra_chapters=[0.5, 10.1],
        is_ranobelib=True,
        max_chapters=3,
        max_images=8,
    )

    lines = _lines(capsys)
    assert lines[0] == ""
    assert lines[1] == "╔══════════════════════════════════════════╗"
    assert lines[2] == "║            Lib Downloader v2.0.0         ║"
    assert lines[3] == "╚══════════════════════════════════════════╝"
    assert lines[4] == ""
    assert lines[5] == "Info: Series: Solo Leveling"
    assert lines[6] == "Info: Запрошенные индексы глав (API index): 1-2"
    assert lines[7] == "Info: Дополнительные главы: [0.5, 10.1]"
    assert lines[8] == "Info: Режим: Текстовые главы (RanobeLib)"
    assert lines[9] == "Info: Параллельность: 3 глав, 8 изображений"
    assert lines[10] == ""


def test_series_header_minimal(capsys):
    reporter = ConsoleReporter()

    reporter.series_header("slug (from slug)", 10, 20)

    lines = _lines(capsys)
    assert "Info: Series: slug (from slug)" in lines
    assert "Info: Запрошенные индексы глав (API index): 10-20" in lines
    assert not any("Дополнительные главы" in line for line in lines)
    assert not any("Текстовые главы" in line for line in lines)
    assert "Info: Параллельность: 1 глав, 5 изображений" in lines


def test_chapters_total(capsys):
    ConsoleReporter().chapters_total(7)

    assert _lines(capsys) == [
        "Info: Найдено глав для загрузки (после проверки API): 7"
    ]


def test_chapter_started_and_finished(capsys):
    reporter = ConsoleReporter()

    reporter.chapter_started(12.5)
    reporter.chapter_finished(12.5)

    assert _lines(capsys) == [
        "Info: Загрузка главы 12.5...",
        "Success: Глава 12.5 загружена",
    ]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("json", "Rate limit (429). Retry in 1.20s... (Attempt 1/5)"),
        (
            "json_exception",
            "Rate limit (429) via exception. Retry in 1.20s... (Attempt 1/5)",
        ),
        ("image", "Rate limit (429) for image. Retry in 1.20s... (Attempt 1/5)"),
    ],
)
def test_rate_limited_texts(capsys, kind, expected):
    ConsoleReporter().rate_limited(1.2, kind=kind, attempt=1, retries=5)

    assert _lines(capsys) == [f"Warning: {expected}"]


def test_summary_with_failures(capsys, tmp_path):
    reporter = ConsoleReporter()

    reporter.summary(3, 5, 2, tmp_path)

    lines = _lines(capsys)
    assert lines[0] == ""
    assert lines[1] == "═" * 50
    assert lines[2] == "Success: Завершено: 3/5 глав"
    assert lines[3] == "Info: Ошибок: 2 глав"
    assert lines[4] == f"Info: Директория вывода: {tmp_path.absolute()}"
    assert lines[5] == "═" * 50
    assert lines[6] == ""


def test_summary_without_failures(capsys, tmp_path):
    reporter = ConsoleReporter()

    reporter.summary(2, 2, 0, tmp_path)

    lines = _lines(capsys)
    assert not any("Ошибок" in line for line in lines)
    assert "Success: Завершено: 2/2 глав" in lines


def test_batch_started(capsys):
    ConsoleReporter().batch_started(3)

    assert _lines(capsys) == [
        "Найдено 3 тайтлов для обновления. Начинаем загрузку по очереди..."
    ]


def test_batch_task_started_with_indices(capsys):
    ConsoleReporter().batch_task_started(1, 2, "first", [1.0, 2.5])

    assert _lines(capsys) == [
        "",
        "[Задача 1/2] >>> Начинаем обновление тайтла: first (Индексы: 1, 2.5)",
    ]


def test_batch_task_started_without_indices(capsys):
    ConsoleReporter().batch_task_started(2, 2, "second", [])

    assert _lines(capsys) == [
        "",
        "[Задача 2/2] >>> Начинаем загрузку тайтла: second "
        "(Все доступные главы)",
    ]


def test_batch_task_finished(capsys):
    ConsoleReporter().batch_task_finished(1, 2, "first")

    assert _lines(capsys) == [
        "[Задача 1/2] <<< Завершено обновление тайтла: first"
    ]


def test_null_reporter_discards_new_events(capsys):
    reporter = NullReporter()

    reporter.series_header("title", 1, 2, extra_chapters=[0.5])
    reporter.chapters_total(3)
    reporter.chapter_started(1)
    reporter.chapter_finished(1)
    reporter.rate_limited(1.0, kind="image", attempt=1, retries=5)
    reporter.summary(1, 2, 1, Path("downloads"))
    reporter.batch_started(2)
    reporter.batch_task_started(1, 2, "slug", [1.0])
    reporter.batch_task_finished(1, 2, "slug")

    assert capsys.readouterr().out == ""


def test_reporter_protocol_exposes_new_events():
    for name in (
        "series_header",
        "chapters_total",
        "chapter_started",
        "chapter_finished",
        "rate_limited",
        "summary",
        "batch_started",
        "batch_task_started",
        "batch_task_finished",
    ):
        assert hasattr(ConsoleReporter(), name)
        assert hasattr(NullReporter(), name)


def test_get_set_reporter_roundtrip():
    original = get_reporter()
    replacement = NullReporter()

    try:
        set_reporter(replacement)
        assert get_reporter() is replacement
    finally:
        set_reporter(original)

    assert isinstance(get_reporter(), ConsoleReporter)


class _RecordingReporter(NullReporter):
    def __init__(self):
        self.calls = []

    def series_header(self, *args, **kwargs):
        self.calls.append(("series_header", args, kwargs))

    def summary(self, *args, **kwargs):
        self.calls.append(("summary", args, kwargs))

    def chapters_total(self, *args, **kwargs):
        self.calls.append(("chapters_total", args, kwargs))

    def chapter_started(self, *args, **kwargs):
        self.calls.append(("chapter_started", args, kwargs))

    def chapter_finished(self, *args, **kwargs):
        self.calls.append(("chapter_finished", args, kwargs))


def test_downloader_delegates_header_and_summary(tmp_path):
    from config import Config
    from downloader import ChapterDownloader

    cfg = Config(
        manga_slug="slug",
        chapter_range=(1, 3),
        extra_chapters=[0.5],
        series_title_override="Title",
        max_concurrent_chapters=2,
        max_concurrent_images=4,
        output_dir=tmp_path,
    )
    reporter = _RecordingReporter()
    downloader_obj = ChapterDownloader(cfg, reporter)

    downloader_obj._print_header(1, 3)
    downloader_obj._print_summary(2, 3, 1)

    assert reporter.calls == [
        (
            "series_header",
            ("Title", 1, 3),
            {
                "extra_chapters": [0.5],
                "is_ranobelib": False,
                "max_chapters": 2,
                "max_images": 4,
            },
        ),
        ("summary", (2, 3, 1, tmp_path), {}),
    ]


def test_resolve_chapter_list_reports_total(tmp_path):
    import asyncio

    from config import Config
    from downloader import ChapterDownloader

    class _FakeApi:
        async def to_chapter_info_list(self, **kwargs):
            return [1, 2, 3]

    cfg = Config(
        manga_slug="slug",
        chapter_range=(1, 3),
        extra_chapters=None,
        output_dir=tmp_path,
    )
    reporter = _RecordingReporter()
    downloader_obj = ChapterDownloader(cfg, reporter)

    chapters = asyncio.run(downloader_obj._resolve_chapter_list(_FakeApi()))

    assert chapters == [1, 2, 3]
    assert reporter.calls == [("chapters_total", (3,), {})]


def test_download_all_chapters_reports_counters(tmp_path):
    import asyncio

    from config import Config
    from downloader import ChapterDownloader

    cfg = Config(
        manga_slug="slug",
        chapter_range=(1, 2),
        max_concurrent_chapters=1,
        output_dir=tmp_path,
    )
    reporter = _RecordingReporter()
    downloader_obj = ChapterDownloader(cfg, reporter)

    async def _fake_download(api, chapter):
        return (tmp_path, chapter)

    downloader_obj.download_chapter = _fake_download

    results = asyncio.run(downloader_obj._download_all_chapters(None, [1, 2]))

    assert results == [(tmp_path, 1), (tmp_path, 2)]
    assert [call[0] for call in reporter.calls] == [
        "chapter_started",
        "chapter_finished",
        "chapter_started",
        "chapter_finished",
    ]
    assert [call[1] for call in reporter.calls] == [(1,), (1,), (2,), (2,)]


