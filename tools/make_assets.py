#!/usr/bin/env python3
"""Images cut from gearmulator's NodalRed2x skin "n2xTrancy" (skin/n2xTrancy/, by theusualsuspects, GPL-3.0):
  skin/parts/logo.png     the "NODAL RED 2X virtual analog" lettering of background.png (on the skin's red)
  vst/images/knob_nr.png  the big knob filmstrip (knob_big.png: 128 frames of 113 px -> 101 frames of 104 px)
  vst/images/tile.png     the 270 x 110 Instruments-browser tile
Committed outputs, so a build does not need the large sources."""
import os
from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SK = os.path.join(ROOT, "skin", "n2xTrancy")
PARTS = os.path.join(ROOT, "skin", "parts")
IMG = os.path.join(ROOT, "vst", "images")
os.makedirs(PARTS, exist_ok=True)
os.makedirs(IMG, exist_ok=True)
RED = (195, 28, 43)

src = Image.open(os.path.join(SK, "background.png")).convert("RGB")
logo = src.crop((1462, 1040, 2252, 1152))
logo.save(os.path.join(PARTS, "logo.png"))

strip = Image.open(os.path.join(SK, "knob_big.png")).convert("RGBA")
fw = strip.width
n = strip.height // fw
film = Image.new("RGBA", (104, 104 * 101))
for i in range(101):
    f = i * (n - 1) // 100
    film.paste(strip.crop((0, f * fw, fw, f * fw + fw)).resize((104, 104), Image.LANCZOS), (0, i * 104))
film.save(os.path.join(IMG, "knob_nr.png"))

tile = Image.new("RGB", (270, 110), RED)
s = min(250 / logo.width, 90 / logo.height)
l = logo.resize((int(logo.width * s), int(logo.height * s)), Image.LANCZOS)
tile.paste(l, ((270 - l.width) // 2, (110 - l.height) // 2))
tile.save(os.path.join(IMG, "tile.png"))
print("assets written (%d knob source frames)" % n)
