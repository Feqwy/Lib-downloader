import asyncio

import pytest

import downloader
from colors import Colors
from config import Config
from downloader import ChapterDownloader
from models import ChapterInfo


def _downloader(tmp_path, **config_overrides) -> ChapterDownloader:
    cfg = Config(
        manga_slug="test-series",
        chapter_range=(1, 1),
        output_dir=tmp_path,
        **config_overrides,
    )
    return ChapterDownloader(cfg)


def _chapter() -> ChapterInfo:
    return ChapterInfo(
        number=5,
        number_str="5",
        index=1,
        volume=1,
        name="",
        pages_count=1,
        series_title=None,
        teams=[],
    )


def test_print_header_default_message(tmp_path, capsys):
    _downloader(tmp_path)._print_header(1, 3)

    assert capsys.readouterr().out == (
        f"\n{Colors.BOLD}╔══════════════════════════════════════════╗{Colors.RESET}\n"
        f"{Colors.BOLD}║            Lib Downloader v2.0.0         ║{Colors.RESET}\n"
        f"{Colors.BOLD}╚══════════════════════════════════════════╝{Colors.RESET}\n"
        f"\n{Colors.info('Series: test-series (from slug)')}\n"
        f"{Colors.info('Запрошенные индексы глав (API index): 1-3')}\n"
        f"{Colors.info('Параллельность: 3 глав, 8 изображений')}\n"
        "\n"
    )


def test_print_header_override_extra_chapters_and_ranobelib(tmp_path, capsys):
    downloader_obj = _downloader(
        tmp_path,
        series_title_override="Override",
        extra_chapters=[0.5, 10.1],
        site_type="ranobelib",
        max_concurrent_chapters=1,
        max_concurrent_images=2,
    )

    downloader_obj._print_header(1, 1)

    assert capsys.readouterr().out == (
        f"\n{Colors.BOLD}╔══════════════════════════════════════════╗{Colors.RESET}\n"
        f"{Colors.BOLD}║            Lib Downloader v2.0.0         ║{Colors.RESET}\n"
        f"{Colors.BOLD}╚══════════════════════════════════════════╝{Colors.RESET}\n"
        f"\n{Colors.info('Series: Override')}\n"
        f"{Colors.info('Запрошенные индексы глав (API index): 1-1')}\n"
        f"{Colors.info('Дополнительные главы: [0.5, 10.1]')}\n"
        f"{Colors.info('Режим: Текстовые главы (RanobeLib)')}\n"
        f"{Colors.info('Параллельность: 1 глав, 2 изображений')}\n"
        "\n"
    )


def test_print_summary_with_errors(tmp_path, capsys):
    _downloader(tmp_path)._print_summary(2, 3, 1)

    assert capsys.readouterr().out == (
        f"\n{Colors.BOLD}{'═' * 50}{Colors.RESET}\n"
        f"{Colors.success('Завершено: 2/3 глав')}\n"
        f"{Colors.info('Ошибок: 1 глав')}\n"
        f"{Colors.info(f'Директория вывода: {tmp_path}')}\n"
        f"{Colors.BOLD}{'═' * 50}{Colors.RESET}\n"
        "\n"
    )


def test_print_summary_without_errors(tmp_path, capsys):
    _downloader(tmp_path)._print_summary(3, 3, 0)

    assert capsys.readouterr().out == (
        f"\n{Colors.BOLD}{'═' * 50}{Colors.RESET}\n"
        f"{Colors.success('Завершено: 3/3 глав')}\n"
        f"{Colors.info(f'Директория вывода: {tmp_path}')}\n"
        f"{Colors.BOLD}{'═' * 50}{Colors.RESET}\n"
        "\n"
    )


def test_download_chapter_error_message(tmp_path, capsys):
    class _BoomAPI:

        async def resolve_volume(self, slug, chapter_num):
            raise RuntimeError("boom")

    assert asyncio.run(_downloader(tmp_path).download_chapter(_BoomAPI(), 5)) is None
    assert capsys.readouterr().out == f"{Colors.error('Глава 5: boom')}\n"


def test_download_images_error_messages(tmp_path, capsys):
    class _ImageAPI:

        async def download_image(self, url, dest):
            if url == "2.jpg":
                raise RuntimeError("boom")

    result = asyncio.run(
        _downloader(tmp_path)._download_images(
            _ImageAPI(), ["1.jpg", "2.jpg", "3.jpg"], tmp_path, "5"
        )
    )

    assert result is False
    assert capsys.readouterr().out == (
        f"{Colors.error('Не удалось загрузить страницу 2 для главы 5: boom')}\n"
        f"{Colors.error('Глава 5: не удалось загрузить 1/3 изображений.')}\n"
    )


def test_download_all_chapters_messages(tmp_path, capsys, monkeypatch):
    downloader_obj = _downloader(tmp_path)

    async def _fake_download_chapter(api, chapter):
        return tmp_path / "chapter", _chapter()

    monkeypatch.setattr(downloader_obj, "download_chapter", _fake_download_chapter)

    asyncio.run(downloader_obj._download_all_chapters(object(), [1]))

    assert capsys.readouterr().out == (
        f"{Colors.info('Загрузка главы 1...')}\n"
        f"{Colors.success('Глава 1 загружена')}\n"
    )


def test_process_results_error_message(tmp_path, capsys):
    successful, failed_count = _downloader(tmp_path)._process_results(
        [1, 2], [RuntimeError("boom"), ("dir", None)]
    )

    assert successful == [("dir", None)]
    assert failed_count == 1
    assert capsys.readouterr().out == f"{Colors.error('Глава 1: boom')}\n"


def test_create_cbz_error_message(tmp_path, capsys, monkeypatch):
    def _boom_zipfile(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(downloader.zipfile, "ZipFile", _boom_zipfile)
    cbz_path = tmp_path / "Volume 01" / "Chapter 5.cbz"

    with pytest.raises(RuntimeError, match="boom"):
        _downloader(tmp_path).create_cbz(tmp_path, _chapter(), cbz_path)

    assert capsys.readouterr().out == (
        f"{Colors.error(f'Не удалось создать CBZ {cbz_path}: boom')}\n"
    )
