# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

ShareFile is a minimal web-based file manager: a single Python stdlib HTTP server (`server.py`) serving a single-page vanilla-JS/HTML frontend (`index.html`). No external dependencies, no build step, no framework. Requires Python 3.13 (per `pyproject.toml` / `.python-version`).

## Running

The project is run through uv (use `uv run`, not bare `python`):

```bash
uv run server.py -d ./shared -p 9000
```

Then open `http://localhost:9000`. `-d` sets the shared root directory (default `./shared`, created if missing), `-p` sets the port (default `9000`). The server binds `0.0.0.0` (`HOST` constant in `server.py`) and has no authentication, so it is reachable from the LAN by design.

There is no test suite, linter config, or CI in this repo. `main.py` is an unrelated uv scaffold stub (`sharefile` console script), not part of the actual app — the app entry point is `server.py`.

## Architecture

Everything is two files:

- **`server.py`** — `FileHandler(BaseHTTPRequestHandler)` routes requests by hand in `do_GET`/`do_POST` (no router/framework). Single-threaded `HTTPServer`, so one slow request blocks others. REST-ish JSON API under `/api/*`:
  - `GET /api/list?path=` — directory listing
  - `GET /api/download?path=` — file download (streamed)
  - `GET /api/info?path=` — file/dir metadata
  - `POST /api/upload` — multipart upload with `path` and `file` fields, parsed manually (no `cgi`/`email` module — hand-rolled boundary splitting; the whole body is read into memory)
  - `POST /api/delete`, `/api/mkdir`, `/api/rename` — JSON body requests (parsed via `read_json_body()`)
  - `/api/thumbnail` is routed but unimplemented (`pass`)
  - `/` serves `index.html` via `serve_file()`, resolved relative to `server.py`'s directory (not the shared root)
- **`index.html`** — the entire frontend: markup, CSS, and JS in one file. `api()` is a thin `fetch` + `.json()` wrapper used for JSON calls; uploads (file picker and drag-and-drop) build `FormData` and call `fetch("/api/upload")` directly, once per file. UI state is the global `currentPath`; `loadDir()`/`refresh()` re-render the listing after each mutation.

### Path safety

Filesystem access goes through `FileHandler.safe_path()`, which resolves a request-relative path against `self.root` and rejects anything that normalizes outside of it. Any new endpoint touching the filesystem must route through this method — do not construct paths from user input directly.

Known gaps to keep in mind when touching this area:
- `safe_path()` uses a plain `startswith(root)` check, so a sibling directory sharing the root's prefix (e.g. `shared2` next to `shared`) is not rejected.
- `api_upload` joins the client-supplied multipart `filename` onto the target directory with `os.path.join` without re-checking it through `safe_path()`.

### Adding an API endpoint

1. Add the route in `do_GET`/`do_POST`'s if/elif chain.
2. Implement `api_<name>` following the existing pattern: resolve untrusted input via `safe_path()`, respond via `json_response()` for JSON (errors are `{"error": ...}`, success typically `{"ok": true, ...}`) or stream manually for binary/file responses (see `api_download`).
3. Wire up the corresponding call in `index.html` through the `api()` helper; the frontend checks `r.error` and shows it with `toast()`.
