"""12HP panel for Veilsy: hole list (CSV), a 1:1 drill template (SVG) and
the panel artwork (SVG, as a PCB panel). Everything is computed from
PLACEMENT in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the faceplate board is seen from the
front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack    sleeve pad towards the top of the board; the barrel sits 0.78 mm
          below the WQP518MA footprint origin
  pot     Alpha 9 mm, pins down; the shaft is 4.0 mm above the footprint origin
  LED     3 mm, lens centred on the origin
Run from vca/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("veilsy_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)
_spec = importlib.util.spec_from_file_location("vca_mushroom", os.path.join(HERE, "mushroom.py"))
mushroom = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mushroom)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 12HP
HP = circuit.HP
HOLE = {"pot": 7.5, "jack": 6.5, "led": 3.2}
JACK_BARREL = circuit.JACK_BARREL
POT_SHAFT = circuit.POT_SHAFT
N = circuit.CHANNELS
OUT = os.path.join(HERE, "..", "panel")
STEM = "veilsy"


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
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 40}mm" height="{H + 30}mm" '
         f'viewBox="-20 -15 {W + 40} {H + 30}">',
         '<title>Veilsy 12HP panel - drill template (print at 100%)</title>',
         '<style>text{font-family:Arial,Helvetica,sans-serif} .dim{font-size:1.6px;fill:#444} '
         '.lbl{font-size:1.8px;fill:#06c}</style>',
         f'<rect x="-20" y="-15" width="{W + 40}" height="{H + 30}" fill="#ffffff"/>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.25"/>',
         f'<rect x="{circuit.BOARD_X0:.2f}" y="{PANEL_H - circuit.BOARD_Y0 - circuit.BOARD_H:.2f}" '
         f'width="{circuit.BOARD_W}" height="{circuit.BOARD_H}" fill="none" stroke="#999" stroke-width="0.15" '
         'stroke-dasharray="1,1"/>']
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
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Veilsy 12HP panel, front view. '
             'Red circles: final hole size. Dashed: the board.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the Marblesy style: black solder mask, white
# silkscreen, bare (ENIG) copper for the outputs. SVG groups: #silk,
# #copper, #holes and #mockup (knobs, nuts, LEDs, preview only).
# Tune ART, run, look at veilsy-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227", "red": "#ff4a3a",
    "knob": 5.0, "scale": 5.8,                # radii, mm: LEVEL, Offset's knobs, the scale 0.2 in (13.3 mm columns)
    "knob_s": 4.0, "scale_s": 5.0,            # CV AMT and RESPONSE, small knobs
    "nut": 4.0, "led": 1.75,
    "title": "Stoma", "subtitle": "Quad VCA",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
    "label": 1.9,                             # row words, channel numbers are 3.0
}
# the rows' words: turned 90 degrees in the left margin, each on a bracket that spans its row: a line at
# BRACKET_X broken round the word, serifs pointing at the row (the mixer's style, the user's pick)
WORD_X = 3.65                                   # baseline of the vertical words; the letters reach ~1.4 mm left
BRACKET_X, SERIF = 2.9, 1.6
BRACKET_GAP, BRACKET_MIN = 0.7, 2.0             # gap between word and line; shortest line piece
CHAR_W = 0.68                                   # estimated advance per character (bold sans), x font size
INPUTS = [f"J{k}" for k in range(1, N + 1)]
CVS = [f"J{N + k}" for k in range(1, N + 1)]
OUTPUTS = [f"J{2 * N + k}" for k in range(1, N + 1)]
SMALL = {f"RV{3 * k - 1}" for k in range(1, N + 1)} | {f"RV{3 * k}" for k in range(1, N + 1)}
RESPONSE_KNOBS = {f"RV{3 * k}" for k in range(1, N + 1)}
BAND_CLEAR = 0.4      # bare board (under black mask) between a copper band and a hole through it; DRC asks 0.3
# preview only: knob pointers (degrees from 12 o'clock) and how bright each LED is
MOCK_ANGLE = {"RV1": 135, "RV2": -135, "RV3": -135,     # 1: a mixer channel at full, LIN
              "RV4": -135, "RV5": 60, "RV6": -20,       # 2: pumped by Envy's INV, between LIN and EXP
              "RV7": -100, "RV8": 100, "RV9": 135,      # 3: an envelope, EXP
              "RV10": -135, "RV11": 100, "RV12": 135}   # 4: the same envelope (CV 3 normalled), EXP
MOCK_LED = {"D1": 0.95, "D2": 0.55, "D3": 0.2, "D4": 0.2}


def bands(pos):
    """The bare-copper band round the LEDs and the OUT jacks: [((x, y, w, h, rx), [(x, y, r) holes])]
    from the top-left in the panel frame, each hole through it as a clearance circle."""
    x0, x1 = pos[OUTPUTS[0]][2] - 5.6, pos[OUTPUTS[-1]][2] + 5.6
    y0, y1 = pos["D1"][3] - 3.4, pos[OUTPUTS[0]][3] + 5.6
    x, y, w, h = x0, y0, x1 - x0, y1 - y0
    cuts = []
    for kind, label, hx, hy in pos.values():
        r = HOLE[kind] / 2 + BAND_CLEAR
        if x - r < hx < x + w + r and y - r < hy < y + h + r:
            if not (x + r < hx < x + w - r and y + r < hy < y + h - r):
                raise ValueError(f"the hole at ({hx:.2f}, {hy:.2f}) crosses the edge of the copper band")
            cuts.append((hx, hy, r))
    return [((x, y, w, h, 1.4), cuts)]


def _arc(cx, cy, r, a0, a1):
    """SVG path of an arc from angle a0 to a1 (degrees, clockwise from 12 o'clock)."""
    p0 = (cx + r * math.sin(math.radians(a0)), cy - r * math.cos(math.radians(a0)))
    p1 = (cx + r * math.sin(math.radians(a1)), cy - r * math.cos(math.radians(a1)))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M {p0[0]:.2f} {p0[1]:.2f} A {r} {r} 0 {large} 1 {p1[0]:.2f} {p1[1]:.2f}"


def scale_ticks():
    """Tick angles (degrees from 12 o'clock) and lengths: both ends and noon long, the halves short."""
    return [(-135 + 67.5 * i, 1.0 if i in (0, 2, 4) else 0.6) for i in range(5)]


def knob_radii(ref):
    return (ART["knob_s"], ART["scale_s"]) if ref in SMALL else (ART["knob"], ART["scale"])


def curve(cx, cy, law, w=2.2, h=1.9, n=9):
    """A response glyph centred on (cx, cy), gain over control: a straight ramp (LIN) or e^x (EXP)."""
    pts = []
    for i in range(n):
        u = i / (n - 1)
        v = u if law == "lin" else (math.exp(3.0 * u) - 1) / (math.exp(3.0) - 1)
        pts.append((cx - w / 2 + w * u, cy + h / 2 - h * v))
    return ("line", pts, 0.25)


def layout(pos):
    """Everything the artwork and (later) the panel PCB draw, in one list, so the two never drift apart:
    ("text", x, y, s, size, anchor), ("line", pts, w), ("dots", pts), ("arc", cx, cy, r, a0, a1, w),
    ("serif", x, y, s, size, anchor), and ("vtext", x, y, s, size): a word reading bottom to top,
    centred on y, with its baseline at x."""
    A = ART
    W = PANEL_W
    out = []

    def text(x, y, s, size, anchor="middle"):
        out.append(("text", x, y, s, size, anchor))

    # title band, rule and mushroom mark
    out.append(("serif", 12.0, 7.4, A["title"], 5.2, "start"))     # the same spots on every module's panel
    text(W - 12.0, 6.6, A["subtitle"], 2.1, "end")
    out.append(("dots", [(3, 9.6), (W - 3, 9.6)]))
    out.append(("dots", [(3, 10.6), (W - 3, 10.6)]))
    out.append(("gold", mushroom.polygons(W)))     # the mushroom mark under the rule, bare gold
    out.append(("line", [(3, 118.6), (W - 3, 118.6)], 0.3))
    # channel numbers over the columns
    for k, x in enumerate(circuit.CH_X, start=1):
        text(x, 16.0, str(k), 3.0)
    # knobs: scale arcs with ticks; RESPONSE gets its two laws as little curves under the scale's ends
    for ref, (kind, label, x, y) in pos.items():
        if kind != "pot":
            continue
        r = knob_radii(ref)[1]
        out.append(("arc", x, y, r, -135, 135, 0.3))
        for a, ln in scale_ticks():
            ra = math.radians(a)
            out.append(("line", [(x + r * math.sin(ra), y - r * math.cos(ra)),
                                 (x + (r + ln) * math.sin(ra), y - (r + ln) * math.cos(ra))], 0.3))
        if ref in RESPONSE_KNOBS:
            out.append(curve(x - 4.7, y + 6.2, "lin"))
            out.append(curve(x + 4.7, y + 6.2, "exp"))
    # the rows' words, once each in the left margin on a bracket as tall as the row
    for word, y, h in row_words(pos):
        size = A["label"]
        gap = CHAR_W * size * len(word) / 2 + BRACKET_GAP
        half = max(h, gap + BRACKET_MIN)
        out.append(("vtext", WORD_X, y, word, size))
        out.append(("line", [(BRACKET_X + SERIF, y - half), (BRACKET_X, y - half), (BRACKET_X, y - gap)], 0.3))
        out.append(("line", [(BRACKET_X, y + gap), (BRACKET_X, y + half), (BRACKET_X + SERIF, y + half)], 0.3))
    # IN k and CV k take IN k-1 and CV k-1 when unpatched: dotted normals between the nuts
    for row in (INPUTS, CVS):
        for a, b in zip(row, row[1:]):
            ax, ay = pos[a][2], pos[a][3]
            bx, by = pos[b][2], pos[b][3]
            out.append(("dots", [(ax + A["nut"] + 0.9, ay), (bx - A["nut"] - 0.9, by)]))
    return out


def row_words(pos):
    """(word, centre y, half height) of each row: the bracket spans the first column's knob scale with
    its ticks, or its jack nut."""
    return [("LEVEL", pos["RV1"][3], ART["scale"] + 1.0), ("CV AMT", pos["RV2"][3], ART["scale_s"] + 1.0),
            ("RESPONSE", pos["RV3"][3], ART["scale_s"] + 1.0),
            ("IN", pos[INPUTS[0]][3], ART["nut"]), ("CV", pos[CVS[0]][3], ART["nut"]),
            ("OUT", pos[OUTPUTS[0]][3], ART["nut"])]


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>Veilsy 12HP panel - artwork</title>',
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

    # -- bare copper: the output band, with a + between the outputs (an unpatched one adds into the next)
    s.append('<g id="copper">')
    for (bx, by, bw, bh, brx), cuts in bands(pos):
        s.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh:.2f}" rx="{brx}" class="copper"/>')
        for x, y, r in cuts:
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" class="cu-text"/>')
    for a, b in zip(OUTPUTS, OUTPUTS[1:]):
        text((pos[a][2] + pos[b][2]) / 2, pos[a][3] + 1.0, "+", 2.8, cls="cu-text")
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
            r = knob_radii(ref)[0]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="#2a2a2a" stroke="#000" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r * 0.62:.2f}" fill="#e8e8e4"/>')
            a = math.radians(MOCK_ANGLE.get(ref, 0))
            s.append(f'<line x1="{x + 0.3 * r * math.sin(a):.2f}" y1="{y - 0.3 * r * math.cos(a):.2f}" '
                     f'x2="{x + 0.95 * r * math.sin(a):.2f}" y2="{y - 0.95 * r * math.cos(a):.2f}" '
                     f'stroke="#555" stroke-width="{0.6 if r >= 5 else 0.5}" stroke-linecap="round"/>')
        elif kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["nut"]}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "led":
            lit = MOCK_LED.get(ref, 0.0)
            if lit > 0.05:
                s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.2" fill="{A["red"]}" opacity="{0.35 * lit:.2f}"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["led"]}" fill="#3a1512" stroke="#000" stroke-width="0.2"/>')
            if lit > 0.05:
                s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["led"]}" fill="{A["red"]}" opacity="{lit:.2f}"/>')
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Panel clearances: knob scales, jack nuts and LEDs must not touch each other or the edges;
    reports gaps under 1 mm."""
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    items = []
    for ref, (kind, label, x, y) in pos.items():
        r = {"pot": knob_radii(ref)[1] + 0.6, "jack": ART["nut"], "led": ART["led"] + 0.25}[kind]
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
    # the row brackets must not run into each other
    spans = []
    for word, y, h in row_words(pos):
        half = max(h, CHAR_W * ART["label"] * len(word) / 2 + BRACKET_GAP + BRACKET_MIN)
        spans.append((y - half, y + half, word))
    for (a0, a1, wa), (b0, b1, wb) in zip(spans, spans[1:]):
        if b0 - a1 < 1.0:
            bad.append(f"brackets {wa} - {wb}: {b0 - a1:.2f} mm")
    return bad


# ------------------------------------------------------------------ the board behind the panel
# One board carries the panel parts on its front. Before any PCB work, prove that the rows leave room for
# the parts' pads on the rear and their bodies on the front (panel frame, mm, y down; from parts.md):
#   jack   pads on the column line: sleeve 6.48 above the barrel, switch 3.38 above, tip 4.92 below,
#          r 1.0; body 9 x 10.5 from 4.51 above the barrel to 6.0 below
#   pot    pins down: three pins 2.5 mm apart 7.5 below the shaft, r 0.9; lugs on the shaft line at
#          +-4.8, r 1.5; housing 9.5 wide from 4.85 above the shaft to 6.5 below
#   LED    pads at +-1.27 on its row, r 0.8; body r 1.9 (the 3 mm LED's flange)
PAD_GAP = 1.0           # copper to copper between different parts' pads, so a track can pass
GND_GAP = 0.3           # between two ground pads (pot lugs side by side): no track needs to pass
BODY_GAP = 0.2


def pads_and_body(kind, x, y):
    """[(x, y, r, ground)] pads and the body box (x0, y0, x1, y1) of a panel part whose hole is at (x, y)."""
    if kind == "jack":
        pads = [(x, y - 6.48, 1.0, True), (x, y - 3.38, 1.0, False), (x, y + 4.92, 1.0, False)]
        return pads, (x - 4.5, y - 4.51, x + 4.5, y + 6.0)
    if kind == "pot":
        pads = [(x + dx, y + 7.5, 0.9, False) for dx in (-2.5, 0.0, 2.5)]
        pads += [(x - 4.8, y, 1.5, True), (x + 4.8, y, 1.5, True)]
        return pads, (x - 4.75, y - 4.85, x + 4.75, y + 6.5)
    if kind == "led":
        return [(x - 1.27, y, 0.8, False), (x + 1.27, y, 0.8, False)], (x - 1.9, y - 1.9, x + 1.9, y + 1.9)
    raise ValueError(kind)


def board_check(feats):
    """Pads of different panel parts at least PAD_GAP apart (GND_GAP between two ground pads), bodies
    BODY_GAP apart, everything on the board; returns the problems."""
    parts = [(ref, *pads_and_body(kind, *panel_xy(hx, hy))) for kind, ref, label, ox, oy, hx, hy in feats]
    bx0, by0 = circuit.BOARD_X0, PANEL_H - circuit.BOARD_Y0 - circuit.BOARD_H
    bx1, by1 = bx0 + circuit.BOARD_W, by0 + circuit.BOARD_H
    bad = []
    for i, (a, pa, ba) in enumerate(parts):
        for b, pb, bb in parts[i + 1:]:
            short = [(math.hypot(xa - xb, ya - yb) - ra - rb, GND_GAP if ga and gb else PAD_GAP)
                     for xa, ya, ra, ga in pa for xb, yb, rb, gb in pb]
            gap, need = min(short, key=lambda g: g[0] - g[1])
            if gap < need:
                bad.append(f"pads {a} - {b}: {gap:.2f} mm")
            dx = max(bb[0] - ba[2], ba[0] - bb[2])
            dy = max(bb[1] - ba[3], ba[1] - bb[3])
            if max(dx, dy) < BODY_GAP:
                bad.append(f"bodies {a} - {b}: {max(dx, dy):.2f} mm")
        for x, y, r, g in pa:
            if min(x - bx0, bx1 - x, y - by0, by1 - y) - r < 0.5:
                bad.append(f"pad of {a} at the board edge")
    return bad


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, f"{STEM}-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, f"{STEM}-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, f"{STEM}-panel.svg"))
    for b in check(feats):
        print("tight:", b)
    for b in board_check(feats):
        print("board:", b)
    print(f"{len(feats)} features + 4 mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
