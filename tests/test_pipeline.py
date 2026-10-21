"""Offline tests for the v0.8 pipeline: no SwarmUI, no game install, no third-party art needed."""
import base64
import io
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import pipeline  # noqa: E402
from regions import REGIONS, TEMPLATE_SIZE  # noqa: E402

NON_LIMB = {r["part"] for r in REGIONS if r["role"] != "limb"}


def _blob(size=(256, 256), color=(200, 40, 40), box=(60, 50, 190, 210)):
    """A black-outlined coloured shape on a white canvas, like a model output."""
    k = 4                                            # supersample so the edge is antialiased like a real output
    im = Image.new("RGB", (size[0] * k, size[1] * k), "white")
    d = ImageDraw.Draw(im)
    d.ellipse([v * k for v in box], fill=color, outline=(0, 0, 0), width=6 * k)
    return im.resize(size, Image.LANCZOS)


def _template():
    """Synthetic template: opaque chrome with a transparent box per region and a marked limb art."""
    t = Image.new("RGBA", (TEMPLATE_SIZE, TEMPLATE_SIZE), (90, 30, 30, 255))
    d = ImageDraw.Draw(t)
    for r in REGIONS:
        x, y, w, h = r["rect"]
        d.rectangle([x, y, x + w - 1, y + h - 1], fill=(0, 0, 0, 0))
        d.line([x + 3, y + 3, x + w - 4, y + h - 4], fill=(255, 255, 255, 255), width=2)   # a "wireframe"
        if r["role"] == "limb":
            d.ellipse([x + 20, y + 20, x + w - 20, y + h - 20], fill=(40, 40, 40, 255))
    return t


def test_region_map_is_exact_grid():
    assert len(REGIONS) == 39
    assert len({r["part"] for r in REGIONS}) == 39 and len({r["rect"] for r in REGIONS}) == 39
    heads = [r["rect"] for r in REGIONS if r["role"] == "head"]
    assert len(heads) == 7 and all(rect[2:] == (234, 332) for rect in heads), heads
    for r in REGIONS:
        x, y, w, h = r["rect"]
        assert 0 <= x and 0 <= y and x + w <= TEMPLATE_SIZE and y + h <= TEMPLATE_SIZE, r


def test_specs_cover_every_non_limb_box():
    assert set(pipeline.ORDER) - {"bodyref"} == NON_LIMB
    assert set(pipeline.LAYOUT) >= NON_LIMB
    for part, (src, *_rest) in pipeline.XFORMS.items():
        assert pipeline.ORDER.index(src) < pipeline.ORDER.index(part), f"{part} derives from a later piece"
    for part in pipeline.USES_BODYREF:
        assert pipeline.ORDER.index("bodyref") < pipeline.ORDER.index(part)
    for part, (x0, y0, x1, y1) in pipeline.LAYOUT.items():
        assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1, part


def test_cut_out_keeps_enclosed_white_and_has_no_white_fringe():
    im = _blob()
    ImageDraw.Draw(im).ellipse((110, 100, 130, 120), fill="white")          # enclosed highlight
    a = np.asarray(pipeline.cut_out(im))
    assert a[0, 0, 3] == 0 and a[-1, -1, 3] == 0, "background must be transparent"
    assert a[120, 125, 3] == 255 and a[160, 125, 3] == 255, "subject must stay opaque"
    assert a[110, 120, 3] == 255, "enclosed white must stay opaque"
    edge = (a[..., 3] > 0) & (a[..., 3] < 255)
    assert edge.any() and a[edge][:, :3].max() < 60, "soft edge must be black, not a white halo"


def test_check_rejects_blank_collage_tall_and_wrong_colours():
    ok = pipeline.cut_out(_blob())
    assert pipeline.check(ok) == ""
    assert pipeline.check(pipeline.cut_out(Image.new("RGB", (256, 256), "white"))) == "blank"
    two = Image.new("RGB", (400, 200), "white")
    d = ImageDraw.Draw(two)
    d.ellipse((10, 40, 180, 170), fill=(20, 20, 200), outline=(0, 0, 0), width=5)
    d.ellipse((220, 40, 390, 170), fill=(20, 20, 200), outline=(0, 0, 0), width=5)
    assert pipeline.check(pipeline.cut_out(two)) == "several figures"
    tall = Image.new("RGB", (256, 256), "white")
    ImageDraw.Draw(tall).rectangle((100, 10, 150, 240), fill=(20, 20, 200), outline=(0, 0, 0), width=4)
    assert pipeline.check(pipeline.cut_out(tall), max_aspect=1.4) == "too tall for this piece"
    red, blue = _blob(color=(200, 40, 40)), _blob(color=(30, 60, 200))
    assert pipeline.check(ok, red, blue, min_sim=0.7) == "colours differ from the reference"
    assert pipeline.check(ok, red, red, min_sim=0.7) == ""


def test_palette_sim_orders_colours():
    red, blue = _blob(color=(200, 40, 40)), _blob(color=(30, 60, 200))
    assert pipeline.palette_sim(red, red) > 0.99
    assert pipeline.palette_sim(red, blue) < 0.3


def test_fit_lands_in_the_real_median_box_bottom_anchored_for_heads():
    sprite = pipeline.cut_out(_blob())
    for part in ("helm3", "pbod1", "bigbod2", "sword", "backoffb"):
        x, y, w, h = pipeline.BY_PART[part]["rect"]
        out = pipeline.fit(sprite, part)
        assert out.size == (w, h)
        bb = out.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
        x0, y0, x1, y1 = pipeline.LAYOUT[part]
        assert bb[0] >= x0 * w - 2 and bb[2] <= x1 * w + 2, (part, bb)
        assert bb[1] >= y0 * h - 2 and bb[3] <= y1 * h + 2, (part, bb)
    out = pipeline.fit(sprite, "helm3")
    bb = out.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    assert abs(bb[3] - pipeline.LAYOUT["helm3"][3] * 332) <= 2, "heads sit on the real baseline"


def test_xform_squashes_and_rotates():
    s = pipeline.cut_out(_blob(box=(40, 90, 220, 170)))            # wide ellipse
    narrow = pipeline.xform(s, 0.25, 1, 0)
    assert narrow.width < s.getbbox()[2] * 0.4
    turned = pipeline.xform(s, 1, 1, 90)
    assert turned.height > turned.width * 0.9, "90 degrees must swap the long axis"


def test_cover_fills_the_box():
    out = pipeline.cover(Image.new("RGB", (300, 600), (10, 20, 30)), (130, 130))
    assert out.size == (130, 130) and np.asarray(out)[..., 3].min() == 255


class FakeSwarm:
    """Stands in for SwarmUI: returns a coloured outlined blob; records every request."""

    def __init__(self):
        self.calls = []

    def list_models(self):
        return [pipeline.EDIT_MODELS["klein"], pipeline.ANIMA_MODEL]

    def render(self, prompt, w, h, model, steps, cfg, seed, negative="", images=None, controlnet=None, **kw):
        self.calls.append(dict(prompt=prompt, w=w, h=h, model=model, images=len(images or []),
                               controlnet=controlnet is not None))
        color = (200, 40, 40) if "enlarged" not in prompt else (30, 90, 200)
        return _blob((w, h), color, (w // 5, h // 5, w * 4 // 5, h * 4 // 5))


class FakeJob:
    def __init__(self, d):
        self.job_dir, self.result, self.logs = Path(d), {}, []
        self.cancel = threading.Event()
        self.phase = self.current = ""
        self.done = self.total = 0

    def say(self, m):
        self.logs.append(m)


class FakeEngine:
    def __init__(self):
        self.swarm = FakeSwarm()


def test_full_run_with_fake_backend_paints_every_box_and_keeps_limbs():
    base = _template()
    with tempfile.TemporaryDirectory() as d:
        eng, job = FakeEngine(), FakeJob(d)
        canvas, cells = pipeline.run(eng, job, base, {}, "a test knight", 7, "klein")
        a, t = np.asarray(canvas), np.asarray(base)
        assert canvas.size == base.size
        for r in REGIONS:
            x, y, w, h = r["rect"]
            box_a, box_t = a[y:y + h, x:x + w], t[y:y + h, x:x + w]
            if r["role"] == "limb":
                assert (box_a == box_t).all(), f"{r['part']}: limb art must stay the template's"
            else:
                assert (box_a[..., 3] > 40).any(), f"{r['part']}: box was not painted"
                if r["role"] not in ("hudicon", "banner"):       # these two are full-bleed art by design
                    assert not (box_a[..., 3] == 255).all(), f"{r['part']}: art must not fill the whole box"
        outside = np.ones(a.shape[:2], bool)
        for r in REGIONS:
            x, y, w, h = r["rect"]
            outside[y:y + h, x:x + w] = False
        assert (a[outside] == t[outside]).all(), "pixels outside the boxes must be untouched"
        assert {p for p, _ in cells} == NON_LIMB
        calls = eng.swarm.calls
        assert calls[0]["model"] == pipeline.ANIMA_MODEL and calls[0]["images"] == 0, "call 0 designs the master"
        assert {c["model"] for c in calls[1:]} == {pipeline.EDIT_MODELS["klein"]}, "pieces must use the edit model"
        assert {c["images"] for c in calls[1:]} == {1, 2}      # master, plus master+torso for bodies/giants
        assert (Path(d) / "master.png").exists()


def test_anima_backend_sends_a_controlnet_guide_per_piece():
    with tempfile.TemporaryDirectory() as d:
        eng, job = FakeEngine(), FakeJob(d)
        pipeline.run(eng, job, _template(), {"controlnet": True}, "a test knight", 7, "anima")
        piece_calls = eng.swarm.calls[1:]                            # call 0 is the master
        assert piece_calls and all(c["controlnet"] for c in piece_calls)
        assert all(c["model"] == pipeline.ANIMA_MODEL for c in eng.swarm.calls)


def test_missing_edit_model_gives_a_download_hint():
    class NoModels(FakeSwarm):
        def list_models(self):
            return [pipeline.ANIMA_MODEL]

    eng = FakeEngine()
    eng.swarm = NoModels()
    with tempfile.TemporaryDirectory() as d:
        try:
            pipeline.run(eng, FakeJob(d), _template(), {}, "x", 1, "klein")
        except RuntimeError as e:
            assert "huggingface.co/black-forest-labs" in str(e)
        else:
            raise AssertionError("a missing model must fail with the download hint")


def test_render_payload_uses_swarmui_parameter_ids():
    """Regression: the ControlNet guide went out as 'controlnetimage', which SwarmUI silently ignores."""
    import engine

    class Fake(engine.SwarmClient):
        sent = None

        def session(self):
            return "s"

        def _post(self, path, body, timeout=120):
            Fake.sent = body
            buf = io.BytesIO()
            Image.new("RGB", (4, 4)).save(buf, "PNG")
            return {"images": [{"data": base64.b64encode(buf.getvalue()).decode()}]}

    c = Fake()
    img = Image.new("RGB", (8, 8))
    c.render("p", 64, 64, "m", 8, 1.0, 5, images=[img, img], controlnet=img, controlnet_strength=0.8)
    body = Fake.sent
    assert body["controlnetimageinput"].startswith("data:image/png;base64,")
    assert "controlnetimage" not in body
    assert body["controlnetmodel"] == engine.CONTROLNET_MODEL and body["controlnetstrength"] == 0.8
    assert body["promptimages"].count("|") == 1 and body["promptimages"].startswith("data:image/png")
    c.render("p", 64, 64, "m", 8, 1.0, 5)
    assert "promptimages" not in Fake.sent and "controlnetmodel" not in Fake.sent


def test_cancel_raises_cancelled_before_any_piece():
    with tempfile.TemporaryDirectory() as d:
        eng, job = FakeEngine(), FakeJob(d)
        job.cancel.set()
        try:
            pipeline.run(eng, job, _template(), {}, "x", 1, "klein")
        except pipeline.Cancelled:
            assert len(eng.swarm.calls) == 1, "only the master may have been drawn"
        else:
            raise AssertionError("cancel must stop the run")
