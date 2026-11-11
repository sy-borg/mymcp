"""MarkItDown MCP server built with FastMCP.

Converts files (PDF, Word, Excel, PowerPoint, HTML, PDF, CSV, EPUB, ...)
to Markdown using Microsoft's `markitdown` package, so the content can be
consumed by AI agents. HTTP(S) URLs can also be converted: they are
downloaded to a temporary file first.

Input files must live inside one of the allowed root directories. Roots are
taken from the ``FILESYSTEM_ROOTS`` environment variable (colon-separated,
like ``PATH``) so this server interoperates with ``servers.filesystem``. If
unset, the current working directory is used.

Run (stdio transport)::

    .venv/bin/python -m servers.markitdown
"""

from __future__ import annotations

import io
import mimetypes
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from markitdown import MarkItDown

mcp = FastMCP(
    "MarkItDown",
    instructions=(
        "Converts files (PDF, Word, Excel, PowerPoint, HTML, CSV, images, ...) "
        "to Markdown so agents can read them. All paths must stay inside one "
        "of the allowed roots. URLs (http/https) are downloaded to a temporary "
        "file and converted as well."
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


_CONTENT_TYPE_EXTENSIONS = {
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/csv": ".csv",
    "application/json": ".json",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/zip": ".zip",
    "application/epub+zip": ".epub",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}


def _suffix_for_url(url: str, content_type: str | None) -> str:
    """Pick a filename extension for *url*, preferring the URL path."""
    path = urllib.parse.urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix:
        return suffix
    if content_type:
        mime = content_type.split(";", 1)[0].strip().lower()
        if mime in _CONTENT_TYPE_EXTENSIONS:
            return _CONTENT_TYPE_EXTENSIONS[mime]
        guessed = mimetypes.guess_extension(mime)
        if guessed:
            return guessed
    return ".html"


def _download(url: str, *, timeout: float, max_bytes: int) -> Path:
    """Download *url* to a temporary file and return its path."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ToolError(f"Only http(s) URLs are supported, got '{parsed.scheme or url}'.")

    request = urllib.request.Request(
        url, headers={"User-Agent": "mymcp-markitdown/1.0"}
    )
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except Exception as exc:
        raise ToolError(f"Download of '{url}' failed: {exc}") from exc

    with response:
        content_type = response.headers.get("Content-Type")
        chunks: list[bytes] = []
        received = 0
        try:
            while chunk := response.read(64 * 1024):
                received += len(chunk)
                if received > max_bytes:
                    raise ToolError(
                        f"Download of '{url}' exceeded max_bytes ({max_bytes})."
                    )
                chunks.append(chunk)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"Download of '{url}' failed: {exc}") from exc

    tmp = tempfile.NamedTemporaryFile(
        prefix="markitdown_url_",
        suffix=_suffix_for_url(url, content_type),
        delete=False,
    )
    try:
        with tmp:
            tmp.write(b"".join(chunks))
    except Exception:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        raise
    return Path(tmp.name)


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
def convert_url(
    url: str,
    max_chars: int = 250_000,
    timeout: float = 30.0,
    max_bytes: int = 50_000_000,
) -> str:
    """Download *url* (http/https) to a temporary file and convert it to Markdown.

    The file type is derived from the URL path, falling back to the response's
    Content-Type header. The temporary file is removed afterwards.

    Args:
        url: The http(s) URL to fetch and convert.
        max_chars: Returned Markdown is truncated to this many characters.
        timeout: Download timeout in seconds.
        max_bytes: Refuse to download more than this many bytes.
    """
    tmp_path = _download(url, timeout=timeout, max_bytes=max_bytes)
    try:
        return _convert(tmp_path, max_chars=max_chars)
    finally:
        tmp_path.unlink(missing_ok=True)


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
