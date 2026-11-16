#!/usr/bin/env python3
"""vst/build/params.h of the released 0.1.0 wrapper build (its nodalred2x.so has the same sha1 as the release zip's) -> vst/released-0.1.0.tsv:
key, min, max, normalised default, option count of every one of the 149 released indices (136 keys, 13 "<key>__open" popup flags)."""
import re, os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
src = open(os.path.join(ROOT, "vst", "build", "params.h")).read()
body = src[src.index("static const param_t"):]
rows = re.findall(r'\{"([^"]+)", "(?:[^"\\]|\\.)*", "[^"]*", ([-\d.e+]+)f?, ([-\d.e+]+)f?, ([-\d.e+]+)f?, (\d+),', body)
open(os.path.join(ROOT, "vst", "released-0.1.0.tsv"), "w").write(
    "\n".join("%s\t%g\t%g\t%.6g\t%s" % (k, float(lo), float(hi), float(d), n) for k, lo, hi, d, n in rows) + "\n")
print(len(rows), "rows")
