"""14HP panel for Senay: hole list (CSV), a 1:1 drill template (SVG) and the
panel artwork (SVG, as a PCB panel). Everything is computed from PLACEMENT
in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the faceplate board is seen from the
front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack   sleeve pad towards the top of the board; the barrel sits 0.78 mm
         below the WQP518MA footprint origin
  pot    pins down; the Alpha shaft is 7.5 mm from the pin row, 4.0 mm
         above the PTV09A origin
  toggle sub-mini SPDT, bushing on the origin
  LED    3 mm, lens on the origin
Run from sena/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sena_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)
_spec = importlib.util.spec_from_file_location("sena_mushroom", os.path.join(HERE, "mushroom.py"))
mushroom = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mushroom)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 14HP
HP = circuit.HP
BOARD_X0 = (PANEL_W - circuit.BOARD_W) / 2
BOARD_Y0 = (PANEL_H - circuit.BOARD_H) / 2   # board centred on the panel
# toggle: a 6.0 mm hole suits an M5 bushing with play; NOT yet checked against the Dailywell
# 2MS1T1B1M2QES drawing (a 1/4-40 bushing would need 6.5). Check before ordering the panel.
HOLE = {"pot": 7.5, "jack": 6.5, "toggle": 6.0, "led": 3.2}
JACK_BARREL = circuit.JACK_BARREL
POT_SHAFT = circuit.POT_SHAFT
OUT = os.path.join(HERE, "..", "panel")


def features():
    """[(kind, ref, label, origin_x, origin_y, hole_x, hole_y)] in board mm, y up."""
    labels = {r: lbl for r, lbl, *_ in circuit.JACKS + circuit.POTS + circuit.TOGGLES + circuit.LEDS}
    out = []
    for ref, (x, y, rot) in circuit.PLACEMENT.items():
        if ref.startswith("J"):
            out.append(("jack", ref, labels[ref], x, y, x, y + JACK_BARREL))
        elif ref.startswith("RV"):
            out.append(("pot", ref, labels[ref], x, y, x, y + POT_SHAFT))
        elif ref.startswith("SW"):
            out.append(("toggle", ref, labels[ref], x, y, x, y))
        elif ref.startswith("LED"):
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
         '<title>Senay 14HP panel - drill template (print at 100%)</title>',
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
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Senay 14HP panel, front view. '
             'Red circles: final hole size. Dashed: the faceplate board.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the Marblesy style: black solder mask, white
# silkscreen, bare (ENIG) copper behind the outputs. SVG groups: #silk,
# #copper, #holes and #mockup (knobs, nuts, levers, LEDs: preview only).
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227", "lit": "#d94040",
    "knob": 5.0, "scale": 6.0,                # radii, mm
    "nut": 4.0, "toggle": 4.0, "led": 2.0,    # clearance radii: jack nut, toggle nut, LED ring
    "title": "Nettle", "subtitle": "Quad VCO + noise",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
    "label": 1.9,
}
# the rows' words: turned 90 degrees in the left margin, each on a bracket that spans its row
WORD_X = 3.65
BRACKET_X, SERIF = 2.9, 1.6
BRACKET_GAP, BRACKET_MIN = 0.7, 2.0
CHAR_W = 0.68                                   # estimated advance per character (bold sans), x font size
OUTS = [f"J{3 * k}" for k in circuit.CHANNELS]
NOISE = ["J13", "J14", "J15", "J16"]
NOISE_WORD = {"J13": "WHITE", "J14": "PINK", "J15": "BLUE", "J16": "BROWN"}
BAND_CLEAR = 0.4      # bare board (under black mask) between a copper band and a hole through it; DRC asks 0.3


def bands(pos):
    """The bare-copper patches: (x, y, w, h, rx) from the top-left in the panel frame, with the holes
    through each as clearance circles (x, y, r). One square round each OUT jack, one band under the
    noise bank holding its labels."""
    rects = [(pos[j][2] - 4.8, pos[j][3] - 4.8, 9.6, 9.6) for j in OUTS]
    x0, x1, y = pos["J13"][2], pos["J16"][2], pos["J13"][3]
    rects.append((x0 - 4.8, y - 7.8, x1 - x0 + 9.6, 13.2))
    out = []
    for x, y, w, h in rects:
        cuts = []
        for kind, label, hx, hy in pos.values():
            r = HOLE[kind] / 2 + BAND_CLEAR
            if x - r < hx < x + w + r and y - r < hy < y + h + r:
                if not (x + r < hx < x + w - r and y + r < hy < y + h - r):
                    raise ValueError(f"the hole at ({hx:.2f}, {hy:.2f}) crosses the edge of a copper band")
                cuts.append((hx, hy, r))
        out.append(((x, y, w, h, 1.4), cuts))
    return out


def jack_label_y(pos, ref):
    return pos[ref][3] - ART["nut"] - 1.6


def knob_label_y(pos, ref):
    return pos[ref][3] + ART["scale"] + 2.6


def _arc(cx, cy, r, a0, a1):
    """SVG path of an arc from angle a0 to a1 (degrees, clockwise from 12 o'clock)."""
    p0 = (cx + r * math.sin(math.radians(a0)), cy - r * math.cos(math.radians(a0)))
    p1 = (cx + r * math.sin(math.radians(a1)), cy - r * math.cos(math.radians(a1)))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M {p0[0]:.2f} {p0[1]:.2f} A {r} {r} 0 {large} 1 {p1[0]:.2f} {p1[1]:.2f}"


def scale_ticks():
    """Tick angles (degrees from 12 o'clock) and lengths of a knob's scale: ends and centre."""
    return [(-135, 1.0), (0, 1.0), (135, 1.0)]


def layout(pos):
    """Everything the artwork and the panel PCB draw, in one list, so the two never drift apart:
    ("text", x, y, s, size, anchor), ("line", pts, w), ("dots", pts), ("arc", cx, cy, r, a0, a1, w),
    ("ring", cx, cy, r, w), ("serif", x, y, s, size, anchor) and ("vtext", x, y, s, size): a word
    reading bottom to top, centred on y, with its baseline at x."""
    A = ART
    W = PANEL_W
    out = []

    def text(x, y, s, size=A["label"], anchor="middle"):
        out.append(("text", x, y, s, size, anchor))

    # the frame, the same spots on every module's panel
    out.append(("serif", 12.0, 7.4, A["title"], 5.2, "start"))
    text(W - 12.0, 6.6, A["subtitle"], 2.1, "end")
    out.append(("dots", [(3, 9.6), (W - 3, 9.6)]))
    out.append(("dots", [(3, 10.6), (W - 3, 10.6)]))
    out.append(("gold", mushroom.polygons(W)))     # the mushroom mark under the rule, bare gold
    out.append(("line", [(3, 118.6), (W - 3, 118.6)], 0.3))
    # knobs: scale arcs with ticks; FREQ labelled once (row 1), each modifier knob with its word
    for ref, (kind, label, x, y) in pos.items():
        if kind != "pot":
            continue
        r = A["scale"]
        out.append(("arc", x, y, r, -135, 135, 0.3))
        for a, ln in scale_ticks():
            ra = math.radians(a)
            out.append(("line", [(x + r * math.sin(ra), y - r * math.cos(ra)),
                                 (x + (r + ln) * math.sin(ra), y - (r + ln) * math.cos(ra))], 0.3))
        if ref == "RV1" or not label.startswith("FREQ"):
            text(x, knob_label_y(pos, ref), label.split(" ")[0])
    # jacks: the three columns named once over the top row (a word over a lower row's jack sits just
    # under the toggles above it and reads as theirs); the FREQ inputs' daisy chain as dots from one
    # jack down to the next
    for k in circuit.CHANNELS[:-1]:
        f, nxt = f"J{3 * k - 2}", f"J{3 * k + 1}"
        out.append(("dots", [(pos[f][2], pos[f][3] + A["nut"] + 0.9), (pos[nxt][2], pos[nxt][3] - A["nut"] - 0.9)]))
    text(pos["J1"][2], jack_label_y(pos, "J1"), "FREQ")
    text(pos["J2"][2], jack_label_y(pos, "J2"), "CV")
    text(pos["J3"][2], jack_label_y(pos, "J3") - 0.8, "OUT")         # above its copper square
    # toggles: positions named once, on channel 1
    t1, t2, t3 = (pos[r] for r in ("SW1", "SW2", "SW3"))
    yl = t1[3] - A["toggle"] - 0.8
    text(t1[2] - 2.6, yl, "V/O")
    text(t1[2] + 2.8, yl, "FM")
    text(t2[2], yl, "FINE")
    text(t3[2], t3[3] - A["toggle"] - 0.8, "VCO")
    text(t3[2], t3[3] + A["toggle"] + 2.0, "LFO")
    # LEDs: a thin ring
    for ref, (kind, label, x, y) in pos.items():
        if kind == "led":
            out.append(("ring", x, y, A["led"], 0.25))
    # the rows' words, once each in the left margin on a bracket as tall as the row
    for word, y, h in row_words(pos):
        size = A["label"]
        gap = CHAR_W * size * len(word) / 2 + BRACKET_GAP
        half = max(h, gap + BRACKET_MIN)
        out.append(("vtext", WORD_X, y, word, size))
        out.append(("line", [(BRACKET_X + SERIF, y - half), (BRACKET_X, y - half), (BRACKET_X, y - gap)], 0.3))
        out.append(("line", [(BRACKET_X, y + gap), (BRACKET_X, y + half), (BRACKET_X + SERIF, y + half)], 0.3))
    return out


def row_words(pos):
    """(word, centre y, half height) of each row: a channel's bracket spans from its jacks' nuts to
    its toggles' nuts; the noise bank's spans its jacks."""
    out = []
    for k in circuit.CHANNELS:
        top = pos[f"J{3 * k - 2}"][3] - ART["nut"]
        bottom = pos[f"SW{3 * k - 2}"][3] + ART["toggle"]
        out.append((circuit.WAVE[k], (top + bottom) / 2, (bottom - top) / 2))
    out.append(("NOISE", pos["J13"][3], ART["nut"]))
    return out


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>Senay 14HP panel - artwork</title>',
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

    # -- bare copper: a square round each OUT jack, the noise band with its labels knocked out
    s.append('<g id="copper">')
    for (bx, by, bw, bh, brx), cuts in bands(pos):
        s.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh}" rx="{brx}" class="copper"/>')
        for x, y, r in cuts:
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" class="cu-text"/>')
    for ref in NOISE:
        text(pos[ref][2], jack_label_y(pos, ref), NOISE_WORD[ref], A["label"], cls="cu-text")
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
    s.append('</g>')
    # -- holes
    s.append('<g id="holes">')
    for ref, (kind, label, x, y) in pos.items():
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{HOLE[kind] / 2:.2f}" class="hole"/>')
    for x, y in MOUNTS:
        s.append(slot(x, y, cls="hole"))
    s.append('</g>')
    # -- mockup of the fitted parts (preview only): FREQ knobs at noon, modifiers at assorted
    # settings, channel 2 in FM, channel 4 fine-tuned, channel 3 in LFO, its LED lit
    s.append('<g id="mockup">')
    knob_at = {"RV2": -60, "RV4": 30, "RV6": 100, "RV8": -20}
    lever = {"SW1": "l", "SW2": "l", "SW3": "u", "SW4": "r", "SW5": "l", "SW6": "u", "SW7": "l", "SW8": "l",
             "SW9": "d", "SW10": "l", "SW11": "r", "SW12": "u"}
    for ref, (kind, label, x, y) in pos.items():
        if kind == "pot":
            r = A["knob"]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="#2a2a2a" stroke="#000" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r * 0.62:.2f}" fill="#e8e8e4"/>')
            a = math.radians(knob_at.get(ref, 0))
            s.append(f'<line x1="{x + 0.3 * r * math.sin(a):.2f}" y1="{y - 0.3 * r * math.cos(a):.2f}" '
                     f'x2="{x + 0.95 * r * math.sin(a):.2f}" y2="{y - 0.95 * r * math.cos(a):.2f}" '
                     f'stroke="#555" stroke-width="0.6" stroke-linecap="round"/>')
        elif kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["nut"]}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "toggle":
            hexagon = " ".join(f"{x + 3.6 * math.cos(math.radians(30 + 60 * i)):.2f},"
                               f"{y + 3.6 * math.sin(math.radians(30 + 60 * i)):.2f}" for i in range(6))
            s.append(f'<polygon points="{hexagon}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.4" fill="#d6d7d3" stroke="#777" stroke-width="0.15"/>')
            dx, dy = {"l": (-1, 0), "r": (1, 0), "u": (0, -1), "d": (0, 1)}[lever[ref]]
            s.append(f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x + 2.8 * dx:.2f}" y2="{y + 2.8 * dy:.2f}" '
                     f'stroke="#efefec" stroke-width="1.2" stroke-linecap="round"/>')
        elif kind == "led":
            fill = A["lit"] if ref == "LED3" else "#3a1414"
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.5" fill="{fill}" stroke="#000" stroke-width="0.2"/>')
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Panel clearances: knob scales, toggle and jack nuts, LED rings must not touch each other or
    the edges; reports gaps under 1 mm."""
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    rad = {"pot": ART["scale"] + 0.6, "jack": ART["nut"], "toggle": ART["toggle"], "led": ART["led"]}
    items = [(ref, x, y, rad[kind]) for ref, (kind, label, x, y) in pos.items()]
    bad = []
    for i, (a, xa, ya, ra) in enumerate(items):
        for b, xb, yb, rb in items[i + 1:]:
            gap = math.hypot(xa - xb, ya - yb) - ra - rb
            if gap < 1.0:
                bad.append(f"{a} - {b}: {gap:.2f} mm")
        edge = min(xa, PANEL_W - xa) - ra
        if edge < 2.0:
            bad.append(f"{a} - panel edge: {edge:.2f} mm")
        if ya - ra < 10.6 or ya + ra > 118.6:
            bad.append(f"{a} - outside the band and rule")
    return bad


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, "senay-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "senay-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "senay-panel.svg"))
    for b in check(feats):
        print("tight:", b)
    print(f"{len(feats)} features + 4 mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
