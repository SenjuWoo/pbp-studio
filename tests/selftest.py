# Offline self-test for PBP Studio -- no AI backend, no game install needed.
# Covers the magic table, XML writer, settings, backend readiness, export and the master-image upload.
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from PIL import Image

from magics import ui_magics, magic_number, MAGIC_TABLE
from engine import pbp_xml, slugify


def test_magics():
    ui = ui_magics()
    assert len(ui) == 26, len(ui)
    assert magic_number("Default Magic") == 1, "default magic must stay index 1 (shipped template)"
    assert magic_number("Lightning") == 3
    assert [n for n, m in MAGIC_TABLE if m == "Paint"] == [26]


def test_xml():
    xml = pbp_xml('A&B "quoted"', 3)
    assert 'displayname="A&amp;B &quot;quoted&quot;"' in xml, xml
    assert "<magictype>3</magictype>" in xml
    assert xml.endswith("\r\n")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    assert root.tag == "character" and root.get("displayname") == 'A&B "quoted"'


def test_slug():
    assert slugify("Green Knight!") == "Green_Knight"
    assert slugify("") == "character"


def test_settings_defaults_and_roundtrip():
    import engine

    old = engine.SETTINGS_FILE, engine.APP_DATA
    try:
        with tempfile.TemporaryDirectory() as d:
            engine.APP_DATA, engine.SETTINGS_FILE = Path(d), Path(d) / "settings.json"
            s = engine.load_settings()
            assert s["backend"] == "klein" and s["steps"] == 40
            engine.save_settings({"backend": "qwen", "seed": None})
            assert json.loads(engine.SETTINGS_FILE.read_text())["backend"] == "qwen"
            assert engine.load_settings()["backend"] == "qwen"
            engine.SETTINGS_FILE.write_text("{not json", encoding="utf-8")
            assert engine.load_settings()["backend"] == "klein", "a corrupt settings file must fall back"
    finally:
        engine.SETTINGS_FILE, engine.APP_DATA = old


def test_wait_ready_rejects_dead_backend():
    """A SwarmUI whose backend errored must raise, not report ready."""
    import engine

    client = engine.SwarmClient(url="http://127.0.0.1:1")
    client._post = lambda path, body, timeout=30: {"0": {"status": "errored"}}
    try:
        client.wait_ready(log=lambda m: None, timeout_s=0.3, poll_s=0.05)
    except RuntimeError as e:
        assert "never became ready" in str(e)
    else:
        raise AssertionError("dead backend must not report ready")


def test_wait_ready_restarts_an_errored_backend_once():
    """SwarmUI's ComfyUI process errors out after an interrupted session; one restart must recover it."""
    import engine

    calls = []

    def fake(path, body, timeout=30):
        calls.append(path)
        if path == "/API/ListBackends":
            return {"0": {"status": "running" if "/API/RestartBackends" in calls else "errored"}}
        if path == "/API/GenerateText2Image":
            return {"images": ["x"]}
        return {"success": True}

    c = engine.SwarmClient(url="http://127.0.0.1:1")
    c.session = lambda: "s"
    c._post = fake
    assert c.wait_ready(log=lambda m: None, timeout_s=5, poll_s=0.01) is True
    assert calls.count("/API/RestartBackends") == 1


def test_export_writes_painting_and_xml():
    import engine
    from test_pipeline import FakeJob

    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
        e = engine.Engine()
        job = FakeJob(d)
        job.say = lambda m: None
        canvas = Image.new("RGBA", (2048, 2048), (0, 0, 0, 0))
        e._export(job, canvas, [("helm", Image.new("RGBA", (234, 332), (255, 0, 0, 255)))],
                  {"output_dir": out, "name": "Taco & Co", "magic": "Poison"})
        assert Image.open(Path(out) / "painting.png").size == (2048, 2048)
        xml = (Path(out) / "pbp.xml").read_text(encoding="utf-8")
        assert 'displayname="Taco &amp; Co"' in xml and f"<magictype>{magic_number('Poison')}</magictype>" in xml
        assert job.state == "done" and Path(job.result["sheet"]).exists()
        assert not list(Path(out).glob("*.tmp")), "temp files must not be left in the watched folder"


def test_master_upload_is_validated_and_stored_as_png():
    import base64
    import engine
    import server

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 200, 30)).save(buf, "JPEG")
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    path = Path(server.save_master(url)["path"])
    try:
        assert path.suffix == ".png" and Image.open(path).size == (40, 30)
        assert path.resolve().is_relative_to(engine.APP_DATA.resolve())
    finally:
        path.unlink(missing_ok=True)
    try:
        server.save_master("data:image/png;base64,AAAA")
    except RuntimeError as e:
        assert "not a readable image" in str(e)
    else:
        raise AssertionError("garbage must be rejected")


def test_list_models_returns_bare_names():
    """A model in a sub-folder is listed with its folder; the backend check must still find it."""
    import engine

    c = engine.SwarmClient(url="http://127.0.0.1:1")
    c.session = lambda: "s"
    c._post = lambda path, body, timeout=30: {"files": [{"name": "Anima/woomixAnima_v15.safetensors"},
                                                       {"name": "flux-2-klein-4b-fp8.safetensors"}]}
    assert c.list_models() == ["woomixAnima_v15", "flux-2-klein-4b-fp8"]


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    import test_server_guard
    failed += test_server_guard.main()
    print(f"\n{len(tests)} selftests + server guard: {'FAIL' if failed else 'ALL PASS'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
