#!/usr/bin/env python3
"""NodalRed2x's native MPC skin: skins/TUI.json + skins/Q-Links.json + the PNGs they use (docs/SDK-PORTING.md; the widget machinery is
Vavra's tools/make_tui.py, one theme, no skin switch). The art is drawn from code by tools/n2x_art.py in the look of the Nord Lead 2x
front panel (docs/reference/); the pages are laid out here like its sections, every control in a block of up to four with its own
Q-Link frame (at most four blocks per sub-tab).

Choices are drawn the Nord way: a column of green LEDs with the option names, each a radio Button on the choice parameter (no pick-list
pop-ups; ui_open stays 0). Two-way switches are black buttons with an LED. The bank and sound names in the red display take the data
wheel and Q-Links (an invisible value field over each).
    python3 tools/make_tui.py              # -> skins/   (build-sdk.sh copies it to Plugin Skins/)
    python3 tools/make_tui.py --preview    # also docs/skin-preview/<tab>.png, composed offline (Titillium at the MPC's text scale)"""
import json, os, re, shutil, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n2x_art as A

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("NR2X_SKIN_OUT", os.path.join(ROOT, "skins"))
PREVIEW = os.environ.get("NR2X_PREVIEW", os.path.join(ROOT, "docs", "skin-preview"))
LOCK = [l.strip() for l in open(os.path.join(ROOT, "params.lock")) if l.strip()]
PARAMS = {p["key"]: p for p in json.load(open(os.path.join(ROOT, "vst", "params.json")))["params"]}
POPUPS = [k[:-len("__open")] for k in LOCK if k.endswith("__open")]
UI_INDEX = LOCK.index(POPUPS[0] + "__open")          # 136: ui_open sits in the first popup slot
TUI_PX = 0.62                                        # a Label draws its text at about 0.62 x its height (Maze, on the device)
GESTURE = "Instant"
KNOB = 84
BIG = 104
KNOB_SIZES = (KNOB, BIG)
CLEAR = "clear.png"
MAX_CHARS = int(re.search(r"kFavNameMax = (\d+)", open(os.path.join(ROOT, "src", "params_gen.h")).read()).group(1))


def kname(size):
    return "nknob%d" % size


def PI(key):
    return UI_INDEX if key == "ui_open" else LOCK.index(key)


def P(key):
    return "Parameter %d" % PI(key)


def hexcol(rgb, a=255):
    return "%02x%02x%02x%02x" % ((a,) + tuple(rgb))


# ---- a JSON writer that keeps key order and allows the overlay widgets' duplicate "version" key ------------------------------
class Obj:
    def __init__(self, *pairs):
        self.pairs = list(pairs)


def dump(v, ind=0):
    sp = "  " * ind
    pairs = v.pairs if hasattr(v, "pairs") else list(v.items()) if isinstance(v, dict) else None
    if pairs is not None:
        if not pairs:
            return "{}"
        return "{\n%s\n%s}" % (",\n".join("%s  %s: %s" % (sp, dump(k), dump(x, ind + 1)) for k, x in pairs), sp)
    if isinstance(v, list):
        return "[]" if not v else "[\n%s\n%s]" % (",\n".join(sp + "  " + dump(x, ind + 1) for x in v), sp)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
    return '"%s"' % str(v).replace("\\", "\\\\").replace('"', '\\"')


# ---- TUI building blocks --------------------------------------------------------------------------------------------------
def bounds(b, focus="No", ind=None):
    d = {"version": 2 if ind else 1, "acceptsHWFocus": focus, "showWhenDataModelInvalid": "Show", "whenVisible": "Always",
         "boundsType": "Absolute", "bounds": b}
    if ind:
        d["additionalInvalidatingHandles"] = ind     # needs bounds version 2, or the MPC ignores it (JE-8086 lesson)
    return d


def entry(name, typ, data, b, remap=None, focus="No", ind=None, visible=None):
    e = {"version": 2, "componentData": {"version": 1, "name": name, "type": typ, "data": data},
         "handle remapping": {"version": 1, "map": [{"key": "Data", "value": remap}] if remap else []},
         "bounds": bounds(b, focus, ind)}
    if visible:
        e["bounds"]["whenVisible"] = visible
    return e


def bg(colour="0", image=""):
    return {"version": 1, "focussed": {"version": 1, "colour": colour, "image": image}, "unfocussed": {"version": 1, "colour": colour, "image": image}}


def component(children, actions=None, ignore=False, background=None):
    return {"version": 2, "actions": actions or [], "backgroundData": background or bg(), "ignoreMousePresses": ignore,
            "disableCoarseDataWheel": False, "componentsData": children}


def act(on, handler, extra=""):
    return {"version": 1, "onAction": on, "handler": handler, "handleName": "Data", "additionalData": extra}


def text_style(h, colour, just="horizontallyCentred verticallyCentred", style="SemiBold"):
    return {"version": 1, "font": {"version": 1, "name": "Titillium Web", "style": style, "height": float(h)}, "colour": colour,
            "justification": just, "case": "Original"}


def label(b, key, h=22, colour=None, just="horizontallyCentred verticallyCentred", style="SemiBold"):
    colour = colour or hexcol(A.INK)
    return entry("label", "Label", {"version": 1, "textStyle": text_style(h, colour, just, style), "type": "Value", "handleName": "Data"}, b, P(key))


def focus_style():
    return {"version": 1, "backgroundColour": "00000000", "outlineColour": hexcol(A.FRAME), "backgroundInset": 4.0, "outlineThickness": 2.0}


FIELDS = set()                                         # (w, h) of every display field that steps a value (display_row)
FIELD_KEY = {"bank_name": "bank_index", "preset_name": "preset"}


def definitions():
    def knob_def(strip, size=KNOB, frames=101):
        return component([
            entry("focus", "Focus", focus_style(), "-6 -6 %d %d" % (size + 12, size + 12), visible="WhenFocussed"),
            entry("knob", "Knob", {"version": 3, "knobType": "FilmStrip", "filmStrip": strip, "numFrames": frames, "invert": False,
                                   "dragOrientation": "Vertical", "handleName": "Data"}, "0 0 %d %d" % (size, size)),
        ], actions=[act("Mouse Down", "Q-Link"), act("Double Click", "Show Overlay", "knob overlay"), act("Enter Pressed", "Show Overlay", "knob overlay")])
    overlay = component([entry("overlay", "KnobOverlay", Obj(
        ("version", 2), ("version", 1),
        ("actions", [{"version": 1, "onAction": "Focus Lost", "handler": "Focus Lost", "handleName": "Focus Lost", "additionalData": ""}]),
        ("overlayType", "Knob With Header"), ("scaleType", "Linear"), ("polarityType", "Unipolar"),
        ("showMinusSign", True), ("handleName", "Data")), "0 0 1280 800", focus="Yes")], ignore=True)
    out = [{"key": "knob overlay", "value": overlay}]
    for size in KNOB_SIZES:
        out.append({"key": kname(size), "value": knob_def(kname(size) + ".png", size)})
    for w, h in sorted(FIELDS):      # an invisible value slider over a live name: the data wheel, a Q-Link or a drag steps it
        ts = {"version": 1, "font": {"version": 1, "name": "Roboto", "style": "Regular", "height": 20.0}, "colour": "00000000",
              "justification": "horizontallyCentred verticallyCentred", "case": "Original"}
        out.append({"key": "lcdfield%dx%d" % (w, h), "value": component([
            entry("focus", "Focus", focus_style(), "0 0 %d %d" % (w, h), visible="WhenFocussed"),
            entry("field", "Knob", {"version": 4, "knobType": "ValueSlider", "textStyle": ts, "dragOrientation": "Horizontal",
                                    "handleName": "Data"}, "0 0 %d %d" % (w, h)),
        ], actions=[act("Mouse Down", "Q-Link")])})
    return out


def save(im, name):
    im.save(os.path.join(OUT, name))
    return name


def slug(text):
    """a file-name part from a caption: the MPC's drive is case-insensitive, so one-character captions get their code (c<ord>)"""
    if len(text) == 1:
        return "c%d" % ord(text)
    text = text.replace(".", " dot ").replace("/", " of ").replace("+", " plus ").replace("-", " minus ").replace("<", " lt ").replace(">", " gt ")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "x"


def button(kids, key, b, on, off, bid=1, n=1, name=None):
    kids.append(entry(name or key, "Button", {"version": 2, "onImage": on, "offImage": off, "buttonId": bid, "numButtonsInGroup": n,
                                              "handleName": "Data", "gestureBehaviour": GESTURE}, b, remap=P(key)))


def hit_zone(kids, key, x, y, w, h):
    """an invisible momentary touch zone over a printed arrow (a light flash while held)"""
    on = "hit_%dx%d.png" % (w, h)
    if not os.path.exists(os.path.join(OUT, on)):
        save(A.arrow_image(w, h, 1, True), on)
    button(kids, key, "%d %d %d %d" % (x, y, w, h), on, CLEAR, name=key + " hit")


# ---- a page: art + widgets at the same coordinates + Q-Link blocks -----------------------------------------------------------
STAGES = {k: k[-1] for k in ("FilterEnvA", "FilterEnvD", "FilterEnvS", "FilterEnvR", "AmpEnvA", "AmpEnvD", "AmpEnvS", "AmpEnvR")}
STAGES.update({"ModEnvA": "A", "ModEnvD": "D"})


class Page:
    def __init__(self, name, fn):
        self.name, self.fn = name, fn
        self.art = A.panel()
        self.kids, self.panels, self.overlay = [], [], []
        self.pos = {}                 # key -> (x0, y0, x1, y1) of the control with its caption and value
        self.subs = [[]]              # per sub-tab: [(keys, rect)]

    # controls
    def knob(self, key, cx, cy, cap, size=KNOB, navy=False):
        """a knob as the original skin: the caption on a slate pill above, the knob, the live value under it (in a light box on the
        charcoal, where a white tick scale rings the knob)"""
        r = int(size * 0.34)                                   # the knob's visible radius inside its film frame
        A.caption(self.art, cx, cy - r - 40, cap, size=16, width=130)
        A.knob_ring(self.art, cx, cy, r)                       # the lilac disc with its tick scale (the n2xTrancy panel)
        stage = STAGES.get(key)
        if stage:                                              # the envelope stage, pictured over the caption as on the panel
            A.stage_glyph(self.art, cx, cy - r - 64, stage, A.WHITE if navy else A.INK)
        if navy:
            A.value_box(self.art, cx, cy + r + 36)
        self.kids.append(entry(key, kname(size), {"version": 1, "handleName": "Data"},
                               "%d %d %d %d" % (cx - size // 2, cy - size // 2, size, size), remap=P(key), focus="Yes"))
        self.kids.append(label("%d %d 100 26" % (cx - 50, cy + r + 23), key, 24, hexcol(A.INK), style="Bold"))
        hw = 62 if size >= KNOB else 56
        self.pos[key] = (cx - hw, cy - r - (76 if stage else 54), cx + hw, cy + r + 50)

    def leds(self, key, x, y, w, cap=None, rh=28, labels=None, cols=1, order=None, navy=False, cyc=True):
        """a choice as the original skin's segmented buttons: one slate button per option, red while it is the choice (radio Buttons)"""
        opts = PARAMS[key]["options"]
        names = labels or opts
        order = order or list(range(len(opts)))           # the rows top to bottom, as option indices
        if cap:
            A.caption(self.art, x + w * cols // 2, y - 20, cap, size=15, width=w * cols)
        rows = -(-len(order) // cols)
        for r, i in enumerate(order):
            c, rr = r // rows, r % rows
            bx, by = x + c * w, y + rr * rh
            ink, t = (A.WHITE, "n") if navy else (A.INK, "g")
            on = save(A.led_option(w, rh, names[i], True, ink=ink), "opt_%s_%d_%d_%s_on.png" % (slug(names[i]), w, rh, t))
            off = save(A.led_option(w, rh, names[i], False, ink=ink), "opt_%s_%d_%d_%s_off.png" % (slug(names[i]), w, rh, t))
            button(self.kids, key, "%d %d %d %d" % (bx, by, w, rh), on, off, bid=i, n=len(opts), name="%s %d" % (key, i))
        bottom = y + rows * rh
        if key + "_next" in LOCK and cyc:              # the Nord panel's button that steps through the options (round)
            cw, ch = 60, 26
            on = save(A.key_button(cw, ch, "", True), "cyc_%dx%d_on.png" % (cw, ch))
            off = save(A.key_button(cw, ch, "", False), "cyc_%dx%d_off.png" % (cw, ch))
            button(self.kids, key + "_next", "%d %d %d %d" % (x + 4, bottom + 6, cw, ch), on, off)
            bottom += 6 + ch
        self.pos[key] = (x, y - 34, x + w * cols, bottom)

    def leds_n(self, *a, **k):
        self.leds(*a, navy=True, **k)

    def toggle(self, key, cx, cy, cap, w=64, h=32):
        """an on/off choice as the original's slider switch, its caption on a pill above"""
        A.caption(self.art, cx, cy - h // 2 - 20, cap, size=15, width=140)
        on = save(A.toggle(w, h, cap, True), "tg_%dx%d_on.png" % (w, h))
        off = save(A.toggle(w, h, cap, False), "tg_%dx%d_off.png" % (w, h))
        button(self.kids, key, "%d %d %d %d" % (cx - w // 2, cy - h // 2, w, h), on, off)
        self.pos[key] = (cx - 60, cy - h // 2 - 34, cx + 60, cy + h // 2)

    def key(self, key, cx, cy, cap, w=96, h=48, dark=False):
        t = "key_%s_%dx%d%s" % (slug(cap), w, h, "_d" if dark else "")
        on = save(A.key_button(w, h, cap, True, dark=dark), t + "_on.png")
        off = save(A.key_button(w, h, cap, False, dark=dark), t + "_off.png")
        button(self.kids, key, "%d %d %d %d" % (cx - w // 2, cy - h // 2, w, h), on, off)

    # Q-Link blocks
    def block(self, keys, rect=None, pad=3):
        ks = [k for k in keys if k]
        if rect is None:
            boxes = [self.pos[k] for k in ks]
            rect = (min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad, max(b[2] for b in boxes) + pad, max(b[3] for b in boxes) + pad)
        assert len(self.subs[-1]) < 4, "%s: more than four Q-Link blocks on a sub-tab" % self.name
        self.subs[-1].append((ks, rect))

    def subtab(self):
        self.subs.append([])

    def section(self, x0, y0, x1, y1, title):
        A.section(self.art, x0, y0, x1, y1, title)

    def tabs(self, bgfile):
        kids = [entry("bg", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": bgfile}, "0 0 1280 628")] + self.kids + self.panels + self.overlay
        out = []
        for sub, blocks in enumerate(self.subs):
            groups = ["%d %d %d %d" % (r[0], r[1], r[2] - r[0], r[3] - r[1]) for _, r in blocks]
            out.append({"version": 1, "tabName": self.name, "fnKeyIndex": self.fn, "fnKeySubIndex": sub,
                        "componentDefinition": component(kids, background=bg(hexcol(A.RED))), "qlinkBoundsData": groups})
        return out


def display_row(pg, x0, y0, y1, fields, size, aw=40):
    """one row of the red display: fields [(x_end, get, prev, next)], a rule between fields, arrows that step the bank / sound"""
    d = ImageDraw.Draw(pg.art)
    xs = x0
    for i, (xe, get, prev, nxt) in enumerate(fields):
        if i:
            d.line((xs, y0 + 6, xs, y1 - 6), fill=(90, 20, 20, 255), width=1)
        cy = (y0 + y1) // 2
        pad = aw if prev else 0
        if prev:
            for k, ax, dr in ((prev, xs, -1), (nxt, xe - aw, 1)):
                A.tri(d, ax + aw // 2, cy, dr)
                hit_zone(pg.kids, k, ax, y0, aw, y1 - y0)
        pg.kids.append(label("%d %d %d %d" % (xs + pad + 8, y0, xe - xs - 2 * pad - 14, y1 - y0), get, size, hexcol(A.LCD_INK), "left verticallyCentred", "Bold"))
        if get in FIELD_KEY:
            fw, fh = xe - xs - 2 * pad, y1 - y0
            FIELDS.add((fw, fh))
            pg.kids.append(entry(FIELD_KEY[get] + " field", "lcdfield%dx%d" % (fw, fh), {"version": 1, "handleName": "Data"},
                                 "%d %d %d %d" % (xs + pad, y0, fw, fh), remap=P(FIELD_KEY[get]), focus="Yes"))
        xs = xe


# ---- the pages ---------------------------------------------------------------------------------------------------------------
FAV_KEYS = (("all_notes_off", "PANIC"), ("init_patch", "RELOAD"), ("random_patch", "RANDOM"), ("fav_save", "+ FAV"), ("fav_delete", "- FAV"))


def page_main(fn):
    """MAIN, the original skin's MAIN with the new controls: the NODAL RED 2X lettering and the red display (bank | sound, < >) along the
    top on the red; the charcoal performance panel (MASTER LEVEL, the status display, BEND RANGE, the keys, then play mode,
    portamento with AUTO, detune with UNISON, octave shift, mod wheel); QUICK EDIT at the right, two rows of four knobs."""
    pg = Page("MAIN", fn)
    A.wordmark(pg.art, 14, 34, 270)
    x0, x1, y0, y1 = 304, 1268, 26, 92
    A.lcd(pg.art, x0, y0, x1, y1)
    display_row(pg, x0, y0, y1, [(640, "bank_name", "bank_prev", "bank_next"), (x1, "preset_name", "preset_prev", "preset_next")], 30, aw=40)
    A.dark_panel(pg.art, 8, 112, 776, 620)
    pg.knob("gain", 80, 204, "MASTER LEVEL", navy=True)
    A.lcd(pg.art, 168, 148, 560, 236)
    display_row(pg, 168, 148, 192, [(560, "loading_status", None, None)], 24)
    display_row(pg, 168, 192, 236, [(560, "engine_stats", None, None)], 24)
    pg.knob("bend_range", 680, 204, "BEND RANGE", navy=True)
    for i, (k, cap) in enumerate(FAV_KEYS):
        pg.key(k, 80 + i * 150, 318, cap, w=138, h=40)
    pg.kids.append(label("168 238 392 22", "fav_text", 16, hexcol(A.INK_ON_NAVY)))
    ry = 384
    pg.leds_n("VoiceMode", 24, ry, 130, "PLAY MODE", rh=34, order=[0, 1, 2], labels=["Mono", "Legato", "Poly"])
    pg.knob("Portamento", 250, ry + 50, "PORTAMENTO", navy=True)
    pg.toggle("Auto", 250, ry + 176, "AUTO")
    pg.knob("unison_detune", 400, ry + 50, "DETUNE", navy=True)
    pg.toggle("Unison", 400, ry + 176, "UNISON")
    pg.leds_n("OctaveShift", 486, ry, 120, "OCT SHIFT", rh=32)
    pg.leds_n("ModWheelDest", 626, ry, 136, "MOD W DEST", rh=32, labels=["Filter", "FM", "Osc 2", "LFO 1", "Morph"])
    pg.section(786, 112, 1272, 620, "quick edit")
    a = [("Cutoff", "Cutoff"), ("Resonance", "Resonance"), ("FilterEnvAmount", "Env Amt"), ("FilterEnvD", "F.Decay")]
    b = [("AmpEnvA", "Attack"), ("AmpEnvR", "Release"), ("Mix", "Osc Mix"), ("Lfo1Rate", "LFO 1 Rate")]
    for i, (k, c) in enumerate(a):
        pg.knob(k, 850 + i * 120, 262, c)
    for i, (k, c) in enumerate(b):
        pg.knob(k, 850 + i * 120, 482, c)
    pg.block([k for k, _ in a]); pg.block([k for k, _ in b])
    pg.block(["gain", "bend_range", "Portamento", "unison_detune"])
    pg.block(["bank_index", "preset"], rect=(x0 - 4, y0 - 4, x1 + 4, y1 + 4))
    keyboard(pg)
    return pg


def page_banks(fn):
    """BANKS: the red display with BANK / SOUND steppers and the keys on the navy; a BANKS section (10 tiles, the page stepper under
    them, level with the last program row) and a PROGRAMS section (30 tiles, 3 x 10 down the columns, its page stepper in its header
    at the far right). Tile names are Value labels UNDER transparent Buttons (a label on top would swallow the tap); a picked tile
    stays lit (the engine's <tile>_on)."""
    pg = Page("BANKS", fn)
    x0, x1 = 16, 760
    A.lcd(pg.art, x0, 14, x1, 66)
    display_row(pg, x0, 14, 66, [(300, "bank_name", "bank_prev", "bank_next"), (x1, "preset_name", "preset_prev", "preset_next")], 28, aw=36)
    for i, (k, cap) in enumerate(FAV_KEYS[2:]):
        pg.key(k, 852 + i * 132, 40, cap, w=118, h=50)
    layer = Image.new("RGBA", pg.art.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    on_cache = {}

    def tile_on(w, h):
        S = 4
        im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        dd = ImageDraw.Draw(im)
        dd.rounded_rectangle((0, 0, w * S - 1, h * S - 1), 3 * S, fill=A.RED + (140,), outline=A.RED + (255,), width=3 * S)
        return im.resize((w, h), Image.LANCZOS)

    def tile(key, x, y, w, h):
        ld.rounded_rectangle((x, y, x + w - 1, y + h - 1), 3, fill=A.TILE + (255,))
        pg.kids.append(label("%d %d %d %d" % (x + 10, y, w - 16, h), key, 21, hexcol(A.TILE_INK), "left verticallyCentred", "Bold"))
        if (w, h) not in on_cache:
            on_cache[(w, h)] = save(tile_on(w, h), "tile_on_%dx%d.png" % (w, h))
        button(pg.kids, key, "%d %d %d %d" % (x, y, w, h), on_cache[(w, h)], CLEAR, name=key + " tile")

    def stepper(x0, y0, w, h, get, prev, nxt, title=None):
        """a page stepper in a section's header: < > keys at its ends, the page text on a small red display between them
        (with the section's title at its left when given)"""
        aw = 44
        for k, bx, dr in ((prev, x0, -1), (nxt, x0 + w - aw, 1)):
            pg.key(k, bx + aw // 2, y0 + h // 2, "<" if dr < 0 else ">", w=aw, h=h, dark=True)
        tx = x0 + aw + 4
        if title:
            t = A.text_img(title, 20, A.TITLE, slant=0.2)
            layer.alpha_composite(t, (tx + 8, y0 + h // 2 - t.height // 2 + 1))
            tx += t.width + 22
        ld.rounded_rectangle((tx, y0, x0 + w - aw - 5, y0 + h - 1), 5, fill=A.LCD_BG + (255,))
        pg.kids.append(label("%d %d %d %d" % (tx, y0, x0 + w - aw - 5 - tx, h), get, 20, hexcol(A.LCD_INK), style="Bold"))

    ty0, pitch, th = 124, 48, 42                        # the tile rows: banks and programs on the same grid
    pg.section(10, 82, 316, 620, "")
    for i in range(10):
        tile("bank_slot_%d" % (i + 1), 22, ty0 + pitch * i, 282, th)
    pg.section(326, 82, 1270, 620, "programs")
    pg.kids.append(label("500 84 300 26", "fav_text", 18, hexcol(A.TITLE), "left verticallyCentred", "Bold"))
    for c in range(3):
        for r in range(10):
            tile("patch_slot_%d" % (c * 10 + r + 1), 338 + c * 310, ty0 + pitch * r, 300, th)
    pg.art = Image.alpha_composite(pg.art, layer)
    pg.art_after = []
    # the steppers drawn on top of the sections (their keys are widgets)
    layer = Image.new("RGBA", pg.art.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    stepper(16, 84, 294, 24, "bank_page_text", "bank_page_prev", "bank_page_next", title="BANKS")
    stepper(1006, 84, 258, 24, "patch_page_text", "patch_page_prev", "patch_page_next")
    pg.art = Image.alpha_composite(pg.art, layer)
    pg.block(["bank_index", "preset"], rect=(x0 - 4, 10, x1 + 4, 70))
    keyboard(pg)
    return pg


KB_ROWS = [("1234567890", ["kb_bksp"]), ("QWERTYUIOP", []), ("ASDFGHJKL-", []), ("ZXCVBNM", ["kb_space"])]


def keyboard(pg):
    """The naming keyboard for +FAV (Profit-5's): a full-page panel, the name being typed with the maximum length at its right,
    42 keys; shown while kb_open = 1, over everything else on the page (it is added last)."""
    ind = ["IndexedEnabling/1/2/Parameter %d" % PI("kb_open")]
    panel = A.panel()
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle((20, 8, 1260, 620), 14, fill=A.FRAME + (255,))
    d.rounded_rectangle((26, 14, 1254, 614), 10, fill=A.CHAR + (255,))
    t = A.text_img("FAVOURITE NAME", 21, A.FRAME)
    panel.alpha_composite(t, (48, 52 - t.height // 2))
    A.lcd(panel, 290, 26, 1236, 78)
    mx = A.text_img("MAX %d CHARACTERS" % MAX_CHARS, 15, (255, 150, 140))
    panel.alpha_composite(mx, (1226 - mx.width, 52 - mx.height // 2))
    pg.overlay.append(entry("kb panel", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": save(panel.convert("RGB"), "kb_panel.png")},
                            "0 0 1280 628", ind=ind))
    pg.overlay.append(entry("kb name", "Label", {"version": 1, "textStyle": text_style(44, hexcol(A.LCD_INK), "left verticallyCentred", "Bold"),
                                                 "type": "Value", "handleName": "Data"}, "306 26 %d 52" % (1220 - 306 - mx.width - 20), P("fav_name"), ind=ind))
    kw, kh, gap, x0, y0 = 98, 84, 8, 64, 100

    def kbkey(k, cap, x, y, w):
        on = save(A.key_cap(w, kh, cap, True), "kb_%s_%d_on.png" % (k, w))
        off = save(A.key_cap(w, kh, cap, False), "kb_%s_%d_off.png" % (k, w))
        pg.overlay.append(entry(k, "Button", {"version": 2, "onImage": on, "offImage": off, "buttonId": 1, "numButtonsInGroup": 1,
                                              "handleName": "Data", "gestureBehaviour": GESTURE}, "%d %d %d %d" % (x, y, w, kh), remap=P(k), ind=ind))
    for r, (chars, extra) in enumerate(KB_ROWS):
        y = y0 + r * (kh + gap)
        x = x0 + r * 30
        for c in chars:
            kbkey("kb_" + ("dash" if c == "-" else c.lower()), c, x, y, kw)
            x += kw + gap
        for k in extra:
            kbkey(k, {"kb_bksp": "DELETE", "kb_space": "SPACE"}[k], x, y, 1216 - x)
    y = y0 + 4 * (kh + gap)
    kbkey("kb_shift", "SHIFT", x0, y, 220)
    kbkey("kb_cancel", "CANCEL", 640 - 130, y, 260)
    kbkey("kb_save", "SAVE", 1216 - 260, y, 260)


def page_oscfilter(fn):
    """OSC & FILTER, the middle of the panel: OSC 1 | OSC 2 | MIX along the top, the FILTER under them (type, frequency, resonance,
    envelope amount, keyboard tracking, velocity, distortion, its envelope)."""
    pg = Page("OSC/FILTER", fn)
    pg.section(10, 8, 400, 236, "osc 1")
    pg.leds("O1Waveform", 24, 78, 130, "WAVEFORM")
    pg.knob("FmDepth", 232, 136, "FM Amount")
    pg.knob("PW", 340, 136, "Pulse Width")
    pg.section(410, 8, 990, 236, "osc 2")
    pg.leds("O2Waveform", 424, 78, 130, "WAVEFORM")
    pg.toggle("O2Keytrack", 610, 90, "KBD TRACK")
    pg.toggle("Sync", 610, 152, "SYNC")
    pg.toggle("RingMod", 610, 214, "RING MOD")
    pg.knob("O2Pitch", 760, 136, "Semitones")
    pg.knob("O2PitchFine", 890, 136, "Fine Tune")
    pg.section(1000, 8, 1270, 236, "mix")
    pg.knob("Mix", 1135, 136, "Osc 1 / Osc 2")
    pg.section(10, 246, 1270, 618, "filter")
    pg.leds("FilterType", 24, 306, 140, "FILTER TYPE", order=[2, 1, 0, 3, 4, 5], labels=["LP 12 dB", "LP 24 dB", "HP 24 dB", "Band Pass", "Notch + LP", "Notch"])
    pg.leds("FilterKeytrack", 186, 306, 110, "KBD TRACK", order=[3, 2, 1, 0], labels=["Off", "1/3", "2/3", "Full"])
    pg.toggle("FilterVelocity", 370, 330, "VELOCITY")
    pg.toggle("Distortion", 370, 410, "DISTORTION")
    ky = 362
    for i, (k, c) in enumerate((("Cutoff", "Frequency"), ("Resonance", "Resonance"), ("FilterEnvAmount", "Env Amount"))):
        pg.knob(k, 530 + i * 150, ky, c)
    ky2 = 540
    for i, (k, c) in enumerate((("FilterEnvA", "Attack"), ("FilterEnvD", "Decay"), ("FilterEnvS", "Sustain"), ("FilterEnvR", "Release"))):
        pg.knob(k, 530 + i * 150, ky2, c)
    pg.block(["FmDepth", "PW"]); pg.block(["O2Pitch", "O2PitchFine"]); pg.block(["Mix"])
    pg.block(["Cutoff", "Resonance", "FilterEnvAmount"])
    pg.subtab()
    pg.block(["FilterEnvA", "FilterEnvD", "FilterEnvS", "FilterEnvR"])
    return pg


def page_mod(fn):
    """AMP & MOD: the AMPLIFIER (ADSR, gain) and the MOD ENV along the top; LFO 1 and LFO 2 / ARPEGGIATOR under them, each with its LED
    choices and cycle keys, the knobs at its right."""
    pg = Page("AMP/MOD", fn)
    pg.section(10, 8, 760, 250, "amplifier")
    for i, (k, c) in enumerate((("AmpEnvA", "Attack"), ("AmpEnvD", "Decay"), ("AmpEnvS", "Sustain"), ("AmpEnvR", "Release"), ("Gain", "Gain"))):
        pg.knob(k, 90 + i * 145, 156, c)
    pg.section(770, 8, 1270, 250, "mod env")
    pg.leds("ModEnvDest", 784, 92, 110, "DEST", labels=["Osc 2", "FM", "PW"])
    pg.knob("ModEnvA", 960, 156, "Attack")
    pg.knob("ModEnvD", 1080, 156, "Decay")
    pg.knob("ModEnvLevel", 1200, 156, "Amount")
    pg.section(10, 260, 630, 618, "lfo 1")
    pg.leds("Lfo1Waveform", 24, 320, 120, "WAVEFORM")
    pg.leds("Lfo1Dest", 150, 320, 120, "DEST")
    pg.leds("lfo1_sync", 280, 320, 90, "SYNC", cols=2)
    pg.knob("Lfo1Rate", 550, 370, "Rate")
    pg.knob("Lfo1Level", 550, 530, "Amount")
    pg.section(640, 260, 1270, 618, "lfo 2 / arpeggiator")
    pg.leds("Lfo2Dest", 654, 320, 160, "DEST / ARP")
    pg.leds("lfo2_sync", 830, 320, 90, "SYNC", cols=2)
    pg.knob("Lfo2Rate", 1170, 370, "Rate")
    pg.knob("ArpRange", 1170, 530, "Amt / Range")
    pg.block(["AmpEnvA", "AmpEnvD", "AmpEnvS", "AmpEnvR"]); pg.block(["Gain"]); pg.block(["ModEnvA", "ModEnvD", "ModEnvLevel"])
    pg.subtab()
    pg.block(["Lfo1Rate", "Lfo1Level"]); pg.block(["Lfo2Rate", "ArpRange"])
    return pg


def page_morph(fn):
    """MORPH: how far each parameter moves with the morph source (velocity or the mod wheel), as on the panel (hold the morph button and
    turn a knob there): rows of sections, OSC | AMP, FILTER | VOICE, MOD; every amount -128 .. +127."""
    pg = Page("MORPH", fn)
    M = 72
    rows = [
        [("osc", 10, 630, [("O2PitchSens", "Semitones"), ("O2PitchFineSens", "Fine Tune"), ("MixSens", "Mix"), ("PWSens", "Pulse Width"), ("FmDepthSens", "FM Amount")]),
         ("amplifier", 640, 1270, [("AmpEnvASens", "Attack"), ("AmpEnvDSens", "Decay"), ("AmpEnvSSens", "Sustain"), ("AmpEnvRSens", "Release"), ("GainSens", "Gain")])],
        [("filter", 10, 890, [("CutoffSens", "Frequency"), ("ResonanceSens", "Resonance"), ("FilterEnvAmountSens", "Env Amount"), ("FilterEnvASens", "F.Attack"),
                              ("FilterEnvDSens", "F.Decay"), ("FilterEnvSSens", "F.Sustain"), ("FilterEnvRSens", "F.Release")]),
         ("voice", 900, 1270, [("PortamentoSens", "Portamento")])],
        [("mod", 10, 1270, [("ModEnvASens", "M.Env Attack"), ("ModEnvDSens", "M.Env Decay"), ("ModEnvLevelSens", "M.Env Amount"), ("Lfo1RateSens", "LFO 1 Rate"),
                            ("Lfo1LevelSens", "LFO 1 Amount"), ("Lfo2RateSens", "LFO 2 Rate"), ("ArpRangeSens", "Arp Range")])]]
    blocks = []
    for r, row in enumerate(rows):
        y0 = 8 + r * 206
        for title, x0, x1, knobs in row:
            pg.section(x0, y0, x1, y0 + 198, title)
            pitch = min(170, (x1 - x0 - 20) // max(len(knobs), 2))
            xs = [x0 + 10 + pitch // 2 + i * pitch for i in range(len(knobs))]
            if len(knobs) == 1:
                xs = [x0 + 90]
            for (k, c), x in zip(knobs, xs):
                pg.knob(k, x, y0 + 112, c, size=M)
            keys = [k for k, _ in knobs]
            for i in range(0, len(keys), 4):
                blocks.append(keys[i:i + 4])
    A.plain_text(pg.art, 1150, 8 + 206 + 100, "how far each value", size=15, colour=A.INK, width=200)
    A.plain_text(pg.art, 1150, 8 + 206 + 122, "moves with the mod", size=15, colour=A.INK, width=200)
    A.plain_text(pg.art, 1150, 8 + 206 + 144, "wheel set to Morph", size=15, colour=A.INK, width=200)
    for i, bl in enumerate(blocks):
        if i and i % 4 == 0:
            pg.subtab()
        pg.block(bl, pad=1)
    return pg


PAGES = [("MAIN", page_main), ("BANKS", page_banks), ("OSC/FILTER", page_oscfilter), ("AMP/MOD", page_mod), ("MORPH", page_morph)]


def qlinks_for(pages):
    maps = []
    for pg in pages:
        for sub, blocks in enumerate(pg.subs):
            q = {"Q-Link %d" % n: -1 for n in range(1, 17)}
            column = bool(blocks) and all((r[3] - r[1]) > (r[2] - r[0]) for _, r in blocks)
            for gi, (keys, _) in enumerate(blocks[:4]):
                for i, key in enumerate(keys[:4]):
                    q["Q-Link %d" % ((13 + gi - 4 * i) if column else (13 - 4 * gi + i))] = PI(key)
            maps.append({"Tab": pg.fn + 1, "SubTab": sub + 1, "Bank Direction": "Column" if column else "RowTopDown", "Q-Links": q})
    return {"version": 4, "info": {"version": 1, "type": "CompleteDescription"},
            "Screen Mode Q-Links": {"version": 4, "map": maps}, "Program Mode Q-Links": {"Q-Link %d" % n: -1 for n in range(1, 17)}}


# ---- offline preview: compose a tab the way the MPC draws it --------------------------------------------------------------
SAMPLE = {"preset_name": "04 SOFT PAD", "bank_name": "STARTERS", "loading_status": "Ready - ROM loaded",
          "engine_stats": "DROPOUTS 0   CPU 70%", "patch_page_text": "PAGE 1 / 4", "bank_page_text": "1 / 1", "fav_text": "FAVOURITES 3 / 64",
          "bank_slot_1": "STARTERS", "bank_slot_2": "PROGBANK0", "bank_slot_3": "PROGBANK1", "bank_slot_4": "PROGBANK2", "bank_slot_5": "PROGBANK3"}
NAMES = ["SAW LEAD", "PULSE BASS", "SOFT PAD", "PLUCK", "SYNC SWEEP", "", ""]


def sample_text(key):
    if key in SAMPLE:
        return SAMPLE[key]
    if key.startswith("bank_slot_"):
        return ""
    if key.startswith("patch_slot_"):
        i = int(key[11:])
        return "%02d %s" % (i, NAMES[i % len(NAMES)])
    p = PARAMS.get(key, {})
    if "options" in p:
        return p["options"][p["options"].index(p["default"]) if isinstance(p["default"], str) else int(p["default"])]
    return str(p.get("default", ""))


def preview(pages, arts, defs, sub=0, keyboard=False):
    os.makedirs(PREVIEW, exist_ok=True)
    kb = "IndexedEnabling/1/2/Parameter %d" % PI("kb_open")
    for pg in pages:
        im = Image.open(os.path.join(OUT, arts[pg.name])).convert("RGBA")
        d = ImageDraw.Draw(im)
        for e in pg.kids + pg.panels + pg.overlay:
            cd = e["componentData"]
            x, y, w, h = [int(float(v)) for v in e["bounds"]["bounds"].split()]
            hs = e["bounds"].get("additionalInvalidatingHandles", [])
            if (kb in hs) != keyboard and (keyboard or kb in hs):
                continue
            if cd["type"].startswith("nknob"):
                st = Image.open(os.path.join(OUT, cd["type"] + ".png"))
                im.alpha_composite(st.crop((0, w * 60, w, w * 61)).convert("RGBA"), (x, y))
            elif cd["type"] == "Image" and keyboard:
                im.alpha_composite(Image.open(os.path.join(OUT, cd["data"]["image"])).convert("RGBA"), (x, y))
            elif cd["type"] == "Label":
                key = LOCK[int(e["handle remapping"]["map"][0]["value"].split()[1])]
                ts = cd["data"]["textStyle"]
                cen = "horizontallyCentred" in ts["justification"]
                col = tuple(int(ts["colour"][i:i + 2], 16) for i in (2, 4, 6))
                f, s = A.F(int(ts["font"]["height"] * TUI_PX * 1.25), ts["font"]["style"] == "Bold"), ("My Pad_" if key == "fav_name" else sample_text(key))
                if f.getlength(s) > w:
                    while s and f.getlength(s + "...") > w:
                        s = s[:-1]
                    s = s.rstrip() + "..."
                d.text((x + w / 2 if cen else x + 2, y + h / 2), s, font=f, fill=col, anchor="mm" if cen else "lm")
            elif cd["type"] == "Button" and cd["name"] in ("bank_slot_1 tile", "patch_slot_4 tile"):
                im.alpha_composite(Image.open(os.path.join(OUT, cd["data"]["onImage"])).convert("RGBA"), (x, y))
            elif cd["type"] == "Button" and cd["data"]["offImage"] != CLEAR:
                k = LOCK[int(e["handle remapping"]["map"][0]["value"].split()[1])]
                p = PARAMS.get(k, {})
                dflt = p.get("default", 0)
                if "options" in p and isinstance(dflt, str):
                    dflt = p["options"].index(dflt)
                lit = ("options" in p and cd["data"]["numButtonsInGroup"] > 1 and cd["data"]["buttonId"] == dflt) or k in ("Sync", "Distortion")
                im.alpha_composite(Image.open(os.path.join(OUT, cd["data"]["onImage" if lit else "offImage"])).convert("RGBA"), (x, y))
        for _, r in (pg.subs[sub] if sub < len(pg.subs) and not keyboard else []):   # the Q-Link outlines (the bounds overlay on)
            d.rectangle(r, outline=(255, 255, 255, 200), width=2)
        name = re.sub(r"[^a-z0-9]+", "_", pg.name.lower()).strip("_")
        im.convert("RGB").save(os.path.join(PREVIEW, "%s%s.png" % (name, "_keyboard" if keyboard else "")))


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    save(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), CLEAR)
    pages, arts, tabs = [], {}, []
    for fn, (name, make) in enumerate(PAGES):
        pg = make(fn)
        arts[name] = save(pg.art.convert("RGB"), "bg_%s.png" % re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"))
        pages.append(pg)
        tabs += pg.tabs(arts[name])
    used = {e["componentData"]["type"] for pg in pages for e in pg.kids if e["componentData"]["type"].startswith("nknob")}
    for t in sorted(used):                                   # every knob size used gets its strip and component
        size = int(t[5:])
        if not os.path.exists(os.path.join(OUT, t + ".png")):
            save(A.knob_strip(size), t + ".png")
    globals()["KNOB_SIZES"] = tuple(sorted(int(t[5:]) for t in used))
    for pg in pages:   # the Q-Link frames of one sub-tab must not overlap (the MPC draws them all)
        for sub, blocks in enumerate(pg.subs):
            rs = [r for _, r in blocks]
            for i in range(len(rs)):
                for j in range(i + 1, len(rs)):
                    a, b = rs[i], rs[j]
                    assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), "%s sub-tab %d: Q-Link frames overlap %s %s" % (pg.name, sub + 1, a, b)
    on_q = {k for pg in pages for blocks in pg.subs for keys, _ in blocks for k in keys}
    shown = {k for pg in pages for k in pg.pos if "options" not in PARAMS.get(k, {})}
    missing = sorted(shown - on_q)
    if missing:
        print("knobs on no Q-Link:", ", ".join(missing))
    defs = definitions()
    tui = {"pageData": {"version": 1, "componentDefinitions": {"version": 2, "importFiles": [], "localComponentDefinitions": defs},
                        "replacementStrings": [], "info": {"version": 1, "type": "CompleteDescription"}, "tabs": tabs}}
    open(os.path.join(OUT, "TUI.json"), "w").write(dump(tui) + "\n")
    open(os.path.join(OUT, "Q-Links.json"), "w").write(dump(qlinks_for(pages)) + "\n")
    bad = [f for f in os.listdir(OUT) if re.search(r'[<>:"/\\|?*]', f)]
    assert not bad, "file names that exFAT rejects: %s" % bad
    low = {}
    for f in os.listdir(OUT):                                # the MPC's drive is case-insensitive
        assert f.lower() not in low, "file names differ only in case: %s %s" % (f, low[f.lower()])
        low[f.lower()] = f
    for f in os.listdir(OUT):
        if f.endswith(".png"):
            assert Image.open(os.path.join(OUT, f)).height <= 16384, "%s is taller than 16384 px" % f
    if "--preview" in sys.argv:
        dd = {x["key"]: x["value"] for x in defs}
        preview(pages, arts, dd)
        preview([pg for pg in pages if pg.name == "MAIN"], arts, dd, keyboard=True)
    print("wrote", OUT, "-", len(tabs), "tabs,", len(os.listdir(OUT)), "files")


if __name__ == "__main__":
    main()
