import os
import sys
import json
import shutil
import argparse
import mimetypes
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote, quote

HOST = "0.0.0.0"
#HOST = "192.168.100.68"
PORT = 9000


class FileHandler(BaseHTTPRequestHandler):
    root = "./shared"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/" or path == "":
            self.serve_file("index.html", "text/html")
        elif path == "/api/list":
            self.api_list(parsed.query)
        elif path.startswith("/api/download"):
            self.api_download(parsed.query)
        elif path.startswith("/api/info"):
            self.api_info(parsed.query)
        elif path.startswith("/api/thumbnail"):
            pass
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/upload":
            self.api_upload()
        elif path == "/api/delete":
            self.api_delete()
        elif path == "/api/mkdir":
            self.api_mkdir()
        elif path == "/api/rename":
            self.api_rename()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    # --- API ---

    def api_list(self, query):
        params = parse_qs(query)
        rel = params.get("path", [""])[0]
        full = self.safe_path(rel)

        if not full or not os.path.isdir(full):
            self.json_response({"error": "Directory not found"}, 404)
            return

        items = []
        for name in sorted(os.listdir(full)):
            fp = os.path.join(full, name)
            stat = os.stat(fp)
            items.append(
                {
                    "name": name,
                    "is_dir": os.path.isdir(fp),
                    "size": stat.st_size,
                    "mtime": int(stat.st_mtime),
                }
            )
        self.json_response({"path": rel, "items": items})

    def api_download(self, query):
        params = parse_qs(query)
        rel = params.get("path", [""])[0]
        full = self.safe_path(rel)

        if not full or not os.path.isfile(full):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        mime, _ = mimetypes.guess_type(full)
        if not mime:
            mime = "application/octet-stream"

        size = os.path.getsize(full)
        name = os.path.basename(full)
        # HTTP headers are latin-1 only: ASCII fallback + RFC 5987 UTF-8 name
        fallback = (
            name.encode("ascii", "replace").decode().replace('"', "_").replace("\\", "_")
        )
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(size))
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}",
        )
        self.end_headers()

        with open(full, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def api_upload(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.json_response({"error": "Expected multipart/form-data"}, 400)
            return

        boundary = content_type.split("boundary=")[-1].encode()
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Parse multipart manually (no external deps)
        parts = body.split(b"--" + boundary)
        rel_path = ""
        file_data = b""
        file_name = ""

        for part in parts[1:]:
            if part.strip() == b"" or part.strip() == b"--":
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            headers_raw = part[:header_end].decode("utf-8", errors="replace")
            data = part[header_end + 4 :]
            if data.endswith(b"\r\n"):
                data = data[:-2]

            if 'name="path"' in headers_raw:
                rel_path = data.decode("utf-8").strip("/")
            elif 'name="file"' in headers_raw:
                for h in headers_raw.split("\r\n"):
                    if "filename=" in h:
                        file_name = h.split('filename="')[1].rstrip('"')
                file_data = data

        if not file_name:
            self.json_response({"error": "No file provided"}, 400)
            return

        if rel_path:
            target_dir = self.safe_path(rel_path)
        else:
            target_dir = self.safe_path("")

        if not target_dir or not os.path.isdir(target_dir):
            self.json_response({"error": "Invalid path"}, 400)
            return

        filepath = os.path.join(target_dir, file_name)
        with open(filepath, "wb") as f:
            f.write(file_data)

        self.json_response({"ok": True, "message": f"Uploaded {file_name}"})

    def api_delete(self):
        data = self.read_json_body()
        if not data:
            return
        rel = data.get("path", "")
        full = self.safe_path(rel)

        if not full or not os.path.exists(full):
            self.json_response({"error": "Not found"}, 404)
            return

        if os.path.isdir(full):
            shutil.rmtree(full)
        else:
            os.remove(full)
        self.json_response({"ok": True, "message": "Deleted"})

    def api_mkdir(self):
        data = self.read_json_body()
        if not data:
            return
        rel = data.get("path", "")
        full = self.safe_path(rel)

        if not full:
            self.json_response({"error": "Invalid path"}, 400)
            return

        try:
            os.makedirs(full, exist_ok=True)
            self.json_response({"ok": True, "message": "Created"})
        except OSError as e:
            self.json_response({"error": str(e)}, 500)

    def api_rename(self):
        data = self.read_json_body()
        if not data:
            return
        src = self.safe_path(data.get("src", ""))
        dst = self.safe_path(data.get("dst", ""))

        if not src or not os.path.exists(src):
            self.json_response({"error": "Source not found"}, 404)
            return
        if not dst:
            self.json_response({"error": "Invalid destination"}, 400)
            return

        try:
            os.rename(src, dst)
            self.json_response({"ok": True, "message": "Renamed"})
        except OSError as e:
            self.json_response({"error": str(e)}, 500)

    def api_info(self, query):
        params = parse_qs(query)
        rel = params.get("path", [""])[0]
        full = self.safe_path(rel)

        if not full or not os.path.exists(full):
            self.json_response({"error": "Not found"}, 404)
            return

        stat = os.stat(full)
        self.json_response(
            {
                "name": os.path.basename(full),
                "is_dir": os.path.isdir(full),
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
            }
        )

    # --- Helpers ---

    def safe_path(self, rel: str) -> str | None:
        root = os.path.abspath(self.root)
        rel = rel.lstrip("/")
        target = os.path.normpath(os.path.join(root, rel))
        if not target.startswith(root):
            return None
        return target

    def json_response(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            self.json_response({"error": "Invalid JSON"}, 400)
            return None

    def serve_file(self, filename, content_type):
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if not os.path.isfile(filepath):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print(f"[{self.client_address[0]}] {format % args}")


def main():
    parser = argparse.ArgumentParser(description="ShareFile Web Server")
    parser.add_argument(
        "-p", "--port", type=int, default=PORT, help="Port (default 9000)"
    )
    parser.add_argument(
        "-d", "--dir", default="./shared", help="Root directory (default ./shared)"
    )
    args = parser.parse_args()

    root = os.path.abspath(args.dir)
    os.makedirs(root, exist_ok=True)
    FileHandler.root = root

    server = HTTPServer((HOST, args.port), FileHandler)
    print(f"[*] ShareFile server running on http://0.0.0.0:{args.port}")
    print(f"[*] Shared directory: {root}")
    print(f"[*] Open http://localhost:{args.port} in browser")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
