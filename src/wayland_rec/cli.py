import argparse
import html
import json
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from wayland_rec.cli import parse_args, run_session

OUTPUT_DIR = Path.cwd() / "recordings"
RECORD_LOCK = threading.Lock()
STATUS = {"state": "idle", "last_file": "", "error": ""}

HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Wayland Session Recorder — Local QA Dashboard</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
    label { display: block; margin-top: 1rem; font-weight: 600; }
    input { width: 100%; padding: 0.5rem; margin-top: 0.25rem; box-sizing: border-box; }
    button { margin-top: 1.25rem; padding: 0.65rem 1.25rem; font-size: 1rem; cursor: pointer; }
    .box { margin-top: 1.5rem; padding: 1rem; background: #f4f4f6; border-radius: 6px; }
    video { width: 100%; max-height: 480px; margin-top: 1rem; background: #000; border-radius: 6px; }
  </style>
</head>
<body>
  <h1>Wayland &amp; PipeWire Session Recorder</h1>
  <p>Launch an isolated headless Firefox session and capture video + audio to MP4.</p>
  <form method="POST" action="/record">
    <label>Target URL (http/https)
      <input type="url" name="url" placeholder="https://ubuntu.com" required>
    </label>
    <label>Duration (seconds, 3–300)
      <input type="number" name="duration" value="15" min="3" max="300" required>
    </label>
    <label>Output Filename
      <input type="text" name="filename" value="capture.mp4" pattern="[A-Za-z0-9._-]+" required>
    </label>
    <button type="submit">Start Headless Recording</button>
  </form>
  <div class="box" id="status-box">
    <strong>Status:</strong> <span id="status-text">__STATE__</span>
    <div id="player-area">__DETAILS__</div>
  </div>
  <script>
    async function pollStatus() {
      try {
        const res = await fetch('/status');
        const data = await res.json();
        document.getElementById('status-text').textContent = data.state;
        const area = document.getElementById('player-area');
        if (data.state === 'completed' && data.last_file) {
          const url = '/files/' + encodeURIComponent(data.last_file) + '?t=' + Date.now();
          area.innerHTML =
            '<p>Recorded: <a href="' + url + '" download>' + data.last_file + '</a></p>' +
            '<video controls autoplay playsinline src="' + url + '"></video>';
          return;
        } else if (data.state === 'error') {
          area.textContent = 'Error: ' + data.error;
          return;
        }
      } catch (e) {}
      setTimeout(pollStatus, 1500);
    }
    if (document.getElementById('status-text').textContent.startsWith('recording')) {
      setTimeout(pollStatus, 1500);
    }
  </script>
</body>
</html>
"""


def _run_recording_job(url: str, duration: float, out_path: Path) -> None:
    global STATUS
    try:
        with tempfile.TemporaryDirectory(prefix="wayland_rec_ff_") as prof:
            Path(prof, "user.js").write_text(
                'user_pref("media.autoplay.default", 0);\n'
                'user_pref("media.autoplay.blocking_policy", 0);\n'
            )
            cmd = f"firefox --no-remote --profile {prof} --kiosk {url}"
            args = parse_args([
                "--cmd", cmd,
                "--out", str(out_path),
                "--duration", str(duration),
            ])
            run_session(args)
        STATUS = {"state": "completed", "last_file": out_path.name, "error": ""}
    except Exception as exc:
        STATUS = {"state": "error", "last_file": "", "error": str(exc)}
    finally:
        RECORD_LOCK.release()


class RecorderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            details = ""
            if STATUS["last_file"]:
                fn = html.escape(STATUS["last_file"])
                details = (
                    f'<p>Recorded: <a href="/files/{fn}" download>{fn}</a></p>'
                    f'<video controls autoplay playsinline src="/files/{fn}"></video>'
                )
            elif STATUS["error"]:
                details = f'Error: {html.escape(STATUS["error"])}'
            page = HTML_PAGE.replace("__STATE__", html.escape(STATUS["state"])).replace("__DETAILS__", details)
            self._send_bytes(page.encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/status":
            self._send_bytes(json.dumps(STATUS).encode("utf-8"), "application/json")
        elif parsed.path.startswith("/files/"):
            name = Path(parsed.path).name
            file_path = OUTPUT_DIR / name
            if file_path.is_file():
                self._send_bytes(file_path.read_bytes(), "video/mp4")
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Recording not found")
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        global STATUS
        if self.path != "/record":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(body)

        url = form.get("url", [""]).strip()
        duration = float(form.get("duration", ["15"]))
        filename = Path(form.get("filename", ["capture.mp4"])).name

        parsed_url = urlparse(url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid HTTP/HTTPS URL")
            return
        if not (3 <= duration <= 300):
            self.send_error(HTTPStatus.BAD_REQUEST, "Duration must be between 3 and 300 seconds")
            return
        if not filename.endswith(".mp4"):
            filename += ".mp4"

        if not RECORD_LOCK.acquire(blocking=False):
            self.send_error(HTTPStatus.CONFLICT, "A recording is already in progress")
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / filename
        STATUS = {"state": f"recording ({url})...", "last_file": "", "error": ""}

        thread = threading.Thread(target=_run_recording_job, args=(url, duration, out_path), daemon=True)
        thread.start()

        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.end_headers()

    def _send_bytes(self, data: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(prog="wayland-rec-ui", description="Local web UI for wayland-rec.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), RecorderHandler)
    print(f"Serving local QA recorder UI at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()

