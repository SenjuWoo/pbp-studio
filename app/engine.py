# PBP Studio -- core engine:
#   template discovery (game install -> official download -> cache),
#   local SwarmUI client (auto-start the installed SwarmUI/ComfyUI stack),
#   per-region image generation (img2img over the template box, or no-AI solid colorize),
#   composition into painting.png and writing of the PBP folder (painting.png + pbp.xml).
# Everything here is stdlib + Pillow only, so the app runs on a bare Python install.
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from regions import REGIONS, TEMPLATE_SIZE
from colorize import (colorize_box, parse_palette, palette_words as pal_words,
                      detail_prompt, AI_NEGATIVE, multiply_lines, overlay_edges)
from magics import magic_number

APP_NAME = "PBP-Studio"
APP_VERSION = "0.2.0"
APP_DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
SETTINGS_FILE = APP_DATA / "settings.json"
TEMPLATE_CACHE = APP_DATA / "template" / "painting.png"
OFFICIAL_TEMPLATE_URL = "https://www.castlecrashers.com/PBP/painting.png"

SWARM_URL_DEFAULT = "http://localhost:7801"
SWARM_ROOT_CANDIDATES = [
    os.environ.get("SWARMUI_ROOT", ""),
    r"S:\Misc\SwarmUI",
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "SwarmUI"),
    r"C:\SwarmUI",
    r"D:\SwarmUI",
    r"S:\SwarmUI",
]

STYLE_SUFFIX = ("Castle Crashers video game art style, 2D cartoon game sprite, "
                "thick clean black outlines, flat bright colors, simple cel shading, "
                "white background, no text")
NEGATIVE = ("text, watermark, signature, photo, realistic, 3d render, blurry, low quality, scenery, "
            "background, multiple objects, multiple views, collage, grid, duplicated parts, extra heads, clones")


# ---------------------------------------------------------------- settings
_default_settings = {
    "output_dir": str(Path.home() / "Documents" / "PBP-Studio"),
    "swarm_url": SWARM_URL_DEFAULT,
    "swarm_root": "",
    "template_path": "",
    "game_dir": "",
    "creativity": 0.4,
    "steps": 20,
    "name": "",
    "magic": "Poison",
}


def load_settings():
    s = dict(_default_settings)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return s


def save_settings(patch: dict):
    s = load_settings()
    s.update({k: v for k, v in patch.items() if v is not None})
    APP_DATA.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_FILE)
    return s


# ---------------------------------------------------------------- game / template discovery
def find_game_dir():
    """Locate the Castle Crashers install (registry -> libraryfolders.vdf -> known paths)."""
    roots = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam = winreg.QueryValueEx(k, "SteamPath")[0]
        roots.append(Path(steam))
    except Exception:
        pass
    roots.append(Path(r"C:\Program Files (x86)\Steam"))
    for root in list(roots):
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
                    p = Path(m.group(1).replace("\\\\", "\\"))
                    if p not in roots:
                        roots.append(p)
            except Exception:
                pass
    for root in roots:
        cand = root / "steamapps" / "common" / "CastleCrashers"
        if (cand / "castle.exe").exists():
            return str(cand)
    return ""


def _valid_template(path: Path):
    try:
        im = Image.open(path)
        if im.size != (TEMPLATE_SIZE, TEMPLATE_SIZE):
            return False
        # spot-check: the first head box should be mostly white (draw area)
        x, y, w, h = REGIONS[0]["rect"]
        crop = im.convert("RGB").crop((x, y, x + w, y + h))
        px = list(crop.getdata())
        whiteish = sum(1 for r, g, b in px if min(r, g, b) > 200)
        return whiteish / len(px) > 0.3
    except Exception:
        return False


def resolve_template(settings=None):
    """Return (path, source) for a valid 2048x2048 template; downloads the official one into
    the app cache if neither a configured path nor the game install has it. Never bundled/redistributed."""
    settings = settings or load_settings()
    p = settings.get("template_path")
    if p and _valid_template(Path(p)):
        return Path(p), "custom path"
    game = settings.get("game_dir") or find_game_dir()
    if game:
        gp = Path(game) / "data" / "pbplocal" / "violet" / "painting.png"
        if _valid_template(gp):
            return gp, "game install"
    if _valid_template(TEMPLATE_CACHE):
        return TEMPLATE_CACHE, "app cache"
    TEMPLATE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TEMPLATE_CACHE.with_suffix(".download")
    try:
        with urllib.request.urlopen(OFFICIAL_TEMPLATE_URL, timeout=60) as r:
            tmp.write_bytes(r.read())
        os.replace(tmp, TEMPLATE_CACHE)
    except Exception as e:
        raise RuntimeError(
            f"Could not find the template: no game install detected and the official download "
            f"failed ({e}). Point the app at the game folder or a painting.png copy in the UI.") from e
    if not _valid_template(TEMPLATE_CACHE):
        raise RuntimeError("Downloaded template failed validation (not 2048x2048 or wrong layout).")
    return TEMPLATE_CACHE, "official download"


# ---------------------------------------------------------------- SwarmUI client
class SwarmClient:
    """Minimal synchronous client for the user's local SwarmUI (port 7801)."""

    def __init__(self, url=SWARM_URL_DEFAULT, root=""):
        self.url = url.rstrip("/")
        self.root = root or self._find_root()
        self._session = None
        self._lock = threading.Lock()

    def _find_root(self):
        for c in SWARM_ROOT_CANDIDATES:
            if c and (Path(c) / "src" / "bin" / "live_release" / "SwarmUI.exe").exists():
                return c
        return ""

    # --- lifecycle -------------------------------------------------
    def is_up(self, timeout=3.0):
        try:
            self._post("/API/GetNewSession", {}, timeout=timeout)
            return True
        except Exception:
            return False

    def ensure_up(self, log=print, wait_s=240):
        if self.is_up():
            return True
        if not self.root:
            raise RuntimeError("SwarmUI not running and no install found to start. "
                               "Set the SwarmUI folder in settings (swarm_root).")
        exe = Path(self.root) / "src" / "bin" / "live_release" / "SwarmUI.exe"
        log(f"Starting SwarmUI from {self.root} ...")
        env = dict(os.environ)
        env.setdefault("ASPNETCORE_ENVIRONMENT", "Production")
        env.setdefault("ASPNETCORE_URLS", "http://localhost:7801")
        env["DOTNET_CLI_UI_LANGUAGE"] = "en"
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        subprocess.Popen([str(exe)], cwd=self.root, env=env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **kwargs)
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if self.is_up():
                return True
            time.sleep(3)
        raise RuntimeError(f"SwarmUI did not come up within {wait_s}s")

    # --- http ------------------------------------------------------
    def _post(self, path, body, timeout=120):
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def session(self):
        with self._lock:
            if self._session is None:
                self._session = self._post("/API/GetNewSession", {})["session_id"]
            return self._session

    # --- generation ------------------------------------------------
    def generate(self, prompt, width, height, seed=0, init_png=None, creativity=0.4,
                 steps=20, cfg=6.0, model="woomixAnima_v15", timeout=900, negative=None):
        """Run one img2img (or txt2img when init_png is None). Returns a PIL RGB image."""
        body = {
            "session_id": self.session(),
            "model": model,
            "prompt": prompt,
            "negativeprompt": negative or NEGATIVE,
            "width": int(width), "height": int(height),
            "steps": int(steps), "cfgscale": float(cfg),
            "seed": int(seed) if seed else -1,
            "images": 1,
        }
        if init_png is not None:
            buf = io.BytesIO()
            init_png.save(buf, "PNG")
            body["initimage"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
            body["initimagecreativity"] = float(creativity)
        t_req = time.time()
        res = self._post("/API/GenerateText2Image", body, timeout=timeout)
        imgs = res.get("images") or []
        if not imgs:
            raise RuntimeError(f"SwarmUI returned no images: {json.dumps(res)[:300]}")
        entry = imgs[0]
        if isinstance(entry, dict):                       # base64 payload form
            data = entry.get("data") or entry.get("image")
            if data:
                return Image.open(io.BytesIO(base64.b64decode(data.split(",")[-1]))).convert("RGB")
            entry = entry.get("path", "")
        rel = str(entry)
        if rel.startswith("View/"):
            rel = rel[len("View/"):]
        local = Path(self.root) / "Output" / rel
        # SwarmUI can answer a moment before the file is flushed -- wait, then fall back to
        # the newest png in that folder (we are the only producer while generating).
        t0 = time.time()
        while not local.exists() and time.time() - t0 < 25:
            time.sleep(0.4)
        if not local.exists():
            folder = local.parent
            try:
                cands = [p for p in folder.glob("*.png") if p.stat().st_mtime >= t_req - 2]
                if cands:
                    local = max(cands, key=lambda p: p.stat().st_mtime)
            except OSError:
                pass
        if not local.exists():
            raise RuntimeError(f"Generated image file not found: {local}")
        return Image.open(local).convert("RGB")

    def output_path_of(self, entry):
        rel = str(entry)
        if rel.startswith("View/"):
            rel = rel[len("View/"):]
        return Path(self.root) / "Output" / rel


# ---------------------------------------------------------------- pipeline
def slugify(name: str, fallback="character"):
    s = re.sub(r"[^A-Za-z0-9 _-]+", "", name).strip().replace(" ", "_")
    return s[:48] or fallback


def pbp_xml(displayname: str, magic_num: int) -> str:
    """Match the shipped violet/pbp.xml layout (CRLF, indented magictype), XML-escaped name."""
    from xml.sax.saxutils import escape
    safe = escape(displayname, {'"': "&quot;", "'": "&apos;"})
    return ('<?xml version="1.0" encoding="UTF-8"?>\r\n'
            f'<character displayname="{safe}">\r\n'
            f'    <magictype>{int(magic_num)}</magictype>\r\n'
            '</character>\r\n')


def build_part_prompt(design: str, role: str, extra_style: str = ""):
    frag = ROLE_PROMPTS.get(role, "part of the character")
    bits = [f"{design.strip()}, {frag}",
            "single isolated object, one centered drawing, whole object visible"]
    if extra_style.strip():
        bits.append(extra_style.strip())
    bits.append(STYLE_SUFFIX)
    return ", ".join(bits)


def prep_init(crop: Image.Image, gw: int, gh: int) -> Image.Image:
    """Frame the template art so the subject nearly fills a white canvas of the gen size.
    Prevents the model from filling empty canvas with extra copies of the object."""
    rgb = crop.convert("RGB")
    # bbox of non-white art pixels
    gray = rgb.convert("L")
    mask = gray.point(lambda v: 255 if v < 235 else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return rgb.resize((gw, gh), Image.LANCZOS)
    subject = rgb.crop(bbox)
    sc = min(gw * 0.88 / subject.width, gh * 0.88 / subject.height)
    subject = subject.resize((max(1, int(subject.width * sc)), max(1, int(subject.height * sc))), Image.LANCZOS)
    canvas = Image.new("RGB", (gw, gh), (255, 255, 255))
    canvas.paste(subject, ((gw - subject.width) // 2, (gh - subject.height) // 2))
    return canvas


def gen_size(w, h, target_min=512, cap=1024):
    """Upscale box to a diffusion-friendly size (min side ~ target_min, /8 aligned)."""
    scale = max(1.0, target_min / max(w, h))
    sw, sh = int(w * scale), int(h * scale)
    if max(sw, sh) > cap:
        k = cap / max(sw, sh)
        sw, sh = int(sw * k), int(sh * k)
    return (max(64, sw // 8 * 8), max(64, sh // 8 * 8))


class Job:
    def __init__(self, jid, params):
        self.id = jid
        self.params = params
        self.state = "queued"          # queued|running|done|error|cancelled
        self.phase = "queued"
        self.done = 0
        self.total = 0
        self.current = ""
        self.logs = []
        self.error = ""
        self.cancel = threading.Event()
        self.job_dir = APP_DATA / "jobs" / jid
        self.result = {}

    def say(self, msg):
        self.logs.append(f"{time.strftime('%H:%M:%S')}  {msg}")
        if len(self.logs) > 400:
            del self.logs[:100]

    def status(self):
        return {"id": self.id, "state": self.state, "phase": self.phase,
                "done": self.done, "total": self.total, "current": self.current,
                "logs": self.logs[-60:], "error": self.error, "result": self.result}


class Engine:
    def __init__(self):
        self.settings = load_settings()
        self.swarm = SwarmClient(self.settings.get("swarm_url", SWARM_URL_DEFAULT),
                                 self.settings.get("swarm_root", ""))
        self.template_path = None
        self.template_source = ""
        self._job_lock = threading.Lock()
        self.job = None

    # --- helpers ---------------------------------------------------
    def status(self):
        template = {"ok": False, "path": "", "source": ""}
        try:
            p, src = resolve_template(self.settings)
            self.template_path, self.template_source = p, src
            template = {"ok": True, "path": str(p), "source": src}
        except Exception as e:
            template["error"] = str(e)
        game = self.settings.get("game_dir") or find_game_dir()
        return {
            "app": {"name": APP_NAME, "version": APP_VERSION},
            "swarm": {"url": self.swarm.url, "up": self.swarm.is_up(), "root": self.swarm.root},
            "template": template,
            "game_dir": game,
            "pbp_local": str(Path(game) / "data" / "pbplocal") if game else "",
            "settings": self.settings,
        }

    def start_job(self, params):
        with self._job_lock:
            if self.job and self.job.state in ("queued", "running"):
                raise RuntimeError("A job is already running")
            jid = time.strftime("%Y%m%d-%H%M%S")
            job = Job(jid, params)
            self.job = job
            t = threading.Thread(target=self._run_job, args=(job,), daemon=True)
            t.start()
            return job

    def cancel_job(self):
        if self.job:
            self.job.cancel.set()
        return True

    # --- the pipeline ----------------------------------------------
    def _run_job(self, job: Job):
        p = job.params
        try:
            job.state = "running"
            job.job_dir.mkdir(parents=True, exist_ok=True)

            # 1. template
            job.phase = "template"
            tpl_path, src = resolve_template(self.settings)
            self.template_path, self.template_source = tpl_path, src
            job.say(f"Template: {tpl_path} ({src})")
            base = Image.open(tpl_path).convert("RGBA")

            # 2. pick regions
            mode = p.get("mode", "full")
            if mode == "sample":
                seen, regions = set(), []
                for r in REGIONS:
                    if r["role"] not in seen:
                        seen.add(r["role"])
                        regions.append(r)
            else:
                regions = list(REGIONS)
            job.total = len(regions)

            solid = p.get("engine", "ai") == "solid"
            design = p.get("design", "").strip() or "a heroic cartoon knight"
            extra = p.get("extra_style", "")
            creativity = float(p.get("creativity", self.settings.get("creativity", 0.4)))
            steps = int(p.get("steps", self.settings.get("steps", 20)))
            seed_base = int(p.get("seed", 0) or 0)
            base_col, accent_col = parse_palette(
                design + " " + extra, p.get("color1", "#3fae4a"), p.get("color2", "#c9303a"))
            pal = pal_words(base_col, accent_col) + ((", " + extra) if extra else "")
            job.say(f"Palette: {pal}")

            if not solid:
                job.phase = "backend"
                job.say("Checking local AI backend (SwarmUI)...")
                self.swarm.ensure_up(log=job.say)
                job.say("AI backend ready.")

            canvas = base.copy()
            sheet_cells = []
            total = len(regions)
            for i, region in enumerate(regions, 1):
                if job.cancel.is_set():
                    job.state, job.phase = "cancelled", "cancelled"
                    job.say("Cancelled.")
                    return
                x, y, w, h = region["rect"]
                part, role = region["part"], region["role"]
                job.current = f"{part} ({role})"
                job.phase = "generating"
                job.say(f"[{i}/{total}] {part} ({role}) {w}x{h}"
                        + ("" if solid else f" - AI detail {creativity:.2f}"))
                crop = base.crop((x, y, x + w, y + h)).convert("RGB")
                # 1) procedural colorize inside the official line art (perfect geometry)
                flat, bmode = colorize_box(crop, role, base_col, accent_col)
                if solid:
                    out = flat
                else:
                    # 2) AI detail pass at low creativity, then lines stamped back
                    prompt = detail_prompt(design, role, pal)
                    gw, gh = gen_size(w, h)
                    init_up = flat.resize((gw, gh), Image.LANCZOS)
                    crea = min(0.75, max(0.2, creativity))
                    seed = (seed_base + i) if seed_base else 0
                    ai = self.swarm.generate(prompt, gw, gh, seed=seed, init_png=init_up,
                                             creativity=crea, steps=steps, negative=AI_NEGATIVE)
                    ai = ai.convert("RGB").resize((w, h), Image.LANCZOS)
                    if bmode == "lineart":
                        # guard: if the model erased the colorization, keep the procedural fill
                        wf_ai, wf_flat = self._white_frac(ai), self._white_frac(flat)
                        if wf_ai > 0.45 and wf_ai > wf_flat + 0.12:
                            job.say(f"    {part}: model erased the colors, keeping clean fill")
                            out = flat
                        else:
                            out = multiply_lines(ai, crop)
                    else:
                        out = overlay_edges(ai, crop)
                out = out.convert("RGBA")
                canvas.paste(out, (x, y))
                sheet_cells.append((part, out.copy()))
                job.done = i
                # live preview
                prev = canvas.resize((1024, 1024), Image.LANCZOS)
                prev.save(job.job_dir / "live_preview.png")
                job.result = {"preview": str(job.job_dir / "live_preview.png"),
                              "preview_name": f"preview_{job.done}"}

            # 3. compose + save outputs
            job.phase = "compose"
            export_dir = Path(p.get("output_dir") or self.settings["output_dir"])
            export_dir.mkdir(parents=True, exist_ok=True)
            skill = Path(__file__).resolve().parent  # noqa  (serve dir resolved in server)
            job.say(f"Writing {export_dir}")
            tmp_png = job.job_dir / "painting.png"
            canvas.convert("RGBA").save(tmp_png, "PNG", optimize=True)
            master = job.job_dir / "painting_master.png"
            shutil.copyfile(tmp_png, master)

            name = (p.get("name") or "Custom Character").strip()[:40]
            magic_num = magic_number(p.get("magic") or "Poison")
            # atomic-ish write into the folder the game watches
            shutil.copyfile(tmp_png, export_dir / "painting.png.tmp")
            os.replace(export_dir / "painting.png.tmp", export_dir / "painting.png")
            xml = pbp_xml(name, magic_num)
            (export_dir / "pbp.xml.tmp").write_text(xml, encoding="utf-8", newline="")
            os.replace(export_dir / "pbp.xml.tmp", export_dir / "pbp.xml")

            # contact sheet of generated parts
            if sheet_cells:
                cols = 6
                cell = 200
                rows = (len(sheet_cells) + cols - 1) // cols
                sheet = Image.new("RGB", (cols * cell, rows * cell), (24, 24, 28))
                d = ImageDraw.Draw(sheet)
                for k, (part, img) in enumerate(sheet_cells):
                    sc = min((cell - 26) / img.width, (cell - 26) / img.height)
                    th = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))))
                    cx, cy = (k % cols) * cell, (k // cols) * cell
                    sheet.paste(th, (cx + 13, cy + 22), th)
                    d.text((cx + 8, cy + 6), part, fill=(120, 220, 120))
                sheet.save(job.job_dir / "pieces_sheet.png")

            job.result = {
                "painting": str(master),
                "preview": str(master),
                "sheet": str(job.job_dir / "pieces_sheet.png"),
                "export_dir": str(export_dir),
                "name": name,
                "magic": p.get("magic"),
                "magic_num": magic_num,
            }
            job.state, job.phase = "done", "done"
            job.say(f"Done. Folder ready: {export_dir}")
        except Exception as e:
            job.state, job.phase = "error", "error"
            job.error = f"{type(e).__name__}: {e}"
            job.say("ERROR: " + job.error)

    @staticmethod
    def _solid_region(crop: Image.Image, color1: str, color2: str, role: str) -> Image.Image:
        """No-AI fallback: multiply the template art with a flat color (white->color, black->black)."""
        try:
            solid = Image.new("RGB", crop.size, color1 if role not in ("weapon", "banner") else color2)
        except Exception:
            solid = Image.new("RGB", crop.size, "#3fae4a")
        rgb = crop.convert("RGB")
        return ImageChops.multiply(rgb, solid).convert("RGBA")

    @staticmethod
    def _white_frac(img: Image.Image) -> float:
        """Fraction of near-white pixels -- used to detect a model that erased the fill."""
        hist = img.convert("L").histogram()
        total = sum(hist) or 1
        return sum(hist[236:]) / total
