# Test: line-preserving AI colorization of the official template boxes.
# For line-art roles: img2img at moderate creativity, then multiply the ORIGINAL line art
# back on top so the game's exact geometry/outlines survive no matter what the model draws.
import sys, io, json, time, urllib.request, base64
from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'app'))
from regions import REGIONS

BASE = "http://localhost:7801"
TPL = r'C:/Program Files (x86)/Steam/steamapps/common/CastleCrashers/data/pbplocal/violet/painting.png'
import pathlib
OUT_DIR = pathlib.Path(__file__).resolve().parent / "_out"
OUT_DIR.mkdir(exist_ok=True)
OUT = str(__import__('pathlib').Path(__file__).resolve().parent / '_out' / 'colorize_test.png')

def post(path, body, timeout=600):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

sess = post("/API/GetNewSession", {})["session_id"]
tpl = Image.open(TPL).convert("RGB")
DESIGN = "green knight with a red plume, forest green armor, gold trim"

def gen(box_idx, creativity, prompt_extra="", steps=20):
    r = REGIONS[box_idx]
    x, y, w, h = r['rect']
    crop = tpl.crop((x, y, x + w, y + h))
    sc = 640 / max(w, h)
    gw, gh = int(w * sc) // 8 * 8, int(h * sc) // 8 * 8
    init = crop.resize((gw, gh), Image.LANCZOS)
    buf = io.BytesIO(); init.save(buf, "PNG")
    body = {
        "session_id": sess, "model": "woomixAnima_v15",
        "prompt": (f"{DESIGN}, coloring book page being colored in, painting over line art, "
                   f"flat colors, cel shading, clean white background{', ' + prompt_extra if prompt_extra else ''}"),
        "negativeprompt": "text, watermark, photo, realistic, 3d, blurry, scenery, background, "
                          "multiple objects, collage, grid, extra objects, dark background",
        "width": gw, "height": gh, "steps": steps, "cfgscale": 6.0, "seed": 4242, "images": 1,
        "initimage": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
        "initimagecreativity": creativity,
    }
    t0 = time.time()
    res = post("/API/GenerateText2Image", body)
    rel = str(res["images"][0]).replace("View/", "", 1)
    path = rf"S:/Misc/SwarmUI/Output/{rel}"
    for _ in range(30):
        try:
            img = Image.open(path); break
        except Exception:
            time.sleep(0.4)
    else:
        raise RuntimeError("file never appeared: " + path)
    img = img.convert("RGB").resize((w, h), Image.LANCZOS)
    # line-preserving composite: multiply with original line art (lines -> black, white -> gen)
    gray = crop.convert("L")
    # only preserve where template is actually line art (mostly white + black lines)
    px = list(gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata())
    white = sum(1 for v in px if v > 235) / len(px)
    if white > 0.65:
        lines = Image.merge("RGB", (gray, gray, gray))
        final = ImageChops.multiply(img, lines)
    else:
        final = img  # limb boxes: pre-filled art, keep model's repaint
    return final, img, time.time() - t0, gw, gh

tests = [
    (0, 0.45, "helmet close-up"),
    (0, 0.60, "helmet close-up"),
    (0, 0.75, "helmet close-up"),
    (7, 0.60, "torso front view"),
    (15, 0.60, "beefy torso"),
    (21, 0.65, "arm piece"),
]
results = []
for idx, crea, extra in tests:
    img, raw, dt, gw, gh = gen(idx, crea, extra)
    results.append((idx, crea, img, raw, dt, gw, gh))
    print(f"#{idx} crea={crea} {gw}x{gh} in {dt:.1f}s")

# contact sheet: one row per test, showing template | generated | final
cell_w = 240
sheet = Image.new("RGB", (cell_w * 3, 260 * len(results)), (25, 25, 28))
d = ImageDraw.Draw(sheet)
for row, (idx, crea, img, raw, dt, gw, gh) in enumerate(results):
    r = REGIONS[idx]; x, y, w, h = r['rect']
    crop = tpl.crop((x, y, x + w, y + h))
    for col, src in enumerate((crop, raw, img)):
        sc = min((cell_w - 10) / src.width, 240 / src.height)
        th = src.resize((max(1, int(src.width*sc)), max(1, int(src.height*sc))))
        sheet.paste(th, (col*cell_w + 5, row*260 + 16))
    d.text((5, row*260 + 2), f"#{idx} {r['part']} crea {crea}  [{dt:.0f}s]  tpl | raw | lines", fill=(150, 240, 150))
sheet.save(OUT)
print("saved", OUT)
