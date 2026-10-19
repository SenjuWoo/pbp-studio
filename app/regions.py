# PBP Studio -- region map for the official Painter Boss Paradise template (painting.png 2048x2048).
# Baked from tools/detect_boxes.py output (white draw-box detection) and verified by rendering
# overlay/sheet previews of every box against the official template shipped with the game
# (data/pbplocal/violet/painting.png) and by matching to the sprite-name table extracted from
# castle.exe ([helm helm2..5 pbod1.. shield1 shield2 helm.A helm.B bigbod.. bigarm.. selectbanner
#  hudicon sword backoffb magic]).
#
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
    {"part": "helm",      "role": "head", "rect": (206, 219, 149, 216)},
    {"part": "helm2",     "role": "head", "rect": (449, 245, 160, 176)},
    {"part": "helm3",     "role": "head", "rect": (711, 263, 153, 167)},
    {"part": "helm4",     "role": "head", "rect": (937, 245, 169, 188)},
    {"part": "helm5",     "role": "head", "rect": (1192, 238, 169, 187)},
    {"part": "helm.A",    "role": "head", "rect": (1419, 234, 192, 192)},
    {"part": "helm.B",    "role": "head", "rect": (1688, 268, 153, 145)},
    # -- 5 body boxes (row 2, blue band) -> pbod1, pbodland, knightbodrun, pbodspin, pbodback
    {"part": "pbod1",       "role": "body", "rect": (231, 682, 124, 103)},
    {"part": "pbodland",    "role": "body", "rect": (447, 674, 157, 112)},
    {"part": "knightbodrun","role": "body", "rect": (692, 657, 169, 124)},
    {"part": "pbodspin",    "role": "body", "rect": (936, 650, 173, 135)},
    {"part": "pbodback",    "role": "body", "rect": (1203, 626, 137, 162)},
    # -- weapon + shields (pencil tile + yellow band)
    {"part": "sword",     "role": "weapon", "rect": (1559, 559, 64, 220)},
    {"part": "shield1",   "role": "shield", "rect": (1729, 717, 52, 70)},
    {"part": "shield2",   "role": "shield", "rect": (1807, 718, 53, 58)},
    # -- 6 beefy-form body boxes (row 3, green band) -> bigbod1..4, bigbodback, bigbod911
    {"part": "bigbod1",    "role": "body_big", "rect": (209, 949, 214, 207)},
    {"part": "bigbod2",    "role": "body_big", "rect": (505, 941, 222, 212)},
    {"part": "bigbod3",    "role": "body_big", "rect": (790, 941, 231, 212)},
    {"part": "bigbod4",    "role": "body_big", "rect": (1078, 936, 264, 214)},
    {"part": "bigbodback", "role": "body_big", "rect": (1426, 934, 197, 221)},
    {"part": "bigbod911",  "role": "body_big", "rect": (1698, 936, 234, 220)},
    # -- 15 beefy-form limb boxes (rows 4-6) -> bigarm1..9, bigleft1, bigleft2, bighand1,
    #    bigarmgrap, bigarmthro, bigarm911
    {"part": "bigarm1",    "role": "limb", "rect": (181, 1183, 133, 146)},
    {"part": "bigarm2",    "role": "limb", "rect": (350, 1182, 137, 146)},
    {"part": "bigarm3",    "role": "limb", "rect": (522, 1195, 210, 117)},
    {"part": "bigarm4",    "role": "limb", "rect": (770, 1192, 189, 118)},
    {"part": "bigarm5",    "role": "limb", "rect": (1018, 1190, 185, 122)},
    {"part": "bigarm6",    "role": "limb", "rect": (1291, 1191, 175, 122)},
    {"part": "bigarm7",    "role": "limb", "rect": (1510, 1197, 123, 115)},
    {"part": "bigarm8",    "role": "limb", "rect": (1694, 1186, 179, 140)},
    {"part": "bigarm9",    "role": "limb", "rect": (174, 1351, 140, 144)},
    {"part": "bigleft1",   "role": "limb", "rect": (347, 1358, 127, 126)},
    {"part": "bigleft2",   "role": "limb", "rect": (527, 1356, 199, 123)},
    {"part": "bighand1",   "role": "limb", "rect": (769, 1365, 96, 106)},
    {"part": "bigarmgrap", "role": "limb", "rect": (166, 1520, 215, 124)},
    {"part": "bigarmthro", "role": "limb", "rect": (416, 1519, 207, 130)},
    {"part": "bigarm911",  "role": "limb", "rect": (678, 1517, 187, 129)},
    # -- UI art boxes (bottom right purple area)
    {"part": "hudicon",      "role": "hudicon", "rect": (1201, 1477, 127, 130)},
    {"part": "selectbanner", "role": "banner",  "rect": (1345, 1490, 255, 501)},
    {"part": "backoffb",     "role": "bob",     "rect": (1656, 1661, 190, 325)},
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
