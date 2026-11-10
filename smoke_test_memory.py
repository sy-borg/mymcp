"""Smoke test: exercise the memory server via an in-memory FastMCP client."""

import asyncio
import sys
from pathlib import Path

from fastmcp import Client
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))

TMP_GRAPH = "/tmp/opencode/mymcp_smoke_memory.json"

# Pydantic aliases ("from") make positional dicts need round-tripping.
async def main() -> None:
    from servers.memory import mcp, Entity, Relation

    path = Path(TMP_GRAPH)
    path.unlink(missing_ok=True)
    import os
    os.environ["MEMORY_PATH"] = TMP_GRAPH

    async with Client(mcp) as client:
        tools = await client.list_tools()
        print("tools:", sorted(t.name for t in tools))

        # Entities: create + merge semantics
        r1 = (await client.call_tool("create_entities", {"entities": [
            Entity(name="mymcp", entityType="project", observations=["FastMCP sandbox"]),
            Entity(name="sa", entityType="person"),
        ]})).content[0].text
        print(r1)
        r2 = (await client.call_tool("create_entities", {"entities": [
            Entity(name="mymcp", observations=["runs on Arch", "pink" if False else "two servers"]),
        ]})).content[0].text
        print(r2)

        # Relations: dedupe + existence enforcement
        r3 = (await client.call_tool("create_relations", {"relations": [
            Relation.model_validate({"from": "sa", "to": "mymcp", "relationType": "maintains"}),
        ]})).content[0].text
        print(r3)
        try:
            await client.call_tool("create_relations", {"relations": [
                Relation.model_validate({"from": "ghost", "to": "mymcp", "relationType": "haunts"}),
            ]})
        except Exception:
            print("relation to unknown entity refused ✓")

        # Observations
        r4 = (await client.call_tool("add_observations", {
            "entity_name": "sa", "observations": ["uses Arch Linux"],
        })).content[0].text
        print(r4)
        r5 = (await client.call_tool("add_observations", {
            "entity_name": "sa", "observations": ["uses Arch Linux"],
        })).content[0].text
        print(r5)

        # Queries
        found = eval_result((await client.call_tool("search_nodes", {"query": "arch"})).content)
        print("search 'arch' entities:", [e["name"] for e in found["entities"]])

        opened = (await client.call_tool("open_nodes", {"entity_names": ["mymcp", "ghost"]})).content
        data_o = eval_result(opened)
        print("open_nodes:", [e["name"] for e in data_o["entities"]],
              "| relations:", len(data_o["relations"]), "| note:", data_o.get("note"))

        graph = eval_result((await client.call_tool("read_graph", {})).content)
        assert len(graph["entities"]) == 2 and len(graph["relations"]) == 1
        assert all(e.get("entityType") for e in graph["entities"])

        # Delete: cleans relations too
        await client.call_tool("delete_entities", {"entity_names": ["mymcp"]})
        graph = eval_result((await client.call_tool("read_graph", {})).content)
        assert len(graph["entities"]) == 1 and not graph["relations"], graph
        print("delete cascade ✓")

        r6 = (await client.call_tool("delete_observations", {"entity_name": "sa", "observations": ["uses Arch Linux"]})).content[0].text
        print(r6)

        # Pydantic validation barrier
        try:
            Entity(name="x", biz="bad field")
        except ValidationError:
            print("validation barrier ✓")

    path.unlink(missing_ok=True)
    print("all checks passed")


def eval_result(content) -> dict:
    """Parse a JSON/structured tool result into a dict."""
    import json
    item = content[0]
    return json.loads(item.text)


asyncio.run(main())
