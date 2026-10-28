import asyncio

import pytest

import downloader
from api_client import MangaAPIClient
from config import Config
from downloader import ChapterDownloader
from reporting import ConsoleReporter, NullReporter


def _client(reporter=None) -> MangaAPIClient:
    cfg = Config(manga_slug="series", chapter_range=(1, 1))
    if reporter is None:
        return MangaAPIClient(cfg)
    return MangaAPIClient(cfg, reporter)


def test_api_client_defaults_to_console_reporter():
    assert isinstance(_client().reporter, ConsoleReporter)


def test_api_client_accepts_injected_reporter():
    reporter = NullReporter()

    assert _client(reporter).reporter is reporter


def test_api_client_routes_messages_to_reporter(capsys):
    client = _client(NullReporter())

    async def _boom(url, retries):
        raise RuntimeError("boom")

    client._get_json = _boom

    assert asyncio.run(client.fetch_full_chapter_pool("slug")) == []
    assert capsys.readouterr().out == ""


def _downloader(tmp_path, reporter=None) -> ChapterDownloader:
    cfg = Config(manga_slug="series", chapter_range=(1, 1), output_dir=tmp_path)
    if reporter is None:
        return ChapterDownloader(cfg)
    return ChapterDownloader(cfg, reporter)


def test_downloader_defaults_to_console_reporter(tmp_path):
    assert isinstance(_downloader(tmp_path).reporter, ConsoleReporter)


def test_downloader_routes_header_and_summary_to_reporter(tmp_path, capsys):
    downloader_obj = _downloader(tmp_path, NullReporter())

    downloader_obj._print_header(1, 1)
    downloader_obj._print_summary(1, 1, 0)

    assert capsys.readouterr().out == ""


def test_downloader_passes_reporter_to_api_client(tmp_path, monkeypatch):
    reporter = NullReporter()
    captured = {}

    class _FakeAPIClient:

        def __init__(self, cfg, rep=None):
            captured["reporter"] = rep

        async def __aenter__(self):
            raise RuntimeError("stop")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(downloader, "MangaAPIClient", _FakeAPIClient)

    with pytest.raises(RuntimeError, match="stop"):
        asyncio.run(_downloader(tmp_path, reporter).download_chapters())

    assert captured["reporter"] is reporter


class _ProgressReporter(NullReporter):

    def __init__(self):
        self.events = []

    def progress_start(self, total, desc, unit="img"):
        self.events.append(("start", total, desc, unit))
        return "bar"

    def progress_update(self, progress):
        self.events.append(("update", progress))

    def progress_finish(self, progress):
        self.events.append(("finish", progress))


def test_download_images_reports_progress(tmp_path):
    reporter = _ProgressReporter()

    class _API:

        async def download_image(self, url, dest):
            return None

    result = asyncio.run(
        _downloader(tmp_path, reporter)._download_images(
            _API(), ["1.jpg", "2.jpg", "3.jpg"], tmp_path, "5"
        )
    )

    assert result is True
    assert reporter.events == [
        ("start", 3, "  Downloading Ch5", "img"),
        ("update", "bar"),
        ("update", "bar"),
        ("update", "bar"),
        ("finish", "bar"),
    ]


def test_download_images_progress_finishes_after_failure(tmp_path):
    reporter = _ProgressReporter()

    class _API:

        async def download_image(self, url, dest):
            if url == "2.jpg":
                raise RuntimeError("boom")

    result = asyncio.run(
        _downloader(tmp_path, reporter)._download_images(
            _API(), ["1.jpg", "2.jpg", "3.jpg"], tmp_path, "5"
        )
    )

    assert result is False
    assert reporter.events == [
        ("start", 3, "  Downloading Ch5", "img"),
        ("update", "bar"),
        ("update", "bar"),
        ("update", "bar"),
        ("finish", "bar"),
    ]


