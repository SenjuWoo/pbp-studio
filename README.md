# PBP Studio

Turn a text idea into a **Castle Crashers custom character** for the *Painter Boss Paradise* DLC —
local, offline-friendly, and as automatic as possible.

You type something like *"green knight with a red plume, gold trim"*, pick a name and a magic, press
**Generate character**, and the app:

1. reads the palette out of your description,
2. flat-colors every one of the 39 official template pieces inside the game's own line art (the
   fallback, and the starting point for the AI),
3. redraws each piece with the local AI at your chosen strength, cuts the white background out so
   the sprite is transparent like the official template, and keeps the template's pose and scale,
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
   accent (plume/belt/trim). If you name no colour at all, the first piece is generated freely and
   its palette is reused for the rest, so "taco boy" comes out taco-coloured instead of default green. *AI strength* is how far the model may redraw each piece: 0.40 stays
   close to the official line art, 0.55 (default) adds real detail, above 0.7 it starts inventing.
   *Steps* (40), *CFG* (3.0), *Sampler* (rk_beta) and *Scheduler* (beta57) are sent to SwarmUI and
   can be changed per job; empty sampler/scheduler means "model default", and if your SwarmUI does
   not have them the job falls back to the model defaults with a warning. *Lock colours* (off by default) snaps every piece to the palette - more consistent, flatter art.
   *Seed* is shared by every piece - leave it empty for a random one per character, or pin it to reproduce a result.
2. **Name & magic** — 26 in-game magics.
3. **Output folder** — pick the folder the game will watch. Press *Generate character*.
4. In game: **Painter Boss Paradise → Browse Folder** → pick that folder. The preview updates live.
   Test the character and publish to the Workshop from the in-game menu.

`Install into game (pbplocal)` copies the finished folder into
`CastleCrashers\data\pbplocal\<name>\` next to the shipped `violet` sample.

## How it works (short version)

The official template is **line art on a transparent background**: the game only draws the pixels
that have alpha, so a piece painted on opaque white would show as a white box in game. PBP Studio
therefore colorizes the line art procedurally first (enclosed-region fill with the parsed palette),
seeds an img2img pass with that fill so the pose and scale stay put, and cuts the background out of
the result - near-white pixels connected to the box edge become transparent, while enclosed white
details (eyes, trim) stay opaque. With no AI backend the procedural fill is used as-is.

Before generating, the app waits for a SwarmUI backend that can actually produce an image (a tiny
test render). If the backend is dead it stops with an error and writes nothing, instead of quietly
producing a flat character.

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
