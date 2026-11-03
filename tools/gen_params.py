#!/usr/bin/env python3
"""Write vst/params.json and src/dsp/nodalred2x_params.h from gearmulator's parameter table for the Nord Lead 2x
(skin/parameterDescriptions_n2x.json, the file the NodalRed2x editor is built from).

A Nord Lead 2x single is 66 parameter bytes (index = SingleParam, byte value 0-127, the Sens ones signed -128..127; Sync / Ring mod /
Distortion share byte 52 as bit fields). Most are set with a MIDI controller (n2xmiditypes.h ControlChange), the rest (the morph
amounts, ring mod) with a single dump. The table has no value lists for the switches: the labels below are the instrument's own panel.
Four performance (multi) values are added: LFO 1 / LFO 2 sync, bend range, unison detune.
The VST parameter index is the position in params.json and saved projects bind to it: append only."""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SRC = os.path.join(ROOT, "skin", "parameterDescriptions_n2x.json")
OUT = os.path.join(ROOT, "vst", "params.json")
HDR = os.path.join(ROOT, "src", "dsp", "nodalred2x_params.h")


def load():
    def strip(line):
        out, ins, i = [], False, 0
        while i < len(line):
            c = line[i]
            if c == '"':
                ins = not ins
            if not ins and line.startswith("//", i):
                break
            out.append(c)
            i += 1
        return "".join(out)
    t = "\n".join(strip(l) for l in open(SRC).read().split("\n"))
    return json.loads(re.sub(r",(\s*[\]}])", r"\1", t))


D = load()
DF = D["parameterdescriptiondefaults"]
ROWS = {}
for x in D["parameterdescriptions"]:
    y = dict(DF)
    y.update(x)
    ROWS[x["name"]] = y

OPT = {   # panel labels, by raw value
    "O1Waveform": ["Pulse", "Saw", "Triangle", "Sine"],
    "O2Waveform": ["Pulse", "Saw", "Triangle", "Noise"],
    "FilterType": ["LP 12 dB", "LP 24 dB", "HP 24 dB", "Band Pass", "Notch + LP", "Notch"],
    "FilterKeytrack": ["Off", "1/3", "2/3", "Full"],
    "Lfo1Waveform": ["Steps", "Saw", "Triangle", "Square", "Random"],
    "Lfo1Dest": ["PW", "Filter", "Osc 2", "Osc 1+2", "FM"],
    "Lfo2Dest": ["Arp Down", "Arp Up", "Arp Up/Down", "LFO 2 Amp", "LFO 2 Osc 1+2", "Arp Random", "Arp Echo", "LFO 2 Filter", "Arp Mode 8"],
    "ModEnvDest": ["Osc 2", "FM", "PW"],
    "ModWheelDest": ["Filter", "FM", "Osc 2", "LFO 1", "Morph"],
    "VoiceMode": ["Mono", "Legato", "Poly"],
    "OctaveShift": ["-2", "-1", "0", "+1", "+2"],
    "Auto": ["Off", "On"],
    "FilterVelocity": ["Off", "On"],
    "Unison": ["Off", "On"],
    "O2Keytrack": ["Off", "On"],
}
NAME = {"O2Pitch": "Osc 2 Pitch", "O2PitchFine": "Osc 2 Fine", "Mix": "Osc Mix", "Cutoff": "Cutoff", "Resonance": "Resonance",
        "FilterEnvAmount": "Filter Env Amt", "PW": "Pulse Width", "FmDepth": "FM Amount", "O1Waveform": "Osc 1 Wave", "O2Waveform": "Osc 2 Wave",
        "O2Keytrack": "Osc 2 Keytrack", "FilterKeytrack": "Filter Keytrack", "FilterVelocity": "Filter Velocity", "OctaveShift": "Octave Shift",
        "ModWheelDest": "Mod Wheel Dest", "ModEnvDest": "Mod Env Dest", "ModEnvLevel": "Mod Env Amount", "Lfo1Level": "LFO 1 Amount",
        "Lfo1Dest": "LFO 1 Dest", "Lfo2Dest": "LFO 2 / Arp", "ArpRange": "Arp Range", "FilterType": "Filter Type", "VoiceMode": "Voice Mode",
        "RingMod": "Ring Mod", "Auto": "Auto Glide"}


def nice(name):
    if name in NAME:
        return NAME[name]
    s = name
    sens = s.endswith("Sens")
    if sens:
        s = s[:-4]
    s = re.sub(r"^Lfo(\d)", r"LFO \1 ", s).replace("FilterEnv", "Filter Env ").replace("AmpEnv", "Amp Env ").replace("ModEnv", "Mod Env ")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return ("Morph " if sens else "") + (NAME.get(name[:-4], s) if sens else s)


params, keys_in = [], {}
NP = []     # (key, idx, lo, hi, kind, off, def, mask, shift)    kind 0 int raw=v+off, 1 option raw=index, 5 signed byte
MULTI = []  # (key, MultiParam enum value, lo, hi, option labels or None)


def add(p, sec):
    params.append(p)
    keys_in.setdefault(sec, []).append(p["key"])


add(dict(key="bank_index", name="BANK", min=0, max=63, default=0, display="int"), "Browse")
add(dict(key="preset", name="PRESET", min=0, max=127, default=0, display="int"), "Browse")
add(dict(key="bank_name", name="BANK NAME", min=0, max=0, default=0, display="string", poll=True), "Browse")
add(dict(key="preset_name", name="PRESET NAME", min=0, max=0, default=0, display="string", poll=True), "Browse")
for k, n in (("bank_prev", "BANK -"), ("bank_next", "BANK +"), ("preset_prev", "PRESET -"), ("preset_next", "PRESET +"), ("all_notes_off", "PANIC")):
    add(dict(key=k, name=n, min=0, max=1, default=0, momentary=True), "Browse")
add(dict(key="rom_name", name="ROM", min=0, max=0, default=0, display="string", poll=True), "System")
add(dict(key="loading_status", name="STATUS", min=0, max=0, default=0, display="string", poll=True), "System")
add(dict(key="engine_stats", name="STATS", min=0, max=0, default=0, display="string", poll=True), "System")
add(dict(key="gain", name="GAIN %", min=10, max=400, default=70, display="int"), "System")
add(dict(key="init_patch", name="RELOAD", min=0, max=1, default=0, momentary=True), "System")

SECT = {}
for n in ("O2Pitch", "O2PitchFine", "Mix", "PW", "FmDepth", "O1Waveform", "O2Waveform", "Sync", "RingMod", "O2Keytrack"):
    SECT[n] = "Osc"
for n in ("Cutoff", "Resonance", "FilterEnvAmount", "FilterEnvA", "FilterEnvD", "FilterEnvS", "FilterEnvR", "FilterType", "FilterKeytrack", "FilterVelocity", "Distortion"):
    SECT[n] = "Filter"
for n in ("AmpEnvA", "AmpEnvD", "AmpEnvS", "AmpEnvR", "Gain", "Portamento", "Auto", "VoiceMode", "Unison", "OctaveShift"):
    SECT[n] = "Amp"
for n in ("Lfo1Rate", "Lfo1Level", "Lfo1Waveform", "Lfo1Dest", "Lfo2Rate", "Lfo2Dest", "ModEnvA", "ModEnvD", "ModEnvLevel", "ModEnvDest", "ModWheelDest", "ArpRange"):
    SECT[n] = "Mod"

# (name, byte index, bit mask, shift): the table's own order for the 66 bytes, the bit fields of byte 52 and Distortion
SINGLE = sorted({r["index"]: r for r in ROWS.values() if r.get("page", 0) == 0 and r["index"] < 66}.values(), key=lambda r: r["index"])
FIELDS = [r for r in ROWS.values() if r.get("page", 0) == 0 and (r["index"] < 66 or r["name"] == "Distortion")]
FIELDS.sort(key=lambda r: (r["index"] if r["index"] < 66 else 52, r["name"]))
for r in FIELDS:
    name, idx, lo, hi = r["name"], r["index"], r["min"], r["max"]
    mask = shift = 0
    if name == "Sync":
        idx, mask, shift = 52, 1, 0
    elif name == "RingMod":
        idx, mask, shift = 52, 1, 1
    elif name == "Distortion":
        idx, mask, shift = 52, 1, 4
    sec = SECT.get(name, "Morph" if name.endswith("Sens") else "Other")
    dflt = r.get("default", 64 if r["toText"] in ("signed",) else 0)
    if name in OPT or mask:
        labels = OPT.get(name, ["Off", "On"])
        di = min(max(dflt, 0), len(labels) - 1)
        add(dict(key=name, name=nice(name), options=labels, default=labels[di]), sec)
        NP.append((name, idx, 0, len(labels) - 1, 1, 0, di, mask, shift))
    elif name.endswith("Sens"):
        add(dict(key=name, name=nice(name), min=-128, max=127, default=0, display="int"), sec)
        NP.append((name, idx, -128, 127, 5, 0, 0, 0, 0))
    elif name == "O2Pitch":
        add(dict(key=name, name=nice(name), min=-60, max=60, default=0, display="int"), sec)
        NP.append((name, idx, 0, 120, 0, 60, 60, 0, 0))
    else:
        off = 64 if r["toText"] == "signed" else 0
        add(dict(key=name, name=nice(name), min=lo - off, max=hi - off, default=dflt - off, display="int"), sec)
        NP.append((name, idx, lo, hi, 0, off, dflt, 0, 0))

SYNC = ["Off", "2/1", "1/1", "1/2", "1/4", "1/8", "1/8.", "1/16"]
for key, nm, mp, lo, hi, lab, dflt in (("lfo1_sync", "LFO 1 Sync", 268, 0, 7, SYNC, 0), ("lfo2_sync", "LFO 2 / Arp Sync", 272, 0, 7, SYNC, 0),
                                       ("bend_range", "Bend Range", 312, 0, 8, None, 2), ("unison_detune", "Unison Detune", 313, 0, 8, None, 2)):
    add(dict(key=key, name=nm, options=lab, default=lab[dflt]) if lab else dict(key=key, name=nm, min=lo, max=hi, default=dflt, display="int"), "Mod")
    MULTI.append((key, mp, lo, hi, bool(lab), dflt))

N_BANKS, N_TILES, N_PER = 10, 30, 99
for i in range(1, N_BANKS + 1):
    add(dict(key="bank_slot_%d" % i, name="BANK %d" % i, min=0, max=1, default=0, momentary=True, display="string", poll=True), "Banks")
for i in range(1, N_TILES + 1):
    add(dict(key="patch_slot_%d" % i, name="PATCH %d" % i, min=0, max=1, default=0, momentary=True, display="string", poll=True), "Banks")
add(dict(key="patch_page_text", name="PAGE", min=0, max=0, default=0, display="string", poll=True), "Banks")
add(dict(key="patch_page_prev", name="PAGE -", min=0, max=1, default=0, momentary=True), "Banks")
add(dict(key="patch_page_next", name="PAGE +", min=0, max=1, default=0, momentary=True), "Banks")
add(dict(key="favourite", name="FAVOURITE", min=0, max=63, default=63, display="int"), "Banks")
add(dict(key="fav_save", name="SAVE FAV", min=0, max=1, default=0, momentary=True), "Banks")
add(dict(key="fav_delete", name="DEL FAV", min=0, max=1, default=0, momentary=True), "Banks")
add(dict(key="fav_text", name="FAVOURITES", min=0, max=0, default=0, display="string", poll=True), "Banks")
add(dict(key="bank_page_text", name="BANK PAGE", min=0, max=0, default=0, display="string", poll=True), "Banks")
add(dict(key="bank_page_prev", name="BANK PAGE -", min=0, max=1, default=0, momentary=True), "Banks")
add(dict(key="bank_page_next", name="BANK PAGE +", min=0, max=1, default=0, momentary=True), "Banks")

order = ["Browse", "Banks", "System", "Osc", "Filter", "Amp", "Mod", "Morph", "Other"]
sections = [{"label": s, "keys": keys_in[s]} for s in order if s in keys_in]
json.dump({"name": "NodalRed2x", "params": params, "sections": sections}, open(OUT, "w"), indent=1)

with open(HDR, "w") as f:
    f.write("/* generated by tools/gen_params.py from skin/parameterDescriptions_n2x.json: do not edit.\n"
            " * One row per Nord Lead 2x single parameter: VST key, byte in the single (0-65), raw range, kind (0: raw = value + off, 1: option list,\n"
            " * raw = index, 5: signed byte), default raw, and for a bit field its mask and shift in the byte. */\n#pragma once\n#include <stdint.h>\n"
            "struct nr_param_t { const char *key; uint8_t idx; int16_t lo, hi; uint8_t kind; int16_t off; int16_t def; uint8_t mask, shift; };\n"
            "struct nr_multi_t { const char *key; uint16_t mp; uint8_t lo, hi, option; uint8_t def; };\n"
            "static const nr_param_t g_nr_params[] = {\n")
    for k, idx, lo, hi, kind, off, dflt, mask, sh in NP:
        f.write('    {"%s", %d, %d, %d, %d, %d, %d, %d, %d},\n' % (k, idx, lo, hi, kind, off, dflt, mask, sh))
    f.write("};\nstatic const int NR_NUM_PARAMS = %d;\nstatic const nr_multi_t g_nr_multi[] = {\n" % len(NP))
    for k, mp, lo, hi, opt, dflt in MULTI:
        f.write('    {"%s", %d, %d, %d, %d, %d},\n' % (k, mp, lo, hi, 1 if opt else 0, dflt))
    f.write("};\nstatic const int NR_NUM_MULTI = %d;\n" % len(MULTI))
    f.write("#define NR_BANKS %d\n#define NR_PER_BANK %d\n#define NR_PATCH_TILES %d\n#define NR_BANK_TILES 10\n" % (1, N_PER, N_TILES))
print("params.json: %d params (%d single, %d multi), %d sections" % (len(params), len(NP), len(MULTI), len(sections)))
