"""Regression tests for the 0.6.2 fixes: black limbs, white caps, stray blobs, head variants."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from engine import HEAD_BG, head_variant, keep_largest, key_background, limb_lut  # noqa: E402


def _lum(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def _limb_crop():
    """Synthetic limb: black outline, dark-grey muscle (55), light cuff (180), white outside."""
    img = Image.new("RGB", (48, 48), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([8, 6, 40, 42], fill=(0, 0, 0))          # outline
    d.rectangle([11, 9, 37, 39], fill=(55, 55, 55))      # muscle, the old bug turned this black
    d.rectangle([11, 9, 37, 20], fill=(180, 180, 180))   # cuff
    return img


def test_limb_lut_keeps_muscle_coloured():
    out = np.asarray(limb_lut(_limb_crop(), (225, 169, 63), (170, 30, 40))).astype(int)
    opaque = out.min(axis=2) < 236
    black = (_lum(out) < 22) & opaque
    assert black.mean() < 0.35, f"{black.mean():.0%} of the limb is still black"
    muscle = out[25, 24]                                  # inside the muscle band
    assert muscle[0] > 100 and muscle[2] < 90, muscle     # tinted to the primary, not black
    cuff = out[14, 24]
    assert cuff[0] > 100 and cuff[1] < 90, cuff           # tinted to the accent


def test_keep_largest_drops_stray_bar():
    img = Image.new("RGB", (60, 40), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([10, 5, 45, 35], fill=(20, 20, 20))       # the arm
    d.rectangle([0, 0, 2, 39], fill=(20, 20, 20))         # bigarm8's stray left bar
    out = np.asarray(keep_largest(img))
    assert out[:, :3].min() >= 236, "left bar survived"
    assert out[20, 30].min() < 236, "the arm itself was dropped"


def test_key_background_removes_grey_and_keeps_white_inside():
    img = Image.new("RGB", (64, 64), HEAD_BG)
    d = ImageDraw.Draw(img)
    d.ellipse([10, 10, 54, 54], fill=(240, 240, 240))     # pale head on grey
    d.ellipse([26, 26, 38, 38], fill=(255, 255, 255))     # enclosed white detail must survive
    out = np.asarray(key_background(img, bg=HEAD_BG, tol=30))
    assert out[0, 0, 3] == 0, "grey border not keyed"
    assert out[32, 32, 3] == 255, "enclosed white detail was cut"


def test_head_variant_keeps_alpha_and_size():
    head = Image.new("RGBA", (80, 90), (0, 0, 0, 0))
    ImageDraw.Draw(head).ellipse([10, 10, 70, 80], fill=(230, 190, 60, 255))
    for part in ("helm", "helm2", "helm4", "helm5", "helm.A", "helm.B"):
        out = head_variant(head, part)
        assert out.size == head.size, part
        assert out.mode == "RGBA", part
        assert (np.asarray(out)[..., 3] > 8).any(), f"{part} lost its sprite"
