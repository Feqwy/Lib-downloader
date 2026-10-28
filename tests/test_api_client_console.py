import asyncio
from types import SimpleNamespace

import aiohttp
import pytest

import api_client
from api_client import MangaAPIClient
from colors import Colors
from config import Config


def _client() -> MangaAPIClient:
    return MangaAPIClient(
        Config(manga_slug="series", chapter_range=(1, 1), request_delay=0)
    )


class _FakeResponse:

    def __init__(self, status, error=None):
        self.status = status
        self.headers = {}
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def raise_for_status(self):
        if self._error is not None:
            raise self._error


class _FakeSession:

    def __init__(self, response):
        self._response = response

    def get(self, *args, **kwargs):
        return self._response


def _response_error(status: int) -> aiohttp.ClientResponseError:
    request_info = SimpleNamespace(real_url="http://example.invalid/test")
    return aiohttp.ClientResponseError(request_info, (), status=status)


def _fast_client(monkeypatch) -> MangaAPIClient:
    client = _client()
    monkeypatch.setattr(client, "_calculate_retry_delay", lambda headers, attempt: 0.0)
    return client


IMAGE_403_FAILURE = (
    "Image download failed after 2 attempts: "
    "403, message='', url='http://example.invalid/test'"
)


def test_fetch_full_chapter_pool_error_message(monkeypatch, capsys):
    client = _client()

    async def _boom(url, retries):
        raise RuntimeError("boom")

    monkeypatch.setattr(client, "_get_json", _boom)

    assert asyncio.run(client.fetch_full_chapter_pool("slug")) == []
    assert capsys.readouterr().out == (
        f"{Colors.error('Не удалось получить список глав: boom')}\n"
    )


def test_get_json_rate_limit_status_message(monkeypatch, capsys):
    client = _fast_client(monkeypatch)
    client._session = _FakeSession(_FakeResponse(429))

    with pytest.raises(RuntimeError, match="Retries exhausted"):
        asyncio.run(client._get_json("http://example.invalid", retries=1))

    assert capsys.readouterr().out == (
        f"{Colors.warning('Rate limit (429). Retry in 0.00s... (Attempt 1/1)')}\n"
    )


def test_get_json_rate_limit_exception_message(monkeypatch, capsys):
    client = _fast_client(monkeypatch)
    client._session = _FakeSession(_FakeResponse(200, _response_error(429)))

    with pytest.raises(RuntimeError, match="Retries exhausted"):
        asyncio.run(client._get_json("http://example.invalid", retries=1))

    assert capsys.readouterr().out == (
        f"{Colors.warning('Rate limit (429) via exception. Retry in 0.00s... (Attempt 1/1)')}\n"
    )


def test_get_json_request_failed_message(monkeypatch, capsys):
    client = _fast_client(monkeypatch)
    client._session = _FakeSession(_FakeResponse(200, ValueError("boom")))

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(client._get_json("http://example.invalid", retries=1))

    assert capsys.readouterr().out == (
        f"{Colors.error('Request failed after 1 attempts: boom')}\n"
    )


def test_download_image_rate_limit_message(monkeypatch, capsys, tmp_path):
    client = _fast_client(monkeypatch)
    client._session = _FakeSession(_FakeResponse(429))

    # Current behavior: download_image returns silently when retries run out.
    assert asyncio.run(
        client.download_image(
            "http://example.invalid/1.jpg", tmp_path / "1.jpg", retries=1
        )
    ) is None

    assert capsys.readouterr().out == (
        f"{Colors.warning('Rate limit (429) for image. Retry in 0.00s... (Attempt 1/1)')}\n"
    )


def test_download_image_403_message(monkeypatch, capsys, tmp_path):
    client = _fast_client(monkeypatch)
    client._session = _FakeSession(_FakeResponse(403, _response_error(403)))

    with pytest.raises(aiohttp.ClientResponseError):
        asyncio.run(
            client.download_image(
                "http://example.invalid/1.jpg", tmp_path / "1.jpg", retries=2
            )
        )

    assert capsys.readouterr().out == (
        f"{Colors.warning('403 Forbidden. Warming up and retrying... (Attempt 1/2)')}\n"
        f"{Colors.error(IMAGE_403_FAILURE)}\n"
    )


def test_download_image_failed_message(monkeypatch, capsys, tmp_path):
    client = _fast_client(monkeypatch)
    client._session = _FakeSession(_FakeResponse(200, ValueError("boom")))

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(
            client.download_image(
                "http://example.invalid/1.jpg", tmp_path / "1.jpg", retries=1
            )
        )

    assert capsys.readouterr().out == (
        f"{Colors.error('Image download failed after 1 attempts: boom')}\n"
    )
