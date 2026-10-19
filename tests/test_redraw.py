# Prototype: can a stronger AI pass produce a real "samurai" helmet inside the
# official head box, and does white-keying give us usable alpha?
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from PIL import Image, ImageDraw  # noqa: E402
from engine import SwarmClient, gen_size  # noqa: E402
from colorize import colorize_box  # noqa: E402

OUT = Path(__file__).resolve().parent / "_out"
OUT.mkdir(exist_ok=True)

TPL = Path(r"C:/Program Files (x86)/Steam/steamapps/common/CastleCrashers/data/pbplocal/violet/painting.png")
BOX = (206, 219, 149, 216)  # helm
DESIGN = ("samurai warrior, dark indigo lacquered armor, golden crest on the helmet, "
          "red cords, thick black outlines, flat cel shading, cartoon game sprite")

base = Image.open(TPL).convert("RGBA")
x, y, w, h = BOX
crop = base.crop((x, y, x + w, y + h))
rgb = crop.convert("RGB")
alpha = crop.getchannel("A")

flat, mode = colorize_box(rgb, "head", (38, 42, 74), (196, 62, 48))
print("colorize mode:", mode)

sw = SwarmClient()
sw.ensure_up(log=print, wait_s=180)
gw, gh = gen_size(w, h)

def key_white(im, thr=232):
    # near-white -> transparent; everything else opaque, feathered by luminance
    px = im.convert("RGB").load()
    a = Image.new("L", im.size, 0)
    ap = a.load()
    for j in range(im.size[1]):
        for i in range(im.size[0]):
            r, g, b = px[i, j]
            m = min(r, g, b)
            ap[i, j] = 0 if m >= thr else 255
    return a

rows = [("template", rgb), ("flat", flat)]
for crea in (0.55, 0.70):
    init = flat.resize((gw, gh), Image.LANCZOS)
    ai = sw.generate(DESIGN, gw, gh, seed=1234, init_png=init, creativity=crea, steps=20,
                     negative="multiple objects, multiple views, collage, grid, duplicated parts, "
                              "text, watermark, full scene, background scenery")
    ai = ai.convert("RGB").resize((w, h), Image.LANCZOS)
    keyed = ai.convert("RGBA")
    keyed.putalpha(key_white(ai))
    rows.append((f"ai {crea:.2f}", ai))
    rows.append((f"keyed {crea:.2f}", keyed))

# contact sheet on a checkerboard so transparency is visible
cw, ch = w * 2, h * 2
sheet = Image.new("RGB", (cw * len(rows), ch + 24), (30, 30, 34))
d = ImageDraw.Draw(sheet)
for i, (label, im) in enumerate(rows):
    cell = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for yy in range(0, ch, 16):
        for xx in range(0, cw, 16):
            if (xx // 16 + yy // 16) % 2:
                d.rectangle([i * cw + xx, yy, i * cw + xx + 15, yy + 15], fill=(70, 70, 78))
    cell.alpha_composite(im.convert("RGBA").resize((cw, ch), Image.LANCZOS))
    sheet.paste(cell, (i * cw, 0))
    d.text((i * cw + 6, ch + 6), label, fill=(230, 230, 230))
path = OUT / "redraw_head.png"
sheet.save(path)
print("saved", path)
