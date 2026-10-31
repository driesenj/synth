"""4HP panel for Six: hole list (CSV), a 1:1 drill template (SVG) and the
panel artwork (SVG, as a PCB panel). Everything is computed from PLACEMENT
in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the faceplate board is seen from the
front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack   on its side, sleeve pad to the right; the barrel sits 0.78 mm
         left of the WQP518MA footprint origin
  LED    3 mm bicolour, lens centred on the origin

4HP leaves room for one mounting slot per rail and no room for the frame's
subtitle beside the title: the title keeps its spot (x 12, baseline 7.4,
5.2 serif), the subtitle moves under the dotted band, and the maker line
is shortened to fit 20 mm.
Run from buffered-mult/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("six_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 4HP
HOLE = {"jack": 6.5, "led": 3.2}
JACK_BARREL, (SLEEVE_X, SLEEVE_Y) = circuit.JACK_BARREL, circuit.JACK_SLEEVE
OUT = os.path.join(HERE, "..", "panel")


def features():
    """[(kind, ref, label, origin_x, origin_y, hole_x, hole_y)] in board mm, y up."""
    labels = {r: lbl for r, lbl, *_ in circuit.JACKS + circuit.LEDS}
    out = []
    for ref, (x, y, rot) in circuit.PLACEMENT.items():
        if ref.startswith("J"):
            out.append(("jack", ref, labels[ref], x, y, x - JACK_BARREL * SLEEVE_X, y - JACK_BARREL * SLEEVE_Y))
        elif ref.startswith("D"):
            out.append(("led", ref, labels[ref], x, y, x, y))
    return out


panel_xy = circuit.panel_xy

# Eurorack mounting: centres 3 mm from the top and bottom edge, 7.5 mm from the left edge; a 4HP panel
# has room for one per rail. Slots 5.5 x 3.2 mm (horizontal) give side-to-side play.
MOUNTS = [(7.5, 3.0), (7.5, PANEL_H - 3.0)]
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
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 40}mm" height="{H + 34}mm" '
         f'viewBox="-20 -15 {W + 40} {H + 34}">',
         '<title>Six 4HP panel - drill template (print at 100%)</title>',
         '<style>text{font-family:Arial,Helvetica,sans-serif} .dim{font-size:1.6px;fill:#444} '
         '.lbl{font-size:1.8px;fill:#06c}</style>',
         f'<rect x="-20" y="-15" width="{W + 40}" height="{H + 34}" fill="#ffffff"/>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.25"/>',
         f'<rect x="{circuit.BOARD_X0:.2f}" y="{PANEL_H - circuit.BOARD_Y0 - circuit.BOARD_H:.2f}" '
         f'width="{circuit.BOARD_W}" height="{circuit.BOARD_H}" fill="none" stroke="#999" stroke-width="0.15" '
         'stroke-dasharray="1,1"/>']
    rows = [(k, lbl, *panel_xy(hx, hy)) for k, ref, lbl, ox, oy, hx, hy in feats]
    for x, y in MOUNTS:
        s.append(slot(x, y, stroke="#c00"))
        s.append(f'<text class="dim" x="{x + SLOT_W / 2 + 0.5:.2f}" y="{y + 0.6:.2f}">{SLOT_W}x{SLOT_H}</text>')
    for kind, label, x, y in rows:
        d = HOLE[kind]
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{d / 2:.2f}" fill="none" stroke="#c00" stroke-width="0.2"/>')
        s.append(f'<line x1="{x - 1.5:.2f}" y1="{y:.2f}" x2="{x + 1.5:.2f}" y2="{y:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<line x1="{x:.2f}" y1="{y - 1.5:.2f}" x2="{x:.2f}" y2="{y + 1.5:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<text class="dim" x="{x + d / 2 + 0.4:.2f}" y="{y - d / 2 - 0.2:.2f}">Ø{d}</text>')
        s.append(f'<text class="lbl" x="{-1.0:.2f}" y="{y + 0.6:.2f}" text-anchor="end">{label}</text>')
    s.append('<line x1="0" y1="-8" x2="20" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (0, 20):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="10" y="-10" font-size="2.2" text-anchor="middle">20 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 7}" font-size="2" text-anchor="middle">Six 4HP panel, front view.</text>')
    s.append(f'<text x="{W / 2}" y="{H + 10}" font-size="2" text-anchor="middle">Red: final hole size. '
             'Dashed: the board.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the Marblesy style: black solder mask, white
# silkscreen, bare (ENIG) copper for the outputs. SVG groups: #silk,
# #copper, #holes and #mockup (nuts, LEDs, screws, preview only).
# Tune ART, run, look at six-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227",
    "green": "#57d163", "red": "#e04848",
    "nut": 4.0, "led": 1.75,
    "title": "Six", "subtitle": "buff mult",  # the title starts at x 12 like everywhere: 3 letters fit in 4HP
    "maker": "Seedable",                      # "Seedable Instruments" is 23 mm at 2.2
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
    "label": 1.9,
}
SUBTITLE_Y = 14.2                               # under the dotted band, centred
# the rows' words: turned 90 degrees in the left margin, each on a bracket that spans its row: a line at
# BRACKET_X broken round the word, serifs pointing at the jacks (the mixer's style, the user's pick)
WORD_X = 3.65                                   # baseline of the vertical words; the letters reach ~1.4 mm left
BRACKET_X, SERIF = 2.9, 1.6
BRACKET_GAP, BRACKET_MIN = 0.7, 2.0             # gap between word and line; shortest line piece
CHAR_W = 0.68                                   # estimated advance per character (bold sans), x font size
BAND_HALF_W = 5.4                               # gold band either side of the column
BAND_TOP, BAND_BOTTOM = 5.0, 5.4                # below the IN barrel; below the last OUT barrel
NORMAL_X = 18.0                                 # the dotted IN 1 -> IN 2 normal, right of the column
BAND_CLEAR = 0.4      # bare board (under black mask) between a copper band and a hole through it; DRC asks 0.3
INPUTS = ["J1", "J5"]
GROUP_OUTS = [["J2", "J3", "J4"], ["J6", "J7", "J8"]]
# preview only: lit LEDs
MOCK_LED = {"D1": "green", "D2": "red"}


def bands(pos):
    """The bare-copper band behind each group's LED and outputs: [((x, y, w, h, rx), [(x, y, r) holes])] from
    the top-left in the panel frame, each hole through it as a clearance circle."""
    out = []
    for jin, outs in zip(INPUTS, GROUP_OUTS):
        cx = pos[jin][2]
        x, y = cx - BAND_HALF_W, pos[jin][3] + BAND_TOP
        w, h = 2 * BAND_HALF_W, pos[outs[-1]][3] + BAND_BOTTOM - y
        cuts = []
        for kind, label, hx, hy in pos.values():
            r = HOLE[kind] / 2 + BAND_CLEAR
            if x - r < hx < x + w + r and y - r < hy < y + h + r:
                if not (x + r < hx < x + w - r and y + r < hy < y + h - r):
                    raise ValueError(f"the hole at ({hx:.2f}, {hy:.2f}) crosses the edge of a copper band")
                cuts.append((hx, hy, r))
        out.append(((x, y, w, h, 1.4), cuts))
    return out


def layout(pos):
    """Everything the artwork and the panel PCB draw, in one list, so the two never drift apart:
    ("text", x, y, s, size, anchor), ("line", pts, w), ("dots", pts), ("serif", x, y, s, size, anchor), and
    ("vtext", x, y, s, size): a word reading bottom to top, centred on y, with its baseline at x."""
    A = ART
    W = PANEL_W
    out = []

    def text(x, y, s, size, anchor="middle"):
        out.append(("text", x, y, s, size, anchor))

    # title band, maker line: the same spots as on every module; the subtitle under the band
    out.append(("serif", 12.0, 7.4, A["title"], 5.2, "start"))
    out.append(("dots", [(3, 9.6), (W - 3, 9.6)]))
    out.append(("dots", [(3, 10.6), (W - 3, 10.6)]))
    text(W / 2, SUBTITLE_Y, A["subtitle"], 2.1)
    text(W / 2, 122.4, A["maker"], 2.2)
    out.append(("line", [(3, 118.6), (W - 3, 118.6)], 0.3))
    # the rows' words, once each in the left margin on a bracket as tall as the row
    for word, y, h in row_words(pos):
        size = A["label"]
        gap = CHAR_W * size * len(word) / 2 + BRACKET_GAP
        half = max(h, gap + BRACKET_MIN)
        out.append(("vtext", WORD_X, y, word, size))
        out.append(("line", [(BRACKET_X + SERIF, y - half), (BRACKET_X, y - half), (BRACKET_X, y - gap)], 0.3))
        out.append(("line", [(BRACKET_X, y + gap), (BRACKET_X, y + half), (BRACKET_X + SERIF, y + half)], 0.3))
    # IN 2 takes IN 1 when unpatched: a dotted line round the right of group 1, an arrowhead into IN 2
    (_, _, x1, y1), (_, _, x2, y2) = pos[INPUTS[0]], pos[INPUTS[1]]
    xs = x1 + A["nut"] + 0.9
    out.append(("dots", [(xs, y1), (NORMAL_X, y1), (NORMAL_X, y2), (xs + 1.4, y2)]))
    out.append(("line", [(xs + 0.9, y2 - 0.7), (xs, y2), (xs + 0.9, y2 + 0.7)], 0.3))
    return out


def row_words(pos):
    """(word, centre y, half height) of each row: IN spans its jack nut, OUT its group's three nuts."""
    nut = ART["nut"]
    rows = []
    for jin, outs in zip(INPUTS, GROUP_OUTS):
        rows.append(("IN", pos[jin][3], nut))
        top, bottom = pos[outs[0]][3], pos[outs[-1]][3]
        rows.append(("OUT", (top + bottom) / 2, (bottom - top) / 2 + nut))
    return rows


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>Six 4HP panel - artwork</title>',
         f'<style>text{{font-family:{A["font"]};font-weight:bold;fill:{A["silk"]}}} '
         f'.serif{{font-family:{A["serif"]};font-style:italic;font-weight:normal}} '
         f'.silk{{stroke:{A["silk"]};fill:none;stroke-linecap:round;stroke-linejoin:round}} '
         f'.dots{{stroke-dasharray:0.1 1.0;stroke-width:0.45}} '
         f'.copper{{fill:{A["copper"]}}} .cu-text{{fill:{A["panel"]}}} .hole{{fill:#ffffff;stroke:none}}</style>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="{A["panel"]}"/>']
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}

    def text(x, y, t, size, anchor="middle", cls=""):
        c = f' class="{cls}"' if cls else ""
        s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}"{c}>{t}</text>')

    # -- bare copper: one band per group, behind its LED and outputs
    s.append('<g id="copper">')
    for (bx, by, bw, bh, brx), cuts in bands(pos):
        s.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh:.2f}" rx="{brx}" class="copper"/>')
        for x, y, r in cuts:
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" class="cu-text"/>')
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
        elif kind == "vtext":
            _, x, y, t, size = item
            s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="middle" '
                     f'transform="rotate(-90 {x:.2f} {y:.2f})">{t}</text>')
        elif kind == "line":
            _, pts, w = item
            s.append('<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
                     + f'" class="silk" stroke-width="{w}"/>')
        elif kind == "dots":
            s.append('<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in item[1]) + '" class="silk dots"/>')
    s.append('</g>')
    # -- holes
    s.append('<g id="holes">')
    for ref, (kind, label, x, y) in pos.items():
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{HOLE[kind] / 2:.2f}" class="hole"/>')
    for x, y in MOUNTS:
        s.append(slot(x, y, cls="hole"))
    s.append('</g>')
    # -- mockup of the fitted parts (preview only)
    s.append('<g id="mockup">')
    for ref, (kind, label, x, y) in pos.items():
        if kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["nut"]}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "led":
            lit = MOCK_LED.get(ref)
            if lit:
                s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.2" fill="{A[lit]}" opacity="0.28"/>')
            fill = A[lit] if lit else "#3a3a36"
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["led"]}" fill="{fill}" stroke="#000" stroke-width="0.2"/>')
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Panel clearances: LEDs and jack nuts must not touch each other, the edges or the screw heads; reports
    gaps under 1 mm (2 mm to the side edges). The board's own clearances are pcb.py's."""
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    items = [(ref, x, y, ART["nut"] if kind == "jack" else ART["led"] + 0.25) for ref, (kind, label, x, y) in pos.items()]
    items += [(f"screw {i + 1}", x, y, 2.6) for i, (x, y) in enumerate(MOUNTS)]
    bad = []
    for i, (a, xa, ya, ra) in enumerate(items):
        for b, xb, yb, rb in items[i + 1:]:
            gap = math.hypot(xa - xb, ya - yb) - ra - rb
            if gap < 1.0:
                bad.append(f"{a} - {b}: {gap:.2f} mm")
        edge = min(xa, PANEL_W - xa) - ra
        if not a.startswith("screw") and edge < 2.0:
            bad.append(f"{a} - panel edge: {edge:.2f} mm")
    last_band = bands(pos)[-1][0]
    if last_band[1] + last_band[3] > 118.6 - 1.0:
        bad.append(f"the lower band ends {118.6 - last_band[1] - last_band[3]:.2f} mm above the bottom rule")
    return bad


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, "six-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "six-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "six-panel.svg"))
    for b in check(feats):
        print("tight:", b)
    print(f"{len(feats)} features + {len(MOUNTS)} mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
