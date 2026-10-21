# PBP Studio -- region map for the official Painter Boss Paradise template (painting.png 2048x2048).
# Baked from tools/detect_boxes.py output (white draw-box detection) and verified by rendering
# overlay/sheet previews of every box against the official template shipped with the game
# (data/pbplocal/violet/painting.png) and by matching to the sprite-name table extracted from
# castle.exe ([helm helm2..5 pbod1.. shield1 shield2 helm.A helm.B bigbod.. bigarm.. selectbanner
#  hudicon sword backoffb magic]).
#
# Every region is one transparent draw-box of the official template (the 39 transparent connected
# components of violet/painting.png, exact to the pixel; the old wireframe-sized rects were ~60% of this).
# Every region is one white draw-box in the template. The game slices these regions out of
# painting.png as the character sprites. Coordinates are (x, y, w, h) in template pixels.
# "role" drives the AI prompt fragment and default img2img creativity per region.

TEMPLATE_SIZE = 2048  # official template is 2048x2048 RGBA

ROLE_PROMPTS = {
    # Fragment appended to the global design prompt for each role:
    "head":      "close-up of the character's HEAD / helmet design, front view",
    "body":      "the character's TORSO / chest armor with belt, front view",
    "body_big":  "the character's LARGE beefy torso form, front view",
    "limb":      "one ARM segment piece of the character in the exact pose shown",
    "weapon":    "the character's WEAPON, held at the same angle and shape as the template",
    "shield":    "a small SHIELD matching the character's design, front view",
    "hudicon":   "a small icon showing the character's head and shoulders",
    "banner":    "large character art of the character's upper body for the selection banner",
    "bob":       "a small full-body miniature version of the character",
}

# Per-slot pose text, from the template's own orientation map (every box is a different angle).
# Without this the model paints a front view into every box.
SLOT_PROMPTS = {
    "helm": "head facing three-quarter left",
    "helm2": "head facing slightly front-left",
    "helm3": "head facing three-quarter right",
    "helm4": "head in profile facing right",
    "helm5": "head facing straight forward",
    "helm.A": "head tilted back, flinch pose",
    "helm.B": "back of the head, no face, no eyes, no mouth",
    "pbod1": "chibi torso and legs standing, three-quarter right",
    "pbodland": "chibi torso and legs crouched, landing frame",
    "knightbodrun": "chibi torso and legs running, arms swinging",
    "pbodspin": "chibi torso and legs tucked, mid-air spin",
    "pbodback": "chibi torso and legs seen from behind",
    "sword": "single sword standing vertically, tip up, hilt at the bottom",
    "shield1": "shield seen from the front",
    "shield2": "shield seen from the side, narrow edge only",
    "bigbod1": "huge muscular torso and small legs, upright, three-quarter right, walk frame 1",
    "bigbod2": "huge muscular torso and small legs, upright, three-quarter right, walk frame 2",
    "bigbod3": "huge muscular torso and small legs, upright, three-quarter right, walk frame 3",
    "bigbod4": "huge muscular torso lying horizontally on its back",
    "bigbodback": "huge muscular torso seen from behind",
    "bigbod911": "huge muscular torso tilted diagonally at 45 degrees, falling",
    "bigarm1": "single muscular arm, bent elbow", "bigarm2": "single muscular arm, fist",
    "bigarm3": "single muscular arm, outstretched", "bigarm4": "single muscular arm, raised",
    "bigarm5": "single muscular arm, downward punch", "bigarm6": "single muscular arm, flexed",
    "bigarm7": "single clenched fist", "bigarm8": "single muscular arm, forearm",
    "bigarm9": "single muscular arm, elbow bent back",
    "bigleft1": "single muscular left arm, open hand", "bigleft2": "single muscular left arm, fist",
    "bighand1": "single clenched fist", "bigarmgrap": "single muscular arm, grabbing hand",
    "bigarmthro": "single muscular arm, throwing", "bigarm911": "single muscular arm, raised up",
    "hudicon": "close-up of the head filling the square icon",
    "selectbanner": "waist-up character illustration, dynamic hero pose",
    "backoffb": "full-body chibi character standing, three-quarter view",
}

ROLE_CREATIVITY = {   # default img2img denoise per role (UI slider overrides with an offset)
    "head": 0.72, "body": 0.70, "body_big": 0.70, "limb": 0.78,
    "weapon": 0.85, "shield": 0.85, "hudicon": 0.78, "banner": 0.75, "bob": 0.80,
}

# The 39 draw-boxes, in template reading order. part = game sprite name (best-effort mapping,
# verified visually; harmless if two UI-only slots are swapped since all carry the same design).
REGIONS = [
    # -- 7 head boxes (row 1, red band) -> helm, helm2..helm5, helm.A, helm.B
    {"part": "helm",      "role": "head", "rect": (163, 111, 234, 332)},
    {"part": "helm2",     "role": "head", "rect": (411, 111, 234, 332)},
    {"part": "helm3",     "role": "head", "rect": (659, 111, 234, 332)},
    {"part": "helm4",     "role": "head", "rect": (907, 111, 234, 332)},
    {"part": "helm5",     "role": "head", "rect": (1155, 111, 234, 332)},
    {"part": "helm.A",    "role": "head", "rect": (1403, 111, 234, 332)},
    {"part": "helm.B",    "role": "head", "rect": (1651, 111, 234, 332)},
    # -- 5 body boxes (row 2, blue band) -> pbod1, pbodland, knightbodrun, pbodspin, pbodback
    {"part": "pbod1",       "role": "body", "rect": (163, 533, 234, 258)},
    {"part": "pbodland",    "role": "body", "rect": (411, 533, 234, 258)},
    {"part": "knightbodrun","role": "body", "rect": (659, 533, 234, 258)},
    {"part": "pbodspin",    "role": "body", "rect": (907, 533, 234, 258)},
    {"part": "pbodback",    "role": "body", "rect": (1155, 533, 234, 258)},
    # -- weapon + shields (pencil tile + yellow band)
    {"part": "sword",     "role": "weapon", "rect": (1541, 533, 96, 258)},
    {"part": "shield1",   "role": "shield", "rect": (1691, 661, 90, 130)},
    {"part": "shield2",   "role": "shield", "rect": (1795, 661, 90, 130)},
    # -- 6 beefy-form body boxes (row 3, green band) -> bigbod1..4, bigbodback, bigbod911
    {"part": "bigbod1",    "role": "body_big", "rect": (163, 865, 292, 296)},
    {"part": "bigbod2",    "role": "body_big", "rect": (469, 865, 270, 296)},
    {"part": "bigbod3",    "role": "body_big", "rect": (753, 865, 292, 296)},
    {"part": "bigbod4",    "role": "body_big", "rect": (1059, 865, 292, 296)},
    {"part": "bigbodback", "role": "body_big", "rect": (1365, 865, 292, 296)},
    {"part": "bigbod911",  "role": "body_big", "rect": (1671, 865, 270, 296)},
    # -- 15 beefy-form limb boxes (rows 4-6) -> bigarm1..9, bigleft1, bigleft2, bighand1,
    #    bigarmgrap, bigarmthro, bigarm911
    {"part": "bigarm1",    "role": "limb", "rect": (163, 1179, 158, 152)},
    {"part": "bigarm2",    "role": "limb", "rect": (335, 1179, 156, 152)},
    {"part": "bigarm3",    "role": "limb", "rect": (505, 1179, 234, 152)},
    {"part": "bigarm4",    "role": "limb", "rect": (753, 1179, 234, 152)},
    {"part": "bigarm5",    "role": "limb", "rect": (1001, 1179, 234, 152)},
    {"part": "bigarm6",    "role": "limb", "rect": (1249, 1179, 234, 152)},
    {"part": "bigarm7",    "role": "limb", "rect": (1497, 1179, 160, 152)},
    {"part": "bigarm8",    "role": "limb", "rect": (1671, 1179, 214, 152)},
    {"part": "bigarm9",    "role": "limb", "rect": (163, 1345, 158, 152)},
    {"part": "bigleft1",   "role": "limb", "rect": (335, 1345, 156, 152)},
    {"part": "bigleft2",   "role": "limb", "rect": (505, 1345, 234, 152)},
    {"part": "bighand1",   "role": "limb", "rect": (753, 1345, 140, 152)},
    {"part": "bigarmgrap", "role": "limb", "rect": (163, 1515, 234, 152)},
    {"part": "bigarmthro", "role": "limb", "rect": (411, 1515, 234, 152)},
    {"part": "bigarm911",  "role": "limb", "rect": (659, 1515, 234, 152)},
    # -- UI art boxes (bottom right purple area)
    {"part": "hudicon",      "role": "hudicon", "rect": (1201, 1477, 130, 130)},
    {"part": "selectbanner", "role": "banner",  "rect": (1345, 1477, 258, 514)},
    {"part": "backoffb",     "role": "bob",     "rect": (1627, 1477, 258, 514)},
]

assert len(REGIONS) == 39, f"expected 39 regions, got {len(REGIONS)}"


def regions_by_role():
    out = {}
    for r in REGIONS:
        out.setdefault(r["role"], []).append(r)
    return out


if __name__ == "__main__":
    from collections import Counter
    print(Counter(r["role"] for r in REGIONS))
    for r in REGIONS:
        x, y, w, h = r["rect"]
        assert 0 <= x and 0 <= y and x + w <= TEMPLATE_SIZE and y + h <= TEMPLATE_SIZE, r
    print("region map OK")
