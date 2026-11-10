"""Smoke test: exercise the markitdown server via an in-memory FastMCP client."""

import asyncio
import sys
from pathlib import Path

from fastmcp import Client

sys.path.insert(0, str(Path(__file__).parent))


async def main() -> None:
    from servers.markitdown import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()
        print("tools:", sorted(t.name for t in tools))

        roots_result = await client.call_tool("list_allowed_roots", {})
        print("roots:", [item.text for item in roots_result.content])

        root = Path(__file__).parent
        test_dir = root / ".smoke_test_markitdown"

        from servers.filesystem import mcp as fs_mcp

        async with Client(fs_mcp) as fs:
            await fs.call_tool("create_directory", {"path": str(test_dir)})
            await fs.call_tool(
                "write_text_file",
                {"path": str(test_dir / "hello.txt"), "content": "hello markitdown"},
            )

        # Plain text round-trips as-is.
        txt = (await client.call_tool(
            "convert_file", {"path": str(test_dir / "hello.txt")}
        )).content[0].text
        assert "hello markitdown" in txt, txt
        print("txt convert ✓")

        # HTML converts to Markdown.
        html_path = test_dir / "page.html"
        html_path.write_text(
            "<h1>Title</h1><p>Body <b>bold</b>.</p>", encoding="utf-8"
        )
        html_md = (await client.call_tool(
            "convert_file", {"path": str(html_path)}
        )).content[0].text
        assert "# Title" in html_md and "**bold**" in html_md, html_md
        print("html convert ✓")

        # .docx via the Office converter.
        from docx import Document

        doc = Document()
        doc.add_heading("Docx Heading", level=1)
        doc.add_paragraph("Some docx body text.")
        doc.save(test_dir / "doc.docx")
        docx_md = (await client.call_tool(
            "convert_file", {"path": str(test_dir / "doc.docx")}
        )).content[0].text
        assert "Docx Heading" in docx_md and "Some docx body text." in docx_md, docx_md
        print("docx convert ✓")

        # convert_string for in-memory content.
        blob = (await client.call_tool(
            "convert_string",
            {"content": "<h2>Inline</h2>", "file_extension": ".html"},
        )).content[0].text
        assert "Inline" in blob, blob
        print("convert_string ✓")

        # Escaping the root must be refused.
        try:
            await client.call_tool(
                "convert_file", {"path": "/etc/passwd"}
            )
            print("escape NOT rejected ✗")
        except Exception:
            print("escape rejected ✓")

        # Invalid extension must be refused.
        try:
            await client.call_tool(
                "convert_string", {"content": "x", "file_extension": "html"}
            )
            print("bad extension NOT rejected ✗")
        except Exception:
            print("bad extension rejected ✓")

        from servers.filesystem import mcp as fs_mcp2

        async with Client(fs_mcp2) as fs:
            await fs.call_tool("delete_path", {"path": str(test_dir / "hello.txt")})
            await fs.call_tool("delete_path", {"path": str(html_path)})
            await fs.call_tool("delete_path", {"path": str(test_dir / "doc.docx")})
            await fs.call_tool("delete_path", {"path": str(test_dir)})

        print("all checks passed")


asyncio.run(main())
