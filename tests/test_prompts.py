import pytest

import main
from pathlib import Path


def _feed_input(monkeypatch, answers):
    iterator = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(iterator))


def _record_prompts(monkeypatch, answers):
    prompts = []
    iterator = iter(answers)

    def _input(prompt=""):
        prompts.append(prompt)
        return next(iterator)

    monkeypatch.setattr("builtins.input", _input)
    return prompts


@pytest.mark.parametrize(
    ("choice", "token", "site_type", "label"),
    [
        ("", "", "mangalib", "MangaLib"),
        ("1", "token-1", "mangalib", "MangaLib"),
        ("2", "token-2", "shlib", "SlashLib"),
        ("3", "", "ranobelib", "RanobeLib"),
        ("4", "token-4", "hentailib", "HentaiLib"),
        ("9", "", "mangalib", "MangaLib"),
        ("abc", "", "mangalib", "MangaLib"),
    ],
)
def test_prompt_api_selection(monkeypatch, capsys, choice, token, site_type, label):
    _feed_input(monkeypatch, [choice, token])

    config = main._prompt_api_selection()

    assert config["site_type"] == site_type
    assert config["auth_token"] == (token or None)
    out = capsys.readouterr().out
    assert "Выберите источник API:" in out
    assert f"Выбран API {label}" in out


def test_prompt_api_selection_prints_menu_in_old_order(monkeypatch, capsys):
    _feed_input(monkeypatch, ["1", ""])

    main._prompt_api_selection()

    out = capsys.readouterr().out
    assert "  1. MangaLib (mangalib.me)" in out
    assert "  2. SlashLib (v2.shlib.life)" in out
    assert "  3. RanobeLib (ranobelib.me)" in out
    assert "  4. HentaiLib (hentailib.me)" in out


def test_prompt_api_selection_prints_site_specific_hints(monkeypatch, capsys):
    _feed_input(monkeypatch, ["3", ""])

    main._prompt_api_selection()

    out = capsys.readouterr().out
    assert "Текстовые главы, без изображений" in out
    assert "Для доступа к 18+ контенту требуется Bearer Token" in out


@pytest.mark.parametrize(
    ("url", "site_type", "expected_message", "expected_referer"),
    [
        ("https://v2.shlib.life/manga/1", "shlib", "Обнаружена ссылка на SlashLib", "https://v2.shlib.life/"),
        ("https://hentailib.me/manga/1", "hentailib", "Обнаружена ссылка на HentaiLib", "https://hentailib.me/"),
        ("https://ranobelib.me/manga/1", "ranobelib", "Обнаружена ссылка на RanobeLib", "https://ranobelib.me/"),
        ("https://mangalib.me/manga/1", "mangalib", "Используется API MangaLib", "https://mangalib.me/"),
        # The old CLI had no mangalib.org branch; it fell back to mangalib.me.
        ("https://mangalib.org/manga/1", "mangalib", "Используется API MangaLib", "https://mangalib.me/"),
        ("https://example.com/manga/1", "mangalib", "Используется API MangaLib", "https://mangalib.me/"),
    ],
)
def test_detect_api_config_from_url(
    monkeypatch,
    capsys,
    url,
    site_type,
    expected_message,
    expected_referer,
):
    _feed_input(monkeypatch, [""])

    config = main._detect_api_config_from_url(url)

    assert config["site_type"] == site_type
    assert config["referer"] == expected_referer
    assert config["auth_token"] is None
    assert expected_message in capsys.readouterr().out


def test_detect_api_config_from_url_keeps_token(monkeypatch):
    _feed_input(monkeypatch, ["bearer-token"])

    config = main._detect_api_config_from_url("https://hentailib.me/manga/1")

    assert config["auth_token"] == "bearer-token"
    assert config["site_type"] == "hentailib"


def test_prompt_download_options_defaults(monkeypatch):
    _feed_input(monkeypatch, ["", "", "", "", "", ""])

    options = main._prompt_download_options()

    assert options == {
        "series_title_override": None,
        "max_chapters": 1,
        "max_images": 5,
        "delay": 0.5,
        "output_dir": Path("downloads"),
        "pack_cbz": False,
        "generate_metadata": False,
        "text_output": "both",
    }


def test_prompt_download_options_skips_text_format_for_manga(monkeypatch):
    prompts = _record_prompts(monkeypatch, ["", "", "", "", "", ""])

    options = main._prompt_download_options()

    assert options["text_output"] == "both"
    assert not any("Формат текстовых глав" in prompt for prompt in prompts)


def test_prompt_download_options_asks_text_format_last(monkeypatch):
    prompts = _record_prompts(monkeypatch, ["", "", "", "", "", "", "2"])

    options = main._prompt_download_options(text_site=True)

    assert options["text_output"] == "txt"
    assert "Формат текстовых глав" in prompts[-1]


def test_prompt_download_options_unknown_text_format_falls_back(monkeypatch):
    _feed_input(monkeypatch, ["", "", "", "", "", "", "9"])

    options = main._prompt_download_options(text_site=True)

    assert options["text_output"] == "both"


def test_prompt_download_options_custom_values(monkeypatch):
    _feed_input(monkeypatch, ["3", "4", "0.2", "tmp", "y", "n"])

    options = main._prompt_download_options()

    assert options["max_chapters"] == 3
    assert options["max_images"] == 4
    assert options["delay"] == 0.2
    assert options["output_dir"] == Path("tmp")
    assert options["pack_cbz"] is True
    assert options["generate_metadata"] is False


def test_prompt_download_options_invalid_number_uses_defaults(monkeypatch, capsys):
    # The first invalid int aborts the whole numeric block, so the remaining
    # numeric prompts are not consumed; this matches the old behavior.
    _feed_input(monkeypatch, ["bad", "", "", ""])

    options = main._prompt_download_options()

    assert options["max_chapters"] == 1
    assert options["max_images"] == 5
    assert options["delay"] == 0.5
    assert options["output_dir"] == Path("downloads")
    assert options["pack_cbz"] is False
    assert options["generate_metadata"] is False
    assert "Неверное число" in capsys.readouterr().out


def test_prompt_download_options_includes_title_when_requested(monkeypatch):
    _feed_input(monkeypatch, ["My Title", "2", "3", "0.1", "tmp", "y", "n"])

    options = main._prompt_download_options(include_title=True)

    assert options["series_title_override"] == "My Title"
    assert options["max_chapters"] == 2
    assert options["max_images"] == 3
    assert options["delay"] == 0.1
    assert options["output_dir"] == Path("tmp")
    assert options["pack_cbz"] is True
    assert options["generate_metadata"] is False


def test_prompt_download_options_resets_title_on_invalid_number(monkeypatch):
    # Old behavior: title and numeric values are parsed in one try block, so a
    # bad number resets the title override as well.
    _feed_input(monkeypatch, ["My Title", "bad", "", "", ""])

    options = main._prompt_download_options(include_title=True)

    assert options["series_title_override"] is None
    assert options["max_chapters"] == 1
    assert options["max_images"] == 5
    assert options["delay"] == 0.5


def test_prompt_batch_config_uses_shared_options(monkeypatch):
    _feed_input(monkeypatch, ["1", "", "", "", "", "", "", ""])

    config = main.prompt_batch_config()

    assert config.manga_slug == "dummy-batch-slug"
    assert config.chapter_range == (0, 0)
    assert config.extra_chapters == []
    assert config.site_type == "mangalib"
    assert config.max_concurrent_chapters == 1
    assert config.max_concurrent_images == 5
    assert config.request_delay == 0.5
    assert config.output_dir == Path("downloads")
    assert config.pack_cbz is False
    assert config.generate_metadata is False
    assert config.text_output == "both"


def test_prompt_batch_config_asks_text_format_for_ranobelib(monkeypatch):
    _feed_input(monkeypatch, ["3", "", "", "", "", "", "", "", "3"])

    config = main.prompt_batch_config()

    assert config.site_type == "ranobelib"
    assert config.text_output == "html"


def test_prompt_user_config_uses_shared_options(monkeypatch):
    _feed_input(
        monkeypatch,
        [
            "https://mangalib.me/series",
            "",
            "1",
            "2",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ],
    )

    config = main.prompt_user_config()

    assert config.manga_slug == "series"
    assert config.chapter_range == (1, 2)
    assert config.extra_chapters is None
    assert config.series_title_override is None
    assert config.site_type == "mangalib"
    assert config.max_concurrent_chapters == 1
    assert config.max_concurrent_images == 5
    assert config.request_delay == 0.5
    assert config.output_dir == Path("downloads")
    assert config.pack_cbz is False
    assert config.generate_metadata is False
    assert config.text_output == "both"


def test_prompt_user_config_title_and_extra_chapters(monkeypatch):
    _feed_input(
        monkeypatch,
        [
            "https://ranobelib.me/series",
            "",
            "0",
            "0",
            "0.5, 10.1",
            "My Title",
            "2",
            "3",
            "0.1",
            "tmp",
            "y",
            "n",
            "2",
        ],
    )

    config = main.prompt_user_config()

    assert config.manga_slug == "series"
    assert config.chapter_range == (0, 0)
    assert config.extra_chapters == [0.5, 10.1]
    assert config.series_title_override == "My Title"
    assert config.site_type == "ranobelib"
    assert config.max_concurrent_chapters == 2
    assert config.max_concurrent_images == 3
    assert config.request_delay == 0.1
    assert config.output_dir == Path("tmp")
    assert config.pack_cbz is True
    assert config.generate_metadata is False
    assert config.text_output == "txt"
