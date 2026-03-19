class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"

    @classmethod
    def _colorize(cls, color: str, message: str) -> str:
        # Применяет цвет к сообщению.
        return f"{color}{message}{cls.RESET}"

    @classmethod
    def success(cls, msg: str) -> str:
        # Форматирует сообщение об успехе.
        return cls._colorize(cls.GREEN, f"Success: {msg}")

    @classmethod
    def info(cls, msg: str) -> str:
        # Форматирует информационное сообщение.
        return cls._colorize(cls.CYAN, f"Info: {msg}")

    @classmethod
    def error(cls, msg: str) -> str:
        # Форматирует сообщение об ошибке.
        return cls._colorize(cls.RED, f"Error: {msg}")

    @classmethod
    def warning(cls, msg: str) -> str:
        # Форматирует предупреждение.
        return cls._colorize(cls.YELLOW, f"Warning: {msg}")

    @classmethod
    def chapter(cls, num: int) -> str:
        # Форматирует номер главы.
        return f"{cls.BOLD}{cls.MAGENTA}Chapter {num}{cls.RESET}"

    @classmethod
    def title(cls, text: str) -> str:
        # Форматирует заголовок.
        return f"{cls.BOLD}{cls.BLUE}{text}{cls.RESET}"