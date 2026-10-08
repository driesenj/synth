"""Write the whole circuit as one stripboard-editor project (schematic only,
nothing placed on the board) and a PNG preview of the drawing."""
import collections
import json

import sb
from circuit import all_parts

OUT = "../stripboard/plaitsy-schematic.json"
PNG = "../stripboard/plaitsy-schematic-preview.png"

NOTES = """Plaitsy: a Mutable Instruments Plaits clone on a Daisy Seed, built on stripboard.

This file is the complete circuit of both boards in one schematic; nothing is
placed on the board. The two buildable boards are separate projects:
plaitsy-faceplate-board.json and plaitsy-main-board.json.

Net names: CV_* jack tips, IN_*/OA_* op-amp input/output, ADC_* Seed ADC pins,
POT_*/ATT_* pot wipers, LEDn_R/G LED anodes (Seed GPIO), LEDn_K LED cathodes,
TN_* jack switch lugs fed by the cable-detection probe.

Design notes and pin map: docs/design.md in the plaitsy folder.
Plaits is (c) Emilie Gillet, MIT licence (firmware), CC-BY-SA (hardware)."""


def render_schematic(parts, path, stub=2 * sb.G):
    from PIL import Image, ImageDraw
    xs, ys = [], []
    for p in parts:
        for (x, y), (dx, dy) in sb.sch_pin_points(p).values():
            xs += [x, x + dx * stub]
            ys += [y, y + dy * stub]
    pad = 120
    minx, miny = min(xs) - pad, min(ys) - pad
    W, H = max(xs) - minx + pad, max(ys) - miny + pad
    s = 0.5
    img = Image.new("RGB", (int(W * s), int(H * s)), "white")
    d = ImageDraw.Draw(img)
    f = sb._font(9)
    fb = sb._font(11)
    T = lambda x, y: ((x - minx) * s, (y - miny) * s)
    for p in parts:
        pts = sb.sch_pin_points(p)
        bx = [pt[0] for pt, _ in pts.values()] + [p.sch[0]]
        by = [pt[1] for pt, _ in pts.values()] + [p.sch[1]]
        x0, y0 = T(min(bx) + 10, min(by) - 6)
        x1, y1 = T(max(bx) - 10, max(by) + 6)
        d.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], outline="#888888")
        cx, cy = T(*p.sch)
        d.text((cx - 10, cy - 6), p.ref, fill="black", font=fb)
        for pid, ((x, y), (dx, dy)) in pts.items():
            n = p.net(pid)
            a = T(x, y)
            d.ellipse([a[0] - 2, a[1] - 2, a[0] + 2, a[1] + 2], fill="black")
            if n:
                e = T(x + dx * stub, y + dy * stub)
                d.line([a, e], fill="#2a6ebb", width=1)
                d.text((e[0] + (3 if dx >= 0 else -6 * len(n)), e[1] - 5), n, fill="#b00000", font=f)
    img.save(path)


def main():
    parts = all_parts()
    b = sb.Board("schematic", 41, 23)
    for p in parts:
        b.add(p)
    problems = sb.check_schematic_overlaps(b)
    for pr in problems:
        print("OVERLAP", pr)
    # what the editor will infer from the drawing must equal the netlist
    inferred = sb.infer_schematic_nets(parts)
    bad = 0
    for p in parts:
        for pid in {q.id for q in p.pdef.pins}:
            want = p.net(pid)
            got = inferred.get((p.ref, pid))
            if want != got:
                bad += 1
                print("NET MISMATCH", p.ref, pid, want, got)
    proj = sb.export_project(b, OUT, "Plaitsy - full schematic",
                             "Plaits clone on Daisy Seed + seed_power_opamps: both boards in one schematic",
                             NOTES)
    nets = collections.Counter(n["name"] for n in proj["nets"])
    print(f"wrote {OUT}: {len(proj['components'])} parts, {len(proj['nets'])} nets, "
          f"{len(proj['schematicWires'])} wires, {len(proj['netLabels'])} labels; "
          f"{len(problems)} overlaps, {bad} net mismatches")
    render_schematic(parts, PNG)


if __name__ == "__main__":
    main()
