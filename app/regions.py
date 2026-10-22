# PBP Studio -- region map for the official Painter Boss Paradise template (painting.png, 2048x2048).
#
# Every region is one draw-box of the template: the 39 transparent connected components of
# data/pbplocal/violet/painting.png, exact to the pixel (the game slices these out of painting.png as the
# character sprites). Coordinates are (x, y, w, h) in template pixels, in template reading order.
# "part" is the game's sprite name (from castle.exe's string table); "role" groups boxes for layout_stats.json
# and the pipeline (head, body, body_big, limb, weapon, shield, hudicon, banner, bob).

TEMPLATE_SIZE = 2048  # official template is 2048x2048 RGBA

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


if __name__ == "__main__":
    from collections import Counter
    print(Counter(r["role"] for r in REGIONS))
    for r in REGIONS:
        x, y, w, h = r["rect"]
        assert 0 <= x and 0 <= y and x + w <= TEMPLATE_SIZE and y + h <= TEMPLATE_SIZE, r
    print("region map OK")
