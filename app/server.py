# PBP Studio -- local web server (stdlib http.server).
# Serves the UI, wraps the engine as a small JSON API, and streams job status +
# live preview images to the page. Binds to 127.0.0.1 only.
import json
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

# Only the app's own page may talk to the API. Any web page the user has open can send a
# "simple" POST to 127.0.0.1 (no CORS preflight), and a DNS-rebinding page can reach it under
# a foreign host name, so every request must carry our own Host and, when present, Origin.
_LOCAL_HOSTS = ("127.0.0.1", "localhost")

# Content types for the files the UI loads; anything else is served as raw bytes.
_CTYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
           ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
           ".webp": "image/webp", ".svg": "image/svg+xml", ".json": "application/json",
           ".xml": "application/xml", ".txt": "text/plain", ".ico": "image/x-icon"}


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


def contained(p, roots):
    """Real path of p when it lies inside one of roots, else None.

    Normalise first, then prefix-check against each normalised root: that is the guard that
    stops "..", symlinks and absolute paths from escaping, and the one CodeQL recognises."""
    full = os.path.realpath(str(p))
    for root in roots:
        base = os.path.realpath(str(root))
        if full == base or full.startswith(base.rstrip("\\/") + os.sep):
            return full
    return None


def job_roots():
    """allowed_roots() plus the folder the last finished job exported to (it may be a folder the
    user typed for that run without saving it as the default)."""
    roots = allowed_roots()
    job = engine.job
    export_dir = (getattr(job, "result", None) or {}).get("export_dir") if job else None
    if export_dir:
        roots.append(Path(export_dir))
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

    def _local_request(self):
        """True when the request comes from the app's own page (see _LOCAL_HOSTS)."""
        allowed = {f"{h}:{PORT}" for h in _LOCAL_HOSTS}
        if (self.headers.get("Host") or "").lower() not in allowed:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.lower() in {f"http://{a}" for a in allowed}

    def _file(self, path: Path, cache=False):
        try:
            safe = contained(path, allowed_roots())
            if safe is None:
                return self._err("path not allowed", 403)
            with open(safe, "rb") as fh:
                data = fh.read()
        except Exception as e:
            return self._err(e, 404)
        ctype = _CTYPES.get(os.path.splitext(safe)[1].lower(), "application/octet-stream")
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
        if not self._local_request():
            return self._err("forbidden: request did not come from the PBP Studio page", 403)
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
        if not self._local_request():
            return self._err("forbidden: request did not come from the PBP Studio page", 403)
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
            if parsed.path == "/api/master":
                return self._json(save_master(body.get("data", "")))
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
                # folders only (os.startfile on a file would run it), and only the app's own ones
                safe = contained(body.get("path", ""), job_roots())
                if safe is None:
                    return self._err("only the output folder or a PBP Studio folder can be opened", 403)
                if os.path.isdir(safe):
                    if sys.platform == "win32":
                        os.startfile(safe)  # noqa: S606
                    return self._json({"ok": True})
                return self._err("folder does not exist")
            if parsed.path == "/api/install-to-game":
                try:
                    return self._json(install_to_game(body))
                except PermissionError as e:
                    return self._err(e, 403)
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


def save_master(data_url):
    """Store a user-supplied character image (data URL) as a PNG a job can use as its master design."""
    import base64
    import io
    import time

    from PIL import Image

    try:
        img = Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[-1]))).convert("RGB")
    except Exception:
        raise RuntimeError("that file is not a readable image")
    img.thumbnail((1536, 1536))
    dst = APP_DATA / "master"
    dst.mkdir(parents=True, exist_ok=True)
    path = dst / f"{time.strftime('%Y%m%d-%H%M%S')}.png"
    img.save(path, "PNG")
    return {"path": str(path)}


def install_to_game(body):
    """Copy a finished PBP folder into the game's own data/pbplocal/<slug>/ so it lives with the game.

    The source must be the last job's export folder or another PBP Studio folder, and the
    destination must stay inside data/pbplocal."""
    src = contained(body.get("source_dir", ""), job_roots())
    if src is None:
        raise PermissionError("source folder is not a PBP Studio output folder")
    name = slugify(body.get("name", "") or os.path.basename(src))
    if not os.path.isfile(os.path.join(src, "painting.png")):
        raise RuntimeError("source folder has no painting.png")
    game = find_game_dir()
    if not game:
        raise RuntimeError("Castle Crashers install not found")
    base = Path(game) / "data" / "pbplocal"
    dst = contained(base / name, [base])
    if dst is None or dst == os.path.realpath(base):
        raise PermissionError("character name does not make a folder inside data/pbplocal")
    os.makedirs(dst, exist_ok=True)
    for f in ("painting.png", "pbp.xml"):
        sf = os.path.join(src, f)
        if os.path.isfile(sf):
            tmp = os.path.join(dst, f + ".tmp")
            with open(sf, "rb") as fin, open(tmp, "wb") as fout:
                fout.write(fin.read())
            os.replace(tmp, os.path.join(dst, f))
    return {"ok": True, "installed_to": dst}


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
