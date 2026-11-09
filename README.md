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

Then check the connection:

```sh
opencode mcp list
```

Each new server gets its own entry under `mcp.servers` with the same
interpreter and `-m servers.<name>`.
