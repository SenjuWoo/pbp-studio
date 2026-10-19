# Regression test for the server's file guard: the UI must be servable, and only
# APP_DATA + app/static may be read. Spawns the real server on an ephemeral port.
import http.client
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from engine import APP_DATA  # noqa: E402  (same root the guard allows)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**__import__("os").environ, "PBP_PORT": str(port)}
    proc = subprocess.Popen([sys.executable, str(APP / "server.py"), "--no-browser"],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def get(path):
        with urllib.request.urlopen(base + path, timeout=10) as r:
            return r.status, r.read()

    def code(path):
        try:
            return get(path)[0]
        except urllib.error.HTTPError as e:
            return e.code

    checks = []
    try:
        for _ in range(60):
            try:
                get("/api/status")
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise SystemExit("server did not start")

        st, body = get("/")
        checks.append(("ui served", st == 200 and b"<html" in body.lower() and len(body) > 4000))
        checks.append(("js served", get("/static/app.js")[0] == 200))
        checks.append(("css served", get("/static/style.css")[0] == 200))
        checks.append(("status json", json.loads(get("/api/status")[1])["app"]["name"] == "PBP-Studio"))

        # a file under an allowed root is readable; anything else is refused
        APP_DATA.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=APP_DATA, suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 2048)
            inside = Path(f.name)
        try:
            checks.append(("allowed root readable", get("/api/file?p=" + urllib.parse.quote(str(inside)))[1].startswith(b"\x89PNG")))
        finally:
            inside.unlink(missing_ok=True)

        checks.append(("outside path blocked", code("/api/file?p=" + urllib.parse.quote(r"C:/Windows/win.ini")) == 403))

        # raw request: urllib would normalise the ".." away before sending
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/static/../server.py")
        checks.append(("traversal blocked", conn.getresponse().status in (403, 404)))
        conn.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    bad = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    print(f"{len(checks) - len(bad)}/{len(checks)} passed")
    return 1 if bad else 0


def test_server_guard():
    """pytest entry point: the guard suite spawns the real server on a free port."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
