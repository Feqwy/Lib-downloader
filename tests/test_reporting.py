import pytest

from colors import Colors
from reporting import ConsoleReporter, NullReporter, Reporter


def test_console_reporter_prints_colors_format(capsys):
    reporter = ConsoleReporter()

    reporter.info("info text")
    reporter.success("success text")
    reporter.warning("warning text")
    reporter.error("error text")
    reporter.bold("bold text")
    reporter.line("raw text")
    reporter.line()

    assert capsys.readouterr().out == (
        f"{Colors.CYAN}Info: info text{Colors.RESET}\n"
        f"{Colors.GREEN}Success: success text{Colors.RESET}\n"
        f"{Colors.YELLOW}Warning: warning text{Colors.RESET}\n"
        f"{Colors.RED}Error: error text{Colors.RESET}\n"
        f"{Colors.BOLD}bold text{Colors.RESET}\n"
        "raw text\n"
        "\n"
    )


def test_console_reporter_blank_line(capsys):
    ConsoleReporter().line()

    assert capsys.readouterr().out == "\n"


def test_null_reporter_is_silent(capsys):
    reporter = NullReporter()

    reporter.line("raw")
    reporter.info("info")
    reporter.success("success")
    reporter.warning("warning")
    reporter.error("error")
    reporter.bold("bold")

    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("reporter", [ConsoleReporter(), NullReporter()])
def test_reporter_has_protocol_methods(reporter):
    for name in ("line", "info", "success", "warning", "error", "bold"):
        assert callable(getattr(reporter, name))

    assert set(dir(Reporter)) >= {
        "line", "info", "success", "warning", "error", "bold"
    }


def test_console_reporter_progress_uses_tqdm(capsys):
    reporter = ConsoleReporter()

    progress = reporter.progress_start(3, "  Downloading Ch5", unit="img")
    reporter.progress_update(progress)
    reporter.progress_update(progress)
    reporter.progress_finish(progress)

    assert progress.n == 2
    assert progress.disable is True
    assert "Downloading Ch5" in capsys.readouterr().err


def test_null_reporter_progress_is_silent(capsys):
    reporter = NullReporter()

    progress = reporter.progress_start(3, "  Downloading Ch5", unit="img")
    reporter.progress_update(progress)
    reporter.progress_finish(progress)

    assert progress is None
    assert capsys.readouterr().err == ""


def test_reporter_has_progress_methods():
    for reporter in (ConsoleReporter(), NullReporter()):
        for name in ("progress_start", "progress_update", "progress_finish"):
            assert callable(getattr(reporter, name))

    assert set(dir(Reporter)) >= {
        "progress_start", "progress_update", "progress_finish"
    }
