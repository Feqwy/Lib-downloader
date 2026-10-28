import asyncio

from colors import Colors
from config import Config
from downloader import ChapterDownloader


def _downloader(tmp_path) -> ChapterDownloader:
    cfg = Config(
        manga_slug="series",
        chapter_range=(1, 1),
        output_dir=tmp_path,
        max_concurrent_images=3,
    )
    return ChapterDownloader(cfg)


def _expected_output() -> str:
    return (
        f"{Colors.error('Не удалось загрузить страницу 2 для главы 5: boom')}\n"
        f"{Colors.error('Глава 5: не удалось загрузить 1/3 изображений.')}\n"
    )


def test_download_images_three_images_with_one_failure(tmp_path, capsys):
    calls = []

    class _API:

        async def download_image(self, url, dest):
            calls.append(url)
            if url == "2.jpg":
                raise RuntimeError("boom")

    result = asyncio.run(
        _downloader(tmp_path)._download_images(
            _API(), ["1.jpg", "2.jpg", "3.jpg"], tmp_path, "5"
        )
    )

    # One coroutine per image, each awaited exactly once. Start/completion
    # order is not part of the contract (tqdm uses as_completed internally).
    assert sorted(calls) == ["1.jpg", "2.jpg", "3.jpg"]
    assert len(calls) == 3
    # The exception is handled per image: it does not escape the task, the
    # aggregate result is False and the failure is reported for image 2.
    assert result is False
    assert capsys.readouterr().out == _expected_output()


def test_download_images_counts_failures_regardless_of_completion_order(tmp_path, capsys):
    delays = {"1.jpg": 0.02, "2.jpg": 0.01, "3.jpg": 0.0}

    class _API:

        async def download_image(self, url, dest):
            await asyncio.sleep(delays[url])
            if url == "2.jpg":
                raise RuntimeError("boom")

    result = asyncio.run(
        _downloader(tmp_path)._download_images(
            _API(), ["1.jpg", "2.jpg", "3.jpg"], tmp_path, "5"
        )
    )

    # Images finish in reverse order, but results stay tied to their task:
    # exactly one failure is counted and the summary is unchanged.
    assert result is False
    assert capsys.readouterr().out == _expected_output()


def test_download_images_all_success(tmp_path, capsys):
    calls = []

    class _API:

        async def download_image(self, url, dest):
            calls.append(url)

    result = asyncio.run(
        _downloader(tmp_path)._download_images(
            _API(), ["1.jpg", "2.jpg", "3.jpg"], tmp_path, "5"
        )
    )

    assert result is True
    assert sorted(calls) == ["1.jpg", "2.jpg", "3.jpg"]
    assert len(calls) == 3
    assert capsys.readouterr().out == ""
