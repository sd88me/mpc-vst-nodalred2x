#!/usr/bin/env python3
"""NodalRed2x's art library: the primitives of the native skin, drawn from code in the look of the Clavia Nord Lead 2 / 2x front panel
(docs/reference/): the navy panel, light-grey section fields framed in yellow with the title on the frame, black knobs in a red ring
with a white pointer, black rounded buttons, small green LEDs beside every choice, the red 7-segment program display. tools/make_tui.py
lays the pages out from these; a restyle is this file only.

Fonts: Titillium Web (SIL OFL 1.1, tools/fonts/) for everything baked; the MPC draws live text in Titillium Web too."""
import math, os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIT = os.path.join(ROOT, "tools", "fonts", "TitilliumWeb-SemiBold.ttf")
TIT_B = os.path.join(ROOT, "tools", "fonts", "TitilliumWeb-Bold.ttf")

# ---- palette: the 0.1.0 skin's (vst/layout.conf theme_* lines, from gearmulator's n2xTrancy by theusualsuspects) ------------
RED = (195, 28, 43)            # the body
RED_DK = (128, 12, 22)
CHAR = (59, 55, 65)            # the charcoal area of the program / performance controls
GREY = (168, 164, 168)         # a section's field
GREY_LO = (138, 136, 144)
SLATE = (106, 110, 150)        # title bars, caption pills, buttons, tiles
SLATE_HI = (128, 132, 172)
OPT = (138, 136, 160)          # an option button, off
FRAME = SLATE                  # (focus outline)
TITLE = (255, 255, 255)        # a section's title on its bar
INK = (32, 32, 48)             # values on grey
INK_ON_NAVY = (255, 255, 255)  # text on charcoal
NAVY = CHAR
VALUE = INK
VALUE_BOX = (176, 174, 180)
TICK = (52, 50, 66)            # a knob's scale on the grey sections    # the small value box under a knob on charcoal
KEY = SLATE
LED_ON = (90, 255, 80)
LED_OFF = (36, 70, 38)
LCD_BG = (42, 6, 6)            # the red LED display
LCD_INK = (255, 48, 48)
LCD_BEZEL = (26, 26, 34)
WHITE = (255, 255, 255)
TILE = SLATE
TILE_INK = WHITE
SEL = CHAR
KNOB_SRC = os.path.join(ROOT, "skin", "n2xTrancy", "knob_big.png")
LOGO = os.path.join(ROOT, "skin", "parts", "logo.png")

_fonts = {}


def F(size, bold=True):
    k = (size, bold)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(TIT_B if bold else TIT, size)
    return _fonts[k]


def fit(text, size, width, bold=True):
    while size > 9 and F(size, bold).getlength(text) > width:
        size -= 1
    return F(size, bold)


def text_img(text, size, colour, bold=True, slant=0.0):
    f = F(size, bold)
    l, t, r, b = f.getbbox(text)
    im = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - l, 2 - t), text, font=f, fill=colour)
    if slant:                                      # an oblique (the original's italic titles; Titillium has no italic here)
        w, h = im.size
        e = int(h * slant) + 2
        im = im.transform((w + e, h), Image.AFFINE, (1, slant, -slant * h, 0, 1, 0), Image.BICUBIC)
    return im


def _ss(w, h, S=4):
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im), S


# ---- the panel and its sections ---------------------------------------------------------------------------------------------
def panel(w=1280, h=628):
    """the red body, flat as in the original skin"""
    return Image.new("RGBA", (w, h), RED + (255,))


def dark_panel(im, x0, y0, x1, y1, r=10):
    """the charcoal area of the program / performance controls (white text on it)"""
    ImageDraw.Draw(im).rounded_rectangle((x0, y0, x1, y1), r, fill=CHAR + (255,))


def section(im, x0, y0, x1, y1, title, bar=30):
    """a section as the original skin draws one: a grey field, a slate title bar across its top, the title white and oblique at its left"""
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((x0, y0, x1, y1), 10, fill=GREY + (255,))
    d.rounded_rectangle((x0, y0, x1, y0 + bar), 10, fill=SLATE + (255,))
    d.rectangle((x0, y0 + bar - 10, x1, y0 + bar), fill=SLATE + (255,))
    if title:
        t = text_img(title.upper(), 20, TITLE, slant=0.2)
        im.alpha_composite(t, (x0 + 14, y0 + bar // 2 - t.height // 2 + 1))


def caption(im, cx, cy, text, size=16, colour=None, width=130):
    """a caption on a slate pill (the original skin's labels), white text"""
    if not text:
        return
    f = fit(text, size, width - 16)
    w = int(f.getlength(text)) + 18
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((cx - w // 2, cy - 12, cx + w // 2, cy + 12), 12, fill=SLATE + (255,))
    d.text((cx, cy), text, font=f, fill=WHITE + (255,), anchor="mm")


def plain_text(im, cx, cy, text, size=16, colour=WHITE, width=200):
    f = fit(text, size, width)
    ImageDraw.Draw(im).text((cx, cy), text, font=f, fill=colour + (255,), anchor="mm")


def value_box(im, cx, cy, w=68, h=26):
    """the light box a value sits in under a knob on charcoal"""
    ImageDraw.Draw(im).rounded_rectangle((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2), 4, fill=VALUE_BOX + (255,))


def ticks(im, cx, cy, r, n=11, colour=WHITE):
    """the scale round a knob on charcoal: short white ticks over 270 degrees"""
    d = ImageDraw.Draw(im)
    for k in range(n):
        t = math.radians(135 + 270 * k / (n - 1))
        d.line((cx + math.cos(t) * r, cy + math.sin(t) * r, cx + math.cos(t) * (r + 9), cy + math.sin(t) * (r + 9)), fill=colour + (255,), width=2)


RING = (150, 148, 196)         # the lilac disc behind every knob (gearmulator's n2xTrancy panel)
RING_TICK = (58, 56, 92)


def knob_ring(im, cx, cy, r, n=11):
    """the lilac band of a knob's scale (270 degrees, open at the bottom) with its ticks (the n2xTrancy panel's knob surround)"""
    S = 4
    R = r + 15
    W = 2 * R + 4
    lay = Image.new("RGBA", (W * S, W * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    c = W * S / 2
    d.arc((c - R * S, c - R * S, c + R * S, c + R * S), 135, 405, fill=RING + (255,), width=int(9 * S))   # only the scale's 270 degrees
    for k in range(n):
        t = math.radians(135 + 270 * k / (n - 1))
        r0, r1 = (R - 6) * S, (R - 1) * S
        d.line((c + math.cos(t) * r0, c + math.sin(t) * r0, c + math.cos(t) * r1, c + math.sin(t) * r1), fill=RING_TICK + (255,), width=int(1.8 * S))
    im.alpha_composite(lay.resize((W, W), Image.LANCZOS), (int(cx - W / 2), int(cy - W / 2)))


def stage_glyph(im, cx, cy, stage, colour=INK, w=40, h=18):
    """the little envelope-stage pictures over ADSR knobs (attack ramp, decay, sustain level, release), as printed on the panel"""
    pts = {"A": [(0, 1), (0.45, 0), (1, 0)], "D": [(0, 0), (0.35, 0), (0.7, 0.6), (1, 0.6)],
           "S": [(0, 1), (0.25, 1), (0.25, 0.35), (0.75, 0.35), (0.75, 1), (1, 1)], "R": [(0, 0.2), (0.4, 0.2), (1, 1)]}[stage]
    S = 4
    lay = Image.new("RGBA", ((w + 4) * S, (h + 4) * S), (0, 0, 0, 0))
    ImageDraw.Draw(lay).line([((2 + x * w) * S, (2 + y * h) * S) for x, y in pts], fill=colour + (255,), width=int(2.6 * S), joint="curve")
    im.alpha_composite(lay.resize((w + 4, h + 4), Image.LANCZOS), (int(cx - (w + 4) / 2), int(cy - (h + 4) / 2)))


def rule(im, x0, y0, x1, y1, colour=GREY_LO):
    ImageDraw.Draw(im).line((x0, y0, x1, y1), fill=colour + (255,), width=2)


# ---- knobs ------------------------------------------------------------------------------------------------------------------
def knob_strip(size=80, frames=101, bipolar=False):
    """the original skin's knob (n2xTrancy's knob_big.png, 128 frames) as a film strip of `frames` frames at `size` px"""
    src = Image.open(KNOB_SRC).convert("RGBA")
    fw = src.width
    n = src.height // fw
    strip = Image.new("RGBA", (size, size * frames), (0, 0, 0, 0))
    for i in range(frames):
        k = i * (n - 1) // (frames - 1)
        strip.paste(src.crop((0, k * fw, fw, k * fw + fw)).resize((size, size), Image.LANCZOS), (0, i * size))
    return strip


# ---- buttons and LEDs -------------------------------------------------------------------------------------------------------
def led(d, cx, cy, r, on, S=1):
    d.ellipse((cx - r - S, cy - r - S, cx + r + S, cy + r + S), fill=(10, 14, 10, 255))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(LED_ON if on else LED_OFF) + (255,))
    if on:
        d.ellipse((cx - r * 0.5, cy - r * 0.6, cx + r * 0.1, cy - r * 0.05), fill=(220, 255, 210, 255))


def led_option(w, h, text, on, size=15, ink=None):
    """one option of a choice, as on the Nord panel: a green LED (lit while it is the choice), the option's name beside it"""
    ink = ink or INK
    im, d, S = _ss(w, h)
    led(d, 12 * S, h * S / 2, 6 * S, on, S)
    f = fit(text, size * S, (w - 30) * S)
    d.text((28 * S, h * S / 2), text, font=f, fill=ink + (255,), anchor="lm")
    return im.resize((w, h), Image.LANCZOS)


def _nord_face(im, S, w, h, lit):
    """a Nord button's face: black, rounded, a little relief and a soft top light (blended, not punched)"""
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 2 * S, w * S - 1, h * S - 1), 6 * S, fill=(0, 0, 0, 150))
    face = (64, 64, 70) if lit else (22, 22, 26)
    d.rounded_rectangle((S, S, w * S - 2 * S, h * S - 3 * S), 6 * S, fill=face + (255,), outline=(78, 78, 86, 255), width=S)
    hl = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle((4 * S, 3 * S, w * S - 5 * S, h * S * 0.34), 5 * S, fill=(255, 255, 255, 14))
    im.alpha_composite(hl)
    return ImageDraw.Draw(im)


def key_button(w, h, text, lit, size=16, led_on=None, dark=False):
    """a key as on the Nord panel: a black rounded button, the label in white (lighter face while held); an optional green LED"""
    im, d, S = _ss(w, h)
    d = _nord_face(im, S, w, h, lit)
    if text:
        f = fit(text, size * S, (w - 14) * S)
        d.text((w * S / 2, h * S / 2 - S), text, font=f, fill=WHITE + (255,), anchor="mm")
    if led_on is not None:
        led(d, w * S - 11 * S, 10 * S, 4 * S, led_on, S)
    return im.resize((w, h), Image.LANCZOS)


def toggle(w, h, text, on, size=14):
    """an on/off switch as on the Nord panel: a black button with its green LED, lit while on"""
    im, d, S = _ss(w, h)
    d = _nord_face(im, S, w, h, False)
    led(d, w * S / 2, h * S / 2 - S, 6 * S, on, S)
    return im.resize((w, h), Image.LANCZOS)


def arrow_image(w, h, direction, lit):
    im, d, S = _ss(w, h)
    if lit:
        d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), 5 * S, fill=(255, 255, 255, 60))
    return im.resize((w, h), Image.LANCZOS)


def tri(d, cx, cy, direction, s=9, colour=LCD_INK):
    d.polygon([(cx + direction * s, cy), (cx - direction * s * 0.6, cy - s), (cx - direction * s * 0.6, cy + s)], fill=colour + (255,))


# ---- the program display ----------------------------------------------------------------------------------------------------
def lcd(im, x0, y0, x1, y1):
    """the red LED display: dark red glass in a dark bezel, a faint cell texture"""
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((x0 - 4, y0 - 4, x1 + 4, y1 + 4), 6, fill=LCD_BEZEL + (255,))
    d.rectangle((x0, y0, x1, y1), fill=LCD_BG + (255,))
    for x in range(x0 + 3, x1 - 3, 4):
        d.line((x, y0 + 2, x, y1 - 2), fill=(50, 8, 8, 255), width=1)


# ---- the keyboard overlay and lists (Profit-5's, in this panel's colours) ---------------------------------------------------
def key_cap(w, h, text, lit, size=26):
    return key_button(w, h, text, lit, size)


def list_panel(w, h):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), 10, fill=CHAR + (255,))
    return im


def list_key(w, h, text, lit, size=16):
    return led_option(w, h, text, lit, size)


def wordmark(im, x, y, width=380):
    """the NODAL RED 2X lettering of the original skin (skin/parts/logo.png, on this red), `width` px wide, top left at (x, y)"""
    lg = Image.open(LOGO).convert("RGBA")
    h = int(lg.height * width / lg.width)
    im.alpha_composite(lg.resize((width, h), Image.LANCZOS), (x, y))
    return h
