from typing import Any, Optional


TEXT_OUTPUT_BOTH = "both"
TEXT_OUTPUT_TXT = "txt"
TEXT_OUTPUT_HTML = "html"
TEXT_OUTPUT_CHOICES = (TEXT_OUTPUT_BOTH, TEXT_OUTPUT_TXT, TEXT_OUTPUT_HTML)

TEXT_OUTPUT_MENU = {
    "1": TEXT_OUTPUT_BOTH,
    "2": TEXT_OUTPUT_TXT,
    "3": TEXT_OUTPUT_HTML,
}


def resolve_text_output(value: Any) -> str:
    """Return a known text output preset, falling back to ``both``."""
    return value if value in TEXT_OUTPUT_CHOICES else TEXT_OUTPUT_BOTH


def parse_text_output(raw: Any) -> str:
    """Map a menu answer to a preset; empty or unknown answers mean ``both``."""
    return TEXT_OUTPUT_MENU.get(str(raw or "").strip(), TEXT_OUTPUT_BOTH)


def _title(chapter_name: Optional[str], req_number: Any) -> str:
    return chapter_name or f"Chapter {req_number}"


def render_chapter_html(
    chapter_name: Optional[str],
    req_number: Any,
    html_content: str,
) -> str:
    title = _title(chapter_name, req_number)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Georgia', 'Times New Roman', serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.8;
            color: #333;
        }}
        h1, h2, h3 {{
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }}
        p {{
            margin-bottom: 1em;
            text-align: justify;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    {html_content}
</body>
</html>"""


def render_chapter_txt(
    chapter_name: Optional[str],
    req_number: Any,
    text_content: str,
) -> str:
    header = f"{_title(chapter_name, req_number)}\n"
    header += "=" * len(header.strip()) + "\n\n"
    return header + text_content
