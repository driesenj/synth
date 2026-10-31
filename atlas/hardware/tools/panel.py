"""16HP panel for Atlasy: hole list (CSV), a 1:1 drill template (SVG) and
the panel artwork (SVG, as a PCB panel). Everything is computed from
PLACEMENT in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the faceplate board is seen from the
front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack     sleeve pad towards the top of the board; the barrel sits 0.78 mm
           below the WQP518MA footprint origin
  pot      Alpha 9 mm, pins down; the shaft is 4.0 mm above the footprint origin
  toggle   Dailywell 2M sub-mini, 1/4-40 bushing on the origin
  fader    20 mm travel slide pot through a slot centred on the origin
  numeral  a 3 x 5 grid of small holes in gold rings, lit from behind by the channel's LED
Run from atlas/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("atlas_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 16HP
HP = circuit.HP
panel_xy = circuit.panel_xy
HOLE = {"jack": 6.5, "pot": 7.5, "toggle": 6.5}
SLOT = (circuit.FADER_TRAVEL + 2.4, 2.4)                 # fader slot: travel + lever + play, lever + play
DOT, DOT_PITCH, DOT_RING = 0.8, 1.45, 1.3                # numeral holes, their gold rings (outer diameter)
# 3 x 5 dot-matrix numerals, Atlas style; '#' = a hole
DIGITS = {1: [".#.", "##.", ".#.", ".#.", "###"], 2: ["###", "..#", "###", "#..", "###"],
          3: ["###", "..#", ".##", "..#", "###"], 4: ["#.#", "#.#", "###", "..#", "..#"]}
OUT = os.path.join(HERE, "..", "panel")


def features():
    """[(kind, ref, label, origin_x, origin_y, hole_x, hole_y)] in board mm, y up."""
    labels = {r: lbl for r, lbl, *_ in circuit.JACKS + circuit.POTS + circuit.TOGGLES + circuit.LEDS}
    out = []
    for ref, (x, y, rot) in circuit.PLACEMENT.items():
        if ref.startswith("J"):
            out.append(("jack", ref, labels[ref], x, y, x, y + circuit.JACK_BARREL))
        elif ref == "RV9":
            out.append(("fader", ref, labels[ref], x, y, x, y))
        elif ref.startswith("RV"):
            out.append(("pot", ref, labels[ref], x, y, x, y + circuit.POT_SHAFT))
        elif ref.startswith("SW"):
            out.append(("toggle", ref, labels[ref], x, y, x, y))
        elif ref.startswith("D"):
            out.append(("numeral", ref, labels[ref], x, y, x, y))
    return out


def numeral_dots(k, cx, cy):
    """Hole centres of channel k's numeral round (cx, cy), panel frame."""
    rows = DIGITS[k]
    return [(cx + (c - 1) * DOT_PITCH, cy + (r - 2) * DOT_PITCH)
            for r, line in enumerate(rows) for c, ch in enumerate(line) if ch == "#"]


# Eurorack mounting: centres 3 mm from the top and bottom edge, 7.5 mm from the left edge and
# (HP - 3) * 5.08 further right; slots 5.5 x 3.2 mm (horizontal) give side-to-side play
MOUNTS = [(x, y) for x in (7.5, 7.5 + (HP - 3) * 5.08) for y in (3.0, PANEL_H - 3.0)]
SLOT_W, SLOT_H = 5.5, 3.2


def slot(x, y, cls=None, stroke=None):
    c = f' class="{cls}"' if cls else ""
    st = f' fill="none" stroke="{stroke}" stroke-width="0.2"' if stroke else ""
    return (f'<rect x="{x - SLOT_W / 2:.2f}" y="{y - SLOT_H / 2:.2f}" width="{SLOT_W}" height="{SLOT_H}" '
            f'rx="{SLOT_H / 2}"{c}{st}/>')


def fader_slot(x, y, cls=None, stroke=None):
    w, h = SLOT
    c = f' class="{cls}"' if cls else ""
    st = f' fill="none" stroke="{stroke}" stroke-width="0.2"' if stroke else ""
    return f'<rect x="{x - w / 2:.2f}" y="{y - h / 2:.2f}" width="{w}" height="{h}" rx="{h / 2}"{c}{st}/>'


def write_csv(feats, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "ref", "label", "board_origin_x", "board_origin_y", "panel_x_from_left",
                    "panel_y_from_top", "hole_mm"])
        for kind, ref, label, ox, oy, hx, hy in feats:
            px, py = panel_xy(hx, hy)
            if kind == "numeral":
                k = int(ref[1:])
                w.writerow(["led", ref, label, f"{ox:.2f}", f"{oy:.2f}", f"{px:.2f}", f"{py:.2f}",
                            "no hole: behind the numeral"])
                for dx, dy in numeral_dots(k, px, py):
                    w.writerow(["dot", ref, f"numeral {k}", "", "", f"{dx:.2f}", f"{dy:.2f}", DOT])
            elif kind == "fader":
                w.writerow([kind, ref, label, f"{ox:.2f}", f"{oy:.2f}", f"{px:.2f}", f"{py:.2f}",
                            f"{SLOT[0]} x {SLOT[1]} slot"])
            else:
                w.writerow([kind, ref, label, f"{ox:.2f}", f"{oy:.2f}", f"{px:.2f}", f"{py:.2f}", HOLE[kind]])
        for x, y in MOUNTS:
            w.writerow(["mount", "", "mounting slot", "", "", f"{x:.2f}", f"{y:.2f}", f"{SLOT_W} x {SLOT_H} slot"])


def write_svg(feats, path):
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 40}mm" height="{H + 30}mm" '
         f'viewBox="-20 -15 {W + 40} {H + 30}">',
         '<title>Atlasy 16HP panel - drill template (print at 100%)</title>',
         '<style>text{font-family:Arial,Helvetica,sans-serif} .dim{font-size:1.6px;fill:#444} '
         '.lbl{font-size:1.8px;fill:#06c}</style>',
         f'<rect x="-20" y="-15" width="{W + 40}" height="{H + 30}" fill="#ffffff"/>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.25"/>',
         f'<rect x="{circuit.BOARD_X0:.2f}" y="{circuit.BOARD_Y0:.2f}" width="{circuit.BOARD_W}" '
         f'height="{circuit.BOARD_H}" fill="none" stroke="#999" stroke-width="0.15" stroke-dasharray="1,1"/>']
    for x, y in MOUNTS:
        s.append(slot(x, y, stroke="#c00"))
        s.append(f'<text class="dim" x="{x + SLOT_W / 2 + 0.5:.2f}" y="{y - SLOT_H / 2 - 0.3:.2f}">{SLOT_W}x{SLOT_H}</text>')
    for kind, ref, label, ox, oy, hx, hy in feats:
        x, y = panel_xy(hx, hy)
        if kind == "numeral":
            for dx, dy in numeral_dots(int(ref[1:]), x, y):
                s.append(f'<circle cx="{dx:.2f}" cy="{dy:.2f}" r="{DOT / 2}" fill="none" stroke="#c00" stroke-width="0.12"/>')
            s.append(f'<text class="dim" x="{x:.2f}" y="{y + 2 * DOT_PITCH + 2.4:.2f}" text-anchor="middle">Ø{DOT} dots</text>')
            continue
        if kind == "fader":
            s.append(fader_slot(x, y, stroke="#c00"))
            s.append(f'<text class="dim" x="{x - SLOT[0] / 2:.2f}" y="{y - SLOT[1] / 2 - 0.4:.2f}">'
                     f'{SLOT[0]} x {SLOT[1]} slot</text>')
            s.append(f'<text class="lbl" x="{x:.2f}" y="{y + SLOT[1] / 2 + 2.2:.2f}" text-anchor="middle">{label}</text>')
            continue
        d = HOLE[kind]
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{d / 2:.2f}" fill="none" stroke="#c00" stroke-width="0.2"/>')
        s.append(f'<line x1="{x - 1.5:.2f}" y1="{y:.2f}" x2="{x + 1.5:.2f}" y2="{y:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<line x1="{x:.2f}" y1="{y - 1.5:.2f}" x2="{x:.2f}" y2="{y + 1.5:.2f}" stroke="#000" stroke-width="0.12"/>')
        if kind == "toggle":            # beside the hole: the label of the jack above sits over its top
            s.append(f'<text class="dim" x="{x + d / 2 + 0.4:.2f}" y="{y + 0.55:.2f}">Ø{d}</text>')
        else:
            s.append(f'<text class="dim" x="{x + d / 2 + 0.3:.2f}" y="{y - d / 2 - 0.1:.2f}">Ø{d}</text>')
        s.append(f'<text class="lbl" x="{x:.2f}" y="{y + d / 2 + 2.0:.2f}" text-anchor="middle">{label}</text>')
    s.append('<line x1="5" y1="-8" x2="55" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (5, 55):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="30" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Atlasy 16HP panel, front view. '
             'Red: final hole size. Dashed: the faceplate board.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the Marblesy style: black solder mask, white
# silkscreen, bare (ENIG) copper for the outputs: one gold column down the
# four OUT jacks and a patch round the scanner OUT; the numerals are gold
# rings round their holes, so they read unlit too. SVG groups: #copper,
# #silk, #holes and #mockup (knobs, nuts, toggles, the fader cap and the lit
# numerals; preview only). Tune ART, run, look at atlas-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227", "lit": "#ff4a3a", "dark": "#2b0f0c",
    "knob": 5.0, "scale": 6.0, "nut": 4.0, "toggle_nut": 4.3,
    "title": "Atlas", "subtitle": "Quad multimode filter", "maker": "Seedable Instruments",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
    "label": 1.9,                             # column headers and jack labels
    "mark": 1.55,                             # switch positions, fader scale
}
HEADER_Y = 13.4                               # baseline of the column words, once above row 1
OUT_JACKS = [f"J{4 * r + 4}" for r in range(circuit.CHANNELS)]
NORMALLED = [[f"J{4 * r + 1}" for r in range(circuit.CHANNELS)],    # IN 1 -> 2 -> 3 -> 4
             [f"J{4 * r + 2}" for r in range(circuit.CHANNELS)]]    # FREQ 1 -> 2 -> 3 -> 4
DIVIDER_Y = 102.6
BAND_CLEAR = 0.4      # bare board (under black mask) between copper and a hole through it; DRC asks 0.3
BAND_HALF = 4.7       # half width of the OUT column and the scanner OUT patch
# what the mockup shows: mode per channel (up LP, mid HP, down BP), FM2/RES (up FM2), lit numerals
MOCK_MODE = {"SW1": "up", "SW2": "mid", "SW3": "down", "SW4": "up"}
MOCK_FMRES = {"SW5": "up", "SW6": "down", "SW7": "up", "SW8": "up"}
MOCK_LIT = {"D1", "D3"}
MOCK_KNOB = {"RV1": 30, "RV2": -60, "RV3": 100, "RV4": 20, "RV5": -10, "RV6": 110, "RV7": -100, "RV8": -135}
MOCK_FADER = 0.42     # 0 = channel 1, 1 = channel 4


def copper(pos):
    """[(rect (x, y, w, h, rx), cuts [(x, y, r)])]: the OUT column and the scanner OUT patch. A hole
    through a copper area gets a clearance circle; one crossing its edge is a layout error."""
    x = circuit.JACK_X[3]
    last = pos[OUT_JACKS[-1]][3]
    sy = pos["J18"][3]
    rects = [(x - BAND_HALF, 11.4, 2 * BAND_HALF, last + ART["nut"] + 1.2 - 11.4, 1.4),
             (x - BAND_HALF, DIVIDER_Y + 0.8, 2 * BAND_HALF, sy + ART["nut"] + 1.2 - DIVIDER_Y - 0.8, 1.4)]
    out = []
    for bx, by, bw, bh, rx in rects:
        cuts = []
        for kind, label, hx, hy in pos.values():
            if kind not in HOLE:
                continue
            r = HOLE[kind] / 2 + BAND_CLEAR
            if bx - r < hx < bx + bw + r and by - r < hy < by + bh + r:
                if not (bx + r < hx < bx + bw - r and by + r < hy < by + bh - r):
                    raise ValueError(f"the hole at ({hx:.2f}, {hy:.2f}) crosses the edge of a copper area")
                cuts.append((hx, hy, r))
        out.append(((bx, by, bw, bh, rx), cuts))
    return out


def jack_label_y(pos, ref):
    return pos[ref][3] - ART["nut"] - 1.6


def _arc(cx, cy, r, a0, a1):
    """SVG path of an arc from angle a0 to a1 (degrees, clockwise from 12 o'clock)."""
    p0 = (cx + r * math.sin(math.radians(a0)), cy - r * math.cos(math.radians(a0)))
    p1 = (cx + r * math.sin(math.radians(a1)), cy - r * math.cos(math.radians(a1)))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M {p0[0]:.2f} {p0[1]:.2f} A {r} {r} 0 {large} 1 {p1[0]:.2f} {p1[1]:.2f}"


def stacked(x, y, words, size, step):
    """Switch position words stacked beside a toggle at (x, y): the first for lever up, the last for
    lever down, left-anchored at x, centred on y."""
    n = len(words)
    return [("text", x, y + (i - (n - 1) / 2) * step + 0.36 * size, w, size, "start") for i, w in enumerate(words)]


def layout(pos):
    """Everything the artwork (and later the panel PCB) draws on the silkscreen, in one list:
    ("text", x, y, s, size, anchor), ("serif", x, y, s, size, anchor), ("line", pts, w), ("dots", pts),
    ("arc", cx, cy, r, a0, a1, w)."""
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
    # the four rows are identical: each column says what it is once, above row 1 (the OUT word is
    # knocked out of the copper, see write_artwork); the numerals say which row is which
    for x, word in zip(circuit.JACK_X[:3], ("IN", "FREQ", "FM2/RES")):
        text(x, HEADER_Y, word, A["label"])
    for x, word in zip(circuit.KNOB_X, ("FREQ", "RES")):
        text(x, HEADER_Y, word, A["label"])
    # knob scales: arc with ticks at both ends and at noon
    for ref, (kind, label, x, y) in pos.items():
        if kind != "pot":
            continue
        r = A["scale"]
        out.append(("arc", x, y, r, -135, 135, 0.3))
        for a in (-135, 0, 135):
            ra = math.radians(a)
            out.append(("line", [(x + r * math.sin(ra), y - r * math.cos(ra)),
                                 (x + (r + 1.0) * math.sin(ra), y - (r + 1.0) * math.cos(ra))], 0.3))
    # the switches' positions, stacked beside each lever
    for ref, (kind, label, x, y) in pos.items():
        if kind == "toggle":
            words = ["LP", "HP", "BP"] if label.startswith("MODE") else ["FM2", "RES"]
            out += stacked(x + A["toggle_nut"] + 0.4, y, words, A["mark"], 2.5 if len(words) == 3 else 3.2)
    # IN and FREQ are normalled down the rows: a dotted line from each jack to the next
    for chain in NORMALLED:
        for a, b in zip(chain, chain[1:]):
            x, ya, yb = pos[a][2], pos[a][3], pos[b][3]
            out.append(("dots", [(x, ya + A["nut"] + 0.9), (x, yb - A["nut"] - 0.9)]))
    # the scanner below a dotted divider: its name at the left, SCAN over the CV jack, the fader's scale
    # with a major tick and the channel number where each channel is alone
    out.append(("dots", [(3, DIVIDER_Y), (W - 3, DIVIDER_Y)]))
    sy = circuit.SCAN_Y
    text(3.6, sy - 0.75, "INTERPOLATING", 1.7, "start")
    text(3.6, sy + 1.95, "SCANNER", 1.7, "start")
    text(pos["J17"][2], jack_label_y(pos, "J17"), "SCAN", A["label"])
    fx = pos["RV9"][2]
    x0, x1 = fx - circuit.FADER_TRAVEL / 2, fx + circuit.FADER_TRAVEL / 2
    for i in range(13):
        x = x0 + (x1 - x0) * i / 12
        major = i % 4 == 0
        out.append(("line", [(x, 108.1 - (1.1 if major else 0.55)), (x, 108.1)], 0.3 if major else 0.2))
        if major:
            text(x, jack_label_y(pos, "J17"), str(i // 4 + 1), A["label"])
    out.append(("line", [(x0 - 1.5, 108.1), (x1 + 1.5, 108.1)], 0.2))
    return out


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>Atlasy 16HP panel - artwork</title>',
         '<defs><radialGradient id="glow"><stop offset="0" stop-color="#ff4a3a" stop-opacity="0.55"/>'
         '<stop offset="1" stop-color="#ff4a3a" stop-opacity="0"/></radialGradient></defs>',
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
        s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}"{c}{st}>{t}</text>')

    # -- bare copper: the OUT column and the scanner OUT patch; their words knocked out
    s.append('<g id="copper">')
    for (bx, by, bw, bh, brx), cuts in copper(pos):
        s.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh:.2f}" rx="{brx}" class="copper"/>')
        for x, y, r in cuts:
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" class="cu-text"/>')
    for ref, (kind, label, x, y) in pos.items():
        if kind == "numeral":
            for dx, dy in numeral_dots(int(ref[1:]), x, y):
                s.append(f'<circle cx="{dx:.2f}" cy="{dy:.2f}" r="{DOT_RING / 2}" class="copper"/>')
    text(circuit.JACK_X[3], HEADER_Y, "OUT", A["label"], cls="cu-text")
    text(pos["J18"][2], jack_label_y(pos, "J18"), "OUT", A["label"], cls="cu-text")
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
            text(x, y, t, size, anchor, cls="serif")
        elif kind == "line":
            _, pts, w = item
            s.append('<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
                     + f'" class="silk" stroke-width="{w}"/>')
        elif kind == "dots":
            s.append('<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in item[1]) + '" class="silk dots"/>')
        elif kind == "arc":
            _, x, y, r, a0, a1, w = item
            s.append(f'<path d="{_arc(x, y, r, a0, a1)}" class="silk" stroke-width="{w}"/>')
    s.append('</g>')
    # -- holes
    s.append('<g id="holes">')
    for ref, (kind, label, x, y) in pos.items():
        if kind == "numeral":
            for dx, dy in numeral_dots(int(ref[1:]), x, y):
                s.append(f'<circle cx="{dx:.2f}" cy="{dy:.2f}" r="{DOT / 2}" class="hole"/>')
        elif kind == "fader":
            s.append(fader_slot(x, y, cls="hole"))
        else:
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{HOLE[kind] / 2:.2f}" class="hole"/>')
    for x, y in MOUNTS:
        s.append(slot(x, y, cls="hole"))
    s.append('</g>')
    # -- mockup of the fitted parts (preview only)
    s.append('<g id="mockup">')
    for ref, (kind, label, x, y) in pos.items():
        if kind == "pot":
            r = A["knob"]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="#2a2a2a" stroke="#000" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r * 0.62:.2f}" fill="#e8e8e4"/>')
            a = math.radians(MOCK_KNOB[ref])
            s.append(f'<line x1="{x + 0.3 * r * math.sin(a):.2f}" y1="{y - 0.3 * r * math.cos(a):.2f}" '
                     f'x2="{x + 0.95 * r * math.sin(a):.2f}" y2="{y - 0.95 * r * math.cos(a):.2f}" '
                     f'stroke="#555" stroke-width="0.6" stroke-linecap="round"/>')
        elif kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["nut"]}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "toggle":
            rn = A["toggle_nut"]
            hexagon = " ".join(f"{x + rn * math.cos(math.radians(60 * i)):.2f},{y + rn * math.sin(math.radians(60 * i)):.2f}"
                               for i in range(6))
            s.append(f'<polygon points="{hexagon}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.3" fill="#8d8f8a"/>')
            throw = (MOCK_MODE.get(ref) or MOCK_FMRES.get(ref))
            if throw == "mid":
                s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.5" fill="#e4e4e0" stroke="#666" stroke-width="0.15"/>')
            else:
                ty = y - 5.2 if throw == "up" else y + 5.2
                s.append(f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x:.2f}" y2="{ty:.2f}" stroke="#d8d8d4" '
                         f'stroke-width="1.6" stroke-linecap="round"/>')
                s.append(f'<circle cx="{x:.2f}" cy="{ty:.2f}" r="1.05" fill="#ededea"/>')
        elif kind == "fader":
            s.append(fader_slot(x, y).replace("/>", ' fill="#050505"/>'))
            cx = x - circuit.FADER_TRAVEL / 2 + circuit.FADER_TRAVEL * MOCK_FADER
            s.append(f'<rect x="{cx - 2.2:.2f}" y="{y - 3.4:.2f}" width="4.4" height="6.8" rx="0.6" fill="#2a2a2a" '
                     f'stroke="#000" stroke-width="0.2"/>')
            s.append(f'<line x1="{cx:.2f}" y1="{y - 2.8:.2f}" x2="{cx:.2f}" y2="{y + 2.8:.2f}" stroke="#e8e8e4" '
                     f'stroke-width="0.5"/>')
        elif kind == "numeral":
            lit = ref in MOCK_LIT
            if lit:
                s.append(f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="4.2" ry="5.6" fill="url(#glow)"/>')
            for dx, dy in numeral_dots(int(ref[1:]), x, y):
                s.append(f'<circle cx="{dx:.2f}" cy="{dy:.2f}" r="{DOT / 2}" fill="{A["lit"] if lit else A["dark"]}"/>')
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Panel clearances: knobs, jack nuts, toggle nuts, numerals and the fader slot must not touch each
    other or the edges; reports gaps under 1 mm (0.8 mm for a numeral)."""
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    circles, boxes, bad = [], [], []
    for ref, (kind, label, x, y) in pos.items():
        if kind in ("pot", "jack", "toggle"):
            r = {"pot": ART["knob"], "jack": ART["nut"], "toggle": ART["toggle_nut"]}[kind]
            circles.append((ref, x, y, r))
        elif kind == "numeral":
            hw, hh = DOT_PITCH + DOT_RING / 2, 2 * DOT_PITCH + DOT_RING / 2
            boxes.append((ref, x - hw, y - hh, x + hw, y + hh, 0.8))
        elif kind == "fader":
            boxes.append((ref, x - SLOT[0] / 2 - 2.0, y - 3.4, x + SLOT[0] / 2 + 2.0, y + 3.4, 1.0))   # cap travel
    for i, (a, xa, ya, ra) in enumerate(circles):
        for b, xb, yb, rb in circles[i + 1:]:
            gap = math.hypot(xa - xb, ya - yb) - ra - rb
            if gap < 1.0:
                bad.append(f"{a} - {b}: {gap:.2f} mm")
        edge = min(xa, PANEL_W - xa) - ra
        if edge < 2.0:
            bad.append(f"{a} - panel edge: {edge:.2f} mm")
        for b, x0, y0, x1, y1, need in boxes:
            gap = math.hypot(max(x0 - xa, 0, xa - x1), max(y0 - ya, 0, ya - y1)) - ra
            if gap < need:
                bad.append(f"{a} - {b}: {gap:.2f} mm")
    return bad


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, "atlas-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "atlas-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "atlas-panel.svg"))
    for b in check(feats):
        print("tight:", b)
    print(f"{len(feats)} features + 4 mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
