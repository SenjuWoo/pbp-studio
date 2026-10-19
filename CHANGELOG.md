# Changelog

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
