# PBP Studio -- v0.8 piece pipeline.
#
# One MASTER design (made by Anima from the user's text, or supplied) is the single source of identity.
# Every draw-box is then derived from that master:
#   * edit backends (Flux.2 Klein / Qwen Image 2.1): master + a text pose command -> the piece, so hair,
#     colours and trims stay the same in all 7 head angles, the bodies, giants, weapon, shields and UI art.
#     A "torso reference" piece bridges the master to the bodies and giants (their clothing colours);
#   * anima backend: txt2img with the template wireframe as ControlNet guide (no cross-piece identity).
# Poses that are just a rotation or squash of another piece (landing, run, spin, lying giant, shield edge)
# are derived from it deterministically instead of asking the model.
# Each piece is cut out of its white background, quality-gated (blank / collage -> retry), and fitted
# into the box at the size and position real workshop characters use (layout_stats.json, numbers only).
# The 15 beefy-form limbs keep the template's own dark art: that is what most workshop characters do.
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from regions import REGIONS

class Cancelled(Exception):
    """The user pressed Cancel; the job ends without an error and writes nothing."""


HERE = Path(__file__).resolve().parent
LAYOUT = json.loads((HERE / "layout_stats.json").read_text(encoding="utf-8"))["boxes"]

STYLE = ("Castle Crashers cartoon style, thick black outline, flat bright colors, simple cel shading, "
         "plain white background")
NEG = ("multiple views, collage, grid, several figures, duplicates, text, watermark, photo, realistic, "
       "3d render, blurry, background scenery, shadow on the ground")

EDIT_MODELS = {"klein": "flux-2-klein-4b-fp8", "qwen": "qwen_image_2.1_turbo_int8_convrot"}
ANIMA_MODEL = "woomixAnima_v15"
DOWNLOADS = {
    "klein": "https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8 (flux-2-klein-4b-fp8.safetensors, "
             "4.1 GB) -> SwarmUI/Models/diffusion_models",
    "qwen": "https://huggingface.co/Comfy-Org/Qwen-Image-2.1 (diffusion_models/qwen_image_2.1_turbo_int8_convrot"
            ".safetensors, 7.3 GB) -> SwarmUI/Models/diffusion_models",
}

_HEAD = "the head only (no neck below the chin, no body)"
_TORSO = ("the torso garment only: the armor / clothing from the shoulders to the waist, as a separate piece, "
          "with no head, no neck, no arms, no hands, no legs, no cape and no weapon")
_GIANT = ("hugely enlarged into an enormous round muscular bulky torso, a big rounded blob of clothing, the "
          "arms cut off at the shoulders as short round stumps, no hands, no fists, no head, no legs")

# part -> (kind, what, pose, canvas (w, h)).
#   edit  = generate from the master, cut out;  ref = generated first, not placed (identity bridge);
#   ui    = full-bleed art;  xform = derived from another piece by squash / rotate (see XFORMS).
SPECS = {
    "helm":   ("edit", _HEAD, "turned in three-quarter view, face turned to the left", (1024, 1024)),
    "helm2":  ("edit", _HEAD, "turned slightly to the left, almost facing the viewer", (1024, 1024)),
    "helm3":  ("edit", _HEAD, "turned in three-quarter view, face turned to the right", (1024, 1024)),
    "helm4":  ("edit", _HEAD, "in full side profile, facing right", (1024, 1024)),
    "helm5":  ("edit", _HEAD, "facing straight at the viewer, front view", (1024, 1024)),
    "helm.A": ("edit", _HEAD, "tilted back and up, eyes squeezed shut, flinching in pain", (1024, 1024)),
    "helm.B": ("edit", _HEAD, "seen from behind: only the back of the head, only hair or headgear, no face",
               (1024, 1024)),
    "bodyref":      ("ref", _TORSO, "front view", (768, 768)),
    "pbod1":        ("edit", _TORSO, "standing, three-quarter view facing right", (768, 768)),
    "pbodback":     ("edit", _TORSO, "seen from behind, the plain back of the garment", (768, 768)),
    "pbodland":     ("xform", _TORSO, "squashed after landing", (768, 768)),
    "knightbodrun": ("xform", _TORSO, "leaning forward", (768, 768)),
    "pbodspin":     ("xform", _TORSO, "tilted, spinning", (768, 768)),
    "sword":   ("edit", "only the weapon this character carries",
                "shown alone, perfectly vertical, pointing straight up, handle at the bottom, centered", (512, 1024)),
    "shield1": ("edit", "only a small shield, buckler or round emblem badge that suits this character's design",
                "seen flat from the front, alone, centered", (768, 768)),
    "shield2": ("xform", "the same shield", "edge-on", (768, 768)),
    "bigbod1":    ("edit", _GIANT, "upright, front view", (1024, 1024)),
    "bigbod2":    ("edit", _GIANT, "upright, three-quarter view facing right", (1024, 1024)),
    "bigbodback": ("edit", _GIANT, "upright, seen from behind", (1024, 1024)),
    "bigbod3":    ("xform", _GIANT, "leaning forward", (1024, 1024)),
    "bigbod4":    ("xform", _GIANT, "lying on its back", (1024, 1024)),
    "bigbod911":  ("xform", _GIANT, "falling diagonally", (1024, 1024)),
    "hudicon":      ("ui", "a square close-up portrait icon: head and shoulders, facing the viewer, bold simple "
                           "colored background, thick black outline", "", (768, 768)),
    "selectbanner": ("ui", "a tall vertical character-select illustration: upper body, heroic dynamic pose, "
                           "comic-style colorful background with bold shapes, thick outlines, fill the whole "
                           "image with no white margin", "", (576, 1152)),
    "backoffb":     ("edit", "a tiny collectible figurine of the whole character, full body, standing on a small "
                             "flat blue rectangular base", "front three-quarter view", (768, 1024)),
}
# part -> (source part, scale x, scale y, rotation in degrees counter-clockwise)
XFORMS = {"pbodland": ("pbod1", 1.12, 0.8, 0), "knightbodrun": ("pbod1", 1, 1, -14),
          "pbodspin": ("pbod1", 1, 1, 38), "bigbod3": ("bigbod2", 1, 0.94, -14),
          "bigbod4": ("bigbod1", 1, 1.45, 80), "bigbod911": ("bigbod1", 1, 1, 45), "shield2": ("shield1", 0.28, 1, 0)}
USES_BODYREF = {"pbod1", "pbodback", "bigbod1", "bigbod2", "bigbodback"}
# part -> (reference piece, min colour similarity to it, max height/width): torsos must keep the clothing
# colours and must not come back as a tiny full-body figure (measured: good 0.81-0.99, wrong colours 0.57-0.62)
GATES = {"bodyref": ("master", 0.72, 1.4)}
GATES.update({k: ("bodyref", 0.70, 1.4) for k in USES_BODYREF})
GATES.update({k: ("bodyref", 0.50, 1.4) for k in ("pbodback", "bigbodback")})   # the back lacks the front emblem
ORDER = ["helm5", "helm3", "helm", "helm2", "helm4", "helm.A", "helm.B",
         "bodyref", "pbod1", "pbodback", "pbodland", "knightbodrun", "pbodspin",
         "sword", "shield1", "shield2",
         "bigbod1", "bigbod2", "bigbodback", "bigbod3", "bigbod4", "bigbod911",
         "hudicon", "selectbanner", "backoffb"]
BY_PART = {r["part"]: r for r in REGIONS}
ANCHOR_BOTTOM = {"head", "body", "body_big", "bob"}


def edit_prompt(part):
    kind, what, pose, _ = SPECS[part]
    if kind == "ui":
        return (f"Draw {what} of this exact character. Keep every design detail and color identical to the "
                f"character in the image. Castle Crashers cartoon style, flat colors, simple cel shading.")
    if kind == "ref":
        return ("Cut out ONLY the torso clothing of this exact character, front view: the armor, tabard and belt "
                "from the shoulders to the waist, as a separate piece. Remove the head, neck, hair, arms, hands, "
                "legs, cape and weapon completely. Keep the exact colors and emblem of the clothing. "
                f"{STYLE}, one single object, centered.")
    if part in USES_BODYREF:
        if what == _GIANT:
            task = f"Redraw the torso garment from image 2 {what}, {pose}."
        else:
            task = f"Redraw the torso garment from image 2, {pose}."
        return (f"Image 1 is a character, image 2 is a torso garment piece of that character. {task} "
                f"Same colors, same shapes, same emblem. No head, no arms, no legs. {STYLE}, one single object, centered.")
    return (f"Redraw {what} of this exact character, {pose}. Keep every design detail and every color identical "
            f"to the character in the image. {STYLE}, one single object, centered.")


def anima_prompt(design, part):
    _, what, pose, _ = SPECS[part]
    return f"{design}, {what.split(':')[0]}, {pose}, {STYLE}, single object, centered"


# ---------------------------------------------------------------- image helpers
def resize_rgba(img, size):
    """Premultiplied resize: no dark or white fringe on the transparent edge."""
    return img.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def xform(sprite, sx, sy, angle):
    """Derive a pose from another piece: trim, squash/stretch, rotate (transparent corners)."""
    bb = sprite.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    s = sprite.crop(bb)
    s = resize_rgba(s, (max(1, round(s.width * sx)), max(1, round(s.height * sy))))
    return s.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else s


def cut_out(rgb, tol=24):
    """White canvas -> sprite with a clean black soft edge (outlines are black, so alpha = darkness)."""
    a = np.asarray(rgb.convert("RGB")).astype(np.int16)
    low = a.min(axis=2)
    bg = low >= 255 - tol
    lab, _ = ndimage.label(bg)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    outside = np.isin(lab, border[border > 0])
    solid = ~outside
    ring = ndimage.binary_dilation(outside, iterations=2) & solid
    alpha = np.where(solid, 255, 0).astype(np.float32)
    alpha[ring] = np.clip((255 - low[ring]) * 1.15, 0, 255)
    out = np.dstack([np.where(ring[..., None], 0, a), alpha]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def blobs(img, thr=40):
    m = np.asarray(img.getchannel("A")) > thr
    lab, n = ndimage.label(m)
    sizes = ndimage.sum(m, lab, range(1, n + 1)) if n else np.array([])
    return lab, sizes


def clean(sprite):
    """Keep the main blob plus real attachments (bow, plume); drop specks and stray pieces."""
    lab, sizes = blobs(sprite)
    if len(sizes) <= 1:
        return sprite
    keep = [i + 1 for i, s in enumerate(sizes) if s >= 0.06 * sizes.max()]
    a = np.asarray(sprite).copy()
    a[..., 3] = np.where(np.isin(lab, keep), a[..., 3], 0)
    return Image.fromarray(a, "RGBA")


def palette(img, bins=4):
    """Coarse colour histogram without the white canvas and the black outlines."""
    a = np.asarray(img.convert("RGB")).reshape(-1, 3).astype(int)
    q = a[(a.min(1) < 235) & (a.max(1) > 40)] // (256 // bins)
    h = np.bincount(q[:, 0] * bins * bins + q[:, 1] * bins + q[:, 2], minlength=bins ** 3).astype(float)
    return h / max(h.sum(), 1)


def palette_sim(a, b):
    """Bhattacharyya coefficient of two colour histograms: 1 = same colours."""
    return float(np.sqrt(palette(a) * palette(b)).sum())


def check(sprite, raw=None, ref=None, min_sim=0.0, max_aspect=0.0):
    """Return '' when the piece is usable, else why not (blank / filled canvas / figures / wrong colours / shape)."""
    cov = (np.asarray(sprite.getchannel("A")) > 40).mean()
    if cov < 0.015:
        return "blank"
    if cov > 0.92:
        return "filled the whole canvas"
    _, sizes = blobs(sprite)
    if len(sizes) >= 2:
        s = np.sort(sizes)[::-1]
        if s[1] >= 0.6 * s[0]:
            return "several figures"
    if max_aspect:
        bb = sprite.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
        if bb and (bb[3] - bb[1]) / max(1, bb[2] - bb[0]) > max_aspect:
            return "too tall for this piece"
    if ref is not None and raw is not None and palette_sim(raw, ref) < min_sim:
        return "colours differ from the reference"
    return ""


def fit(sprite, part):
    """Trim the sprite and place it in its box at the median size/position of real workshop art."""
    x, y, w, h = BY_PART[part]["rect"]
    role = BY_PART[part]["role"]
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bb = sprite.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    if not bb:
        return canvas
    sprite = sprite.crop(bb)
    x0, y0, x1, y1 = LAYOUT[part]
    tw, th = max(8, (x1 - x0) * w), max(8, (y1 - y0) * h)
    s = min(tw / sprite.width, th / sprite.height)
    new = resize_rgba(sprite, (max(1, round(sprite.width * s)), max(1, round(sprite.height * s))))
    px = round((x0 + x1) / 2 * w - new.width / 2)
    py = round(y1 * h - new.height) if role in ANCHOR_BOTTOM else round((y0 + y1) / 2 * h - new.height / 2)
    canvas.alpha_composite(new, (max(0, min(px, w - new.width)), max(0, min(py, h - new.height))))
    return canvas


def cover(img, size):
    """Full-bleed art: scale to fill the box, centre-crop."""
    w, h = size
    s = max(w / img.width, h / img.height)
    big = img.convert("RGBA").resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    l, t = (big.width - w) // 2, (big.height - h) // 2
    return big.crop((l, t, l + w, t + h))


def anima_guide(template, part):
    """White strokes on black: the template wireframe of this box, square-padded for ControlNet."""
    x, y, w, h = BY_PART[part]["rect"]
    a = np.asarray(template.crop((x, y, x + w, y + h)).convert("RGBA")).astype(np.float32)
    g = Image.fromarray((np.clip(a[..., 3] / 255 * 2.5, 0, 1) * 255).astype(np.uint8)).convert("RGB")
    side = int(max(w, h) * 1.15)
    sq = Image.new("RGB", (side, side), (0, 0, 0))
    sq.paste(g, ((side - w) // 2, (side - h) // 2))
    return sq.resize((768, 768), Image.LANCZOS)


# ---------------------------------------------------------------- the runner
def run(engine, job, base, p, design, seed, backend):
    """Generate every non-limb piece; returns (canvas, [(part, piece)]). `base` is the template RGBA."""
    sw = engine.swarm
    canvas = base.copy()
    # clear every box we repaint: the wireframe must not survive into the character
    for r in REGIONS:
        if r["role"] != "limb":
            x, y, w, h = r["rect"]
            canvas.paste((0, 0, 0, 0), (x, y, x + w, y + h))

    cfg = float(p.get("cfg", 3.0))
    steps = int(p.get("steps", 40))
    sampler = (p.get("sampler") or "").strip()
    sched = (p.get("scheduler") or "").strip()

    # ---- master design
    job.phase = "master"
    mpath = p.get("master_png")
    if mpath and Path(mpath).exists():
        master = Image.open(mpath).convert("RGB")
        job.say(f"Master design: using {mpath}")
    else:
        job.say("Designing the character (Anima)...")
        prompt = (f"{design}, full body, chibi proportions, standing, three-quarter view, holding a weapon, "
                  f"{STYLE}, single character")
        master = sw.render(prompt, 1024, 1024, ANIMA_MODEL, steps, cfg, seed, NEG, sampler=sampler,
                           scheduler=sched).convert("RGB")
    master.save(job.job_dir / "master.png")
    job.result = {"preview": str(job.job_dir / "master.png"), "master": str(job.job_dir / "master.png")}

    model = ANIMA_MODEL if backend == "anima" else EDIT_MODELS[backend]
    if backend != "anima" and model not in sw.list_models():
        raise RuntimeError(f"Model '{model}' is not installed in SwarmUI. Get it from {DOWNLOADS[backend]}, "
                           f"or pick another backend.")
    made, sprites, cells = {}, {}, []       # raw generations (references), cut-out sprites, placed pieces
    job.total = len(ORDER)
    for i, part in enumerate(ORDER, 1):
        if job.cancel.is_set():
            raise Cancelled()
        kind, _, _, (gw, gh) = SPECS[part]
        job.phase, job.current = "generating", part
        if kind == "ref" and backend == "anima":
            job.done = i
            continue
        why = ""
        if kind == "xform" and backend != "anima":
            src_part, sx, sy, ang = XFORMS[part]
            sprite = xform(sprites[src_part], sx, sy, ang)
        else:
            sprite, raw = None, None
            for attempt in range(3):
                s = (seed + 97 * attempt + 13 * i) % (2**31 - 1) or 1
                try:
                    if backend == "anima":
                        guide = anima_guide(base, part) if p.get("controlnet", True) else None
                        img = sw.render(anima_prompt(design, part), gw, gh, ANIMA_MODEL, steps, cfg, s, NEG,
                                        controlnet=guide,
                                        controlnet_strength=float(p.get("controlnet_strength", 1.0)),
                                        sampler=sampler, scheduler=sched)
                    else:
                        refs = [master] + ([made["bodyref"]] if part in USES_BODYREF and "bodyref" in made else [])
                        img = sw.render(edit_prompt(part), gw, gh, model, 8, 1.0, s, images=refs)
                except Exception as e:
                    why = f"backend error: {str(e)[:160]}"
                    job.say(f"    {part}: {why}")
                    continue
                if kind == "ui":
                    sprite, raw, why = cover(img, BY_PART[part]["rect"][2:]), img, ""
                    break
                cut = clean(cut_out(img))
                gate = GATES.get(part)
                ref_img = {"master": master, "bodyref": made.get("bodyref")}.get(gate[0]) if gate else None
                why = check(cut, img, ref_img, gate[1] if gate else 0.0, gate[2] if gate else 0.0)
                if not why:
                    sprite, raw = cut, img
                    break
                job.say(f"    {part}: attempt {attempt + 1} rejected ({why})")
                (job.job_dir / "raw").mkdir(exist_ok=True)
                img.save(job.job_dir / "raw" / f"{part}_rejected{attempt + 1}.png")
                if sprite is None:                  # keep the first try if every attempt fails the gate
                    sprite, raw = cut, img
            if sprite is None:
                raise RuntimeError(f"{part}: the backend produced nothing ({why})")
            made[part] = raw
        sprites[part] = sprite
        job.done = i
        if kind == "ref":
            job.say(f"[{i}/{len(ORDER)}] {part} (reference, not placed)")
            continue
        x, y, w, h = BY_PART[part]["rect"]
        piece = sprite if kind == "ui" else fit(sprite, part)
        canvas.alpha_composite(piece, (x, y))
        cells.append((part, piece))
        canvas.resize((1024, 1024), Image.LANCZOS).save(job.job_dir / "live_preview.png")
        job.result = {"preview": str(job.job_dir / "live_preview.png"), "master": str(job.job_dir / "master.png")}
        job.say(f"[{i}/{len(ORDER)}] {part} ok" + (f" (kept despite: {why})" if why else ""))
    return canvas, cells
