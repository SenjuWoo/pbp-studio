# Reproducible settings sweep for PBP Studio. Fixed designs + seeds, objective metrics, contact sheets.
#   py -3 tools/tune.py master  -> Anima master-design grid (sampler, scheduler, CFG, steps, prompt)
#   py -3 tools/tune.py klein   -> Flux.2 Klein piece grid (steps, canvas) on the best masters
# Results: %LOCALAPPDATA%\PBP-Studio\tune\<stage>\results.json + sheet_*.png. Summary: docs/TUNING.md.
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import engine     # noqa: E402
import pipeline   # noqa: E402

OUT = engine.APP_DATA / "tune"
DESIGNS = {   # deliberately different: armoured human, food head, robot, animal
    "knight": "red-haired knight girl with a white ribbon, green eyes, silver armor with a blue tabard with a gold cross",
    "taco": "taco boy: his head is a folded taco shell filled with beef, lettuce and salsa; brown gloves and boots",
    "robot": "robot knight with chrome armor, glowing blue lights and a red cape",
    "cat": "cute orange cat knight with leather armor and a round wooden shield",
}
SEEDS = {"knight": 11, "taco": 22, "robot": 33, "cat": 44}
NEG_OLD = pipeline.NEG
NEG_OFFICIAL = ("worst quality, low quality, score_1, score_2, score_3, artist name, blurry, jpeg artifacts, "
                "chromatic aberration, " + pipeline.NEG)


def prompt(design, variant):
    if variant == "plain":                # 0.8.0 prompt
        return (f"{design}, full body, chibi proportions, standing, three-quarter view, holding a weapon, "
                f"{pipeline.STYLE}, single character"), NEG_OLD
    if variant == "quality":              # + the model card's quality prefix and negative
        return ("masterpiece, best quality, score_7, safe, " + prompt(design, "plain")[0]), NEG_OFFICIAL
    # tags first, then two natural-language sentences (model card format) = the app's prompt since 0.9.0
    return pipeline.master_prompt(design), pipeline.MASTER_NEG


# ---------------------------------------------------------------- metrics
def metrics(img):
    """bg: white border share; ok: one clean figure; outline: dark share of the silhouette rim;
    flat: mean luminance gradient inside the figure (lower = flatter cel shading)."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    border = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
    bg = float((border.min(1) >= 235).mean())
    sprite = pipeline.clean(pipeline.cut_out(img))
    why = pipeline.check(sprite)
    m = np.asarray(sprite.getchannel("A")) > 128
    ring = m & ~ndimage.binary_erosion(m, iterations=3)
    outline = float((a[ring].max(1) < 80).mean()) if ring.any() else 0.0
    inner = ndimage.binary_erosion(m, iterations=6)
    lum = a.mean(2)
    g = np.hypot(ndimage.sobel(lum, 0), ndimage.sobel(lum, 1))
    flat = float(g[inner].mean()) if inner.any() else 999.0
    return {"bg": round(bg, 3), "ok": why == "", "why": why, "outline": round(outline, 3),
            "flat": round(flat, 1), "cover": round(float(m.mean()), 3)}


def sheet(rows, path, cell=256):
    """rows: [(label, [images...])] -> one labelled contact sheet."""
    cols = max(len(r[1]) for r in rows)
    out = Image.new("RGB", (cols * cell + 260, len(rows) * cell), "white")
    d = ImageDraw.Draw(out)
    for i, (label, ims) in enumerate(rows):
        d.text((6, i * cell + 6), label, fill=(0, 0, 0))
        for j, im in enumerate(ims):
            out.paste(im.convert("RGB").resize((cell, cell)), (260 + j * cell, i * cell))
    out.save(path)


def agg(rs):
    k = lambda f: round(float(np.mean([r[f] for r in rs])), 3)
    return {"n": len(rs), "ok": k("ok"), "bg": k("bg"), "outline": k("outline"), "flat": k("flat"), "sec": k("sec")}


# ---------------------------------------------------------------- stages
def run_grid(sw, stage, configs):
    d = OUT / stage
    d.mkdir(parents=True, exist_ok=True)
    results, rows = [], []
    for cfg in configs:
        ims = []
        for name, design in DESIGNS.items():
            p, neg = prompt(design, cfg["prompt"])
            t = time.time()
            img = sw.render(p, 1024, 1024, pipeline.ANIMA_MODEL, cfg["steps"], cfg["cfg"], SEEDS[name], neg,
                            sampler=cfg["sampler"], scheduler=cfg["scheduler"])
            r = dict(cfg, design=name, sec=round(time.time() - t, 1), **metrics(img))
            img.save(d / f"{cfg['id'].replace('/', '-')}_{name}.png")
            results.append(r)
            ims.append(img)
            print(json.dumps(r), flush=True)
        rows.append((cfg["id"], ims))
    sheet(rows, d / "sheet.png")
    summary = {c["id"]: agg([r for r in results if r["id"] == c["id"]]) for c in configs}
    json.dump({"results": results, "summary": summary}, open(d / "results.json", "w"), indent=1)
    for k, v in sorted(summary.items(), key=lambda kv: (-kv[1]["ok"], -kv[1]["outline"], kv[1]["flat"])):
        print(f"{k:40} {v}")
    return summary


def master_stage(sw, which):
    if which == "sampler":       # step 1: sampler x scheduler at the model card's middle CFG/steps
        samplers = ["er_sde", "rk_beta", "dpmpp_2m_sde_gpu", "euler_ancestral"]
        scheds = ["beta", "simple", "beta57"]
        cfgs = [dict(id=f"{s}/{h}", sampler=s, scheduler=h, cfg=3.5, steps=36, prompt="plain")
                for s, h in itertools.product(samplers, scheds)]
    elif which == "cfg":         # step 2: CFG x steps on the chosen sampler/scheduler
        s, h = sys.argv[3], sys.argv[4]
        cfgs = [dict(id=f"cfg{c}/st{n}", sampler=s, scheduler=h, cfg=c, steps=n, prompt="plain")
                for c, n in itertools.product([3.0, 4.0, 5.0], [30, 40])]
    else:                        # step 3: prompt format
        s, h, c, n = sys.argv[3], sys.argv[4], float(sys.argv[5]), int(sys.argv[6])
        cfgs = [dict(id=f"prompt-{v}", sampler=s, scheduler=h, cfg=c, steps=n, prompt=v)
                for v in ("plain", "quality", "tags+prose")]
    return run_grid(sw, f"master-{which}", cfgs)


def klein_stage(sw):
    """Steps x canvas on the 4 best masters: first-try gate pass, colour fidelity to the master, speed."""
    d = OUT / "klein"
    d.mkdir(parents=True, exist_ok=True)
    masters = {n: Image.open(p).convert("RGB") for n, p in
               ((n, OUT / "best_masters" / f"{n}.png") for n in DESIGNS)}
    parts = ["helm5", "helm3", "helm4", "helm.B", "bodyref", "sword", "backoffb"]
    results, rows = [], []
    for steps, canvas in [(4, 1024), (6, 1024), (8, 1024), (8, 768)]:
        for name, master in masters.items():
            ims = []
            for k, part in enumerate(parts):
                kind, _, _, (gw, gh) = pipeline.SPECS[part]
                if canvas != 1024:
                    gw, gh = gw * canvas // 1024 // 16 * 16, gh * canvas // 1024 // 16 * 16
                t = time.time()
                img = sw.render(pipeline.edit_prompt(part), gw, gh, pipeline.EDIT_MODELS["klein"], steps, 1.0,
                                SEEDS[name] + k, images=[master])
                sec = time.time() - t
                cut = pipeline.clean(pipeline.cut_out(img))
                gate = pipeline.GATES.get(part)
                why = pipeline.check(cut, img, master if gate else None, gate[1] if gate else 0, gate[2] if gate else 0)
                r = dict(id=f"st{steps}/c{canvas}", design=name, part=part, sec=round(sec, 1), ok=why == "",
                         why=why, sim=round(pipeline.palette_sim(img, master), 3), **{
                             k2: v for k2, v in metrics(img).items() if k2 in ("outline", "flat", "bg")})
                results.append(r)
                ims.append(img)
                print(json.dumps(r), flush=True)
            rows.append((f"st{steps}/c{canvas} {name}", ims))
    sheet(rows, d / "sheet.png", cell=200)
    summary = {}
    for cid in sorted({r["id"] for r in results}):
        rs = [r for r in results if r["id"] == cid]
        summary[cid] = {"n": len(rs), "ok": round(np.mean([r["ok"] for r in rs]), 3),
                        "sim": round(np.mean([r["sim"] for r in rs]), 3),
                        "outline": round(np.mean([r["outline"] for r in rs]), 3),
                        "sec": round(np.mean([r["sec"] for r in rs]), 1)}
        print(f"{cid:14} {summary[cid]}")
    json.dump({"results": results, "summary": summary}, open(d / "results.json", "w"), indent=1)


if __name__ == "__main__":
    sw = engine.SwarmClient()
    sw.ensure_up(log=print)
    sw.wait_ready(log=print, timeout_s=300)
    if sys.argv[1] == "master":
        master_stage(sw, sys.argv[2])
    else:
        klein_stage(sw)
