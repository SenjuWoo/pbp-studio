# Changelog

## 0.3.5 - no more green default
- When the description names no colour ("Taco boy"), the app no longer forces the green/red default
  onto every piece. The first piece is generated freely, its palette is extracted, and every other
  piece is painted and locked to that palette - so the character keeps the colours the subject implies.
- Solid (no-AI) mode still uses the named colours or the archetype palette.

## 0.3.4 - one character, not 39
- All pieces now share one seed per job (it was a fresh random seed per piece, which is why the
  helmet, body and arms looked like different characters).
- AI output is snapped to the character's palette (outline, dark/base/light, accent, white), so a
  piece can no longer invent its own colours.
- Prompt asks for the same design in every piece.

## 0.3.3 - never ship a flat character again
- The app now waits for a ComfyUI backend that can actually generate (a tiny test image), not just
  for SwarmUI's web port. "No backends available!" previously failed all 39 pieces in silence and
  wrote a flat-fill character.
- Each piece is retried once; if four pieces in a row fail the job stops with a clear error and
  writes nothing, instead of producing a character with no AI art.
- Existing settings that still held the old 0.40 default are moved to 0.55 once, even if an already
  open page tries to save 0.40 again.

## 0.3.2 - the launcher always starts
- Fixed: after closing the window the port could still be in TIME_WAIT, and the strict bind made
  START.bat fail on the next launch. The server now probes for a running instance first (and just
  opens the browser), then binds normally, which is what Windows needs for an immediate restart.

## 0.3.1 - one server, quiet disconnects
- The server refuses to share its port: a second instance now exits with a clear message instead
  of silently binding the same address (two servers on 8777 made the UI answer inconsistently).
- Browser tab closes and refreshes no longer print `ConnectionAbortedError` tracebacks.

## 0.3.0 - real sprites, transparent background
- Pieces are now cut out: near-white background connected to the box border becomes transparent,
  enclosed white details stay opaque. The official template is transparent inside its boxes, so the
  old opaque white output would have shown as white rectangles around every part in game.
- The AI pass now redraws each piece at the requested strength instead of barely tinting the guide;
  the procedural fill is used as the init image and as the fallback, and blank/erased results are
  rejected automatically.
- Colour pickers only override the description when you actually change them; when no colour is
  named, a scheme matching the subject is used (samurai -> indigo/gold, ninja -> black/red, ...)
  instead of the old green/red default.
- Default AI strength 0.40 -> 0.55, slider range up to 0.80.

## 0.2.1 - fix: UI refused to load
- The static UI was being filtered by the same path guard used for generated files, so `/` returned
  `{"error": "path not allowed"}` on a fresh launch. The shipped `app/static` folder is now an
  allowed root, and the guard uses a real path-containment check instead of a string prefix.

## 0.2.0 - first working build
- Line-art-aware character generation: procedural flat colorization of all 39 official template
  boxes (adaptive region fill, enclosed-area palette assignment, shading-preserving limb recolor),
  then an optional local-AI detail pass at low creativity with the official lines stamped back on top.
- Palette parsed from the character description (armor / accent), with color pickers as fallback.
- Local SwarmUI client: auto-detect install, auto-start, per-piece img2img, file-flush safe reads.
- Anti-erasure guard: if the model whitens a piece, the clean procedural fill is kept instead.
- Magic table for the in-game `<magictype>` value; name + magic written to `pbp.xml`.
- Web UI: single page, live per-piece preview, progress log, magic grid, folder picker,
  install-into-game (`data/pbplocal`), settings panel.
- No-AI offline mode (flat colors) when no local image backend is running.
- Local-only server (127.0.0.1), no telemetry, no uploads.

## 0.1.0 - research build
- Reverse-engineered the PBP format: `painting.png` (2048x2048) + `pbp.xml`; workshop = `PKTB`.
- Detected and verified all 39 template draw-boxes; mapped sprite names from the game executable.
- Magic name table extracted from `castle.exe`; validated numbering against the shipped template.
