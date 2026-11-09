"""Smoke test: exercise the filesystem server via an in-memory FastMCP client."""

import asyncio
import sys
from pathlib import Path

from fastmcp import Client

sys.path.insert(0, str(Path(__file__).parent))


async def main() -> None:
    from servers.filesystem import mcp

    root = Path(__file__).parent
    async with Client(mcp) as client:
        tools = await client.list_tools()
        print("tools:", sorted(t.name for t in tools))

        roots_result = await client.call_tool("list_allowed_roots", {})
        print("roots:", [item.text for item in roots_result.content])

        test_dir = root / ".smoke_test"
        await client.call_tool("create_directory", {"path": str(test_dir)})
        await client.call_tool(
            "write_text_file",
            {"path": str(test_dir / "hello.txt"), "content": "hello mcp"},
        )
        listing = (await client.call_tool("list_directory", {"path": str(root)})).content[0].text
        print("listing contains:", [line for line in listing.splitlines() if "smoke" in line])

        content = (await client.call_tool(
            "read_text_file", {"path": str(test_dir / "hello.txt")}
        )).content[0].text
        assert content == "hello mcp", content

        found = (await client.call_tool(
            "search_files", {"path": str(test_dir), "pattern": "**/*.txt"}
        )).content[0].text
        print("search:", found)

        info = (await client.call_tool(
            "get_file_info", {"path": str(test_dir / "hello.txt")}
        )).content[0].text
        print("info:", info)

        # Escaping the root must be refused.
        try:
            await client.call_tool(
                "write_text_file", {"path": "/etc/mymcp_escape_test", "content": "nope"}
            )
        except Exception as exc:
            print("escape rejected ✓")

        # Deleting a non-empty directory must be refused.
        try:
            await client.call_tool("delete_path", {"path": str(test_dir)})
        except Exception:
            print("non-empty delete refused ✓")

        await client.call_tool("delete_path", {"path": str(test_dir / "hello.txt")})
        await client.call_tool("delete_path", {"path": str(test_dir)})
        print("all checks passed")


asyncio.run(main())
