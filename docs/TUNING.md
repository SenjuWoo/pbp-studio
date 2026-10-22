# Tuning: how the defaults were chosen

Every default below comes from a measured sweep, not from a guess. Reproduce with `tools/tune.py`
(fixed designs and seeds, same four test characters every time: armoured knight girl, taco-head boy,
chrome robot knight, cat knight). Hardware: RTX 4080 SUPER 16 GB, SwarmUI, October 2026.

Metrics per image (all computed on the cut-out sprite, see `tools/tune.py`):
**pass** = clean single figure (not blank, not several figures, not filling the canvas),
**bg** = share of the canvas border that is pure white (clean cut-out), **outline** = share of the silhouette
rim that is near-black (Castle Crashers needs bold outlines), **flat** = mean gradient inside the figure
(lower = flatter cel shading), **s** = seconds per image. Settings were also compared on contact sheets by eye.

## Sources used for the candidate list
- Anima model card (circlestone-labs/Anima): 30-50 steps, CFG 4-5, sampler `er_sde` ("neutral style, flat colors,
  sharp lines"), prefix `masterpiece, best quality, score_7, safe,`, negative
  `worst quality, low quality, score_1, score_2, score_3, artist name, blurry, jpeg artifacts, chromatic aberration`,
  lowercase tags followed by at least two descriptive sentences.
- WooMix v1.0 page (the checkpoint used here): CFG 3.0-3.5, 30-40 steps, ER-SDE or DPM++ 2M SDE,
  schedulers beta / simple / kl_optimal / sgm_uniform, `qwen_image_vae`, short negatives.
- Flux.2 Klein 4B distilled: CFG 1 (fixed for distilled), 4-8 steps; multi-reference editing by index.

## 1. Anima sampler x scheduler (CFG 3.5, 36 steps, 12 combos x 4 designs = 48 images)
All 48 passed the gate. Differences are small; speed and clean cut-out decide.

| sampler / scheduler | pass | bg | outline | flat | s |
|---|---|---|---|---|---|
| **er_sde / simple** | 100% | **0.999** | 0.908 | 106.3 | **19.1** |
| rk_beta / beta (0.8.0 used rk_beta / beta57) | 100% | 0.975 | 0.908 | 103.6 | 32.5 |
| rk_beta / beta57 | 100% | 0.978 | 0.907 | 101.5 | 33.2 |
| euler_ancestral / beta | 100% | 0.987 | 0.907 | 99.5 | 26.4 |
| euler_ancestral / simple | 100% | 0.995 | 0.906 | 103.0 | 76.6 |
| dpmpp_2m_sde_gpu / simple | 100% | 0.993 | 0.904 | 103.6 | 32.8 |
| dpmpp_2m_sde_gpu / beta | 100% | 0.985 | 0.898 | 106.2 | 30.5 |
| er_sde / beta57 | 100% | 0.988 | 0.885 | 103.7 | 20.9 |
| er_sde / beta | 100% | 0.990 | 0.880 | 98.6 | 18.9 |

**Chosen: `er_sde` + `simple`.** Best outline and cleanest cut-out, 42 % faster than the old rk_beta.

## 2. Anima CFG x steps (er_sde / simple, 6 combos x 4 designs)
| CFG / steps | pass | bg | outline | flat | s |
|---|---|---|---|---|---|
| **4.0 / 40** | 100% | 0.999 | **0.912** | 105.1 | 20.7 |
| 5.0 / 40 | 100% | 0.999 | 0.910 | 108.5 | 31.2 |
| 4.0 / 30 | 100% | 1.000 | 0.909 | 108.3 | 17.8 |
| 3.0 / 30 | 100% | 0.998 | 0.908 | 106.8 | 48.5 |
| 5.0 / 30 | 100% | 1.000 | 0.907 | 108.1 | 20.3 |
| 3.0 / 40 | 100% | 0.998 | 0.852 | 106.8 | 21.6 |

**Chosen: CFG 4.0, 40 steps** (inside both the model card and the WooMix range). CFG 5 started to drift from the
prompt (the cat turned gold); CFG 3 / 40 lost outline strength.

## 3. Anima prompt format (er_sde / simple, CFG 4, 40 steps)
| prompt | pass | bg | outline | flat |
|---|---|---|---|---|
| plain (0.8.0) | 100% | 0.999 | 0.912 | 105.1 |
| + quality prefix and official negative | 100% | 0.991 | 0.910 | 108.5 |
| **tags first + two sentences, official negative** | 100% | **1.000** | 0.908 | **103.2** |

**Chosen: tags + prose** (`pipeline.master_prompt`). Metrics are equal within noise (it has the cleanest
background and flattest shading); on the sheets it followed the design words most closely (silver chrome robot,
orange armoured cat) and it is the format the model card asks for.

## 4. Flux.2 Klein 4B fp8: steps x canvas (4 masters x 7 piece types = 28 pieces per row)
| steps / canvas | pass | colour similarity to master | s per piece |
|---|---|---|---|
| 4 / 1024 | 96.4% | 0.757 | 7.0 |
| **6 / 1024** | 96.4% | **0.770** | **7.0** |
| 8 / 1024 | 96.4% | 0.769 | 9.9 |
| 8 / 768 | 92.9% | 0.722 | 30.4 |

**Chosen: 6 steps, 1024 canvas, CFG 1.** Same pass rate as 8 steps, best colour fidelity, 30 % faster.
768 is slower (VRAM pressure) and worse. The only failures in the whole sweep were the torso reference of the
knight (the master includes hair and skin that a torso does not, so the colour gate against the master was
too strict): that gate went from 0.72 to 0.55 (good torsos measured 0.62-0.91). The gate that matters for
identity, every body and giant piece against the torso reference (0.70), is unchanged.

## 5. Prompt fix found by looking at the sheets
The "back of the head" piece (`helm.B`) came out as a bald egg for every character that has a ponytail,
ribbon, helmet or taco head. Rewording to "seen from directly behind: the back of the same head (or helmet), no
face visible" carries the character's own features to the back view on all four test designs.

## 6. Validation of the final settings: four different characters, full atlas each
Klein backend, tuned defaults, command-line run (`tools/bench.py`), one seed per design:

| design | time | gate retries | result |
|---|---|---|---|
| taco-head boy | 2 min 41 s | 0 | every box painted; taco head in all 7 angles, torso and giants keep the red/brown outfit |
| robot knight | 3 min 21 s | 5 | chrome helmet and armour in all angles, blue lights carried over |
| cat knight | 2 min 55 s | 2 | cat ears and orange armour in all angles |
| knight girl | 3 min 44 s | 12 | ribbon, ponytail and green eyes in all 7 heads; giants keep the cross emblem |

For comparison, the 0.8.0 settings needed 4 min 47 s on the knight. Known weak spots: the taco's side views invent a human
face inside the taco, and giants of the knight tend to repaint the blue tabard red (the colour gate rejects most
of those; when all three tries fail the closest one is kept).
One run stalled for 11 minutes inside SwarmUI (a single render call that never returned); render calls now time out
after 4 minutes and the piece is retried with a new seed.

## 7. Pose conformance to the template (0.9.1)
The pose of every box was audited against the template's wireframes and against ten real Workshop characters
(KATE, NARUTO, SMASH GIRL, SQUIRREL GIRL, WAIFU KNIGHT, HEYLEE, SASUKO, LUCOA, VANA, MARISSA). The 0.8/0.9.0 angle text
had come from old project notes and was wrong:

| slot | real characters | was | now |
|---|---|---|---|
| heads 1-3 | almost frontal, a growing turn to the viewer's **right** | 1-2 facing left, 3 right | about 15 / 25 / 40 degrees right |
| head 4 | full right profile | right profile | right profile |
| head 5 | straight on | straight on | straight on |
| head 6 | head **bowed** forward and down | tilted back and up | tilted forward and down about 30 degrees, eyes shut, features kept |
| head 7 | back of the head | back | back, features kept (ponytail, ribbon, helmet) |
| giant 3 | side view leaning right | front view tilted 14 degrees | real side-profile piece |
| giant 4 | torso lying **on its back**, chest up, collar left | front view rotated 80 degrees (on its side) | side view of giant 3 turned 90 degrees, flattened and stretched into a wide loaf |

Head angle test (4 designs x 6 angles, with and without the front head as a second reference): the master alone
over-turns the early slots (the robot already faces 45 degrees in slot 1) and the face drifts between slots (the taco
loses its face, then grows a human one); adding the front head (`helm5`, drawn first) as image 2 keeps one face
and makes the 15 / 25 / 40 degree turns graded. Klein under-turns, so 10 degrees asked for came out near zero;
15 / 25 / 40 was asked to get roughly 5 / 15 / 25 degrees of real turn. Slot 6 was tested in six wordings on four designs.
"Bowed deeply forward, seen from above" looked best on the knight but made the taco, cat and robot into bald heads
(colour similarity to the front head 0.32-0.55); "tilted forward and down about 30 degrees as if hurt ... every hair, ear,
hat, helmet, shell and accessory exactly as in image 2" kept the character in all 12 renders (0.65-0.96), so that is the
wording, with a colour gate of 0.55 against the front head. The same sweep showed the back view is fine as it is
(the robot's red back is its cape).

The turn of the graded slots is chosen by measurement: `turn_score` is 1 - IoU of the two silhouettes (both scaled
to the same height and centred), expressed as a share of the front-to-profile span of the same character; slots 1-3
aim at 0.22 / 0.36 / 0.55 and keep the closest of three candidates. Every head is scaled to the pixel area of the
front head so the seven slots have the same head size above the body.

Stalls: in the full runs of this tuning, two renders never returned (the taco's `bodyref` and `pbod1`, both 768 px, each
cost the 240 s timeout) and one earlier run lost 11 minutes to a single call. The retry after each stall finished in
seconds, so the timeout is now 90 s for Klein and the hung call is interrupted. A cold start (launching SwarmUI and
loading Anima, then Klein) adds several more minutes to a first run.

## Final defaults
| setting | 0.8.0 | 0.9.0 |
|---|---|---|
| Anima sampler / scheduler | rk_beta / beta57 | **er_sde / simple** |
| Anima CFG / steps | 3.0 / 40 | **4.0 / 40** |
| Master prompt | plain sentence | **tags + prose + model-card negative** |
| Klein steps / CFG | 8 / 1 | **6 / 1** |
| Torso colour gate | 0.72 | **0.55** |

Existing `settings.json` files that still hold the old shipped values are migrated automatically;
values you changed on purpose are kept.
