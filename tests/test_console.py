import main
import utils


def test_main_reuses_utils_console_setup():
    assert main.configure_utf8_console is utils.configure_utf8_console
