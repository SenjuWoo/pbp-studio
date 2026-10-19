# Measure AI panels for the head box: silhouette agreement, guide extension, palette spread.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from PIL import Image
import numpy as np
from engine import SwarmClient, gen_size
from colorize import colorize_box

TPL = Path(r"C:/Program Files (x86)/Steam/steamapps/common/CastleCrashers/data/pbplocal/violet/painting.png")
X, Y, W, H = (206, 219, 149, 216)
base = Image.open(TPL).convert("RGBA")
crop = base.crop((X, Y, X + W, Y + H))
alpha = np.array(crop.getchannel("A")) > 8
flat, mode = colorize_box(crop.convert("RGB"), "head", (38, 42, 74), (196, 62, 48))
DESIGN = ("samurai warrior, dark indigo lacquered armor, golden crest on the helmet, red cords, "
          "thick black outlines, flat cel shading, cartoon game sprite")
sw = SwarmClient()
sw.ensure_up(log=lambda m: None, wait_s=120)
gw, gh = gen_size(W, H)
out = Path(__file__).resolve().parent / "_out"
out.mkdir(exist_ok=True)


def white_key(rgb, thr=232):
    return np.array(rgb).min(axis=2) < thr


for crea in (0.55, 0.70):
    ai = sw.generate(DESIGN, gw, gh, seed=1234, init_png=flat.resize((gw, gh)),
                     creativity=crea, steps=20,
                     negative="multiple objects, multiple views, collage, grid, duplicated parts, "
                              "text, watermark, full scene, background scenery")
    ai = ai.convert("RGB").resize((W, H), Image.LANCZOS)
    ai.save(out / f"panel_ai_{crea:.2f}.png")
    m = white_key(ai)
    inter = int((m & alpha).sum())
    union = int((m | alpha).sum())
    outside = float((m & ~alpha).sum()) / max(1, int(m.sum()))
    corners = float(np.mean([m[:8, :8].mean(), m[:8, -8:].mean(), m[-8:, :8].mean(), m[-8:, -8:].mean()]))
    print(f"crea {crea}: ai_cov={m.mean():.3f} tmpl_cov={alpha.mean():.3f} IoU={inter/union:.3f} "
          f"outside_guide={outside:.3f} corner_content={corners:.3f}")
    arr = np.array(ai).reshape(-1, 3)[m.reshape(-1)]
    print(f"   mean_rgb={arr.mean(axis=0).round(0)} std={arr.std(axis=0).round(0)}")
