"""26HP panel for Eight: hole list (CSV), a 1:1 drill template (SVG) and
the panel artwork (SVG, as a PCB panel). Everything is computed from
PLACEMENT in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the board is seen from the front, x to the
right, y up, origin at the board's bottom-left corner. Panel-facing parts
sit on the board's bottom layer.
  jack    sleeve pad towards the top of the board; the barrel sits 0.78 mm
          below the WQP518MA footprint origin
  pot     Alpha 9 mm, pins down; the shaft is 4.0 mm above the footprint origin
  button  Thonk low-profile LED button, 5.5 mm cap centred on the origin
  LED     3 mm, lens centred on the origin
Run from 8-step-sequencer/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("eight_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)
_spec = importlib.util.spec_from_file_location("eight_mushroom", os.path.join(HERE, "mushroom.py"))
mushroom = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mushroom)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 26HP
HP = circuit.HP
HOLE = {"pot": 7.5, "jack": 6.5, "ledbutton": 6.5}
JACK_BARREL = circuit.JACK_BARREL
POT_SHAFT = circuit.POT_SHAFT
ROW = circuit.ROW
OUT = os.path.join(HERE, "..", "panel")


def features():
    """[(kind, ref, label, origin_x, origin_y, hole_x, hole_y)] in board mm, y up."""
    labels = {r: lbl for r, lbl, *_ in circuit.JACKS + circuit.POTS + circuit.BUTTONS}
    out = []
    for ref, (x, y, rot) in circuit.PLACEMENT.items():
        if ref.startswith("J"):
            out.append(("jack", ref, labels[ref], x, y, x, y + JACK_BARREL))
        elif ref.startswith("RV"):
            out.append(("pot", ref, labels[ref], x, y, x, y + POT_SHAFT))
        elif ref.startswith("SW"):
            out.append(("ledbutton", ref, labels[ref], x, y, x, y))
    return out


panel_xy = circuit.panel_xy

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
    """Drill template, plus the board and where the Mega's sockets land behind it (dashed)."""
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 40}mm" height="{H + 30}mm" '
         f'viewBox="-20 -15 {W + 40} {H + 30}">',
         '<title>Eight 26HP panel - drill template (print at 100%)</title>',
         '<style>text{font-family:Arial,Helvetica,sans-serif} .dim{font-size:1.6px;fill:#444} '
         '.lbl{font-size:1.8px;fill:#06c}</style>',
         f'<rect x="-20" y="-15" width="{W + 40}" height="{H + 30}" fill="#ffffff"/>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.25"/>',
         f'<rect x="{circuit.BOARD_X0:.2f}" y="{PANEL_H - circuit.BOARD_Y0 - circuit.BOARD_H:.2f}" '
         f'width="{circuit.BOARD_W}" height="{circuit.BOARD_H}" fill="none" stroke="#999" stroke-width="0.15" '
         'stroke-dasharray="1,1"/>']
    # the Mega on the board's rear: outline and socket pads
    mx0, my0 = panel_xy(circuit.MEGA_AT[0], circuit.MEGA_AT[1] + circuit.MEGA_H)
    s.append(f'<rect x="{mx0:.2f}" y="{my0:.2f}" width="{circuit.MEGA_W}" height="{circuit.MEGA_H}" fill="none" '
             'stroke="#0a0" stroke-width="0.15" stroke-dasharray="0.6,0.6"/>')
    for name in circuit.SOCKETED:
        x, y = panel_xy(*circuit.mega_pad_xy(name))
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{circuit.MEGA_PAD}" fill="none" stroke="#0a0" stroke-width="0.12"/>')
    s.append(f'<text class="dim" x="{mx0 + 1:.2f}" y="{ROW["mega_2"] - 5.2:.2f}" style="fill:#0a0">'
             'Mega 2560 Pro on the rear, USB at the left edge</text>')
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
    s.append('<line x1="15" y1="-8" x2="65" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (15, 65):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="40" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Eight 26HP panel, front view. '
             'Red circles: final hole size. Dashed grey: the board. Green: the Mega behind it.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the Marblesy style: black solder mask, white
# silkscreen, bare (ENIG) copper for the outputs. SVG groups: #silk,
# #copper, #holes and #mockup (knobs, nuts, button caps, preview only).
# Tune ART, run, look at eight-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227", "red": "#ff4a3a", "green": "#4bd66e",
    "knob": 5.0, "scale": 6.0,                # radii, mm, Offset's knobs
    "dial": 6.6,                              # the ROWS / DIRECTION / BUTTONS arc
    "nut": 4.0, "cap": 2.75, "ring": 4.35,
    "title": "Furrow", "subtitle": "Dual 8-step",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
    "label": 1.9,                             # knob, button and jack labels; step numbers are 3.0
    "mark": 1.8,                              # ROWS / DIRECTION / BUTTONS positions
    "legend": 1.6,                            # the SHIFT functions under the B buttons
    "row": 4.4,                               # the A / B letters on their brackets
}
CHAR_W = 0.68                                   # estimated advance per character (bold sans), x font size
BRACKET_X, SERIF = 2.9, 1.6                     # the A / B brackets in the left margin, serifs towards the rows
LABEL_Y = ROW["controls"] + 10.5                # baseline of the control names (ROWS, DIRECTION, BUTTONS, DUTY, SHIFT)
STEP_NO_Y = ROW["pot_a"] - 8.6                  # step numbers over the columns
OUTPUTS = ["J3", "J4", "J5", "J6"]
RINGS = {"RV17": circuit.ROWS_MODES, "RV18": circuit.DIRECTIONS, "RV19": circuit.BUTTON_MODES}
RING_TICK = 1.0                                 # a ROWS / DIRECTION / BUTTONS position's tick
CONTROL_WORD = {"RV17": "ROWS", "RV18": "DIRECTION", "RV19": "BUTTONS", "RV20": "DUTY"}
# SHIFT + step button k of a row: the row's range (1-4) or quantizer (5-8). Boxed, like SHIFT itself.
LEGEND = ["1V", "2V", "5V", "8V", "OFF", "MIN", "MAJ", "CHR"]
LEGEND_GROUPS = [("RANGE", 0, 3), ("SCALE", 4, 7)]
BOX_PAD, BOX_H = 0.6, 2.5                       # legend boxes: padding each side of the word, height
BAND_CLEAR = 0.4      # bare board (under black mask) between a copper band and a hole through it; DRC asks 0.3
# preview only: knob pointers (degrees from 12 o'clock), which positions are selected, which steps are
# on and which one plays (the sketch shows the playing step inverted)
MOCK_ANGLE = {f"RV{k}": a for k, a in enumerate([-90, 40, -10, 110, -60, 75, 0, -120], start=1)}
MOCK_ANGLE.update({f"RV{8 + k}": a for k, a in enumerate([20, -100, 60, 90, -30, 130, -75, 10], start=1)})
MOCK_POSITION = {"RV17": 2, "RV18": 2, "RV19": 0}   # A+B, PING-PONG, GATE
MOCK_ANGLE.update({ref: circuit.ring_angles(len(RINGS[ref]))[i] for ref, i in MOCK_POSITION.items()})
MOCK_ANGLE["RV20"] = -25
MOCK_ON = {"A": [1, 1, 0, 1, 1, 1, 0, 1], "B": [1, 0, 1, 1, 0, 1, 1, 0]}
MOCK_PLAYING = {"A": 4, "B": 4}                 # step 5 of both rows


def bands(pos):
    """The bare-copper band round the outputs and their labels: [((x, y, w, h, rx), [(x, y, r) holes])]
    from the top-left in the panel frame, each hole through it as a clearance circle."""
    x0, x1 = pos[OUTPUTS[0]][2] - 5.6, pos[OUTPUTS[-1]][2] + 5.6
    jy = pos[OUTPUTS[0]][3]
    y0, y1 = jack_label_y(pos, OUTPUTS[0]) - 2.7, jy + ART["nut"] + 1.4
    x, y, w, h = x0, y0, x1 - x0, y1 - y0
    cuts = []
    for kind, label, hx, hy in pos.values():
        r = HOLE[kind] / 2 + BAND_CLEAR
        if x - r < hx < x + w + r and y - r < hy < y + h + r:
            if not (x + r < hx < x + w - r and y + r < hy < y + h - r):
                raise ValueError(f"the hole at ({hx:.2f}, {hy:.2f}) crosses the edge of the copper band")
            cuts.append((hx, hy, r))
    return [((x, y, w, h, 1.4), cuts)]


def jack_label_y(pos, ref):
    return pos[ref][3] - ART["nut"] - 1.6


def _arc(cx, cy, r, a0, a1):
    """SVG path of an arc from angle a0 to a1 (degrees, clockwise from 12 o'clock)."""
    p0 = (cx + r * math.sin(math.radians(a0)), cy - r * math.cos(math.radians(a0)))
    p1 = (cx + r * math.sin(math.radians(a1)), cy - r * math.cos(math.radians(a1)))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M {p0[0]:.2f} {p0[1]:.2f} A {r} {r} 0 {large} 1 {p1[0]:.2f} {p1[1]:.2f}"


def _polar(cx, cy, r, a):
    return cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a))


def scale_ticks():
    """Tick angles (degrees from 12 o'clock) and lengths: both ends and noon long, the halves short."""
    return [(-135 + 67.5 * i, 1.0 if i in (0, 2, 4) else 0.6) for i in range(5)]


def ring_labels(cx, cy, words):
    """(x, baseline, word, anchor) for each position of a ROWS / DIRECTION / BUTTONS knob, at the end of
    its tick. A word straight up is centred over it; the others near the top go above their tick,
    running away from 12 o'clock; the rest beside it, outwards."""
    out = []
    size = ART["mark"]
    for word, a in zip(words, circuit.ring_angles(len(words))):
        anchor = "end" if a < 0 else "start"
        tx, ty = _polar(cx, cy, ART["dial"] + RING_TICK, a)
        wx, wy = _polar(cx, cy, ART["dial"] + RING_TICK + 0.7, a)
        top_y, side = ty - 0.6, (wx, wy + 0.36 * size)
        if abs(a) < 1:
            out.append((cx, top_y, word, "middle"))
        elif abs(a) < 30:
            out.append((cx + math.copysign(0.9, a), top_y, word, anchor))
        else:
            out.append((*side, word, anchor))
    return out


def text_box(x, y, s, size, anchor):
    """Rough extent of a line of text: (x0, y0, x1, y1), panel frame."""
    w = CHAR_W * size * len(s)
    x0 = {"start": x, "middle": x - w / 2, "end": x - w}[anchor]
    return x0, y - 0.74 * size, x0 + w, y + 0.05 * size


def layout(pos):
    """Everything the artwork and (later) the panel PCB draw, in one list, so the two never drift apart:
    ("text", x, y, s, size, anchor), ("line", pts, w), ("dots", pts), ("arc", cx, cy, r, a0, a1, w),
    ("ring", cx, cy, r, w), ("box", x, y, w, h, rx, w), and ("serif", x, y, s, size, anchor)."""
    A = ART
    W = PANEL_W
    out = []

    def text(x, y, s, size, anchor="middle"):
        out.append(("text", x, y, s, size, anchor))

    def tick(cx, cy, r, a, ln):
        out.append(("line", [_polar(cx, cy, r, a), _polar(cx, cy, r + ln, a)], 0.3))

    # title band, rule and mushroom mark
    out.append(("serif", 12.0, 7.4, A["title"], 5.2, "start"))     # the same spots on every module's panel
    text(W - 12.0, 6.6, A["subtitle"], 2.1, "end")
    out.append(("dots", [(3, 9.6), (W - 3, 9.6)]))
    out.append(("dots", [(3, 10.6), (W - 3, 10.6)]))
    out.append(("gold", mushroom.polygons(W)))     # the mushroom mark under the rule, bare gold
    out.append(("line", [(3, 118.6), (W - 3, 118.6)], 0.3))
    # step numbers over the columns
    for k, x in enumerate(circuit.STEP_X, start=1):
        text(x, STEP_NO_Y, str(k), 3.0)
    for ref, (kind, label, x, y) in pos.items():
        if kind != "pot":
            continue
        if ref in RINGS:
            # ROWS / DIRECTION / BUTTONS: an arc over the knob's whole travel with a tick at each position,
            # the words outside
            words = RINGS[ref]
            half = circuit.KNOB_TRAVEL / 2
            out.append(("arc", x, y, A["dial"], -half, half, 0.3))
            for a in circuit.ring_angles(len(words)):
                tick(x, y, A["dial"], a, RING_TICK)
            for lx, ly, word, anchor in ring_labels(x, y, words):
                text(lx, ly, word, A["mark"], anchor)
            text(x, LABEL_Y, CONTROL_WORD[ref], A["label"])
        else:
            # step and DUTY knobs: scale arc with ticks (all run from low at CCW to high at CW)
            r = A["scale"]
            out.append(("arc", x, y, r, -135, 135, 0.3))
            for a, ln in scale_ticks():
                tick(x, y, r, a, ln)
            if ref in CONTROL_WORD:
                text(x, LABEL_Y, CONTROL_WORD[ref], A["label"])
    # LED buttons: a ring round each cap; SHIFT's name boxed like the functions it reaches
    for ref, (kind, label, x, y) in pos.items():
        if kind == "ledbutton":
            out.append(("ring", x, y, A["ring"], 0.3))
    sx = pos["SW17"][2]
    out += boxed(sx, LABEL_Y - 0.36 * A["label"] + 0.05, "SHIFT", A["label"])
    # the rows' letters, once each in the left margin on a bracket as tall as the row
    for word, y0, y1 in row_brackets(pos):
        yc = (y0 + y1) / 2
        gap = A["row"] * 0.62
        out.append(("serif", BRACKET_X + 0.35, yc + 0.34 * A["row"], word, A["row"], "middle"))
        out.append(("line", [(BRACKET_X + SERIF, y0), (BRACKET_X, y0), (BRACKET_X, yc - gap)], 0.3))
        out.append(("line", [(BRACKET_X, yc + gap), (BRACKET_X, y1), (BRACKET_X + SERIF, y1)], 0.3))
    # SHIFT functions under the B buttons, boxed, grouped by a bracket each
    ly = legend_y(pos)
    for word, x in zip(LEGEND, circuit.STEP_X):
        out += boxed(x, ly, word, A["legend"])
    gy = ly + BOX_H / 2 + 2.2
    for word, i0, i1 in LEGEND_GROUPS:
        x0, x1 = circuit.STEP_X[i0] - 4.5, circuit.STEP_X[i1] + 4.5
        xc = (x0 + x1) / 2
        half = CHAR_W * A["legend"] * len(word) / 2 + 1.0
        text(xc, gy + 0.36 * A["legend"], word, A["legend"])
        out.append(("line", [(x0, gy - 1.0), (x0, gy), (xc - half, gy)], 0.3))
        out.append(("line", [(xc + half, gy), (x1, gy), (x1, gy - 1.0)], 0.3))
    # jack labels; the outputs' go on their copper (see write_artwork)
    for ref, (kind, label, x, y) in pos.items():
        if kind == "jack" and ref not in OUTPUTS:
            text(x, jack_label_y(pos, ref), label, A["label"])
    return out


def boxed(x, yc, word, size):
    """A word in a thin rounded box, centred on (x, yc)."""
    w = CHAR_W * size * len(word) + 2 * BOX_PAD
    return [("box", x - w / 2, yc - BOX_H / 2, w, BOX_H, 0.6, 0.25),
            ("text", x, yc + 0.36 * size, word, size, "middle")]


def legend_y(pos):
    """Centre line of the SHIFT legend boxes, under the B buttons' rings."""
    return pos["SW9"][3] + ART["ring"] + 1.2 + BOX_H / 2


def row_brackets(pos):
    """(letter, top, bottom) of each row's bracket: from the top of its knob scale to the bottom of its
    button ring."""
    knob = ART["scale"] + 1.0
    return [("A", pos["RV1"][3] - knob, pos["SW1"][3] + ART["ring"]),
            ("B", pos["RV9"][3] - knob, pos["SW9"][3] + ART["ring"])]


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>Eight 26HP panel - artwork</title>',
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

    # -- bare copper: the output band, labels knocked out
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
            text(x, y, t, size, anchor, cls="serif")
        elif kind == "gold":
            s.append(f'<path d="{mushroom.svg_path(item[1])}" class="copper"/>')
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
        elif kind == "box":
            _, x, y, bw, bh, rx, w = item
            s.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bw:.2f}" height="{bh:.2f}" rx="{rx}" class="silk" '
                     f'stroke-width="{w}"/>')
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
        if kind == "pot":
            r = A["knob"]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="#2a2a2a" stroke="#000" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r * 0.62:.2f}" fill="#e8e8e4"/>')
            a = math.radians(MOCK_ANGLE.get(ref, 0))
            s.append(f'<line x1="{x + 0.3 * r * math.sin(a):.2f}" y1="{y - 0.3 * r * math.cos(a):.2f}" '
                     f'x2="{x + 0.95 * r * math.sin(a):.2f}" y2="{y - 0.95 * r * math.cos(a):.2f}" '
                     f'stroke="#555" stroke-width="0.6" stroke-linecap="round"/>')
        elif kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["nut"]}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "ledbutton":
            k = int(ref[2:])
            if k <= 16:
                row, i = ("A", k - 1) if k <= 8 else ("B", k - 9)
                lit = MOCK_ON[row][i] != (i == MOCK_PLAYING[row])
                colour = A["red"] if row == "A" else A["green"]
            else:
                lit, colour = False, None
            if lit:
                s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["cap"] + 1.2}" fill="{colour}" opacity="0.3"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["cap"]}" fill="{colour if lit else "#2b2b2b"}" '
                     'stroke="#000" stroke-width="0.4"/>')
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Panel clearances: knob scales, button rings and jack nuts must not touch each other or the
    edges, and no label may run into another label or a part; reports gaps under 1 mm (labels: 0.4)."""
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    items = []
    for ref, (kind, label, x, y) in pos.items():
        r = {"pot": (ART["knob"] if ref in RINGS else ART["scale"]) + 0.6, "jack": ART["nut"],
             "ledbutton": ART["ring"]}[kind]
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
    texts = [it for it in layout(pos) if it[0] == "text"]
    texts += [("text", pos[r][2], jack_label_y(pos, r), pos[r][1], ART["label"], "middle") for r in OUTPUTS]
    boxes = [(t[3], text_box(*t[1:6])) for t in texts]
    for i, (sa, (ax0, ay0, ax1, ay1)) in enumerate(boxes):
        if ax0 < 2.0 or ax1 > PANEL_W - 2.0:
            bad.append(f"label {sa!r} - panel edge")
        for sb, (bx0, by0, bx1, by1) in boxes[i + 1:]:
            if ax0 < bx1 + 0.4 and bx0 < ax1 + 0.4 and ay0 < by1 + 0.4 and by0 < ay1 + 0.4:
                bad.append(f"label {sa!r} - label {sb!r}")
        for ref, x, y, r in items:
            dx = max(ax0 - x, 0.0, x - ax1)
            dy = max(ay0 - y, 0.0, y - ay1)
            if math.hypot(dx, dy) < r + 0.4:
                bad.append(f"label {sa!r} - {ref}: {math.hypot(dx, dy) - r:.2f} mm")
    return bad


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, "eight-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "eight-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "eight-panel.svg"))
    for b in check(feats):
        print("tight:", b)
    print(f"{len(feats)} features + 4 mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
