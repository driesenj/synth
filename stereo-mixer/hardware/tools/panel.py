"""28HP panel for the stereo mixer: hole list (CSV), a 1:1 drill template
(SVG) and the panel artwork (SVG, as a PCB panel). Everything is computed
from PLACEMENT in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the faceplate board is seen from the
front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack   sleeve pad towards the top of the board; the barrel sits 0.78 mm
         below the WQP518MA footprint origin
  pot    pins down; the Alpha shaft is 7.5 mm from the pin row, 4.0 mm
         above the PTV09A origin (the dual-gang footprint uses the same frame)
  button Thonk low-profile LED button, 5.5 mm cap centred on the origin
Run from stereo-mixer/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("mixer_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 28HP
HP = circuit.HP
BOARD_X0 = (PANEL_W - circuit.BOARD_W) / 2
BOARD_Y0 = (PANEL_H - circuit.BOARD_H) / 2   # board centred on the panel
HOLE = {"pot": 7.5, "jack": 6.5, "ledbutton": 6.5}
JACK_BARREL = circuit.JACK_BARREL
POT_SHAFT = circuit.POT_SHAFT
OUT = os.path.join(HERE, "..", "panel")


def features():
    """[(kind, ref, label, origin_x, origin_y, hole_x, hole_y)] in board mm, y up."""
    labels = {r: lbl for r, lbl, *_ in circuit.JACKS}
    labels.update({r: lbl for r, lbl, *_ in circuit.POTS + circuit.POTS2})
    labels.update({r: lbl for r, lbl, *_ in circuit.BUTTONS})
    out = []
    for ref, (x, y, rot) in circuit.PLACEMENT.items():
        if ref.startswith("J"):
            out.append(("jack", ref, labels[ref], x, y, x, y + JACK_BARREL))
        elif ref.startswith("RV"):
            out.append(("pot", ref, labels[ref], x, y, x, y + POT_SHAFT))
        elif ref.startswith("SW"):
            out.append(("ledbutton", ref, labels[ref], x, y, x, y))
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
         '<title>Stereo mixer 28HP panel - drill template (print at 100%)</title>',
         '<style>text{font-family:Arial,Helvetica,sans-serif} .dim{font-size:1.6px;fill:#444} '
         '.lbl{font-size:1.8px;fill:#06c}</style>',
         f'<rect x="-20" y="-15" width="{W + 40}" height="{H + 30}" fill="#ffffff"/>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.25"/>',
         f'<rect x="{BOARD_X0:.2f}" y="{PANEL_H - BOARD_Y0 - circuit.BOARD_H:.2f}" width="{circuit.BOARD_W}" '
         f'height="{circuit.BOARD_H}" fill="none" stroke="#999" stroke-width="0.15" stroke-dasharray="1,1"/>']
    rows = [(k, lbl, *panel_xy(hx, hy)) for k, ref, lbl, ox, oy, hx, hy in feats]
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
    s.append('<line x1="5" y1="-8" x2="55" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (5, 55):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="30" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Stereo mixer 28HP panel, front view. '
             'Red circles: final hole size. Dashed: the faceplate board. Button holes suit the Thonk LED button.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the Marblesy style: black solder mask, white
# silkscreen, bare (ENIG) copper for the outputs. SVG groups: #silk,
# #copper, #holes and #mockup (knobs, nuts, button caps, preview only).
# Tune ART, run, look at stereo-mixer-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227", "lit": "#d94040",
    "knob": {"small": 5.0, "mid": 6.0},       # radii, mm: channel / RETURN / DRUMS knobs, MASTER
    "scale": {"small": 6.0, "mid": 7.5},
    "cap_led": 2.75, "nut": 4.0, "ring": 4.35,
    "title": "Mixer", "subtitle": "Stereo voice mixer", "maker": "Seedable Instruments",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
    "label": 1.9,                             # knob, button and jack labels
}
KNOB_SIZE = {ref: "small" for ref, *_ in circuit.POTS + circuit.POTS2}
KNOB_SIZE["RV25"] = "mid"
PAN_POTS = [f"RV{3 * k - 1}" for k in circuit.MONO]
MASTER_POTS = ["RV23", "RV24", "RV25"]          # labelled one by one; the channel rows share one word per row
MONO_INS = [f"J{k}" for k in circuit.MONO]
# the channel rows' words: turned 90 degrees in the left margin, each on a bracket that spans its row (the
# STEREO bracket on its side): a line at BRACKET_X broken round the word, serifs pointing at the row
WORD_X = 3.65                                   # baseline of the vertical words; the letters reach ~1.4 mm left
BRACKET_X, SERIF = 2.9, 1.6
BRACKET_GAP, BRACKET_MIN = 0.7, 2.0             # gap between word and line; shortest line piece
CHAR_W = 0.68                                   # estimated advance per character (bold sans), x font size
OUTPUTS = ["J16", "J17"]
# labels: knobs take their row word, jacks a short word above them
KNOB_WORD = {ref: lbl.split(" ")[0] for ref, lbl, *_ in circuit.POTS + circuit.POTS2}
JACK_WORD = {f"J{k}": "IN" for k in circuit.MONO}
JACK_WORD.update({"J7": "L", "J8": "R", "J9": "L", "J10": "R", "J11": "L", "J12": "R", "J13": "DRUM IN",
                  "J14": "FX IN", "J15": "SEND", "J16": "OUT L", "J17": "OUT R"})
NORMALS = [("J7", "J8"), ("J9", "J10"), ("J11", "J12")]      # R follows L: dotted line between them
BAND_CLEAR = 0.4      # bare board (under black mask) between a copper band and a hole through it; DRC asks 0.3


def bands(pos):
    """The bare-copper patches: (x, y, w, h, rx) from the top-left in the panel frame, with the holes
    through each as clearance circles (x, y, r). One band round OUT L / R, one patch round SEND."""
    out = []
    ox, rx_, jy = pos["J16"][2], pos["J17"][2], pos["J16"][3]
    sx, sy = pos["J15"][2], pos["J15"][3]
    for x, y, w, h in ((ox - 4.8, jy - 8.8, rx_ - ox + 9.6, 14.6), (sx - 4.8, sy - 8.8, 9.6, 14.6)):
        cuts = []
        for kind, label, hx, hy in pos.values():
            r = HOLE[kind] / 2 + BAND_CLEAR
            if x - r < hx < x + w + r and y - r < hy < y + h + r:
                if not (x + r < hx < x + w - r and y + r < hy < y + h - r):
                    raise ValueError(f"the hole at ({hx:.2f}, {hy:.2f}) crosses the edge of a copper band")
                cuts.append((hx, hy, r))
        out.append(((x, y, w, h, 1.4), cuts))
    return out


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
    n = {"small": 3, "mid": 7}[size]
    return [(-135 + 270 * i / (n - 1), 1.0 if i in (0, n - 1, (n - 1) // 2) else 0.6) for i in range(n)]


def layout(pos):
    """Everything the artwork and the panel PCB draw, in one list, so the two never drift apart:
    ("text", x, y, s, size, anchor, cls), ("line", pts, w), ("dots", pts), ("arc", cx, cy, r, a0, a1, w),
    ("ring", cx, cy, r, w), ("serif", x, y, s, size, anchor), and ("vtext", x, y, s, size): a word reading
    bottom to top, centred on y, with its baseline at x."""
    A = ART
    W = PANEL_W
    out = []

    def text(x, y, s, size, anchor="middle"):
        out.append(("text", x, y, s, size, anchor))

    # title band, maker line
    out.append(("serif", 12.0, 7.6, A["title"], 5.2, "start"))
    text(W - 12.0, 6.8, A["subtitle"], 2.1, "end")
    out.append(("dots", [(3, 9.6), (W - 3, 9.6)]))
    out.append(("dots", [(3, 10.6), (W - 3, 10.6)]))
    text(W / 2, 122.4, A["maker"], 2.2)
    out.append(("line", [(3, 118.6), (W - 3, 118.6)], 0.3))
    # channel numbers over the columns; the stereo pair gets a bracket and STEREO in its empty PAN row
    for k in range(1, 9):
        text(circuit.CH_X[k - 1], 16.0, str(k), 3.0)
    x7, x8 = circuit.CH_X[6], circuit.CH_X[7]
    yp = circuit.ROW["pan"]
    text((x7 + x8) / 2, yp + 0.8, "STEREO", 2.1)
    for x0, x1 in ((x7 - 3.5, (x7 + x8) / 2 - 5.4), ((x7 + x8) / 2 + 5.4, x8 + 3.5)):
        out.append(("line", [(x0, yp), (x1, yp)], 0.3))
    out.append(("line", [(x7 - 3.5, yp - 1.6), (x7 - 3.5, yp + 1.6)], 0.3))
    out.append(("line", [(x8 + 3.5, yp - 1.6), (x8 + 3.5, yp + 1.6)], 0.3))
    # the master section, set off by a rule
    xs = (circuit.CH_X[7] + circuit.M1) / 2
    out.append(("line", [(xs, 13.0), (xs, 110.0)], 0.3))
    # knobs: scale arcs with ticks; the master section's knobs get their word underneath, the channel rows
    # get theirs once (row_words below); L / R just under the ends of each pan scale
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
        if ref in MASTER_POTS:
            text(x, knob_label_y(pos, ref), KNOB_WORD[ref], A["label"] if size == "small" else 2.2)
        if ref in PAN_POTS:
            text(x - 4.9, y + 6.4, "L", 1.6)
            text(x + 4.9, y + 6.4, "R", 1.6)
    # mute buttons: a ring round each cap
    for ref, (kind, label, x, y) in pos.items():
        if kind == "ledbutton":
            out.append(("ring", x, y, A["ring"], 0.3))
    # the channel rows' words, once each in the left margin on a bracket as tall as the row
    for word, y, h in row_words(pos):
        size = A["label"]
        gap = CHAR_W * size * len(word) / 2 + BRACKET_GAP
        half = max(h, gap + BRACKET_MIN)
        out.append(("vtext", WORD_X, y, word, size))
        out.append(("line", [(BRACKET_X + SERIF, y - half), (BRACKET_X, y - half), (BRACKET_X, y - gap)], 0.3))
        out.append(("line", [(BRACKET_X, y + gap), (BRACKET_X, y + half), (BRACKET_X + SERIF, y + half)], 0.3))
    # jack labels (the outputs' go on their copper, see bands; the mono INs share the IN row word),
    # dotted normals R <- L
    for ref, (kind, label, x, y) in pos.items():
        if kind == "jack" and ref not in OUTPUTS + ["J15"] + MONO_INS:
            text(x, jack_label_y(pos, ref), JACK_WORD[ref], A["label"])
    for a, b in NORMALS:
        ax, ay = pos[a][2], pos[a][3]
        bx, by = pos[b][2], pos[b][3]
        if abs(ax - bx) < 0.1:          # one above the other: from under L's nut to above R's label
            out.append(("dots", [(ax, ay + A["nut"] + 0.9), (bx, jack_label_y(pos, b) - 2.6)]))
        else:                           # side by side: between the two nuts
            out.append(("dots", [(ax + A["nut"] + 0.9, ay), (bx - A["nut"] - 0.9, by)]))
    return out


def row_words(pos):
    """(word, centre y, half height) of each channel row: the bracket spans the first column's knob scale
    with its ticks, button ring or jack nut."""
    knob = ART["scale"]["small"] + 1.0
    return [("SEND", pos["RV3"][3], knob), ("PAN", pos["RV2"][3], knob), ("LEVEL", pos["RV1"][3], knob),
            ("MUTE", pos["SW1"][3], ART["ring"]), ("IN", pos["J1"][3], ART["nut"])]


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>Stereo mixer 28HP panel - artwork</title>',
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

    # -- bare copper: the output band and the SEND patch, labels knocked out
    s.append('<g id="copper">')
    for (bx, by, bw, bh, brx), cuts in bands(pos):
        s.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh}" rx="{brx}" class="copper"/>')
        for x, y, r in cuts:
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" class="cu-text"/>')
    for ref in OUTPUTS + ["J15"]:
        text(pos[ref][2], jack_label_y(pos, ref), JACK_WORD[ref], A["label"], cls="cu-text")
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
    # -- mockup of the fitted parts (preview only); MUTE 3 shown lit
    s.append('<g id="mockup">')
    for ref, (kind, label, x, y) in pos.items():
        if kind == "pot":
            r = A["knob"][KNOB_SIZE[ref]]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="#2a2a2a" stroke="#000" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r * 0.62:.2f}" fill="#e8e8e4"/>')
            a = math.radians(0 if ref in PAN_POTS else -135)
            s.append(f'<line x1="{x + 0.3 * r * math.sin(a):.2f}" y1="{y - 0.3 * r * math.cos(a):.2f}" '
                     f'x2="{x + 0.95 * r * math.sin(a):.2f}" y2="{y - 0.95 * r * math.cos(a):.2f}" '
                     f'stroke="#555" stroke-width="0.6" stroke-linecap="round"/>')
        elif kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["nut"]}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "ledbutton":
            fill = A["lit"] if ref == "SW3" else "#2b2b2b"
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["cap_led"]}" fill="{fill}" stroke="#000" stroke-width="0.4"/>')
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Panel clearances: knob scales, button rings and jack nuts must not touch each other or the
    edges; reports gaps under 1 mm."""
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    items = []
    for ref, (kind, label, x, y) in pos.items():
        r = {"pot": ART["scale"].get(KNOB_SIZE.get(ref, "small"), 6.0) + 0.6 if kind == "pot" else 0,
             "jack": ART["nut"], "ledbutton": ART["ring"]}[kind]
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
    write_csv(feats, os.path.join(OUT, "stereo-mixer-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "stereo-mixer-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "stereo-mixer-panel.svg"))
    for b in check(feats):
        print("tight:", b)
    print(f"{len(feats)} features + 4 mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
