# Test: hybrid pipeline = procedural flat colorize -> AI detail img2img (low creativity)
# -> multiply template lines back. Compares creativity 0.40 vs 0.60 on key boxes.
import sys, io, json, time, urllib.request, base64
from PIL import Image, ImageDraw

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'app'))
from regions import REGIONS
from colorize import colorize_box, parse_palette, detail_prompt, multiply_lines, overlay_edges

BASE = "http://localhost:7801"
TPL = r'C:/Program Files (x86)/Steam/steamapps/common/CastleCrashers/data/pbplocal/violet/painting.png'
import pathlib
OUT_DIR = pathlib.Path(__file__).resolve().parent / "_out"
OUT_DIR.mkdir(exist_ok=True)
OUT = str(__import__('pathlib').Path(__file__).resolve().parent / '_out' / 'hybrid_test.png')
DESIGN = "green knight with a red plume"

def post(path, body, timeout=600):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

sess = post("/API/GetNewSession", {})["session_id"]
tpl = Image.open(TPL).convert("RGB")
base, accent = parse_palette(DESIGN)

def ai_detail(init_img, role, creativity, steps=20):
    w, h = init_img.size
    sc = 640 / max(w, h)
    gw, gh = max(64, int(w * sc) // 8 * 8), max(64, int(h * sc) // 8 * 8)
    up = init_img.resize((gw, gh), Image.LANCZOS)
    buf = io.BytesIO(); up.save(buf, "PNG")
    prompt = detail_prompt(DESIGN, role, "forest green armor, red accents, gold trim")
    body = {"session_id": sess, "model": "woomixAnima_v15", "prompt": prompt,
            "negativeprompt": "text, watermark, photo, realistic, 3d, blurry, background scenery, "
                              "multiple objects, collage, grid, extra objects, hands, holding, frame, border, "
                              "dark background, sketch, uncolored",
            "width": gw, "height": gh, "steps": steps, "cfgscale": 6.0, "seed": 555, "images": 1,
            "initimage": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
            "initimagecreativity": creativity}
    t0 = time.time()
    res = post("/API/GenerateText2Image", body)
    rel = str(res["images"][0]).replace("View/", "", 1)
    path = rf"S:/Misc/SwarmUI/Output/{rel}"
    for _ in range(40):
        try:
            img = Image.open(path); img.load(); break
        except Exception:
            time.sleep(0.4)
    else:
        raise RuntimeError("missing " + path)
    return img.convert("RGB").resize((w, h), Image.LANCZOS), time.time() - t0

tests = [(0, "head"), (7, "body"), (15, "body_big"), (21, "limb"), (36, "hudicon"), (37, "banner")]
rows = []
for idx, role in tests:
    x, y, w, h = REGIONS[idx]["rect"]
    crop = tpl.crop((x, y, x + w, y + h))
    flat, mode = colorize_box(crop, role, base, accent)
    for crea in (0.40, 0.60):
        ai, dt = ai_detail(flat, role, crea)
        final = multiply_lines(ai, crop) if mode == "lineart" else overlay_edges(ai, crop)
        rows.append((idx, role, crea, mode, flat, ai, final, dt))
        print(f"#{idx} {role} crea={crea} {dt:.1f}s")

cw = 220
sheet = Image.new("RGB", (cw * 4, 260 * len(rows)), (26, 26, 30))
d = ImageDraw.Draw(sheet)
for row, (idx, role, crea, mode, flat, ai, final, dt) in enumerate(rows):
    for col, src in enumerate((flat, ai, final)):
        sc = min((cw - 12) / src.width, 235 / src.height)
        th = src.resize((max(1, int(src.width * sc)), max(1, int(src.height * sc))))
        sheet.paste(th, (col * cw + 6, row * 260 + 20))
    d.text((6, row * 260 + 3), f"#{idx} {role} crea {crea} ({dt:.0f}s)  flat | ai | final", fill=(140, 240, 140))
sheet.save(OUT)
print("saved", OUT)
