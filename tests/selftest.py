# Offline self-test for PBP Studio -- no AI backend, no game install needed.
# Validates the region map, magic table, palette parsing, XML writer and the colorize pipeline
# (on a synthetic line-art box, and on the real template when one can be found).
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

import numpy as np
from PIL import Image, ImageDraw

from regions import REGIONS, TEMPLATE_SIZE
from colorize import parse_palette, colorize_box, palette_words, box_mode
from magics import ui_magics, magic_number, MAGIC_TABLE
from engine import pbp_xml, slugify, gen_size, resolve_template


def test_region_map():
    assert len(REGIONS) == 39, len(REGIONS)
    seen = []
    for r in REGIONS:
        x, y, w, h = r["rect"]
        assert x >= 0 and y >= 0 and x + w <= TEMPLATE_SIZE and y + h <= TEMPLATE_SIZE, r
        assert w > 20 and h > 20, r
        assert r["role"], r
        seen.append((r["part"], r["rect"]))
    assert len({p for p, _ in seen}) == 39, "duplicate part names"
    assert len({t for _, t in seen}) == 39, "duplicate rects"
    roles = {r["role"] for r in REGIONS}
    for needed in ("head", "body", "body_big", "limb", "weapon", "shield", "hudicon", "banner", "bob"):
        assert needed in roles, needed


def test_magics():
    ui = ui_magics()
    assert len(ui) == 26, len(ui)
    assert magic_number("Default Magic") == 1, "default magic must stay index 1 (shipped template)"
    assert magic_number("Lightning") == 3
    assert [n for n, m in MAGIC_TABLE if m == "Paint"] == [26]


def test_palette():
    base, accent = parse_palette("green knight with a red plume")
    assert base == (58, 160, 62), base
    assert accent == (196, 44, 44), accent
    # no color named -> falls back to the pickers
    base2, accent2 = parse_palette("a scary monster", "#112233", "#445566")
    assert base2 == (0x11, 0x22, 0x33) and accent2 == (0x44, 0x55, 0x66)
    assert "green" in palette_words((58, 160, 62), (196, 44, 44))


def test_xml():
    xml = pbp_xml('A&B "quoted"', 3)
    assert 'displayname="A&amp;B &quot;quoted&quot;"' in xml, xml
    assert "<magictype>3</magictype>" in xml
    assert xml.endswith("\r\n")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    assert root.tag == "character" and root.get("displayname") == 'A&B "quoted"'


def test_slug_and_size():
    assert slugify("Green Knight!") == "Green_Knight"
    assert slugify("") == "character"
    w, h = gen_size(149, 216)
    assert w % 8 == 0 and h % 8 == 0 and max(w, h) >= 512


def test_colorize_synthetic():
    """A black-outlined box must get its interior filled with the base color."""
    img = Image.new("RGB", (200, 120), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 15, 180, 105], outline=(0, 0, 0), width=4)
    out, mode = colorize_box(img, "head", (58, 160, 62), (196, 44, 44))
    assert mode == "lineart", mode
    assert tuple(out.getpixel((100, 60))) == (58, 160, 62), out.getpixel((100, 60))
    assert tuple(out.getpixel((5, 5))) == (255, 255, 255), "background must stay white"


def test_colorize_template():
    """When the real template is available, every box must end up colored and untouched outside."""
    try:
        path, src = resolve_template()
    except Exception as e:
        print(f"  (template not available: {e}) -> skipping real-template check")
        return
    base, accent = parse_palette("green knight with a red plume")
    tpl = Image.open(path).convert("RGB")
    assert tpl.size == (TEMPLATE_SIZE, TEMPLATE_SIZE)
    populated = 0
    for r in REGIONS:
        x, y, w, h = r["rect"]
        crop = tpl.crop((x, y, x + w, y + h))
        out, mode = colorize_box(crop, r["role"], base, accent)
        assert out.size == (w, h)
        # at least some pixels of the piece must be non-white (colored or line art)
        px = np.asarray(out.convert("RGB"))
        nonwhite = (px.min(axis=2) < 200).mean()
        assert nonwhite > 0.02, f"{r['part']} looks empty"
        if mode == "lineart":
            colored = ((px.max(axis=2).astype(int) - px.min(axis=2)) > 30).mean()
            if colored > 0.02:
                populated += 1
    assert populated >= 15, f"only {populated} line-art boxes got colored"
    print(f"  real template: {populated} line-art boxes colorized ({src})")


def test_alpha_cutout():
    """Background cut out, enclosed white (eyes, trim) kept, real box keeps its ink."""
    import numpy as np
    from PIL import ImageDraw
    from engine import alpha_from_bg

    im = Image.new("RGB", (80, 80), "white")
    ImageDraw.Draw(im).ellipse((20, 20, 60, 60), fill=(30, 30, 40))
    a = np.array(alpha_from_bg(im))
    assert a[0, 0] == 0 and a[-1, -1] == 0, "background must be transparent"
    assert a[40, 40] == 255, "subject must stay opaque"

    ring = Image.new("RGB", (80, 80), "white")
    d = ImageDraw.Draw(ring)
    d.ellipse((10, 10, 70, 70), fill=(20, 20, 20))
    d.ellipse((30, 30, 50, 50), fill="white")
    a2 = np.array(alpha_from_bg(ring))
    assert a2[40, 40] == 255 and a2[0, 0] == 0, "enclosed white must stay opaque"
    print("  alpha: background cut, enclosed white kept")


def test_subject_palettes():
    """No colour named -> subject scheme; a named colour still wins."""
    from colorize import parse_palette

    assert parse_palette("samurai warrior") == ((43, 47, 82), (201, 162, 39))
    assert parse_palette("samurai in crimson armor")[0] == (168, 24, 44)
    assert parse_palette("a ninja") == ((34, 37, 43), (176, 42, 42))
    print("  palettes: archetypes + explicit override")


def test_settings_migration():
    """An old 0.40 default becomes 0.55 once; a deliberate value is left alone."""
    import json
    import tempfile
    import engine

    old = engine.SETTINGS_FILE, engine.APP_DATA
    try:
        with tempfile.TemporaryDirectory() as d:
            engine.APP_DATA = Path(d)
            engine.SETTINGS_FILE = Path(d) / "settings.json"
            engine.SETTINGS_FILE.write_text(json.dumps({"creativity": 0.40}), encoding="utf-8")
            assert engine.load_settings()["creativity"] == 0.55
            assert json.loads(engine.SETTINGS_FILE.read_text())["creativity"] == 0.55

            engine.SETTINGS_FILE.write_text(json.dumps({"creativity": 0.62}), encoding="utf-8")
            assert engine.load_settings()["creativity"] == 0.62
    finally:
        engine.SETTINGS_FILE, engine.APP_DATA = old
    print("  settings: 0.40 migrates once, 0.62 kept")


def test_wait_ready_rejects_dead_backend():
    """A SwarmUI whose backend errored must raise, not fall through to flat fills."""
    import engine

    client = engine.SwarmClient(url="http://127.0.0.1:1")
    client._post = lambda path, body, timeout=30: {"0": {"status": "errored"}}
    try:
        client.wait_ready(log=lambda m: None, timeout_s=0.3, poll_s=0.05)
    except RuntimeError as e:
        assert "never became ready" in str(e)
    else:
        raise AssertionError("dead backend must not report ready")
    print("  backend: errored state raises")


def test_palette_lock():
    """Off-palette AI output is snapped to the character's own colours."""
    from colorize import palette_lock

    px = np.zeros((32, 32, 3), np.uint8)
    px[:, :16] = (200, 40, 40)
    px[:, 16:] = (30, 120, 60)
    out = np.array(palette_lock(Image.fromarray(px), (30, 120, 60), (200, 40, 40)))
    cols = {tuple(int(v) for v in c) for c in out.reshape(-1, 3)}
    allowed = {(18, 18, 22), (16, 66, 33), (30, 120, 60), (55, 168, 93), (200, 40, 40), (255, 255, 255)}
    assert cols <= allowed, f"invented colours survived: {cols - allowed}"
    assert (30, 120, 60) in cols and (200, 40, 40) in cols
    print("  palette lock: only the character's colours survive")


def test_palette_source():
    """A description without colours must not be treated as green/red."""
    from colorize import has_colors, extract_palette

    assert has_colors("green knight with a red plume")
    assert has_colors("#3fae4a knight")
    assert not has_colors("Taco boy")
    assert not has_colors("a samurai")

    px = np.zeros((32, 32, 3), np.uint8)
    px[:, :16] = (196, 154, 119)
    px[:, 16:] = (75, 31, 23)
    base, accent = extract_palette(Image.fromarray(px))
    assert base in {(196, 154, 119), (75, 31, 23)}
    assert accent != base
    print("  palette source: unnamed colours are left to the AI")


def test_negative_for():
    """Armour is only banned when the description did not ask for it."""
    from colorize import negative_for

    assert "plate armor" not in negative_for("green knight with a red plume")
    assert "plate armor" in negative_for("Taco boy")
    print("  negative prompt: knights only banned when unasked")


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
    print()
    import test_server_guard
    failed += test_server_guard.main()
    print(f"\n{len(tests)} pipeline tests + server guard: {'FAIL' if failed else 'ALL PASS'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
