# Changelog

## 0.9.1 - poses follow the template
Audited every box against the template wireframes and ten real Workshop characters.
- **Heads:** slots 1-3 now face almost the viewer with a growing turn to the viewer's right (they faced left before),
  slot 6 is tilted forward and down (it was tilted back), and every angle is drawn from the master *and* the front head,
  so the face stays identical and the turns are graded instead of over-turned.
- **Giants:** the 3rd is a real side-profile piece; the 4th lies **on its back** (chest up, collar left, flat underside,
  wide loaf like the template) by turning that side view 90 degrees, instead of rotating the front view onto its side.
  Giants get "no feet".
- **Graded turns are measured, not hoped for.** Klein's "15 degrees" came out anywhere from 5 to 40, so slots 1-3 draw
  three candidates each and keep the one whose silhouette difference from the character's own front and profile heads
  is closest to the target (22 % / 36 % / 55 % of the way to the profile).
- **All seven heads are scaled to the same pixel area** as the front head. Before, a ponytail or a profile shrank the
  head (fitted by bounding box) and it no longer lined up with the body below.
- Head prompts say again "nothing but the head: no body, no legs, no feet, no weapon" (the front-head form had lost it, and
  the taco's profile came back with boots and a sword); a head taller than 1.55 x its width is rejected.
- Slot 6 is a plain 30 degree forward tilt with eyes shut and every feature kept: "bowed, seen from above" turned the taco,
  cat and robot into bald heads, so it is also gated on colour similarity to the front head (0.55).
- **Stalled SwarmUI calls recover in about 90 s, not 4 minutes:** per-backend render timeouts (Klein 90 s, Qwen 240 s,
  Anima 120 s, 300 s for the first call that loads the model), and a timed-out call now sends `InterruptAll` before the
  retry (a hung render had cost one run 11 minutes and another two 4-minute timeouts).
- New tests pin the head-slot order, the turn choice, same-size heads, the head aspect gate, the lying giant and the
  interrupt on timeout; `docs/TUNING.md` section 7 has the evidence.

## 0.9.0 - settings tuned by measurement
Every default now comes from a reproducible sweep (`tools/tune.py`, results in `docs/TUNING.md`): 12 sampler x
scheduler combos, CFG x steps, three prompt formats and Klein steps x canvas, on four different test characters.
- **Anima (design step):** `er_sde` + `simple` (was rk_beta + beta57; same quality, 42 % faster, cleanest cut-out),
  CFG 4.0 (was 3.0), 40 steps, and the model-card prompt format (quality tags, lowercase tags, then two sentences)
  with the model-card negative.
- **Klein pieces:** 6 steps (was 8): same pass rate, best colour fidelity, 30 % faster; 1024 canvas confirmed
  (768 was slower and worse).
- **Back-of-head piece** now says "from directly behind: the back of the same head (or helmet)", so ponytails, ribbons,
  helmets and taco heads carry over instead of a bald egg.
- Torso colour gate against the master 0.72 -> 0.55 (it rejected good torsos of the knight); the identity gate
  against the torso reference stays at 0.70.
- The pipeline applies the tuned sampler when a job sets none (the command-line path used SwarmUI's default).
- `settings.json` written by older versions: untouched old defaults are replaced by the tuned ones, your own
  values are kept.
- When all three tries of a piece fail the gate, the one closest to the colour reference is kept (it used to be
  the first). Render calls time out after 4 minutes (a stalled SwarmUI call blocked one run for 11 minutes).
- `tools/tune.py` added; new tests for the migration, the master prompt, the applied settings and the
  closest-attempt rule. Validated on four different characters (taco, robot, cat, knight): see `docs/TUNING.md`.

## 0.8.0 - one master design, exact boxes, edit-model pieces
The generator was rebuilt after decoding 37 real Workshop characters (PKTB: Blowfish-ECB container,
analysed locally, never shipped) and measuring where and how big real art sits in every box.
- **Root causes fixed.** (1) `regions.py` rects were the wireframe footprint (~60 % of the real boxes);
  they are now the template's 39 transparent components, exact to the pixel. (2) The ControlNet guide was
  sent as `controlnetimage`; SwarmUI's id is `controlnetimageinput`, so it was silently ignored. (3) Each
  box was repainted independently, so identity drifted and boxes filled with several small figures.
- **New pipeline (`app/pipeline.py`).** One full-body master design from Anima (or your own image,
  or the last design), then every piece is redrawn from it by an image-edit model with a text pose
  command: Flux.2 Klein 4B fp8 (default, ~8 s per piece) or Qwen Image 2.1 turbo int8. Torso reference
  bridges the master to bodies and giants so they keep the clothing colours.
- Landing / run / spin bodies, the lying and falling giants and the shield edge are derived from other
  pieces by squash and rotate (deterministic, consistent).
- Pieces are cut out of the white canvas with a black soft edge, gated (blank, filled canvas, several
  figures, too tall, colours differ from the reference) with up to 3 seeds, then fitted to the median
  real size/position per box (`app/layout_stats.json`, numbers only, bottom-anchored for heads).
- The 15 beefy-form limbs keep the template's own art (what most Workshop characters do).
- Anima-only model stays as a no-download fallback: txt2img + lineart ControlNet, now with the guide
  actually delivered.
- UI: model selector, your own character image, reuse last design, master design shown in the result.
  Removed: AI strength, colour lock, flat-colour offline mode and its colour pickers.
- Removed the 0.1-0.7 img2img/silhouette/stamp code and its tests; new offline tests cover the pipeline
  with a fake SwarmUI on a synthetic template, and a regression test pins the ControlNet parameter name.
- `tools/bench.py` runs a full job from the command line.
- Benchmark (same design + seed, RTX 4080 SUPER): Klein 287 s / 4 gate retries, Qwen 1240 s / 18, Anima-only 645 s / 0 but off-model (busts as heads, full figures in body boxes). Klein is the default.

## 0.7.2 - sheet order by role, giant boxes unbroken
- Contact sheet sorted by role group then template position: heads, bodies, weapon and shields,
  giants, limbs, then hudicon / selectbanner / backoffb (`sheet_order`, covered by a test).
- `fit_to_template` only trusts the largest ink blob when that blob holds more than half the ink;
  otherwise it uses all of it. The unconditional rule made bigbod1 collapse to pose 0.04 - it is back
  at 0.98 with rim coverage 0.92.

## 0.7.1 - limbs get their own design, clean edges, ordered sheet
- **Limb init is now the plain colour silhouette**, not the LUT art, and the 0.45 creativity cap is
  gone: limbs run at the normal 0.55, so the model can invent plating and sleeves instead of
  repainting the template muscle. LUT remains the fallback only.
- Limb prompt asks for "armour plating, colour palette, line weight and material style of the head and
  body pieces"; every prompt now also says "same helmet, same armour colours and materials".
- **White caps removed.** After the border flood fill, near-white components that touch the sprite's
  own edge and are under 15% of its area are dropped; enclosed highlights (eyes) are kept because
  they are not on the edge and a pale character is one large blob.
- **Outline drawn at final resolution** (1px under 200px, 2px above). Drawn before the downscale it
  blurred to grey, which is why 0.7.0's limbs lost their black line work.
- **`fit_to_template` measures the largest ink blob**, not all ink: bigarm8's stray template bar no
  longer becomes the target box, so the arm cannot be dragged onto the crop edge.
- Limbs keep only their largest opaque blob, so a second arm or stray line cannot survive.
- Contact sheet is sorted by template position (row, then x) instead of generation order.
- Verified: limbs log `AI 0.55`; mean luminance of the limb pieces 123-139 (pitch black was ~10);
  bigarm8 left 10 columns transparent; helm3 0% white in the top third.

## 0.7.0 - limbs get a real AI pass, facing is in every prompt
- **Limbs are no longer a flat LUT.** All 15 beefy pieces go through the same SwarmUI path as heads
  and bodies, seeded with the LUT-recoloured limb and the limb's own contour as ControlNet. The LUT
  is now only the fallback when the AI fails or erases the piece.
- Limb prompts add "match the armour plating, colour palette, line weight and material style of the
  head and body pieces, do not invent a different armour design".
- Every prompt now ends with "do not flip or rotate the subject"; the exact angle per box was
  already supplied by `regions.SLOT_PROMPTS`.
- Blank/erased detection retries once at 0.15 lower creativity before falling back, and now measures
  white only over opaque pixels (`_white_frac` was counting transparent background as white, so every
  keyed piece read as blank and every generation ran twice).
- Measured on a full run: limbs log `AI 0.45` (previously `limb LUT`), 0 blank fallbacks, runtime
  180s vs 240s for the double-generation version.

## 0.6.2 - remove the knight wireframe, fix black limbs and the white cap
- **No more stamping the template sketch over output.** `stamp_contour` is gone. Heads, bodies,
  sword, shields, hudicon, banner and backoffb get their alpha from their own generated image.
- **Alpha is keyed from the canvas border colour** (`key_background`), not "is it white": heads are
  generated on mid-grey, so a white helmet cap cannot survive as background. A 2px black outline is
  drawn on the sprite's own island instead of borrowing the knight's.
- **Limbs no longer turn black.** The old threshold (`lum < 60` = outline) swallowed the template's
  dark-grey muscle (RGB 45-65). New zones: outline `L < 22`, muscle `22-85` mapped to the primary
  colour with shading preserved, cuff `>= 85` mapped to the accent. Only the largest connected blob
  survives, so bigarm8's stray left bar is gone.
- **hudicon** is the alpha-matted head with a 4px margin; **backoffb** is the head dropped onto the
  body's neck on a transparent canvas - neither is diffused.
- **Torsos are prompted headless** ("neck down, no head, no face") with face words added to the
  negative prompt, so no faces appear on chests.
- Self-check on the output atlas: bigarm1 13.9% near-black (limit 35%), helm3 0.0% white in the top
  third (limit 5%), bigarm8 left 10 columns fully transparent, selectbanner 31% wireframe overlap
  (limit 60%).

## 0.6.1 - headroom and a HUD icon that fills its box
- The head anchor taken from the banner now gets 10% headroom, so the top of the skull is not
  clipped by the crop edge (the "face cut through" look on the portrait).
- `hudicon` trims the generated head to its own bounds and squares it before scaling, so the icon
  fills its slot (coverage 0.60 -> 0.65, match against helm3 1.00).

## 0.6.0 - the ControlNet bug, and an anchor chain that keeps one character
- **Fixed the bug that made 0.5.0 look like flat paint on a knight.** ControlNet was being sent with
  no init image on the first piece; SwarmUI rejects that ("Must specify either a ControlNet Image,
  or Init image") and the error handler read it as "model missing" and disabled ControlNet for the
  whole job. Every piece after that ran uncontrolled. ControlNet is never sent without an init now,
  and the fallback only fires on a real model error.
- **Anchor chain instead of 39 independent drawings.** The banner is generated first with pure
  txt2img and defines the character; helm3 is derived from the banner's head; the other six head
  slots are mirror/squash/symmetry/tilt/wiped-face variants of helm3 at low denoise.
- **Every generation is a 512x512 square** with the piece centred in a 12% margin, so the shared seed
  produces the same latent structure in every slot, then the piece is cropped back and normalised
  onto the template's own ink box (`fit_to_template`).
- **hudicon is a crop of the generated head** (similarity to helm3: 0.99), not a diffusion pass.
- **backoffb is the head stacked on the body** and refined at 0.40.
- **Limbs use a three-tone LUT** (outline / muscle shadow / cuff) plus speck removal, so bigarm8's
  stray bar is gone.
- Shields are generated on the padded square, so shield2 is a narrow strip (15.7% coverage) instead
  of a solid rectangle; the 3px border of every template crop is cleared so corner ticks never enter.
- Measured: pose head 0.96, body 1.00, giant 0.99, backoffb 0.91, shield1 0.91; head-to-head
  similarity 0.74 mean (was 0.56); hudicon 0.99 against helm3.

## 0.5.0 - per-slot poses, no knight tracing, clean limbs
- **Per-slot pose text for all 39 boxes.** Every box now carries its own angle from the template map
  (head 3/4 left, 3/4 right, profile, front, tilted, back-of-head with no face; bodies idle, landing,
  running, spinning, back view; giant torsos walk frames, lying down, rear, falling at 45 degrees;
  shield front vs side edge; sword vertical).
- **ControlNet now gets the contour only.** The raw template line art was forcing the bucket helmet
  and chest cross onto every character; the interior detail is stripped, the outline is kept.
- **The img2img seed is a clean flat silhouette**, not the colorized knight sketch, so the model is
  not painting over someone else's character.
- **The 15 beefy limbs are painted programmatically** (the template's own limb shading tinted to the
  character palette) instead of diffused. No more faces on biceps, no potatoes, and 15 fewer AI calls.
- **Bold outlines are stamped back on** from the template contour, so pieces keep the thick Behemoth
  line work regardless of what the model returns.
- Style prompts now ask for Behemoth / Dan Paladin flat cel art, with anime and soft-shading banned.
- Measured: pose agreement head 0.91, body 0.95, weapon 0.99, giant 0.93; outline coverage on the
  piece rim head 0.97, body 0.99, weapon 0.99.

## 0.4.0 - the template owns the pose (ControlNet)
- Installed and wired the official **Anima LLLite lineart** ControlNet. Every box is now generated
  with the template's own line art as the control image, so side views stay side views and back
  views stay back views instead of everything coming out front-facing.
- Measured pose agreement with the template (bounding-box IoU): head 0.87 -> 0.96, body 0.76 -> 0.87,
  weapon 0.81 -> 0.95, giant 0.96 -> 0.94, limbs 0.91, full-body 0.96.
- The per-family "master" copy is gone: it won on img2img strength and flattened every pose. Design
  consistency now comes from the shared seed, the derived palette and the prompt.
- Limb boxes are prompted as fists (they are hands, not arms), giants as beefy torsos.
- New UI: "Lock pose" (ControlNet on/off) and "Pose strength" (default 1.0). If the model is missing
  the job warns once and continues without it.

## 0.3.8 - one master per family
- The first box of each family (head, body, giant, limbs, weapon, shield, full-body) is painted from
  the prompt; every other box in that family is painted from that master image. Heads now share one
  taco, giants share one giant, limbs share one arm.
- Measured palette similarity between pieces: bodies 0.69 -> 0.81, limbs 0.49 -> 0.81,
  full-body 0.38 -> 0.96, heads 0.56 -> 0.65 (pose changes limit heads).

## 0.3.7 - stop drawing knights
- Role prompts no longer say "helmet head" / "torso armor", which was telling the model to draw a
  knight whatever you asked for. It is "character head" / "torso" now.
- Unless the description mentions armour, "knight, plate armor, medieval helmet" are added to the
  negative prompt.
- The design is weighted 1.3x and the UI asks for a visual description ("two words gives you a
  generic knight").

## 0.3.6 - colour depth restored
- The palette lock is now opt-in ("Lock colours", off by default). On, it flattens each piece to six
  tones for maximum consistency; off, the AI keeps its full shading (thousands of colours per piece).
- When no colour is named, the first piece still decides the palette and the rest are prompted with
  those colour words - consistency without quantising the art.

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
