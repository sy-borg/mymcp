"""Persistent memory MCP server built with FastMCP.

Stores a knowledge graph of entities, observations, and relations in a JSON
file so an agent can accumulate knowledge across sessions.

Graph model::

    {
      "entities":  [{"name": str, "entityType": str, "observations": [str]}],
      "relations": [{"from": str, "to": str, "relationType": str}]
    }

Storage location: the ``MEMORY_PATH`` env var, or by default
``$XDG_DATA_HOME/mymcp-memory/graph.json`` (falls back to
``~/.local/share/mymcp-memory/graph.json``). Writes are atomic; concurrent
writers are not coordinated, so use one session per graph.

Run (stdio transport)::

    .venv/bin/python -m servers.memory
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

mcp = FastMCP(
    "Memory",
    instructions=(
        "Persistent knowledge-graph memory across sessions. Create entities, "
        "propose relations between them, remember facts as observations, and "
        "query the graph later with search_nodes or open_nodes."
    ),
)


class Entity(BaseModel):
    name: str
    entityType: str = "generic"
    observations: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    from_: str = Field(alias="from")
    to: str
    relationType: str

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------- storage


def _storage_path() -> Path:
    return Path(os.environ.get("MEMORY_PATH", "")).expanduser() if os.environ.get("MEMORY_PATH") else (
        (Path(os.environ.get("XDG_DATA_HOME", "")).expanduser()
         if os.environ.get("XDG_DATA_HOME") else Path.home() / ".local/share")
        / "mymcp-memory" / "graph.json"
    )


def _empty() -> dict[str, list]:
    return {"entities": [], "relations": []}


def _load() -> dict[str, list]:
    path = _storage_path()
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ToolError(f"Cannot read memory at '{path}': {exc}") from exc
    if not isinstance(data, dict) or "entities" not in data or "relations" not in data:
        return _empty()
    return {"entities": data["entities"], "relations": data["relations"]}


def _save(graph: dict[str, list]) -> Path:
    path = _storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _find(graph: dict[str, list], name: str) -> dict[str, Any] | None:
    return next((e for e in graph["entities"] if e["name"] == name), None)


def _relation_exists(graph: dict[str, list], rel: Relation) -> bool:
    return any(
        r.get("from") == rel.from_ and r.get("to") == rel.to and r.get("relationType") == rel.relationType
        for r in graph["relations"]
    )


# ----------------------------------------------------------------- tools


@mcp.tool
def create_entities(
    entities: list[Entity] = Field(description="Entities to create or merge."),
) -> str:
    """Create entities, or merge observations into ones that already exist.

    New entities are appended as-is. Existing ones keep their entityType and
    gain any new (deduplicated) observations.
    """
    graph = _load()
    created, merged = [], []
    for entity in entities:
        existing = _find(graph, entity.name)
        if existing is None:
            graph["entities"].append(entity.model_dump())
            created.append(entity.name)
        else:
            old = set(existing["observations"])
            fresh = [o for o in entity.observations if o not in old]
            existing["observations"].extend(fresh)
            if fresh:
                merged.append(f"{entity.name} (+{len(fresh)} observations)")
    _save(graph)
    return f"Created {created or 'none'}; merged {merged or 'none'}."


@mcp.tool
def create_relations(
    relations: list[Relation] = Field(description="Triples: from, to, relationType."),
) -> str:
    """Create directed relations between entities (deduplicated).

    Both ends must already exist as entities — facts live on entities,
    structure lives on relations.
    """
    graph = _load()
    missing = sorted(
        {n for rel in relations for n in (rel.from_, rel.to) if _find(graph, n) is None}
    )
    if missing:
        raise ToolError(f"Unknown entities: {missing}. Create them first.")
    fresh, skipped = [], []
    for rel in relations:
        if _relation_exists(graph, rel):
            skipped.append(rel)
        else:
            graph["relations"].append({"from": rel.from_, "to": rel.to, "relationType": rel.relationType})
            fresh.append(rel)
    _save(graph)
    return f"Created {len(fresh)} relation(s), skipped {len(skipped)} existent."


@mcp.tool
def add_observations(entity_name: str, observations: list[str]) -> str:
    """Attach new observations (facts) to an existing entity. Deduplicates."""
    if not observations:
        return "No observations given."
    graph = _load()
    entity = _find(graph, entity_name)
    if entity is None:
        raise ToolError(f"Entity '{entity_name}' does not exist.")
    old = set(entity["observations"])
    fresh = [o for o in observations if o not in old]
    entity["observations"].extend(fresh)
    _save(graph)
    return f"Added {len(fresh)} observation(s) to '{entity_name}' ({len(old)} already known)."


@mcp.tool
def delete_entities(entity_names: list[str]) -> str:
    """Delete entities and every relation connected to them."""
    graph = _load()
    for name in entity_names:
        graph["entities"] = [e for e in graph["entities"] if e["name"] != name]
        graph["relations"] = [
            r for r in graph["relations"] if r.get("from") != name and r.get("to") != name
        ]
    _save(graph)
    return f"Deleted {len(entity_names)} entity(ies) and any relations connected to them."


@mcp.tool
def delete_observations(entity_name: str, observations: list[str]) -> str:
    """Remove specific observations from an entity."""
    graph = _load()
    entity = _find(graph, entity_name)
    if entity is None:
        raise ToolError(f"Entity '{entity_name}' does not exist.")
    drop = set(observations)
    before = entity["observations"]
    entity["observations"] = [o for o in before if o not in drop]
    removed = len(before) - len(entity["observations"])
    _save(graph)
    return f"Removed {removed} observation(s) from '{entity_name}'."


@mcp.tool
def read_graph() -> dict[str, list]:
    """Read the entire knowledge graph (all entities and relations)."""
    return _load()


@mcp.tool
def search_nodes(query: str) -> dict[str, list]:
    """Case-insensitive substring search over entity names, types, and observations.

    Returns matching entities plus all relations among them.
    """
    graph = _load()
    q = query.lower()
    matched = [
        e for e in graph["entities"]
        if q in e["name"].lower()
        or q in e["entityType"].lower()
        or any(q in o.lower() for o in e["observations"])
    ]
    names = {e["name"] for e in matched}
    return {
        "entities": matched,
        "relations": [r for r in graph["relations"] if r["from"] in names and r["to"] in names],
    }


@mcp.tool
def open_nodes(entity_names: list[str]) -> dict[str, list]:
    """Fetch named entities plus all relations among (or attached to) them."""
    graph = _load()
    wanted = set(entity_names)
    found = [e for e in graph["entities"] if e["name"] in wanted]
    missing = sorted(wanted - {e["name"] for e in found})
    if missing:
        # Not an error: asking about unknown nodes is a normal read.
        note = [f"[not in graph: {', '.join(missing)}]"]
    else:
        note = []
    return {
        "entities": found,
        "relations": [r for r in graph["relations"] if r["from"] in wanted or r["to"] in wanted],
    } | ({"note": note} if note else {})


if __name__ == "__main__":
    mcp.run()
