#!/usr/bin/env python3
"""Sound names for Nord Lead 2x factory banks, read from Clavia's own "Factory Program Library List" PDF (the dumps carry no names).
    tools/names_from_pdf.py <Factory Program Library List.pdf> <banks dir>
For every .syx / .mid in <banks dir> whose name ends in a bank number (bank0.syx, "NL2X Factory 2.syx" ...), writes "<name>.txt" beside it:
one name per line, sound 1 first, which NodalRed2x shows in its sound list. Nothing of Clavia's is shipped with the plugin: run this on
your own copy of the list. Standard library only (the PDF's page streams are zlib)."""
import os, re, sys, zlib


def rows_of(pdf):
    d = open(pdf, "rb").read()
    objs = {int(n): o for n, o in re.findall(rb"(\d+) 0 obj(.*?)endobj", d, re.S)}

    def stream(n):
        o = objs.get(n, b"")
        m = re.search(rb"stream(\r\n|\n|\r)", o)
        return zlib.decompressobj().decompress(o[m.end():]) if m else b""

    rows = []
    for p in sorted(n for n, o in objs.items() if re.search(rb"/Type\s*/Page\b(?!s)", o)):
        c = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+ 0 R)", objs[p])
        if not c:
            continue
        s = b"".join(stream(int(x)) for x in re.findall(rb"(\d+) 0 R", c.group(1)))   # a page's text runs on across its streams
        for a, b in re.findall(rb"\(((?:\\.|[^\\)])*)\)\s*Tj|\[((?:\\.|[^\]\\])*)\]\s*TJ", s, re.S):
            rows.append("".join(x.decode("latin1") for x in re.findall(rb"\(((?:\\.|[^\\)])*)\)", b)) if b else a.decode("latin1"))
    return rows


def names_of(rows):
    """the program tables: rows of three columns, "B.KK Name" (bank 0 without the "0."), KK, KK+33, KK+66"""
    names = {b: {} for b in range(10)}
    unesc = lambda s: s.replace("\\(", "(").replace("\\)", ")").replace("\\'", "'").strip()

    def find_tag(r, tag, start):
        occ = [m.start() for m in re.finditer(re.escape(tag), r) if m.start() > start]
        good = [i for i in occ if i + len(tag) >= len(r) or not r[i + len(tag)].isdigit()]
        return good[0] if good else (occ[0] if occ else -1)

    for r in rows:
        m = re.match(r"^(\d)\.(\d{1,2})(?=\D)", r)
        if m:
            b, k, pre = int(m.group(1)), int(m.group(2)), "%s." % m.group(1)
        else:
            m = re.match(r"^(\d{1,2})(?=[^\d./])", r)
            if not m:
                continue
            b, k, pre = 0, int(m.group(1)), ""
        if k > 33:
            continue
        pos = [(k, 0, len(pre + str(k)))]
        for c in (k + 33, k + 66):
            if c > 99:
                break
            i = find_tag(r, pre + str(c), pos[-1][1] + pos[-1][2])
            if i < 0:
                break
            pos.append((c, i, len(pre + str(c))))
        for j, (c, i, l) in enumerate(pos):
            nm = unesc(r[i + l:pos[j + 1][1] if j + 1 < len(pos) else len(r)])
            if nm and c not in names[b]:
                names[b][c] = nm
    return names


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    names = names_of(rows_of(sys.argv[1]))
    for f in sorted(os.listdir(sys.argv[2])):
        stem, ext = os.path.splitext(f)
        m = re.search(r"(\d+)$", stem)
        if ext.lower() not in (".syx", ".mid") or not m or int(m.group(1)) not in names:
            continue
        nb = names[int(m.group(1))]
        with open(os.path.join(sys.argv[2], stem + ".txt"), "w") as o:
            o.write("".join("%s\n" % nb.get(k, "") for k in range(1, 100)))
        print("%s: %d names (program bank %s)" % (stem + ".txt", len(nb), m.group(1)))


main()
