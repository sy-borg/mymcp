"""Web search MCP server built with FastMCP.

Searches the web (DuckDuckGo), Wikipedia, and the Arch Linux package
repository, and renders the result pages through a text-mode browser
(lynx/w3m/links) so agents receive clean plain text instead of HTML.

Pages are fetched with Python and rendered through the local browser
binary. Browsers are tried in the order lynx, w3m, links; override with
the ``WEBSEARCH_BROWSER`` env var or a tool's *browser* parameter.
lynx -dump and w3m (``display_link_number=1``) append a numbered
reference list so the result URLs stay visible.

Run (stdio transport)::

    .venv/bin/python -m servers.websearch
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

mcp = FastMCP(
    "WebSearch",
    instructions=(
        "Search the web, Wikipedia, and the Arch Linux package repository, "
        "and read any page as plain text. Results are rendered through a "
        "text browser with a numbered reference list of URLs at the end."
    ),
)

USER_AGENT = "opencode-websearch-mcp/1.0 (local MCP server)"
MAX_HTML_BYTES = 3_000_000
MAX_TEXT_CHARS = 50_000
HTTP_TIMEOUT = 20
RENDER_TIMEOUT = 30

# The "FILE" placeholder is replaced with the temp file path. lynx -dump
# and w3m with display_link_number=1 both emit numbered text followed by a
# "References" section listing all URLs.
_RENDER_ARGS: dict[str, list[str]] = {
    "lynx": ["lynx", "-dump", "-nonumbers", "FILE"],
    "w3m": ["w3m", "-dump", "-o", "display_link_number=1", "FILE"],
    "links": ["links", "-dump", "FILE"],
}
_RENDER_ORDER = ("lynx", "w3m", "links")


def _browser(name: str) -> list[str]:
    """Return the (unrendered) argv of the browser to use.

    *name* is 'auto' or one of the configured browsers. Raise ToolError if
    the browser is unknown or not installed.
    """
    name = name.strip().lower()
    if name != "auto":
        if name not in _RENDER_ARGS:
            raise ToolError(
                f"Unknown browser '{name}'. Choose from: auto, "
                f"{', '.join(_RENDER_ARGS)}."
            )
        if not shutil.which(name):
            raise ToolError(f"Browser '{name}' is not installed.")
        return _RENDER_ARGS[name]
    override = os.environ.get("WEBSEARCH_BROWSER", "").strip().lower()
    candidates = (override,) if override else _RENDER_ORDER
    for candidate in candidates:
        if candidate not in _RENDER_ARGS:
            continue
        if shutil.which(candidate):
            return _RENDER_ARGS[candidate]
    raise ToolError(
        "No text browser found (tried: "
        f"{', '.join(candidates)}). Install one, e.g. 'pacman -S w3m' or "
        "'pacman -S lynx'."
    )


def _http(
    url: str,
    *,
    method: str = "GET",
    data: dict[str, str] | None = None,
) -> bytes:
    """Fetch a URL (capped, with redirects). Raise ToolError on failure."""
    if not url.lower().startswith(("http://", "https://")):
        raise ToolError("Only http(s) URLs are supported.")
    payload = urllib.parse.urlencode(data).encode() if data else None
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"User-Agent": USER_AGENT},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            status = response.status
            effective_url = response.geturl()
            body = response.read(MAX_HTML_BYTES + 1)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Fetch of '{url}' failed: {exc}") from exc
    if status != 200:
        raise ToolError(f"Fetch of '{url}' returned HTTP {status}.")
    return body[:MAX_HTML_BYTES], effective_url


def _inject_base(html_body: bytes, base_url: str) -> bytes:
    """Insert a <base href> tag so relative URLs resolve to the real site.

    Without it, rendering from a temp file makes w3m/lynx list links as
    file://... paths instead of the page's real URLs.
    """
    safe_url = base_url.replace('"', "&quot;")
    tag = f'<base href="{safe_url}">'.encode()
    match = re.search(rb"<\s*head[^>]*>", html_body, re.IGNORECASE)
    if not match:
        match = re.search(rb"<\s*html[^>]*>", html_body, re.IGNORECASE)
        if not match:
            return tag + html_body
    index = match.end()
    return html_body[:index] + tag + html_body[index:]


def _render(html_body: bytes, browser: str, base_url: str) -> str:
    """Render HTML bytes to plain text through the selected browser."""
    html_body = _inject_base(html_body, base_url)
    argv = _browser(browser)
    tmp_dir = "/tmp/opencode" if os.path.isdir("/tmp/opencode") else None
    fd, path = tempfile.mkstemp(suffix=".html", dir=tmp_dir)
    try:
        text = None
        with os.fdopen(fd, "wb") as fh:
            fh.write(html_body)
        full_argv = [path if part == "FILE" else part for part in argv]
        try:
            result = subprocess.run(
                full_argv,
                capture_output=True,
                timeout=RENDER_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(
                f"Rendering timed out after {RENDER_TIMEOUT}s."
            ) from exc
        text = result.stdout.decode("utf-8", errors="replace")
        if result.returncode != 0 and not text.strip():
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise ToolError(f"Rendering failed: {stderr.strip()[:500]}")
    finally:
        os.unlink(path)
    if not text.strip():
        raise ToolError("The page rendered to empty text.")
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n\n[... text truncated ...]"
    return text


def _unwrap_ddg_redirects(text: str) -> str:
    """Replace DuckDuckGo redirect links with the real target URLs."""
    redirect = re.compile(
        r"https?://duckduckgo\.com/l/\?uddg=([^&\s)\x5d]+)(?:&rut=[0-9a-f]+)?"
    )
    return redirect.sub(
        lambda m: urllib.parse.unquote(m.group(1)), text
    )


def _search_page(
    scheme: tuple[str, dict[str, str] | None], query: str, browser: str
) -> str:
    """Fetch a search results page for *query* and render it.

    *scheme* is a ``(url_template, post_data)`` pair: the GET or POST URL
    and the form data to send with it (None for GET).
    """
    url_template, data = scheme
    url = url_template.format(q=urllib.parse.quote_plus(query))
    body, effective_url = _http(
        url,
        method="POST" if data else "GET",
        data=data,
    )
    return _render(body, browser, effective_url)


@mcp.tool
def fetch_page(url: str, browser: str = "auto") -> str:
    """Fetch any http(s) web page and return it as plain text.

    Use this to read pages found by the other tools in this server.
    """
    body, effective_url = _http(url)
    return _render(body, browser, effective_url)


@mcp.tool
def search_web(query: str, browser: str = "auto") -> str:
    """Search the web with DuckDuckGo. Returns rendered, numbered results."""
    try:
        return _unwrap_ddg_redirects(_search_page(
            ("https://lite.duckduckgo.com/lite/?q={q}", None), query, browser
        ))
    except ToolError:
        # Fallback: POST to the main html endpoint if lite fails or is
        # refused (it can demand a form submit).
        return _unwrap_ddg_redirects(_search_page(
            ("https://html.duckduckgo.com/html/", {"q": query}), query, browser
        ))


@mcp.tool
def search_wikipedia(query: str, browser: str = "auto") -> str:
    """Search English Wikipedia. Returns results with article URLs."""
    return _search_page(
        ("https://en.wikipedia.org/w/index.php?search={q}&fulltext=1", None),
        query,
        browser,
    )


@mcp.tool
def search_arch_packages(query: str, browser: str = "auto") -> str:
    """Search the official Arch Linux repositories from archlinux.org."""
    return _search_page(
        ("https://archlinux.org/packages/?q={q}", None), query, browser
    )


if __name__ == "__main__":
    mcp.run()
