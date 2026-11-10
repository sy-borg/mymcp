"""MarkItDown MCP server built with FastMCP.

Converts files (PDF, Word, Excel, PowerPoint, HTML, PDF, CSV, EPUB, ...)
to Markdown using Microsoft's `markitdown` package, so the content can be
consumed by AI agents.

Input files must live inside one of the allowed root directories. Roots are
taken from the ``FILESYSTEM_ROOTS`` environment variable (colon-separated,
like ``PATH``) so this server interoperates with ``servers.filesystem``. If
unset, the current working directory is used.

Run (stdio transport)::

    .venv/bin/python -m servers.markitdown
"""

from __future__ import annotations

import io
import os
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from markitdown import MarkItDown

mcp = FastMCP(
    "MarkItDown",
    instructions=(
        "Converts files (PDF, Word, Excel, PowerPoint, HTML, CSV, images, ...) "
        "to Markdown so agents can read them. All paths must stay inside one "
        "of the allowed roots."
    ),
)

_converter = MarkItDown()


def _roots() -> list[Path]:
    raw = os.environ.get("FILESYSTEM_ROOTS", "")
    if raw.strip():
        roots = [Path(p).expanduser().resolve() for p in raw.split(":") if p.strip()]
    else:
        roots = [Path.cwd().resolve()]
    return [r for r in roots if r.is_dir()]


def _resolve(allowed_roots: list[Path], path: str) -> Path:
    """Resolve *path* and enforce it is inside one of the allowed roots."""
    candidate = Path(path).expanduser()
    resolved = (candidate if candidate.is_absolute() else Path.cwd() / candidate).resolve()
    for root in allowed_roots:
        if resolved == root or root in resolved.parents:
            return resolved
    allowed = ", ".join(str(r) for r in allowed_roots)
    raise ToolError(
        f"Path '{path}' is outside the allowed roots ({allowed})."
    )


def _existing_file(allowed_roots: list[Path], path: str) -> Path:
    resolved = _resolve(allowed_roots, path)
    if not resolved.is_file():
        raise ToolError(f"'{path}' is not a file.")
    return resolved


def _convert(source: Path, *, max_chars: int) -> str:
    try:
        result = _converter.convert(str(source))
    except Exception as exc:
        raise ToolError(f"Conversion of '{source}' failed: {exc}") from exc
    if not result.text_content:
        raise ToolError(f"Conversion of '{source}' produced no content.")
    return result.text_content[:max_chars]


@mcp.tool
def list_allowed_roots() -> list[str]:
    """List the root directories input files may come from."""
    return [str(r) for r in _roots()]


@mcp.tool
def convert_file(path: str, max_chars: int = 250_000) -> str:
    """Convert the file at *path* to Markdown, truncated to *max_chars*.

    Supports PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), HTML,
    CSV, JSON, XML, EPUB, ZIP (file listing), images (via OCR), and more.
    """
    resolved = _existing_file(_roots(), path)
    return _convert(resolved, max_chars=max_chars)


@mcp.tool
def convert_string(content: str, file_extension: str, max_chars: int = 250_000) -> str:
    """Convert raw *content* that is known to have *file_extension* to Markdown.

    Useful for material an agent already holds in memory (a downloaded HTML
    page, a CSV blob, ...). *file_extension* must include the leading dot,
    e.g. ``.html``.
    """
    if not file_extension.startswith("."):
        raise ToolError("file_extension must include the leading dot, e.g. '.html'.")
    stream = io.BytesIO(content.encode("utf-8"))
    result = _converter.convert_stream(stream, file_extension=file_extension)
    if not result.text_content:
        raise ToolError("Conversion produced no content.")
    return result.text_content[:max_chars]


if __name__ == "__main__":
    mcp.run()
