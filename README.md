# ShareFile - Web File Manager

Web-based file manager. Open in browser, manage files on server.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python 3.13 (uv installs it automatically from `.python-version` if missing)
- No external dependencies (uses only stdlib)

## Quick Start

```bash
uv run server.py -d ./shared -p 9000
```

Then open `http://localhost:9000` in browser.

From another machine: `http://<server_ip>:9000`

- `-d` — directory to share (default: `./shared`)
- `-p` — port (default: `9000`)

## Features

- Browse directories
- Upload files (button or drag-and-drop)
- Download files
- Create folders
- Rename files/folders
- Delete files/folders

## Architecture

- `server.py` — HTTP server + REST API
- `index.html` — web interface (served by the server)
