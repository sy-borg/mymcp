# AGENTS.md

## Quick reference for future OpenCode sessions

---

### 1. Virtual environment & dependencies
- Create the isolated environment once:
  ```sh
  python -m venv .venv
  .venv/bin/pip install fastmcp
  ```
- **FastMCP** is the only runtime dependency.  No other packages may be installed system‑wide; use the `.venv` pip.
- **markitdown** is an exception by request ( converts files to Markdown for agents ) and lives only in the `.venv`:
  ```sh
  .venv/bin/pip install "markitdown[all]"
  ```
  The smoke test additionally uses `python-docx` to build a test `.docx`.
- **Websearch** requires an external text browser.  Install one of:
  ```sh
  pacman -S w3m  # or lynx, or links
  ```
  The server will pick the first available browser in the order `WEBSEARCH_BROWSER → lynx → w3m → links`.

### 2. Running a server
The repo contains one server module per MCP server.  Each module defines a `FastMCP` instance named `mcp` and ends with:
```python
if __name__ == "__main__":
    mcp.run()
```
Run any server with the venv Python:
```sh
.venv/bin/python -m servers.<name>
```
Examples:
- Filesystem: `.venv/bin/python -m servers.filesystem`
- Websearch:  `.venv/bin/python -m servers.websearch`
- Memory:     `.venv/bin/python -m servers.memory`
- MarkItDown: `.venv/bin/python -m servers.markitdown`

### 3. Environment variables
| Variable | Purpose | Default (if unset) |
|---|---|---|
| `FILESYSTEM_ROOTS` | Colon‑separated list of root directories the filesystem server may access.  If unset, the current working directory is used. | `.` |
| `WEBSEARCH_BROWSER` | Preferred browser for rendering pages.  The server falls back to `lynx → w3m → links`. | – |
| `MEMORY_PATH` | File path to the JSON graph of the default `global` scope.  Other scopes live as sibling files under a `scopes/` directory next to this path.  If unset, `$XDG_DATA_HOME/mymcp‑memory/graph.json` (~ `~/.local/share/mymcp‑memory/graph.json`) is used. | – |
| `FILESYSTEM_ROOTS` (for `servers.markitdown`) | Allowed input directories for file conversion; same roots as the filesystem server. | `.` |

**Tip:** For tests that touch the memory graph, set `MEMORY_PATH` to a temporary file so the test doesn’t alter the user‑graph.

**Memory scopes:** every memory tool accepts an optional `scope` parameter.  Use the default `global` scope for cross‑project knowledge and a project‑named scope (e.g. the repo name) for project‑specific memory; each scope is its own JSON file under `scopes/`.  `list_scopes` and `delete_scope` manage the set of scopes.

### 4. Opencode registration
OpenCode expects a global config file `~/.config/opencode/opencode.json`.  To register a server manually:
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "filesystem": {
        "type": "local",
        "command": ["/home/sa/src/mymcp/.venv/bin/python", "-m", "servers.filesystem"],
        "cwd": "/home/sa/src/mymcp",
        "environment": {"FILESYSTEM_ROOTS": "{env:HOME}/src"}
      }
    }
  }
}
```
* `{env:NAME}` expands to the environment variable at **registration time**; shell expansions are not performed inside the JSON.

You can also add servers from the shell (which expands `$HOME`):
```sh
opencode mcp add filesystem --global \
  --env "FILESYSTEM_ROOTS=$HOME/src" \
  -- /home/sa/src/mymcp/.venv/bin/python -m servers.filesystem
```
After adding, verify with `opencode mcp list`.

### 5. Smoke tests
The repo ships three minimal tests that exercise each server:
- `smoke_test.py` – filesystem
- `smoke_test_websearch.py` – websearch
- `smoke_test_memory.py` – memory (requires `MEMORY_PATH` set)

Run them with the venv Python:
```sh
.venv/bin/python smoke_test_memory.py
```
For the memory test, set an env var before invoking:
```sh
MEMORY_PATH=/tmp/mymcp_smoke_memory.json .venv/bin/python smoke_test_memory.py
```
The tests delete the temporary graph after finishing.

### 6. Common pitfalls
- **Missing FastMCP**: The venv must contain `fastmcp`.  `pip install fastmcp` in the root of the repo, *not* system‑wide.
- **Websearch rendering**: Without a text browser, `search_web`/`fetch_page` will raise an error.  Ensure `w3m`/`lynx`/`links` is in PATH.
- **Filesystem root escape**: The server refuses paths that resolve outside the configured roots.  Tests validate this behaviour.
- **Atomic writes**: The memory server writes the graph via a temp file and rename.  If the process dies mid‑write, the file remains unchanged.
- **Opencode config path**: If `~/.config/opencode/opencode.json` does not exist, OpenCode will create a default one, but it won’t contain our servers until you add them.

---

**End of AGENTS.md**