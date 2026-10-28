import csv

import pytest

import csv_contract
import main
import server


def test_format_missing_tokens_sorts_by_index():
    entries = [
        {"index": 47, "volume": 4, "number_str": "13"},
        {"index": 46, "volume": 4, "number_str": "12"},
    ]

    assert server._format_missing_tokens(entries) == "46:4:12, 47:4:13"


def test_format_missing_tokens_skips_incomplete_entries():
    entries = [
        {"index": None, "volume": 1, "number_str": "1"},
        {"index": 2, "volume": None, "number_str": "2"},
        {"index": 3, "volume": 1, "number_str": None},
        {"index": 4, "volume": 1, "number_str": "4"},
    ]

    assert server._format_missing_tokens(entries) == "4:1:4"


def test_format_missing_tokens_empty():
    assert server._format_missing_tokens([]) == ""


def test_format_missing_tokens_filters_junk_before_sorting():
    entries = [
        "junk",
        {"index": 2, "volume": 1, "number_str": "2"},
        None,
        42,
        {"index": 1, "volume": 1, "number_str": "1"},
        ["not", "a", "dict"],
    ]

    assert csv_contract.format_missing_tokens(entries) == "1:1:1, 2:1:2"
    assert server._format_missing_tokens(entries) == "1:1:1, 2:1:2"
    assert main._parse_missing_indices("1:1:1, 2:1:2") == [1.0, 2.0]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("46:4:12, 47:4:13", [46.0, 47.0]),
        ("", []),
        ("abc, 5:1:1, :2:3", [5.0]),
        ("1.5:1:1", []),
        (" 7 : 2 : 1 ", [7.0]),
        ("5", [5.0]),
        ("5:1:1, 5:1:1", [5.0, 5.0]),
    ],
)
def test_parse_missing_indices(value, expected):
    assert main._parse_missing_indices(value) == expected


def test_missing_tokens_round_trip():
    entries = [
        {"index": 48, "volume": 4, "number_str": "14"},
        {"index": 46, "volume": 4, "number_str": "12"},
    ]

    formatted = server._format_missing_tokens(entries)

    assert formatted == "46:4:12, 48:4:14"
    assert main._parse_missing_indices(formatted) == [46.0, 48.0]


def test_parse_csv_row_modern_missing_column():
    row = {"SLUG": "solo-leveling", "MISSING": "46:4:12, 47:4:13"}

    assert main._parse_csv_row(row) == {
        "slug": "solo-leveling",
        "chapters": [46.0, 47.0],
    }


def test_parse_csv_row_accepts_lowercase_slug():
    row = {"slug": "solo-leveling", "MISSING": "1:1:1"}

    assert main._parse_csv_row(row) == {"slug": "solo-leveling", "chapters": [1.0]}


def test_parse_csv_row_requires_slug():
    assert main._parse_csv_row({"SLUG": "   ", "MISSING": "1:1:1"}) is None
    assert main._parse_csv_row({}) is None


def test_parse_csv_row_legacy_columns():
    row = {
        "SLUG": "legacy",
        "MISSING": "",
        "СТАТУС": "Не хватает 2",
        "ПРОПУЩЕННЫЕ_ГЛАВЫ": "1, 2.5",
    }

    assert main._parse_csv_row(row) == {"slug": "legacy", "chapters": [1.0, 2.5]}


def test_parse_csv_row_ignores_legacy_status_without_missing_chapters():
    row = {"SLUG": "legacy", "MISSING": "", "СТАТУС": "Актуально"}

    assert main._parse_csv_row(row) is None


def test_parse_csv_row_skips_unparseable_missing_value():
    row = {"SLUG": "bad", "MISSING": "not-an-index"}

    assert main._parse_csv_row(row) is None


def test_parse_csv_row_reports_warning_through_callback(capsys):
    row = {
        "SLUG": "bad-legacy",
        "MISSING": "",
        "СТАТУС": "Не хватает 2",
        "ПРОПУЩЕННЫЕ_ГЛАВЫ": "1, not-a-number",
    }
    messages = []

    assert main._parse_csv_row(row, on_warning=messages.append) is None
    assert messages == ["Could not parse chapter numbers for bad-legacy. Skipping."]
    assert capsys.readouterr().out == ""


def test_parse_csv_row_is_silent_without_callback(capsys):
    row = {
        "SLUG": "bad-legacy",
        "MISSING": "",
        "СТАТУС": "Не хватает 2",
        "ПРОПУЩЕННЫЕ_ГЛАВЫ": "1, not-a-number",
    }

    assert main._parse_csv_row(row) is None
    assert capsys.readouterr().out == ""


def test_read_csv_tasks_warns_through_reporter(tmp_path, capsys):
    csv_path = tmp_path / "chapter_checker_log.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["SLUG", "СТАТУС", "ПРОПУЩЕННЫЕ_ГЛАВЫ"])
        writer.writerow(["bad-legacy", "Не хватает 2", "1, not-a-number"])

    assert main.read_csv_tasks(csv_path) == []
    assert (
        "Warning: Could not parse chapter numbers for bad-legacy. Skipping."
        in capsys.readouterr().out
    )


def test_read_csv_tasks(tmp_path, capsys):
    csv_path = tmp_path / "chapter_checker_log.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            [
                "TIME",
                "SLUG",
                "DOMAIN",
                "MODE",
                "STATUS",
                "LOCAL",
                "SERVER",
                "MISSING_COUNT",
                "MISSING",
            ]
        )
        writer.writerow(
            [
                "2025-01-15_14-30-00",
                "solo-leveling",
                "mangalib.me",
                "CHECK_LOCAL",
                "Не хватает 1",
                "45",
                "46",
                "1",
                "46:4:12",
            ]
        )
        writer.writerow(
            [
                "2025-01-15_14-30-00",
                "actual",
                "mangalib.me",
                "CHECK_LOCAL",
                "Актуально",
                "10",
                "10",
                "0",
                "",
            ]
        )

    tasks = main.read_csv_tasks(csv_path)

    assert tasks == [{"slug": "solo-leveling", "chapters": [46.0]}]
    assert "Total tasks extracted from CSV: 1" in capsys.readouterr().out


def test_read_csv_tasks_missing_file(tmp_path, capsys):
    tasks = main.read_csv_tasks(tmp_path / "missing.csv")

    assert tasks == []
    assert "CSV file not found" in capsys.readouterr().out


class _FrozenDateTime(server.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2025, 1, 15, 14, 30, 0)


CSV_GOLDEN_HEADER = (
    "TIME;SLUG;DOMAIN;MODE;STATUS;LOCAL;SERVER;MISSING_COUNT;MISSING"
)


def _golden_results():
    return [
        {
            "slug": "solo-leveling",
            "status": "Не хватает 2",
            "local_count": 45,
            "server_count": 47,
            "missing_entries": [
                {"index": 47, "volume": 4, "number_str": "13"},
                {"index": 46, "volume": 4, "number_str": "12"},
            ],
        },
        {
            "slug": "actual",
            "status": "Актуально",
            "local_count": 10,
            "server_count": 10,
            "missing_entries": [],
        },
    ]


@pytest.mark.parametrize(
    ("mode", "csv_mode"),
    [("check_local", "CHECK_LOCAL"), ("server_only", "ONLY_SERVER")],
)
def test_save_to_csv_golden_bytes(tmp_path, monkeypatch, mode, csv_mode):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server, "datetime", _FrozenDateTime)

    server.save_to_csv(_golden_results(), mode, "mangalib.me")

    raw = (tmp_path / server.CSV_FILE_NAME).read_bytes()

    expected = "\r\n".join(
        [
            CSV_GOLDEN_HEADER,
            "2025-01-15_14-30-00;solo-leveling;mangalib.me;"
            f"{csv_mode};Не хватает 2;45;47;2;46:4:12, 47:4:13",
            "2025-01-15_14-30-00;actual;mangalib.me;"
            f"{csv_mode};Актуально;10;10;0;",
        ]
    ) + "\r\n"

    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw == expected.encode("utf-8-sig")
