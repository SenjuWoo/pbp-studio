# PBP Studio -- colorization core (v2).
# The official template is line art (black outlines on white) for most boxes; limbs are
# pre-shaded dark art. The in-game knight is composed from these exact boxes, so art MUST
# keep the template geometry. Strategy:
#   1) parse a palette from the user's description (or use picked colors),
#   2) procedurally fill the enclosed areas inside the line art (perfect alignment),
#   3) optional AI img2img pass for shading/detail at low creativity, then multiply the
#      ORIGINAL lines back on top so the game's geometry survives any model drift.
import re
from PIL import Image, ImageChops, ImageFilter, ImageOps

import numpy as np
from scipy import ndimage

COLOR_WORDS = {
    "green": (58, 160, 62), "red": (196, 44, 44), "crimson": (168, 24, 44),
    "blue": (54, 96, 196), "azure": (66, 150, 220), "navy": (36, 52, 120),
    "purple": (128, 60, 168), "violet": (150, 90, 200), "magenta": (200, 60, 160),
    "pink": (232, 120, 170), "orange": (228, 130, 40), "yellow": (232, 204, 72),
    "gold": (212, 168, 48), "brown": (120, 82, 52), "teal": (40, 150, 140),
    "cyan": (70, 190, 210), "gray": (140, 140, 148), "grey": (140, 140, 148),
    "silver": (188, 192, 200), "chrome": (200, 204, 214), "white": (238, 238, 242),
    "black": (40, 40, 46), "dark": (52, 48, 60), "rainbow": (220, 90, 160),
}

# When the user names no colour at all ("Samurai"), pick a scheme that fits the subject
# instead of the green/red default, which made everything look like the same knight.
ARCHETYPES = {
    ("samurai", "ronin", "shogun"): ("#2b2f52", "#c9a227"),
    ("ninja", "shinobi", "assassin"): ("#22252b", "#b02a2a"),
    ("knight", "paladin", "crusader", "templar"): ("#8a94a6", "#2f5d9e"),
    ("pirate", "buccaneer", "corsair"): ("#6b3f24", "#b03030"),
    ("robot", "mech", "cyborg", "android"): ("#9aa4ad", "#23c2d6"),
    ("wizard", "mage", "witch", "sorcerer"): ("#4a2f7a", "#d4b13a"),
    ("viking", "barbarian", "berserker"): ("#6d4b2f", "#8a2b2b"),
    ("demon", "devil", "fiend"): ("#5a1f1f", "#e08a1e"),
    ("angel", "seraph"): ("#e8e4d8", "#d4b13a"),
    ("elf", "ranger", "archer"): ("#2f5a3a", "#6b4a2a"),
    ("vampire", "undead", "skeleton", "ghost"): ("#2a2233", "#8a1f2f"),
    ("soldier", "marine", "trooper", "merc"): ("#4a5a3a", "#2b2b2b"),
    ("alien", "mutant"): ("#3d7a4a", "#8a3ad4"),
}

LINE_THRESHOLD = 232   # template lines are black..~210 grey; paper is ~250-255


def _hex_to_rgb(h):
    h = (h or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return None


def has_colors(text):
    """True when the description actually names a colour (so the user chose the palette)."""
    low = (text or "").lower()
    return bool(re.search(r"#[0-9a-f]{6}\b", low)) or any(
        re.search(r"\b" + re.escape(w), low) for w in COLOR_WORDS)


def extract_palette(rgb, levels=8):
    """Dominant colour and a contrasting second one, taken from a generated piece.

    Used when the description names no colour: the first AI piece decides the palette instead of
    the old green/red default, so "taco boy" comes out taco-coloured.
    """
    q = rgb.convert("RGB").quantize(colors=levels, method=Image.MEDIANCUT)
    pal = q.getpalette() or []
    cols = []
    for cnt, idx in sorted(q.getcolors() or [], reverse=True):
        c = tuple(pal[idx * 3: idx * 3 + 3])
        if len(c) == 3 and 25 < max(c) and min(c) < 235:
            cols.append((cnt, c))
    if not cols:
        return (128, 128, 128), (90, 90, 90)
    base = cols[0][1]
    rest = cols[1:5]
    accent = max(rest, key=lambda cc: sum(abs(a - b) for a, b in zip(cc[1], base)))[1] if rest \
        else tuple(int(v * 0.6) for v in base)
    return base, accent


def parse_palette(text, base_fallback="#3fae4a", accent_fallback="#c9303a"):
    """Base = first color the user names (armor), accent = second distinct (plume/trim)."""
    low = (text or "").lower()
    found = []
    for word, rgb in COLOR_WORDS.items():
        m = re.search(r"\b" + re.escape(word), low)
        if m:
            found.append((m.start(), rgb))
    found.sort()
    if not found:
        for words, (b_hex, a_hex) in ARCHETYPES.items():
            if any(re.search(r"\b" + w, low) for w in words):
                return _hex_to_rgb(b_hex), _hex_to_rgb(a_hex)
    base = found[0][1] if found else (_hex_to_rgb(base_fallback) or (58, 160, 62))
    accent = None
    for _, rgb in found[1:]:
        if rgb != base:
            accent = rgb
            break
    if accent is None:
        accent = _hex_to_rgb(accent_fallback) or (196, 44, 44)
    return base, accent


def _darken(rgb, k=0.5):
    return tuple(int(c * k) for c in rgb)


def palette_words(base, accent):
    """Human prompt words for the palette, so the AI knows what it is painting."""
    def nearest(rgb):
        best, dist = "green", float("inf")
        for w, c in COLOR_WORDS.items():
            d = sum((int(a) - int(b)) ** 2 for a, b in zip(rgb, c))
            if d < dist:
                best, dist = w, d
        return best
    return f"{nearest(base)} armor, {nearest(accent)} accents"


# ------------------------------------------------------------------ box analysis
def box_mode(crop, role=""):
    """'shaded' for pre-painted art boxes (limbs), 'lineart' for white boxes with black lines."""
    if role == "limb":
        return "shaded"
    g = crop.convert("L")
    hist = g.histogram()
    total = sum(hist) or 1
    white = sum(hist[236:]) / total
    return "lineart" if white > 0.5 else "shaded"


def _regions(gray):
    """Label non-line regions with adaptive line thickening.
    Thin/draft line art has 1-3px gaps that leak the interior into the background; try
    increasing dilation and keep the pass that encloses the most area."""
    lines0 = gray < LINE_THRESHOLD
    size = gray.size
    best = None
    for it in (1, 2, 3):
        lines = ndimage.binary_dilation(lines0, iterations=it) if it > 1 else lines0
        lab, n = ndimage.label(~lines)
        if n == 0:
            continue
        corners = {int(lab[0, 0]), int(lab[0, -1]), int(lab[-1, 0]), int(lab[-1, -1])} - {0}
        interior = 0
        for idx in range(1, n + 1):
            if idx in corners:
                continue
            area = int((lab == idx).sum())
            if area >= 25:
                interior += area
        if best is None or interior > best[0]:
            best = (interior, lab, n)
        if interior > 0.30 * size:      # already well enclosed, stop thickening
            break
    if best is None:
        return ndimage.label(~lines0)
    return best[1], best[2]


def flat_colorize(crop, base, accent):
    """Fill each enclosed area of the line art with palette colors, keep the lines black."""
    rgb = crop.convert("RGB")
    gray = np.array(rgb.convert("L"))
    h, w = gray.shape
    lab, n = _regions(gray)
    if n == 0:
        return ImageChops.multiply(rgb, Image.new("RGB", crop.size, base))

    corners = {int(lab[0, 0]), int(lab[0, -1]), int(lab[-1, 0]), int(lab[-1, -1])} - {0}

    comps = []
    for idx in range(1, n + 1):
        mask = lab == idx
        area = int(mask.sum())
        if area < 25:
            continue
        comps.append((idx, area, idx in corners))

    interior = [(i, a) for i, a, is_bg in comps if not is_bg]
    interior_area = sum(a for _, a in interior)
    if interior_area < 0.05 * h * w:
        # art touches the border and merged with a corner region: fall back to
        # "region with the most border pixels is background".
        border = np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]])
        counts = np.bincount(border[border > 0], minlength=n + 1) if (border > 0).any() else np.zeros(n + 1)
        bg_idx = int(np.argmax(counts)) if counts.size else 0
        interior = [(i, a) for i, a, _ in comps if i != bg_idx]
        if not interior:   # nothing enclosed at all -> tint everything
            return ImageChops.multiply(rgb, Image.new("RGB", crop.size, base))

    interior.sort(key=lambda t: -t[1])
    out = np.full((h, w, 3), 255, np.uint8)
    palette = [base, accent, _darken(base, 0.55), base]
    for rank, (idx, area) in enumerate(interior):
        out[lab == idx] = palette[rank % len(palette)] if rank < 3 else (
            base if rank % 2 else _darken(base, 0.8))
    colored = Image.fromarray(out, "RGB")
    # multiply the original line art back: lines -> black, paper -> color, antialias preserved
    return ImageChops.multiply(colored, rgb)


def shade_recolor(crop, base):
    """Keep the template's shading gradients but repaint them in the character's color."""
    rgb = crop.convert("RGB")
    gray = np.array(rgb.convert("L")).astype(np.float32) / 255.0
    # exterior = bright regions touching the border
    bg = gray > 0.86
    exterior = np.zeros(gray.shape, bool)
    if bg.any():
        lab, n = ndimage.label(bg)
        border_labels = set(int(v) for v in np.concatenate(
            [lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]]).tolist()) - {0}
        if border_labels:
            exterior = np.isin(lab, list(border_labels))
    lo, hi = float(gray.min()), float(gray.max())
    norm = (gray - lo) / (hi - lo + 1e-6)
    bright = 0.30 + 0.70 * norm            # darkest -> 30% tint, lightest -> full color
    tinted = np.clip(np.array(base, np.float32)[None, None, :] * bright[..., None], 0, 255)
    tinted[exterior] = 255
    return Image.fromarray(tinted.astype(np.uint8), "RGB")


# ------------------------------------------------------------------ line stamping
def multiply_lines(gen_rgb, crop):
    """Re-stamp the template's own line art over an AI result (line-art boxes)."""
    return ImageChops.multiply(gen_rgb.convert("RGB"), crop.convert("RGB"))


def overlay_edges(gen_rgb, crop):
    """For shaded boxes: stamp only the strong outlines of the template onto the AI result."""
    g = crop.convert("L").filter(ImageFilter.FIND_EDGES)
    g = ImageOps.autocontrast(g, cutoff=1)
    inv = ImageOps.invert(g)
    lines = Image.merge("RGB", (inv, inv, inv))
    return ImageChops.multiply(gen_rgb.convert("RGB"), lines)


# ------------------------------------------------------------------ pipeline entry
def colorize_box(crop, role, base, accent):
    """Procedural base colorization for one template box."""
    mode = box_mode(crop, role)
    if role == "weapon":
        base = (192, 196, 206)          # steel blade; the hilt/guard picks up the accent
    if mode == "lineart":
        return flat_colorize(crop, base, accent), mode
    return shade_recolor(crop, base), mode


def palette_lock(rgb, base, accent, levels=6):
    """Snap a piece onto the character's palette.

    Each box is generated separately, so the model invents its own colours per piece; without
    this the helmet is red, the body green and the arms another green entirely.
    """
    dark = tuple(int(c * 0.55) for c in base)
    light = tuple(min(255, int(c * 1.25 + 18)) for c in base)
    allowed = np.array([(18, 18, 22), dark, base, light, accent, (255, 255, 255)], dtype=np.int32)
    q = np.asarray(rgb.convert("RGB").quantize(colors=levels, method=Image.MEDIANCUT).convert("RGB"))
    px = q.reshape(-1, 3).astype(np.int32)
    d = ((px[:, None, :] - allowed[None, :, :]) ** 2).sum(axis=2)
    return Image.fromarray(allowed[d.argmin(axis=1)].astype(np.uint8).reshape(q.shape), "RGB")


def detail_prompt(design, role, palette_words="", part=""):
    from regions import SLOT_PROMPTS

    frag = SLOT_PROMPTS.get(part) or {
        "head": "single character head, front view",
        "body": "single torso, front view",
        "body_big": "single huge beefy torso",
        "limb": "single cartoon fist, closed hand, knuckles facing the viewer",
        "weapon": "single sword",
        "shield": "single shield",
        "hudicon": "single small character face icon",
        "banner": "single character standing holding a sword",
        "bob": "single small full-body character",
    }.get(role, "single game piece")
    bits = [f"({design}:1.3), {palette_words}".strip(", "),
            f"single isolated piece: {frag}, Behemoth Entertainment style, Dan Paladin style, "
            "thick uniform black outline, flat cel shading, two-tone shading, bold vector cartoon, "
            "high contrast, readable at small size",
            "single isolated 2D cartoon game sprite, centered, plain white background, "
            "no scene, no hands, no frame, no props, no text",
            "same character design in every piece, same helmet, same armour colours and materials as the head and body pieces, "
            "do not flip or rotate the subject"]
    if role == "limb":
        bits.append("match the armour plating, colour palette, line weight and material style of "
                    "the head and body pieces, do not invent a different armour design")
    return ", ".join(b for b in bits if b)


AI_NEGATIVE = ("text, watermark, photo, realistic, 3d render, blurry, background scenery, multiple objects, "
               "collage, grid, hands, holding, picture frame, border, easel, scenery, "
               "anime, manga, soft shading, airbrush, gradient, painterly, sketch")


def negative_for(design):
    """A knight model draws knights; only allow armour words when the design asks for them."""
    import re as _re
    low = (design or "").lower()
    if _re.search(r"knight|armou?r|paladin|warrior|soldier|helmet|guard|squire|viking|samurai", low):
        return AI_NEGATIVE
    return AI_NEGATIVE + ", knight, plate armor, medieval helmet, knight helmet, castle guard"
