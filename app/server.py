# PBP Studio -- local web server (stdlib http.server).
# Serves the UI, wraps the engine as a small JSON API, and streams job status +
# live preview images to the page. Binds to 127.0.0.1 only.
import json
import mimetypes
import os
import socket
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import (APP_DATA, APP_NAME, APP_VERSION, Engine, load_settings, save_settings,
                    find_game_dir, resolve_template, slugify)
from magics import ui_magics, MAGIC_TABLE

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
PORT = int(os.environ.get("PBP_PORT", "8777"))

engine = Engine()
_server_started = threading.Event()


def allowed_roots():
    roots = [APP_DATA.resolve(), STATIC_DIR.resolve()]
    s = load_settings()
    for key in ("output_dir",):
        v = s.get(key)
        if v:
            try:
                roots.append(Path(v).resolve())
            except Exception:
                pass
    t = s.get("template_path")
    if t:
        try:
            roots.append(Path(t).resolve().parent)
        except Exception:
            pass
    return roots


class Handler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"

    # ---------------- helpers ----------------
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionError, OSError):
            pass  # browser closed the tab / refreshed mid-response

    def _err(self, msg, code=400):
        self._json({"error": str(msg)}, code)

    def _file(self, path: Path, cache=False):
        try:
            path = path.resolve()
            if not any(path.is_relative_to(r) for r in allowed_roots()):
                return self._err("path not allowed", 403)
            data = path.read_bytes()
        except Exception as e:
            return self._err(e, 404)
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        try:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=5" if cache else "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionError, OSError):
            pass  # client went away mid-download

    def log_message(self, fmt, *args):
        pass  # quiet by default

    # ---------------- GET ----------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = urllib.parse.parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                return self._file(STATIC_DIR / "index.html")
            if path.startswith("/static/"):
                rel = path[len("/static/"):]
                return self._file(STATIC_DIR / rel, cache=True)
            if path == "/api/status":
                return self._json(engine.status())
            if path == "/api/magics":
                return self._json({"ui": ui_magics(),
                                   "all": [{"num": n, "name": m} for n, m in MAGIC_TABLE]})
            if path == "/api/job":
                job = engine.job
                return self._json(job.status() if job else {"state": "none"})
            if path == "/api/file":
                p = q.get("p", [""])[0]
                if not p:
                    return self._err("missing p")
                return self._file(Path(p))
            return self._err("not found", 404)
        except Exception as e:
            return self._err(e, 500)

    # ---------------- POST ----------------
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            body = {}
        try:
            if parsed.path == "/api/settings":
                s = save_settings(body)
                engine.settings = s
                engine.swarm.url = s.get("swarm_url", engine.swarm.url)
                if body.get("swarm_root") is not None:
                    engine.swarm.root = s.get("swarm_root") or engine.swarm._find_root()
                return self._json({"ok": True, "settings": s})
            if parsed.path == "/api/job":
                job = engine.start_job(body)
                return self._json({"ok": True, "id": job.id})
            if parsed.path == "/api/cancel":
                engine.cancel_job()
                return self._json({"ok": True})
            if parsed.path == "/api/check-backend":
                up = engine.swarm.is_up()
                return self._json({"up": up, "root": engine.swarm.root})
            if parsed.path == "/api/start-backend":
                try:
                    engine.swarm.ensure_up(log=lambda m: None, wait_s=180)
                    return self._json({"up": True})
                except Exception as e:
                    return self._json({"up": False, "error": str(e)})
            if parsed.path == "/api/pick-folder":
                p = pick_folder()
                return self._json({"path": p or ""})
            if parsed.path == "/api/open-folder":
                p = Path(body.get("path", ""))
                if p.exists():
                    if sys.platform == "win32":
                        os.startfile(str(p))  # noqa: S606
                    return self._json({"ok": True})
                return self._err("folder does not exist")
            if parsed.path == "/api/install-to-game":
                return self._json(install_to_game(body))
            if parsed.path == "/api/redownload-template":
                try:
                    settings = load_settings()
                    settings["template_path"] = ""
                    save_settings({"template_path": ""})
                    engine.settings = load_settings()
                    p, src = resolve_template(engine.settings)
                    return self._json({"ok": True, "path": str(p), "source": src})
                except Exception as e:
                    return self._err(e)
            return self._err("not found", 404)
        except Exception as e:
            return self._err(e, 500)


def pick_folder():
    """Native folder picker via PowerShell (runs in the user's session)."""
    if sys.platform != "win32":
        return ""
    script = ("Add-Type -AssemblyName System.Windows.Forms; "
              "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
              "$f.Description = 'Choose the folder the game watches (painting.png + pbp.xml go here)'; "
              "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
              "{ [Console]::Out.Write($f.SelectedPath) }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", script],
                             capture_output=True, timeout=180)
        return out.stdout.decode(errors="ignore").strip()
    except Exception:
        return ""


def install_to_game(body):
    """Copy a finished PBP folder into the game's own data/pbplocal/<slug>/ so it lives with the game."""
    src = Path(body.get("source_dir", ""))
    name = slugify(body.get("name", "") or src.name)
    if not (src / "painting.png").exists():
        raise RuntimeError("source folder has no painting.png")
    game = find_game_dir()
    if not game:
        raise RuntimeError("Castle Crashers install not found")
    dst = Path(game) / "data" / "pbplocal" / name
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("painting.png", "pbp.xml"):
        if (src / f).exists():
            tmp = dst / (f + ".tmp")
            tmp.write_bytes((src / f).read_bytes())
            os.replace(tmp, dst / f)
    return {"ok": True, "installed_to": str(dst)}


def _port_open():
    """Something is listening on our port (fast check; /api/status can be slow on first run)."""
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def _server_answering():
    """True when the listener on the port is PBP Studio itself (static page = fast)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=3) as r:
            return b"PBP Studio" in r.read(4096)
    except Exception:
        return False


def main():
    if not STATIC_DIR.exists():
        print("static/ missing next to server.py", file=sys.stderr)
        sys.exit(2)

    url = f"http://127.0.0.1:{PORT}/"
    if _port_open():
        if _server_answering():
            print(f"{APP_NAME} is already running - opening {url}")
            if "--no-browser" not in sys.argv:
                webbrowser.open(url)
            return
        print(f"{APP_NAME}: port {PORT} is used by another program.\n"
              f"Set PBP_PORT to a different port and run this file again.", file=sys.stderr)
        sys.exit(2)

    class SingleServer(ThreadingHTTPServer):
        # Windows needs this to rebind right after a restart (TIME_WAIT); a real second
        # instance is caught by the probe above instead.
        allow_reuse_address = True

        def handle_error(self, request, client_address):
            # a tab closing mid-response is not an error worth a traceback
            if isinstance(sys.exc_info()[1], (ConnectionError, OSError)):
                return
            super().handle_error(request, client_address)

    try:
        httpd = SingleServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        print(f"{APP_NAME}: could not listen on port {PORT} ({e}).\n"
              f"Set PBP_PORT to a different port and run this file again.", file=sys.stderr)
        sys.exit(2)
    print(f"{APP_NAME} {APP_VERSION} serving at {url}")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
