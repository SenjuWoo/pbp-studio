# PBP Studio -- piece pipeline.
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
# Anima model-card negative + ours; measured best with the tags+prose master prompt (docs/TUNING.md)
MASTER_NEG = ("worst quality, low quality, score_1, score_2, score_3, artist name, blurry, jpeg artifacts, "
              "chromatic aberration, " + NEG)

EDIT_MODELS = {"klein": "flux-2-klein-4b-fp8", "qwen": "qwen_image_2.1_turbo_int8_convrot"}
# seconds per render: a Klein piece takes ~7-10 s, so a longer wait is a stalled SwarmUI (seen ~1 run in 3, always
# cleared by an interrupt + retry). The first call of a job also loads the model, so it gets FIRST_CALL_TIMEOUT.
RENDER_TIMEOUT = {"klein": 90, "qwen": 240, "anima": 120}
FIRST_CALL_TIMEOUT = 300
EDIT_STEPS = 6   # Klein sweep: same gate pass as 8, best colour fidelity, 30% faster (docs/TUNING.md)
ANIMA_MODEL = "woomixAnima_v15"
ANIMA_SAMPLER, ANIMA_SCHEDULER = "er_sde", "simple"   # tuned: docs/TUNING.md
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
          "arms cut off at the shoulders as short round stumps, no hands, no fists, no head, no legs, no feet")

# part -> (kind, what, pose, canvas (w, h)).
#   edit  = generate from the master, cut out;  ref = generated first, not placed (identity bridge);
#   ui    = full-bleed art;  xform = derived from another piece by squash / rotate (see XFORMS).
SPECS = {
    # slots 1-3 face almost the viewer with a growing turn to the viewer's right, 4 is a right profile, 5 is
    # straight on, 6 is bowed forward, 7 is the back (measured on 10 real Workshop characters, docs/TUNING.md)
    "helm":   ("edit", _HEAD, "turned about 15 degrees to the right, almost facing the viewer", (1024, 1024)),
    "helm2":  ("edit", _HEAD, "turned about 25 degrees to the right, still almost facing the viewer", (1024, 1024)),
    "helm3":  ("edit", _HEAD, "turned about 40 degrees to the right, a mild three-quarter view", (1024, 1024)),
    "helm4":  ("edit", _HEAD, "in full side profile, facing right", (1024, 1024)),
    "helm5":  ("edit", _HEAD, "facing straight at the viewer, front view", (1024, 1024)),
    # "bowed ... seen from above" made Klein draw bald heads for taco, cat and robot; a plain 30 degree tilt keeps them
    "helm.A": ("edit", _HEAD, "tilted forward and down about 30 degrees as if hurt, eyes squeezed shut, every hair, ear, "
                              "hat, helmet, shell and accessory exactly as in image 2, nothing removed", (1024, 1024)),
    "helm.B": ("edit", _HEAD, "seen from directly behind: the back of the same head (or helmet), no face visible",
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
    "bigbod3":    ("edit", _GIANT, "seen in a full side profile facing right, the chest bulging toward the right",
                    (1024, 1024)),
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
          "pbodspin": ("pbod1", 1, 1, 38),
          # the template's 4th giant lies on its BACK (chest up, collar left, flat underside): the side view of the
          # standing giant turned 90 degrees counter-clockwise, flattened and stretched into a wide loaf
          "bigbod4": ("bigbod3", 0.8, 1.3, 90),
          "bigbod911": ("bigbod1", 1, 1, 45), "shield2": ("shield1", 0.28, 1, 0)}
USES_BODYREF = {"pbod1", "pbodback", "bigbod1", "bigbod2", "bigbod3", "bigbodback"}
# heads are redrawn from the front head (helm5) as well as the master: identical face, graded turn
USES_FRONT = {"helm", "helm2", "helm3", "helm4", "helm.A", "helm.B"}
# graded slots: how far between the character's own front head (0) and right profile (1) each should turn.
# Klein's turn varies a lot per seed ("15 degrees" came out anywhere from 5 to 40), so several candidates are
# drawn and the one whose silhouette difference from the front head is closest to the target is kept.
TURN_TARGET = {"helm": 0.22, "helm2": 0.36, "helm3": 0.55}
TURN_CANDIDATES = 3
# part -> (reference piece, min colour similarity to it, max height/width): torsos must keep the clothing
# colours and must not come back as a tiny full-body figure (measured: good 0.81-0.99, wrong colours 0.57-0.62)
GATES = {"bodyref": ("master", 0.55, 1.4)}   # torso lacks hair/skin colours: good ones measured 0.62-0.91
GATES.update({k: ("bodyref", 0.70, 1.4) for k in USES_BODYREF})
GATES.update({k: ("bodyref", 0.50, 1.4) for k in ("pbodback", "bigbodback")})   # the back lacks the front emblem
HEAD_ASPECT = 1.55   # a head taller than this came back with a body, legs or a sword (taco profile, measured)
GATES.update({k: (None, 0.0, HEAD_ASPECT) for k in USES_FRONT | {"helm5"}})
GATES["helm.A"] = ("front", 0.55, HEAD_ASPECT)   # measured: bald-head failures 0.32-0.55, good ones 0.65-0.96
ORDER = ["helm5", "helm4", "helm", "helm2", "helm3", "helm.A", "helm.B",
         "bodyref", "pbod1", "pbodback", "pbodland", "knightbodrun", "pbodspin",
         "sword", "shield1", "shield2",
         "bigbod1", "bigbod2", "bigbod3", "bigbodback", "bigbod4", "bigbod911",
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
    if part in USES_FRONT:
        return ("Image 1 is a character, image 2 is the same character's head facing the viewer. "
                f"Redraw only the head from image 2 (nothing but the head: no body, no legs, no feet, no weapon), {pose}. "
                "Keep every design detail and every color identical. "
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


def master_prompt(design):
    """Anima model-card format: lowercase tags first, then two plain sentences (won the prompt sweep)."""
    d = design.strip().rstrip(".")
    return ("masterpiece, best quality, score_7, safe, solo, full body, chibi, standing, holding weapon, "
            "white background, simple background, thick outlines, flat color.\n"
            f"{d[0].upper() + d[1:]}. The character is drawn in the Castle Crashers cartoon style with thick black "
            "outlines, flat bright colors and simple cel shading, standing in a three-quarter view on a plain white "
            "background.")


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


def _aspect(sprite):
    bb = sprite.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    return (bb[3] - bb[1]) / max(1, bb[2] - bb[0]) if bb else 0.0


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


def _mask(sprite, h=160):
    """Alpha silhouette scaled to a fixed height and centred on a fixed canvas, for shape comparison."""
    bb = sprite.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    m = sprite.crop(bb).getchannel("A").point(lambda v: 255 if v > 40 else 0)
    m = m.resize((max(1, round(m.width * h / m.height)), h))
    out = Image.new("L", (400, h), 0)
    out.paste(m, ((400 - m.width) // 2, 0))
    return np.asarray(out) > 0


def turn_score(a, b):
    """0 = same silhouette, 1 = nothing in common: how far head `a` is turned away from head `b`."""
    ma, mb = _mask(a), _mask(b)
    return 1.0 - float((ma & mb).sum() / max(1, (ma | mb).sum()))


def choose_turn(cands, front, profile, target):
    """cands = [(sprite, raw)]; keep the one whose turn, as a share of the front-to-profile span, is closest."""
    span = max(turn_score(profile, front), 1e-3)
    return min(cands, key=lambda c: abs(turn_score(c[0], front) / span - target))


def alpha_area(img):
    return int((np.asarray(img.getchannel("A")) > 40).sum())


def fit(sprite, part, area=0):
    """Trim the sprite and place it in its box at the median size/position of real workshop art.

    area > 0 (heads): scale every head to the same pixel area as the front head, so a ponytail or an
    open-mouthed profile does not shrink the head and the 7 slots line up with the body below.
    """
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
    if area:
        s = min((area / max(1, alpha_area(sprite))) ** 0.5, 0.95 * w / sprite.width, 0.95 * h / sprite.height)
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
def _turn_slot(sw, job, part, model, made, sprites, master, seed, timeout):
    """Draw TURN_CANDIDATES heads for a graded slot and keep the one turned closest to its target."""
    cands = []
    for k in range(TURN_CANDIDATES):
        try:
            img = sw.render(edit_prompt(part), 1024, 1024, model, EDIT_STEPS, 1.0, (seed + 31 * k) % (2**31 - 1) or 1,
                            images=[master, made["helm5"]], timeout=timeout)
        except Exception as e:
            job.say(f"    {part}: backend error: {str(e)[:120]}")
            continue
        cut = clean(cut_out(img))
        if not check(cut, max_aspect=HEAD_ASPECT):
            cands.append((cut, img))
    if not cands:
        raise RuntimeError(f"{part}: no usable head from {TURN_CANDIDATES} tries")
    if "helm4" in sprites:
        return choose_turn(cands, sprites["helm5"], sprites["helm4"], TURN_TARGET[part])
    return cands[0]

def run(engine, job, base, p, design, seed, backend):
    """Generate every non-limb piece; returns (canvas, [(part, piece)]). `base` is the template RGBA."""
    sw = engine.swarm
    canvas = base.copy()
    # clear every box we repaint: the wireframe must not survive into the character
    for r in REGIONS:
        if r["role"] != "limb":
            x, y, w, h = r["rect"]
            canvas.paste((0, 0, 0, 0), (x, y, x + w, y + h))

    cfg = float(p.get("cfg", 4.0))
    steps = int(p.get("steps", 40))
    sampler = (p.get("sampler") or "").strip() or ANIMA_SAMPLER
    sched = (p.get("scheduler") or "").strip() or ANIMA_SCHEDULER

    # ---- master design
    job.phase = "master"
    mpath = p.get("master_png")
    if mpath and Path(mpath).exists():
        master = Image.open(mpath).convert("RGB")
        job.say(f"Master design: using {mpath}")
    else:
        job.say("Designing the character (Anima)...")
        master = sw.render(master_prompt(design), 1024, 1024, ANIMA_MODEL, steps, cfg, seed, MASTER_NEG,
                           sampler=sampler, scheduler=sched, timeout=FIRST_CALL_TIMEOUT).convert("RGB")
    master.save(job.job_dir / "master.png")
    job.result = {"preview": str(job.job_dir / "master.png"), "master": str(job.job_dir / "master.png")}

    model = ANIMA_MODEL if backend == "anima" else EDIT_MODELS[backend]
    if backend != "anima" and model not in sw.list_models():
        raise RuntimeError(f"Model '{model}' is not installed in SwarmUI. Get it from {DOWNLOADS[backend]}, "
                           f"or pick another backend.")
    made, sprites, cells = {}, {}, []       # raw generations (references), cut-out sprites, placed pieces
    head_area = 0                           # pixel area of the placed front head: the size every head is scaled to
    job.total = len(ORDER)
    for i, part in enumerate(ORDER, 1):
        if job.cancel.is_set():
            raise Cancelled()
        kind, _, _, (gw, gh) = SPECS[part]
        job.phase, job.current = "generating", part
        timeout = FIRST_CALL_TIMEOUT if not made else RENDER_TIMEOUT[backend]
        if kind == "ref" and backend == "anima":
            job.done = i
            continue
        why = ""
        if part in TURN_TARGET and backend != "anima":
            sprite, raw = _turn_slot(sw, job, part, model, made, sprites, master, seed + 13 * i, timeout)
            made[part], sprites[part] = raw, sprite
            piece = fit(sprite, part, head_area)
            x, y, w, h = BY_PART[part]["rect"]
            canvas.alpha_composite(piece, (x, y))
            cells.append((part, piece))
            job.done = i
            canvas.resize((1024, 1024), Image.LANCZOS).save(job.job_dir / "live_preview.png")
            job.result = {"preview": str(job.job_dir / "live_preview.png"), "master": str(job.job_dir / "master.png")}
            job.say(f"[{i}/{len(ORDER)}] {part} ok (turn picked from {TURN_CANDIDATES})")
            continue
        if kind == "xform" and backend != "anima":
            src_part, sx, sy, ang = XFORMS[part]
            sprite = xform(sprites[src_part], sx, sy, ang)
        else:
            sprite, raw, best = None, None, None    # best = (colour score, sprite, raw) among rejected tries
            for attempt in range(3):
                s = (seed + 97 * attempt + 13 * i) % (2**31 - 1) or 1
                try:
                    if backend == "anima":
                        guide = anima_guide(base, part) if p.get("controlnet", True) else None
                        img = sw.render(anima_prompt(design, part), gw, gh, ANIMA_MODEL, steps, cfg, s, NEG,
                                        controlnet=guide,
                                        controlnet_strength=float(p.get("controlnet_strength", 1.0)),
                                        sampler=sampler, scheduler=sched, timeout=timeout)
                    else:
                        refs = [master] + ([made["bodyref"]] if part in USES_BODYREF and "bodyref" in made else []) \
                            + ([made["helm5"]] if part in USES_FRONT and "helm5" in made else [])
                        img = sw.render(edit_prompt(part), gw, gh, model, EDIT_STEPS, 1.0, s, images=refs,
                                        timeout=timeout)
                except Exception as e:
                    why = f"backend error: {str(e)[:160]}"
                    job.say(f"    {part}: {why}")
                    continue
                if kind == "ui":
                    sprite, raw, why = cover(img, BY_PART[part]["rect"][2:]), img, ""
                    break
                cut = clean(cut_out(img))
                gate = GATES.get(part)
                ref_img = {"master": master, "bodyref": made.get("bodyref"), "front": made.get("helm5")}.get(
                    gate[0]) if gate else None
                why = check(cut, img, ref_img, gate[1] if gate else 0.0, gate[2] if gate else 0.0)
                if not why:
                    sprite, raw = cut, img
                    break
                job.say(f"    {part}: attempt {attempt + 1} rejected ({why})")
                (job.job_dir / "raw").mkdir(exist_ok=True)
                img.save(job.job_dir / "raw" / f"{part}_rejected{attempt + 1}.png")
                score = palette_sim(img, ref_img) if ref_img is not None else -_aspect(cut)
                if best is None or score > best[0]:
                    best = (score, cut, img)
            if sprite is None and best:             # every attempt failed the gate: keep the closest to the reference
                sprite, raw = best[1], best[2]
            if sprite is None:
                raise RuntimeError(f"{part}: the backend produced nothing ({why})")
            made[part] = raw
        sprites[part] = sprite
        job.done = i
        if kind == "ref":
            job.say(f"[{i}/{len(ORDER)}] {part} (reference, not placed)")
            continue
        x, y, w, h = BY_PART[part]["rect"]
        piece = sprite if kind == "ui" else fit(sprite, part, head_area if part in USES_FRONT else 0)
        if part == "helm5":
            head_area = alpha_area(piece)
        canvas.alpha_composite(piece, (x, y))
        cells.append((part, piece))
        canvas.resize((1024, 1024), Image.LANCZOS).save(job.job_dir / "live_preview.png")
        job.result = {"preview": str(job.job_dir / "live_preview.png"), "master": str(job.job_dir / "master.png")}
        job.say(f"[{i}/{len(ORDER)}] {part} ok" + (f" (kept despite: {why})" if why else ""))
    return canvas, cells
