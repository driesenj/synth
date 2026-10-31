"""10HP panel for the S&H: hole list (CSV), a 1:1 drill template (SVG) and
the panel artwork (SVG, as a PCB panel). Everything is computed from
PLACEMENT in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the faceplate board is seen from the
front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack   sleeve pad towards the top of the board; the barrel sits 0.78 mm
         below the WQP518MA footprint origin
  pot    pins down; the Alpha shaft is 7.5 mm from the pin row, 4.0 mm
         above the PTV09A origin
  LED    3 mm, body centred on the origin
Run from sample-hold/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sh_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 10HP
HP = circuit.HP
BOARD_X0 = (PANEL_W - circuit.BOARD_W) / 2
BOARD_Y0 = (PANEL_H - circuit.BOARD_H) / 2   # board centred on the panel
HOLE = {"pot": 7.5, "jack": 6.5, "led": 3.2}
JACK_BARREL = circuit.JACK_BARREL
POT_SHAFT = circuit.POT_SHAFT
OUT = os.path.join(HERE, "..", "panel")


def features():
    """[(kind, ref, label, origin_x, origin_y, hole_x, hole_y)] in board mm, y up."""
    labels = {r: lbl for r, lbl, *_ in circuit.JACKS + circuit.POTS + circuit.LEDS}
    out = []
    for ref, (x, y, rot) in circuit.PLACEMENT.items():
        if ref.startswith("J"):
            out.append(("jack", ref, labels[ref], x, y, x, y + JACK_BARREL))
        elif ref.startswith("RV"):
            out.append(("pot", ref, labels[ref], x, y, x, y + POT_SHAFT))
        elif ref.startswith("D"):
            out.append(("led", ref, labels[ref], x, y, x, y))
    return out


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return BOARD_X0 + bx, PANEL_H - (BOARD_Y0 + by)


# Eurorack mounting: centres 3 mm from the top and bottom edge, 7.5 mm from the left edge and
# (HP - 3) * 5.08 further right; slots 5.5 x 3.2 mm (horizontal) give side-to-side play
MOUNTS = [(x, y) for x in (7.5, 7.5 + (HP - 3) * 5.08) for y in (3.0, PANEL_H - 3.0)]
SLOT_W, SLOT_H = 5.5, 3.2


def slot(x, y, cls=None, stroke=None):
    c = f' class="{cls}"' if cls else ""
    st = f' fill="none" stroke="{stroke}" stroke-width="0.2"' if stroke else ""
    return (f'<rect x="{x - SLOT_W / 2:.2f}" y="{y - SLOT_H / 2:.2f}" width="{SLOT_W}" height="{SLOT_H}" '
            f'rx="{SLOT_H / 2}"{c}{st}/>')


def write_csv(feats, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "ref", "label", "board_origin_x", "board_origin_y", "panel_x_from_left",
                    "panel_y_from_top", "hole_mm"])
        for kind, ref, label, ox, oy, hx, hy in feats:
            px, py = panel_xy(hx, hy)
            w.writerow([kind, ref, label, f"{ox:.2f}", f"{oy:.2f}", f"{px:.2f}", f"{py:.2f}", HOLE[kind]])
        for x, y in MOUNTS:
            w.writerow(["mount", "", "mounting slot", "", "", f"{x:.2f}", f"{y:.2f}", f"{SLOT_W} x {SLOT_H} slot"])


def write_svg(feats, path):
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 40}mm" height="{H + 30}mm" '
         f'viewBox="-20 -15 {W + 40} {H + 30}">',
         '<title>S&amp;H 10HP panel - drill template (print at 100%)</title>',
         '<style>text{font-family:Arial,Helvetica,sans-serif} .dim{font-size:1.6px;fill:#444} '
         '.lbl{font-size:1.8px;fill:#06c}</style>',
         f'<rect x="-20" y="-15" width="{W + 40}" height="{H + 30}" fill="#ffffff"/>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.25"/>',
         f'<rect x="{BOARD_X0:.2f}" y="{PANEL_H - BOARD_Y0 - circuit.BOARD_H:.2f}" width="{circuit.BOARD_W}" '
         f'height="{circuit.BOARD_H}" fill="none" stroke="#999" stroke-width="0.15" stroke-dasharray="1,1"/>']
    rows = [(k, lbl.replace("&", "&amp;"), *panel_xy(hx, hy)) for k, ref, lbl, ox, oy, hx, hy in feats]
    for x, y in MOUNTS:
        s.append(slot(x, y, stroke="#c00"))
        s.append(f'<text class="dim" x="{x + SLOT_W / 2 + 0.5:.2f}" y="{y - SLOT_H / 2 - 0.3:.2f}">{SLOT_W}x{SLOT_H}</text>')
    for kind, label, x, y in rows:
        d = HOLE[kind]
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{d / 2:.2f}" fill="none" stroke="#c00" stroke-width="0.2"/>')
        s.append(f'<line x1="{x - 1.5:.2f}" y1="{y:.2f}" x2="{x + 1.5:.2f}" y2="{y:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<line x1="{x:.2f}" y1="{y - 1.5:.2f}" x2="{x:.2f}" y2="{y + 1.5:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<text class="dim" x="{x + d / 2 + 0.4:.2f}" y="{y - d / 2 - 0.2:.2f}">Ø{d}</text>')
        s.append(f'<text class="lbl" x="{x:.2f}" y="{y + d / 2 + 2.2:.2f}" text-anchor="middle">{label}</text>')
    s.append('<line x1="0" y1="-8" x2="50" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (0, 50):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="25" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 6}" font-size="2" text-anchor="middle">S&amp;H 10HP panel, front view. '
             'Red circles: final hole size.</text>')
    s.append(f'<text x="{W / 2}" y="{H + 9}" font-size="2" text-anchor="middle">Dashed: the faceplate board.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the Marblesy style: black solder mask, white
# silkscreen, bare (ENIG) copper for the outputs. SVG groups: #silk,
# #copper, #holes and #mockup (knobs, nuts, LED, preview only).
# Tune ART, run, look at sample-hold-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227", "lit": "#e0403a",
    "knob": {"small": 5.0, "mid": 6.0},       # radii, mm: LEVEL; RATE and SLEW
    "scale": {"small": 6.0, "mid": 7.5},
    "nut": 4.0, "led": 1.6,
    "title": "S&H", "subtitle": "Random", "maker": "Seedable Instruments",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
    "label": 1.9,                             # knob and jack labels
}
KNOB_SIZE = {"RV1": "mid", "RV2": "small", "RV3": "mid"}
OUTPUTS = ["J4", "J5", "J6", "J7", "J8", "J9"]
NORMALS = [("J2", "J5"), ("J3", "J6")]        # IN takes WHITE, SLEW IN takes S&H: dotted line between them
GUIDES = [("RV1", "D1"), ("D1", "J1"), ("RV2", "J2"), ("RV3", "J3")]    # dotted, from a control down to its jack
BAND_CLEAR = 0.4      # bare board (under black mask) between a copper band and a hole through it; DRC asks 0.3


def esc(t):
    return t.replace("&", "&amp;")


def bands(pos):
    """The bare-copper patch round the outputs: (x, y, w, h, rx) from the top-left in the panel frame,
    with the holes through it as clearance circles (x, y, r)."""
    xs = [pos[r][2] for r in OUTPUTS]
    ys = [pos[r][3] for r in OUTPUTS]
    x, y = min(xs) - 4.8, min(ys) - 8.8
    w, h = max(xs) - min(xs) + 9.6, max(ys) - min(ys) + 14.6
    cuts = []
    for kind, label, hx, hy in pos.values():
        r = HOLE[kind] / 2 + BAND_CLEAR
        if x - r < hx < x + w + r and y - r < hy < y + h + r:
            if not (x + r < hx < x + w - r and y + r < hy < y + h - r):
                raise ValueError(f"the hole at ({hx:.2f}, {hy:.2f}) crosses the edge of the copper band")
            cuts.append((hx, hy, r))
    return [((x, y, w, h, 1.4), cuts)]


def knob_label_y(pos, ref):
    """Baseline of the label under a knob."""
    return pos[ref][3] + ART["scale"][KNOB_SIZE[ref]] + 2.6


def jack_label_y(pos, ref):
    return pos[ref][3] - ART["nut"] - 1.6


def _arc(cx, cy, r, a0, a1):
    """SVG path of an arc from angle a0 to a1 (degrees, clockwise from 12 o'clock)."""
    p0 = (cx + r * math.sin(math.radians(a0)), cy - r * math.cos(math.radians(a0)))
    p1 = (cx + r * math.sin(math.radians(a1)), cy - r * math.cos(math.radians(a1)))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M {p0[0]:.2f} {p0[1]:.2f} A {r} {r} 0 {large} 1 {p1[0]:.2f} {p1[1]:.2f}"


def scale_ticks(size):
    """Tick angles (degrees from 12 o'clock) and lengths of a knob's scale."""
    n = {"small": 5, "mid": 11}[size]
    return [(-135 + 270 * i / (n - 1), 1.0 if i in (0, n - 1, (n - 1) // 2) else 0.6) for i in range(n)]


def _below(pos, ref):
    """Where a dotted guide leaves a control: under a knob's label, under the LED."""
    kind, label, x, y = pos[ref]
    if kind == "pot":
        return knob_label_y(pos, ref) + 1.4
    return y + ART["led"] + 1.4


def _above(pos, ref):
    """Where a dotted guide arrives: over a jack's label, over the LED."""
    kind, label, x, y = pos[ref]
    if kind == "jack":
        return jack_label_y(pos, ref) - ART["label"] - 0.9
    return y - ART["led"] - 1.4


def layout(pos):
    """Everything the artwork and the panel PCB draw, in one list, so the two never drift apart:
    ("text", x, y, s, size, anchor), ("line", pts, w), ("dots", pts), ("arc", cx, cy, r, a0, a1, w),
    ("ring", cx, cy, r, w), ("serif", x, y, s, size, anchor)."""
    A = ART
    W = PANEL_W
    out = []

    def text(x, y, s, size, anchor="middle"):
        out.append(("text", x, y, s, size, anchor))

    # title band, maker line: the same spots on every module's panel
    out.append(("serif", 12.0, 7.4, A["title"], 5.2, "start"))
    text(W - 12.0, 6.6, A["subtitle"], 2.1, "end")
    out.append(("dots", [(3, 9.6), (W - 3, 9.6)]))
    out.append(("dots", [(3, 10.6), (W - 3, 10.6)]))
    text(W / 2, 122.4, A["maker"], 2.2)
    out.append(("line", [(3, 118.6), (W - 3, 118.6)], 0.3))
    # knobs: scale arcs with ticks, the word underneath
    for ref, (kind, label, x, y) in pos.items():
        if kind != "pot":
            continue
        size = KNOB_SIZE[ref]
        r = A["scale"][size]
        out.append(("arc", x, y, r, -135, 135, 0.3))
        for a, ln in scale_ticks(size):
            ra = math.radians(a)
            out.append(("line", [(x + r * math.sin(ra), y - r * math.cos(ra)),
                                 (x + (r + ln) * math.sin(ra), y - (r + ln) * math.cos(ra))], 0.3))
        text(x, knob_label_y(pos, ref), label, A["label"] if size == "small" else 2.2)
    # the clock LED: a ring like the button rings elsewhere
    for ref, (kind, label, x, y) in pos.items():
        if kind == "led":
            out.append(("ring", x, y, A["led"] + 0.9, 0.3))
    # input labels (the outputs' go on their copper, see bands)
    for ref, (kind, label, x, y) in pos.items():
        if kind == "jack" and ref not in OUTPUTS:
            text(x, jack_label_y(pos, ref), label, A["label"])
    # dotted guides down each column, and the normals from an output up to the input it feeds
    for a, b in GUIDES:
        x = pos[a][2]
        out.append(("dots", [(x, _below(pos, a)), (x, _above(pos, b))]))
    band_top = bands(pos)[0][0][1]
    for a, b in NORMALS:
        x, y = pos[a][2], pos[a][3]
        out.append(("dots", [(x, y + A["nut"] + 0.9), (x, band_top - 0.7)]))
    return out


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>S&amp;H 10HP panel - artwork</title>',
         f'<style>text{{font-family:{A["font"]};font-weight:bold;fill:{A["silk"]}}} '
         f'.serif{{font-family:{A["serif"]};font-style:italic;font-weight:normal}} '
         f'.silk{{stroke:{A["silk"]};fill:none;stroke-linecap:round;stroke-linejoin:round}} '
         f'.dots{{stroke-dasharray:0.1 1.0;stroke-width:0.45}} '
         f'.copper{{fill:{A["copper"]}}} .cu-text{{fill:{A["panel"]}}} .hole{{fill:#ffffff;stroke:none}}</style>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="{A["panel"]}"/>']
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}

    def text(x, y, t, size, anchor="middle", cls="", colour=None):
        c = f' class="{cls}"' if cls else ""
        st = f' style="fill:{colour}"' if colour else ""
        s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}"{c}{st}>{esc(t)}</text>')

    # -- bare copper: the output block, labels knocked out
    s.append('<g id="copper">')
    for (bx, by, bw, bh, brx), cuts in bands(pos):
        s.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh:.2f}" rx="{brx}" class="copper"/>')
        for x, y, r in cuts:
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" class="cu-text"/>')
    for ref in OUTPUTS:
        text(pos[ref][2], jack_label_y(pos, ref), pos[ref][1], A["label"], cls="cu-text")
    s.append('</g>')
    # -- silkscreen
    s.append('<g id="silk">')
    for item in layout(pos):
        kind = item[0]
        if kind == "text":
            _, x, y, t, size, anchor = item
            text(x, y, t, size, anchor)
        elif kind == "serif":
            _, x, y, t, size, anchor = item
            s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" class="serif">{esc(t)}</text>')
        elif kind == "line":
            _, pts, w = item
            s.append('<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
                     + f'" class="silk" stroke-width="{w}"/>')
        elif kind == "dots":
            s.append('<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in item[1]) + '" class="silk dots"/>')
        elif kind == "arc":
            _, x, y, r, a0, a1, w = item
            s.append(f'<path d="{_arc(x, y, r, a0, a1)}" class="silk" stroke-width="{w}"/>')
        elif kind == "ring":
            _, x, y, r, w = item
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" class="silk" stroke-width="{w}"/>')
    s.append('</g>')
    # -- holes
    s.append('<g id="holes">')
    for ref, (kind, label, x, y) in pos.items():
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{HOLE[kind] / 2:.2f}" class="hole"/>')
    for x, y in MOUNTS:
        s.append(slot(x, y, cls="hole"))
    s.append('</g>')
    # -- mockup of the fitted parts (preview only); the clock LED shown lit
    s.append('<g id="mockup">')
    for ref, (kind, label, x, y) in pos.items():
        if kind == "pot":
            r = A["knob"][KNOB_SIZE[ref]]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="#2a2a2a" stroke="#000" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r * 0.62:.2f}" fill="#e8e8e4"/>')
            a = math.radians(-60)
            s.append(f'<line x1="{x + 0.3 * r * math.sin(a):.2f}" y1="{y - 0.3 * r * math.cos(a):.2f}" '
                     f'x2="{x + 0.95 * r * math.sin(a):.2f}" y2="{y - 0.95 * r * math.cos(a):.2f}" '
                     f'stroke="#555" stroke-width="0.6" stroke-linecap="round"/>')
        elif kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["nut"]}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "led":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["led"]}" fill="{A["lit"]}" stroke="#1a1a1a" stroke-width="0.2"/>')
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Panel clearances: knob scales, the LED ring and jack nuts must not touch each other or the
    edges; reports gaps under 1 mm."""
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    items = []
    for ref, (kind, label, x, y) in pos.items():
        r = {"pot": ART["scale"][KNOB_SIZE.get(ref, "small")] + 1.0 if kind == "pot" else 0,
             "jack": ART["nut"], "led": ART["led"] + 0.9}[kind]
        items.append((ref, x, y, r))
    bad = []
    for i, (a, xa, ya, ra) in enumerate(items):
        for b, xb, yb, rb in items[i + 1:]:
            gap = math.hypot(xa - xb, ya - yb) - ra - rb
            if gap < 1.0:
                bad.append(f"{a} - {b}: {gap:.2f} mm")
        edge = min(xa, PANEL_W - xa) - ra
        if edge < 2.0:
            bad.append(f"{a} - panel edge: {edge:.2f} mm")
    return bad


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, "sample-hold-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "sample-hold-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "sample-hold-panel.svg"))
    for b in check(feats):
        print("tight:", b)
    print(f"{len(feats)} features + 4 mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
