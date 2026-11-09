"""Filesystem MCP server built with FastMCP.

Exposes file tools restricted to a set of allowed root directories. Paths
outside the roots are rejected.

Roots are taken from the ``FILESYSTEM_ROOTS`` environment variable
(colon-separated, like ``PATH``). If unset, the current working directory is
used.

Run (stdio transport)::

    .venv/bin/python -m servers.filesystem
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

mcp = FastMCP(
    "Filesystem",
    instructions=(
        "Tools for reading and writing files on the local filesystem. "
        "All paths must stay inside one of the allowed roots."
    ),
)


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


@mcp.tool
def list_allowed_roots() -> list[str]:
    """List the root directories this server is allowed to access."""
    return [str(r) for r in _roots()]


@mcp.tool
def list_directory(path: str) -> list[str]:
    """List the entries of a directory. Directories get a trailing '/'."""
    allowed = _roots()
    resolved = _resolve(allowed, path)
    if not resolved.is_dir():
        raise ToolError(f"'{path}' is not a directory.")
    return sorted(
        (entry.name + "/" if entry.is_dir() else entry.name)
        for entry in resolved.iterdir()
    )


@mcp.tool
def read_text_file(path: str, max_bytes: int = 250_000) -> str:
    """Read a UTF-8 text file, truncated to *max_bytes*."""
    resolved = _existing_file(_roots(), path)
    data = resolved.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


@mcp.tool
def write_text_file(path: str, content: str) -> str:
    """Write *content* to a text file, creating parent directories as needed.

    Overwrites the file if it exists.
    """
    allowed = _roots()
    resolved = _resolve(allowed, path)
    if resolved.is_dir():
        raise ToolError(f"'{path}' is a directory.")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return f"Wrote {len(content.encode('utf-8'))} bytes to '{resolved}'."


@mcp.tool
def create_directory(path: str) -> str:
    """Create a directory, including missing parent directories."""
    resolved = _resolve(_roots(), path)
    resolved.mkdir(parents=True, exist_ok=True)
    return f"Created '{resolved}'."


@mcp.tool
def move_path(source: str, destination: str) -> str:
    """Move or rename a file or directory."""
    allowed = _roots()
    src = _resolve(allowed, source)
    dst = _resolve(allowed, destination)
    if not src.exists():
        raise ToolError(f"Source '{source}' does not exist.")
    if dst.exists():
        raise ToolError(f"Destination '{destination}' already exists.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Moved '{src}' to '{dst}'."


@mcp.tool
def delete_path(path: str) -> str:
    """Permanently delete a file or an empty directory."""
    resolved = _resolve(_roots(), path)
    if resolved.is_dir() and not resolved.is_symlink():
        if any(resolved.iterdir()):
            raise ToolError(
                f"Directory '{resolved}' is not empty; use delete_path on its "
                "contents first (recursive deletion is not offered)."
            )
        resolved.rmdir()
    elif resolved.exists():
        resolved.unlink()
    else:
        raise ToolError(f"'{path}' does not exist.")
    return f"Deleted '{resolved}'."


@mcp.tool
def search_files(path: str, pattern: str) -> list[str]:
    """Glob-search for *pattern* (e.g. ``**/*.py``) starting at *path*."""
    allowed = _roots()
    base = _resolve(allowed, path)
    if not base.is_dir():
        raise ToolError(f"'{path}' is not a directory.")
    return sorted(str(p.relative_to(base)) for p in base.glob(pattern))[:200]


@mcp.tool
def get_file_info(path: str) -> dict[str, object]:
    """Get metadata (size, type, timestamps, permissions) for a path."""
    resolved = _resolve(_roots(), path)
    if not resolved.exists():
        raise ToolError(f"'{path}' does not exist.")
    st = resolved.stat()
    return {
        "path": str(resolved),
        "size_bytes": st.st_size,
        "is_directory": stat.S_ISDIR(st.st_mode),
        "created": st.st_ctime,
        "modified": st.st_mtime,
        "permissions": stat.filemode(st.st_mode),
    }


if __name__ == "__main__":
    mcp.run()
