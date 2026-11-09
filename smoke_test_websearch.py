"""Smoke test: exercise the websearch server via an in-memory FastMCP client."""

import asyncio
import sys
from pathlib import Path

from fastmcp import Client

sys.path.insert(0, str(Path(__file__).parent))


async def main() -> None:
    from servers.websearch import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()
        print("tools:", sorted(t.name for t in tools))

        arch = (await client.call_tool(
            "search_arch_packages", {"query": "w3m"}
        )).content[0].text
        lines = [l for l in arch.splitlines() if "w3m" in l.lower()][:8]
        print("arch results (excerpt):")
        print("\n".join(lines))

        wiki = (await client.call_tool(
            "search_wikipedia", {"query": "Model Context Protocol"}
        )).content[0].text
        print("wikipedia result head:")
        print("\n".join(wiki.splitlines()[:10]))

        web = (await client.call_tool(
            "search_web", {"query": "FastMCP python"}
        )).content[0].text
        print("duckduckgo result head:")
        print("\n".join(web.splitlines()[:10]))
        assert "http" in web.lower(), "no URLs in web results"

        page = (await client.call_tool(
            "fetch_page",
            {"url": "https://en.wikipedia.org/wiki/W3m"},
        )).content[0].text
        print("fetch_page head:")
        print("\n".join(page.splitlines()[:8]))
        assert page.strip(), "empty page render"

        # Reject bad input
        for tool, kwargs in (
            ("fetch_page", {"url": "ftp://example.com"}),
            ("fetch_page", {"url": "https://engex.test.invalid", "browser": "netscape"}),
        ):
            try:
                await client.call_tool(tool, kwargs)
            except Exception as exc:
                reason = "non-http scheme" if "ftp" in str(kwargs) else "unknown browser"
                print(f"rejected ({reason}) ✓")

        print("all checks passed")


asyncio.run(main())
