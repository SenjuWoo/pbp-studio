# PBP Studio

Turn a text idea into a **Castle Crashers custom character** for the *Painter Boss Paradise* DLC —
local, offline-friendly, and as automatic as possible.

You type something like *"green knight with a red plume, gold trim"*, pick a name and a magic, press
**Generate character**, and the app:

1. reads the palette out of your description,
2. flat-colors every one of the 39 official template pieces **inside the game's own line art**
   (so everything stays perfectly aligned with the game's sprites),
3. runs a local AI detail pass over each piece (when a local SwarmUI/ComfyUI install is available)
   for shading and trim, then stamps the official lines back on top,
4. writes `painting.png` + `pbp.xml` into a folder the in-game painter can load and hot-reload.

The result is a normal PBP character folder — you can open the game, point the painter at the folder,
see it live, test it, and publish it to the Steam Workshop from inside the game.

## Requirements

- Windows 10/11, Python 3.10+ (the launcher creates a local `.venv`, nothing system-wide).
- Optional but recommended: a local [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI) install
  with a Stable Diffusion / SDXL model — the app auto-detects it, auto-starts it on port 7801 and
  uses it for the AI detail pass. Without it the app still works in **No-AI flat colors** mode.
- Castle Crashers with the *Painter Boss Paradise* DLC for actually loading/publishing the character.

## Run

Double-click `START.bat` (first run installs Pillow/numpy/scipy into `.venv`).
The UI opens at <http://127.0.0.1:8777/>.

1. **Describe your character** — the first color you name becomes the armor color, the second the
   accent (plume/belt/trim). *AI detail strength* controls how much the model is allowed to restyle:
   keep it low (default 0.40) so it paints inside the official lines instead of redrawing the knight.
2. **Name & magic** — 26 in-game magics.
3. **Output folder** — pick the folder the game will watch. Press *Generate character*.
4. In game: **Painter Boss Paradise → Browse Folder** → pick that folder. The preview updates live.
   Test the character and publish to the Workshop from the in-game menu.

`Install into game (pbplocal)` copies the finished folder into
`CastleCrashers\data\pbplocal\<name>\` next to the shipped `violet` sample.

## How it works (short version)

The official template is **line art**: black outlines on white, limbs pre-shaded. The game composes
the knight from those exact boxes, so the art inside each box must keep the template geometry.
PBP Studio therefore colorizes the line art procedurally first (enclosed-region fill with the
parsed palette), and only then lets the AI add detail via img2img at low creativity, multiplying the
original line art back over the result. The AI can restyle, but it can never move the character.

- `app/regions.py` — the 39 draw-boxes of the official 2048×2048 template with their roles
- `app/colorize.py` — palette parsing, enclosed-region fill, shading recolor, line stamping
- `app/engine.py` — template discovery, SwarmUI client, job pipeline, `painting.png` + `pbp.xml` writer
- `app/magics.py` — the `<magictype>` table (indexes verified against the shipped template + game exe)
- `app/server.py` — local HTTP/JSON server (binds 127.0.0.1 only)
- `docs/HOW-IT-WAS-MADE.txt` — the format research and why the pipeline is built this way

The template is never redistributed: the app uses your installed game's copy, or downloads the
official one from `castlecrashers.com`, and caches it in `%LOCALAPPDATA%\PBP-Studio`.

## Notes

- Everything runs locally; no account, no key, no upload. The only network use is the optional
  one-time template download when no game install is found.
- The `pbp.xml` written by the app is the same format the game itself uses
  (`<character displayname="..."><magictype>N</magictype></character>`).
- Workshop publishing/validation stays in-game (the game owns the upload and the PKTB container).
- Castle Crashers and Painter Boss Paradise are © The Behemoth. This is an unofficial fan tool.
