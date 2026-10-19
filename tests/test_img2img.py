# Smoke-test img2img on an actual template crop via the SwarmUI API.
# Confirms param names (initimage / initimagecreativity) and response path resolution.
import json, time, urllib.request, base64, io
from PIL import Image

BASE = "http://localhost:7801"
TEMPLATE = r'C:/Program Files (x86)/Steam/steamapps/common/CastleCrashers/data/pbplocal/violet/painting.png'

def post(path, body, timeout=900):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

sess = post("/API/GetNewSession", {})["session_id"]

im = Image.open(TEMPLATE).convert('RGB')
crop = im.crop((206, 219, 206 + 149, 219 + 216))     # head box #0
crop = crop.resize((384, 512), Image.LANCZOS)        # upscale init toward SDXL-friendly size
buf = io.BytesIO(); crop.save(buf, 'PNG')
b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

t0 = time.time()
res = post("/API/GenerateText2Image", {
    "session_id": sess,
    "model": "woomixAnima_v15",
    "prompt": "green knight helmet with red plume, cartoon, thick black outlines, flat colors, front view, 2d game sprite, white background",
    "negativeprompt": "text, watermark, photo, blurry, background scenery",
    "width": 384, "height": 512,
    "steps": 16, "cfgscale": 6.0,
    "seed": 777,
    "images": 1,
    "initimage": b64,
    "initimagecreativity": 0.72,
})
print("img2img elapsed %.1fs" % (time.time() - t0))
print("response:", json.dumps(res)[:400])
imgs = res.get("images", [])
if imgs:
    rel = imgs[0] if isinstance(imgs[0], str) else imgs[0].get("path", "")
    local = rel.replace("View/", "", 1)
    path = rf"S:/Misc/SwarmUI/Output/{local}"
    print("resolved local file:", path)
    out = Image.open(path)
    print("output size:", out.size)
    out.save(str(__import__('pathlib').Path(__file__).resolve().parent / '_out' / 'img2img_test.png'))
    print("saved scratch img2img_test.png")
