# PBP Studio -- core engine:
#   template discovery (game install -> official download -> cache),
#   local SwarmUI client (auto-start the installed SwarmUI/ComfyUI stack),
#   the job runner (master design -> pieces, see pipeline.py) and the writer of the PBP folder
#   (painting.png + pbp.xml). Stdlib + Pillow + numpy + scipy only.
import base64
import io
import random
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

from PIL import Image, ImageDraw
import numpy as np

from regions import REGIONS, TEMPLATE_SIZE
from magics import magic_number

APP_NAME = "PBP-Studio"
APP_VERSION = "0.9.2"
APP_DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
SETTINGS_FILE = APP_DATA / "settings.json"
TEMPLATE_CACHE = APP_DATA / "template" / "painting.png"
OFFICIAL_TEMPLATE_URL = "https://www.castlecrashers.com/PBP/painting.png"

DEFAULT_MODEL = "woomixAnima_v15"
CONTROLNET_MODEL = "anima-lllite-lineart-1.safetensors"   # Anima LLLite lineart, locks the template pose
SWARM_URL_DEFAULT = "http://localhost:7801"
SWARM_ROOT_CANDIDATES = [
    os.environ.get("SWARMUI_ROOT", ""),
    r"S:\Misc\SwarmUI",
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "SwarmUI"),
    r"C:\SwarmUI",
    r"D:\SwarmUI",
    r"S:\SwarmUI",
]


# ---------------------------------------------------------------- settings
_default_settings = {
    "output_dir": str(Path.home() / "Documents" / "PBP-Studio"),
    "swarm_url": SWARM_URL_DEFAULT,
    "swarm_root": "",
    "template_path": "",
    "game_dir": "",
    "backend": "klein",             # klein | qwen | anima
    "steps": 40,                    # Anima (design step and the Anima-only model), tuned: docs/TUNING.md
    "cfg": 4.0,
    "sampler": "er_sde",
    "controlnet": True,
    "controlnet_strength": 1.0,
    "scheduler": "simple",
    "name": "",
    "magic": "Poison",
    "settings_version": 4,
}
OLD_DEFAULTS = {"sampler": "rk_beta", "scheduler": "beta57", "cfg": 3.0}   # shipped up to 0.8.0, tuned out in 0.9.0


def load_settings():
    s = dict(_default_settings)
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return s
    if int(raw.get("settings_version", 0)) < 4:
        # an untouched old default is not a choice: let the tuned default replace it
        raw = {k: v for k, v in raw.items() if OLD_DEFAULTS.get(k, object()) != v}
        raw["settings_version"] = 4
    s.update(raw)
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
        px = np.asarray(crop)
        return float((px.min(axis=2) > 200).mean()) > 0.3
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
        self._ready = False
        self._lock = threading.Lock()

    def wait_ready(self, log=print, timeout_s=180, poll_s=4):
        """Wait until a ComfyUI backend is running AND can actually generate.

        "No backends available" is what a freshly started or crashed SwarmUI returns;
        without this check every piece silently falls back to a flat fill.
        """
        if self._ready:
            return True
        t0 = time.time()
        last = "no response"
        restarted = False
        while time.time() - t0 < timeout_s:
            try:
                backends = self._post("/API/ListBackends", {"session_id": self.session()}, timeout=15)
                states = {k: v.get("status") for k, v in backends.items() if isinstance(v, dict)}
                if any(s == "running" for s in states.values()):
                    # running is not enough: prove it with a tiny real generation
                    try:
                        r = self._post("/API/GenerateText2Image", {
                            "session_id": self.session(), "model": DEFAULT_MODEL,
                            "prompt": "ok", "width": 128, "height": 128, "steps": 2,
                            "cfgscale": 5, "seed": 1, "images": 1}, timeout=120)
                        if r.get("images"):
                            self._ready = True
                            log("AI backend ready.")
                            return True
                        last = str(r)[:150]
                    except Exception as e:
                        last = str(e)[:150]
                else:
                    last = f"backends: {states or 'none'}"
                    if "errored" in states.values() and not restarted:
                        # SwarmUI's ComfyUI process dies when its session is interrupted; one restart fixes it
                        restarted = True
                        log("AI backend errored - restarting it once...")
                        self._post("/API/RestartBackends", {"session_id": self.session(), "backend": "all"}, timeout=60)
            except Exception as e:
                last = str(e)[:150]
            if time.time() - t0 > 8:
                log(f"Waiting for the AI backend... ({last})")
            time.sleep(poll_s)
        raise RuntimeError(f"AI backend never became ready ({last})")

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

    def render(self, prompt, w, h, model, steps, cfg, seed, negative="", images=None,
               controlnet=None, controlnet_strength=1.0, sampler="", scheduler="", timeout=900):
        """One generation for any model: txt2img, reference-image edit (Klein/Qwen) or ControlNet."""
        body = {"session_id": self.session(), "model": model, "prompt": prompt,
                "negativeprompt": negative, "width": int(w), "height": int(h),
                "steps": int(steps), "cfgscale": float(cfg), "seed": int(seed) or -1, "images": 1}
        if sampler:
            body["sampler"] = sampler
        if scheduler:
            body["scheduler"] = scheduler
        if images:                      # edit models: reference images, "|"-separated data URLs
            body["promptimages"] = "|".join(image_data_url(im) for im in images)
        if controlnet is not None:
            body.update({"controlnetimageinput": image_data_url(controlnet),
                         "controlnetmodel": CONTROLNET_MODEL,
                         "controlnetstrength": float(controlnet_strength),
                         "controlnetpreprocessor": "None"})
        return self._run(body, timeout)

    def list_models(self):
        r = self._post("/API/ListModels", {"session_id": self.session(), "path": "", "depth": 3,
                                           "subtype": "Stable-Diffusion", "sortBy": "Name"})
        # bare names: a model in a sub-folder is listed as "Anima/woomixAnima_v15.safetensors"
        return [f["name"].replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0] for f in r.get("files", [])]

    def interrupt(self):
        """Best effort: stop whatever SwarmUI is still generating so a retry does not queue behind a hung call."""
        try:
            self._post("/API/InterruptAll", {"session_id": self.session(), "other_sessions": True}, timeout=15)
        except Exception:
            pass

    def _run(self, body, timeout):
        t_req = time.time()
        try:
            res = self._post("/API/GenerateText2Image", body, timeout=timeout)
        except Exception as e:
            if "timed out" in str(e):
                self.interrupt()
            raise
        if res.get("error"):
            raise RuntimeError(str(res["error"])[:300])
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


SHEET_ROLE_ORDER = {"head": 0, "body": 1, "weapon": 2, "shield": 3, "body_big": 4,
                    "limb": 5, "hudicon": 6, "banner": 7, "bob": 8}


def sheet_order(cells, regions=None):
    """Contact sheet in template reading order: heads, bodies, gear, giants, limbs, UI."""
    from regions import REGIONS as _R

    regions = regions or _R
    pos = {r["part"]: (SHEET_ROLE_ORDER.get(r["role"], 9), r["rect"][1], r["rect"][0])
           for r in regions}
    return sorted(cells, key=lambda pc: pos.get(pc[0], (9, 0, 0)))


def image_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


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
            "models": self._installed_models(),
            "template": template,
            "game_dir": game,
            "pbp_local": str(Path(game) / "data" / "pbplocal") if game else "",
            "settings": self.settings,
        }

    def _installed_models(self):
        """Which backends can run right now: {klein, qwen, anima: bool}; empty while SwarmUI is down."""
        import pipeline

        try:
            have = set(self.swarm.list_models())
        except Exception:
            return {}
        return {"klein": pipeline.EDIT_MODELS["klein"] in have, "qwen": pipeline.EDIT_MODELS["qwen"] in have,
                "anima": pipeline.ANIMA_MODEL in have}

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
        """Master design -> every piece (pipeline.py) -> painting.png + pbp.xml."""
        import pipeline

        p = job.params
        try:
            job.state = "running"
            job.job_dir.mkdir(parents=True, exist_ok=True)
            job.phase = "template"
            tpl_path, src = resolve_template(self.settings)
            self.template_path, self.template_source = tpl_path, src
            job.say(f"Template: {tpl_path} ({src})")
            base = Image.open(tpl_path).convert("RGBA")
            design = (p.get("design", "").strip() or "a heroic cartoon knight")
            if p.get("extra_style"):
                design += ", " + p["extra_style"].strip()
            backend = p.get("backend") or self.settings.get("backend") or "klein"
            seed = int(p.get("seed", 0) or 0) or random.randint(1, 2**31 - 1)
            job.say(f"Backend: {backend}   seed: {seed}")
            job.phase = "backend"
            self.swarm.ensure_up(log=job.say)
            self.swarm.wait_ready(log=job.say, timeout_s=240)
            last = APP_DATA / "last_master.png"
            if p.get("reuse_master") and last.exists() and not p.get("master_png"):
                p = dict(p, master_png=str(last))
            canvas, cells = pipeline.run(self, job, base, p, design, seed, backend)
            shutil.copyfile(job.job_dir / "master.png", last)
            self._export(job, canvas, cells, p)
        except pipeline.Cancelled:
            job.state, job.phase = "cancelled", "cancelled"
            job.say("Cancelled - nothing was written.")
        except Exception as e:
            job.state, job.phase = "error", "error"
            job.error = f"{type(e).__name__}: {e}"
            job.say("ERROR: " + job.error)

    def _export(self, job, canvas, sheet_cells, p):
        """Write painting.png + pbp.xml into the output folder and a contact sheet into the job dir."""
        job.phase = "compose"
        export_dir = Path(p.get("output_dir") or self.settings["output_dir"])
        export_dir.mkdir(parents=True, exist_ok=True)
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
            for k, (part, img) in enumerate(sheet_order(sheet_cells)):
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
            "master": str(job.job_dir / "master.png"),
            "export_dir": str(export_dir),
            "name": name,
            "magic": p.get("magic"),
            "magic_num": magic_num,
        }
        job.state, job.phase = "done", "done"
        job.say(f"Done. Folder ready: {export_dir}")
