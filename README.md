# mymcp — local MCP servers

A collection of [FastMCP](https://gofastmcp.com) MCP servers, isolated in a
virtual environment (Arch Linux ships an externally-managed Python).

## Setup

```sh
python -m venv .venv
.venv/bin/pip install fastmcp
```

## Running a server

All servers live in `servers/`, one module per server, and default to stdio
transport:

```sh
.venv/bin/python -m servers.filesystem
```

### filesystem

File tools (read/write/list/move/delete/search) restricted to configured root
directories. Roots come from the colon-separated `FILESYSTEM_ROOTS` env var;
if unset, the current working directory is used.

```sh
FILESYSTEM_ROOTS=/home/sa/src:/home/sa/Documents .venv/bin/python -m servers.filesystem
```

Note: an unrestricted root defeats the purpose — one served project can edit
files in anything under the same root.

### websearch

Searches the web (DuckDuckGo), Wikipedia, and the Arch Linux repository, and
fetches any page — all rendered to plain text through a local text browser
(`w3m`/`lynx`). Results keep a numbered reference list of URLs, so agents can
follow up with `fetch_page`. Fresh results are not cached; DuckDuckGo's
redirect links are unwrapped to real URLs.

Tools: `search_web`, `search_wikipedia`, `search_arch_packages`, `fetch_page`.
Browser selection tries `WEBSEARCH_BROWSER` → lynx → w3m → links;
`browser="auto"` per call unless overridden. Needs one of `w3m`, `lynx`,
`links` installed (e.g. `pacman -S w3m`).

```sh
WEBSEARCH_BROWSER=w3m .venv/bin/python -m servers.websearch
```

No new Python dependencies: pages are fetched with the standard library and
only rendered by the external browser.

### memory

Persistent knowledge-graph memory, stored as JSON (entities with
observations, plus typed relations between them) at
`$MEMORY_PATH` or `$XDG_DATA_HOME/mymcp-memory/graph.json`
(~/.local/share/mymcp-memory/graph.json by default).

Tools: `create_entities` (merges observations into known entities),
`create_relations` (deduplicated, both ends must exist),
`add_observations` / `delete_observations`, `delete_entities` (cascades its
relations), `read_graph`, `search_nodes`, `open_nodes`. Writes are atomic.

```sh
.venv/bin/python -m servers.memory
```

## Adding another server

1. Create `servers/<name>.py` with a `FastMCP` instance called `mcp` and a
   `if __name__ == "__main__": mcp.run()` block.
2. Install any extra dependencies into `.venv`.
3. Register it in OpenCode (global config lives at `~/.config/opencode/opencode.json`).
   V2 requires servers under `mcp.servers`. Use `{env:NAME}` for environment
   substitution — shell expansions like `$HOME` are **not** expanded in JSON:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "filesystem": {
        "type": "local",
        "command": ["/home/sa/src/mymcp/.venv/bin/python", "-m", "servers.filesystem"],
        "cwd": "/home/sa/src/mymcp",
        "environment": {
          "FILESYSTEM_ROOTS": "{env:HOME}/src"
        }
      }
    }
  }
}
```

Alternatively, register from the shell (where `$HOME` *does* expand):

```sh
opencode mcp add filesystem --global \
  --env "FILESYSTEM_ROOTS=$HOME/src" \
  -- /home/sa/src/mymcp/.venv/bin/python -m servers.filesystem
```

Alternatively, register from the shell (where `$HOME` *does* expand) — using
the absolute script path means the server also works from any workspace:

```sh
opencode mcp add websearch --global -- \
  /home/sa/src/mymcp/.venv/bin/python /home/sa/src/mymcp/servers/websearch.py
```

Then check the connection:

```sh
opencode mcp list
```

Each new server gets its own entry under `mcp.servers` with the same
interpreter and `-m servers.<name>`.
