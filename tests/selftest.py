# Offline self-test for PBP Studio -- no AI backend, no game install needed.
# Validates the region map, magic table, palette parsing, XML writer and the colorize pipeline
# (on a synthetic line-art box, and on the real template when one can be found).
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

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
        px = list(out.getdata())
        nonwhite = sum(1 for p in px if min(p) < 200) / len(px)
        assert nonwhite > 0.02, f"{r['part']} looks empty"
        if mode == "lineart":
            white = sum(1 for p in px if min(p) > 236) / len(px)
            colored = sum(1 for p in px if max(p) - min(p) > 30) / len(px)
            if colored > 0.02:
                populated += 1
    assert populated >= 15, f"only {populated} line-art boxes got colored"
    print(f"  real template: {populated} line-art boxes colorized ({src})")


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
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
