# Smoke-test the local SwarmUI API: session -> txt2img -> img2img, print raw shapes.
import json, time, urllib.request, base64, io, sys

BASE = "http://localhost:7801"

def post(path, body, timeout=600):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def get(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())

sess = post("/API/GetNewSession", {})["session_id"]
print("session:", sess)

t0 = time.time()
res = post("/API/GenerateText2Image", {
    "session_id": sess,
    "model": "woomixAnima_v15",
    "prompt": "cartoon knight helmet, thick black outlines, flat colors, front view, 2d game sprite",
    "negativeprompt": "text, watermark, photo, blurry",
    "width": 512, "height": 512,
    "steps": 16, "cfgscale": 6.0,
    "seed": 12345,
    "images": 1,
})
print("t2i elapsed %.1fs" % (time.time() - t0))
print("keys:", list(res.keys()))
print(json.dumps({k: v for k, v in res.items() if k != "images"}, indent=1)[:800])
imgs = res.get("images")
print("images field:", imgs if not isinstance(imgs, list) else imgs[:3])
if isinstance(imgs, list) and imgs:
    print("first image entry type:", type(imgs[0]), str(imgs[0])[:200])
