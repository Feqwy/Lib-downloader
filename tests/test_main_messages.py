import asyncio
from pathlib import Path

import pytest

import main
from config import Config
from reporting import get_reporter


class _StubDownloader:
    calls = []
    reporters = []
    configs = []

    def __init__(self, cfg, reporter=None):
        self.cfg = cfg
        _StubDownloader.calls.append(cfg.manga_slug)
        _StubDownloader.reporters.append(reporter)
        _StubDownloader.configs.append(cfg)

    async def download_chapters(self):
        return []


@pytest.fixture(autouse=True)
def _reset_stub():
    _StubDownloader.calls = []
    _StubDownloader.reporters = []
    _StubDownloader.configs = []
    yield
    _StubDownloader.calls = []
    _StubDownloader.reporters = []
    _StubDownloader.configs = []


def test_update_from_csv_announces_tasks(monkeypatch, capsys):
    tasks = [
        {"slug": "first", "chapters": [1.0, 2.5]},
        {"slug": "second", "chapters": []},
    ]
    monkeypatch.setattr(main, "read_csv_tasks", lambda path: tasks)
    monkeypatch.setattr(
        main, "prompt_batch_config", lambda: Config(manga_slug="base", chapter_range=(0, 0))
    )
    monkeypatch.setattr(main, "clear_console", lambda: None)
    monkeypatch.setattr(main, "ChapterDownloader", _StubDownloader)

    asyncio.run(main.update_from_csv(Path("chapter_checker_log.csv")))

    out = capsys.readouterr().out
    assert "Найдено 2 тайтлов для обновления. Начинаем загрузку по очереди..." in out
    assert "[Задача 1/2] >>> Начинаем обновление тайтла: first (Индексы: 1, 2.5)" in out
    assert "[Задача 2/2] >>> Начинаем загрузку тайтла: second (Все доступные главы)" in out
    assert "[Задача 1/2] <<< Завершено обновление тайтла: first" in out
    assert "[Задача 2/2] <<< Завершено обновление тайтла: second" in out
    assert _StubDownloader.calls == ["first", "second"]


def test_update_from_csv_without_tasks(monkeypatch, capsys):
    monkeypatch.setattr(main, "read_csv_tasks", lambda path: [])

    asyncio.run(main.update_from_csv(Path("empty.csv")))

    assert "Не найдено тайтлов для обновления в CSV. Выход." in capsys.readouterr().out


def test_update_from_csv_keeps_site_type(monkeypatch, capsys):
    monkeypatch.setattr(
        main, "read_csv_tasks", lambda path: [{"slug": "s", "chapters": [1.0]}]
    )
    monkeypatch.setattr(
        main,
        "prompt_batch_config",
        lambda: Config(
            manga_slug="base", chapter_range=(0, 0), site_type="ranobelib"
        ),
    )
    monkeypatch.setattr(main, "clear_console", lambda: None)
    monkeypatch.setattr(main, "ChapterDownloader", _StubDownloader)

    asyncio.run(main.update_from_csv(Path("chapter_checker_log.csv")))

    assert _StubDownloader.configs[0].site_type == "ranobelib"


def test_update_from_csv_keeps_text_output(monkeypatch, capsys):
    monkeypatch.setattr(
        main, "read_csv_tasks", lambda path: [{"slug": "s", "chapters": [1.0]}]
    )
    monkeypatch.setattr(
        main,
        "prompt_batch_config",
        lambda: Config(
            manga_slug="base", chapter_range=(0, 0), text_output="txt"
        ),
    )
    monkeypatch.setattr(main, "clear_console", lambda: None)
    monkeypatch.setattr(main, "ChapterDownloader", _StubDownloader)

    asyncio.run(main.update_from_csv(Path("chapter_checker_log.csv")))

    assert _StubDownloader.configs[0].text_output == "txt"


def test_update_from_csv_passes_reporter_to_downloader(monkeypatch, capsys):
    monkeypatch.setattr(
        main, "read_csv_tasks", lambda path: [{"slug": "s", "chapters": [1.0]}]
    )
    monkeypatch.setattr(
        main, "prompt_batch_config", lambda: Config(manga_slug="base", chapter_range=(0, 0))
    )
    monkeypatch.setattr(main, "clear_console", lambda: None)
    monkeypatch.setattr(main, "ChapterDownloader", _StubDownloader)

    asyncio.run(main.update_from_csv(Path("chapter_checker_log.csv")))

    assert _StubDownloader.reporters == [get_reporter()]


def test_main_loop_passes_reporter_to_downloader(monkeypatch, capsys):
    answers = iter(["1", "5"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(main, "print_main_menu", lambda: None)
    monkeypatch.setattr(main, "clear_console", lambda: None)
    monkeypatch.setattr(
        main,
        "prompt_user_config",
        lambda: Config(manga_slug="slug", chapter_range=(1, 1)),
    )
    monkeypatch.setattr(main, "ChapterDownloader", _StubDownloader)

    asyncio.run(main.main_loop())

    assert _StubDownloader.calls == ["slug"]
    assert _StubDownloader.reporters == [get_reporter()]


def test_main_loop_stop_server_prints_blank_line(monkeypatch, capsys):
    answers = iter(["4", "", "5"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(main, "print_main_menu", lambda: None)
    monkeypatch.setattr(main, "clear_console", lambda: None)
    monkeypatch.setattr(main, "stop_background_server", lambda: None)

    asyncio.run(main.main_loop())

    assert capsys.readouterr().out.startswith("\n")


def test_update_from_csv_reports_base_config_error(monkeypatch, capsys):
    monkeypatch.setattr(
        main, "read_csv_tasks", lambda path: [{"slug": "s", "chapters": [1.0]}]
    )

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "prompt_batch_config", _boom)
    monkeypatch.setattr(main, "clear_console", lambda: None)

    asyncio.run(main.update_from_csv(Path("chapter_checker_log.csv")))

    out = capsys.readouterr().out
    assert "Ошибка при получении базовой конфигурации: boom. Невозможно продолжить." in out


class _FakeProcess:
    pid = 4321

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def test_start_server_as_process_reports_pid(monkeypatch, tmp_path, capsys):
    (tmp_path / "server.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(main.subprocess, "Popen", lambda *a, **k: _FakeProcess())
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(main, "is_server_running", lambda: True)

    process = main._start_server_as_process(tmp_path)

    assert isinstance(process, _FakeProcess)
    assert "Server started successfully (PID: 4321)" in capsys.readouterr().out


def test_start_server_as_process_warns_when_not_running(monkeypatch, tmp_path, capsys):
    (tmp_path / "server.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(main.subprocess, "Popen", lambda *a, **k: _FakeProcess())
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(main, "is_server_running", lambda: False)

    assert main._start_server_as_process(tmp_path) is None
    assert "Warning: Server may have failed to start" in capsys.readouterr().out


def test_start_server_as_process_missing_script(monkeypatch, tmp_path, capsys):
    assert main._start_server_as_process(tmp_path) is None
    assert "Warning: server.py not found at" in capsys.readouterr().out


def test_start_server_as_process_reports_launch_error(monkeypatch, tmp_path, capsys):
    (tmp_path / "server.py").write_text("", encoding="utf-8")

    def _fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(main.subprocess, "Popen", _fail)

    assert main._start_server_as_process(tmp_path) is None
    assert "Error starting server: boom" in capsys.readouterr().out


class _FakeEvent:
    def __init__(self, ready):
        self.ready = ready

    def clear(self):
        pass

    def set(self):
        pass

    def wait(self, timeout=None):
        return self.ready


class _FakeThread:
    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        pass


def test_start_server_in_thread_success(monkeypatch, capsys):
    monkeypatch.setattr(main, "threading", _ThreadModule())
    monkeypatch.setattr(main, "_server_started", _FakeEvent(True))

    assert main._start_server_in_thread() is None
    assert "Server started successfully in background thread" in capsys.readouterr().out


def test_start_server_in_thread_timeout(monkeypatch, capsys):
    monkeypatch.setattr(main, "threading", _ThreadModule())
    monkeypatch.setattr(main, "_server_started", _FakeEvent(False))

    assert main._start_server_in_thread() is None
    assert "Warning: Server thread failed to start within timeout" in capsys.readouterr().out


def test_start_server_in_thread_reports_error(monkeypatch, capsys):
    monkeypatch.setattr(main, "threading", _ThreadModule(raise_on_start=True))

    assert main._start_server_in_thread() is None
    assert "Error starting server thread: boom" in capsys.readouterr().out


class _ThreadModule:
    def __init__(self, raise_on_start=False):
        self.raise_on_start = raise_on_start

    def Thread(self, *args, **kwargs):
        thread = _FakeThread(*args, **kwargs)
        if self.raise_on_start:
            def _start():
                raise RuntimeError("boom")
            thread.start = _start
        return thread


def test_stop_background_server_reports(monkeypatch, capsys):
    monkeypatch.setattr(main, "_server_process", _FakeProcess())

    main.stop_background_server()

    assert "Background server stopped." in capsys.readouterr().out
    assert main._server_process is None


def test_open_log_viewer_reports(monkeypatch, capsys):
    monkeypatch.setattr(main.subprocess, "Popen", lambda *a, **k: _FakeProcess())

    main.open_log_viewer()

    assert "Log viewer opened in new window." in capsys.readouterr().out


def test_open_log_viewer_reports_error(monkeypatch, capsys):
    def _fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(main.subprocess, "Popen", _fail)

    main.open_log_viewer()

    assert "Error opening log viewer: boom" in capsys.readouterr().out


def test_signal_handler_reports_shutdown(monkeypatch, capsys):
    monkeypatch.setattr(main, "stop_background_server", lambda: None)

    with pytest.raises(SystemExit):
        main.signal_handler(None, None)

    assert "Shutting down..." in capsys.readouterr().out


def test_main_reports_server_already_running(monkeypatch, capsys):
    async def _empty_loop():
        return None

    monkeypatch.setattr(main, "configure_utf8_console", lambda: None)
    monkeypatch.setattr(main, "print_launcher_header", lambda: None)
    monkeypatch.setattr(main, "clear_console", lambda: None)
    monkeypatch.setattr(main, "is_server_running", lambda: True)
    monkeypatch.setattr(main, "main_loop", _empty_loop)
    monkeypatch.setattr(main, "stop_background_server", lambda: None)

    asyncio.run(main.main())

    assert "✓ Сервер уже запущен на порту 8080" in capsys.readouterr().out


def test_main_reports_server_start(monkeypatch, capsys):
    async def _empty_loop():
        return None

    monkeypatch.setattr(main, "configure_utf8_console", lambda: None)
    monkeypatch.setattr(main, "print_launcher_header", lambda: None)
    monkeypatch.setattr(main, "clear_console", lambda: None)
    monkeypatch.setattr(main, "is_server_running", lambda: False)
    monkeypatch.setattr(main, "start_background_server", lambda: None)
    monkeypatch.setattr(main, "main_loop", _empty_loop)
    monkeypatch.setattr(main, "stop_background_server", lambda: None)

    asyncio.run(main.main())

    assert "Запуск фонового сервера..." in capsys.readouterr().out
