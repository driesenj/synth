"""14HP panel for Ringsy: hole list (CSV), a 1:1 drill template (SVG) and
the panel artwork (SVG, as a PCB panel). Everything is computed from
PLACEMENT in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the faceplate board is seen from the
front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack    sleeve pad towards the top of the board; the barrel sits 0.78 mm
          below the WQP518MA footprint origin
  pot     Alpha 9 mm; the shaft is 4.0 mm from the PTV09A origin, away from
          the pins (circuit.pot_pins)
  button  Thonk low-profile LED button, 5.5 mm cap centred on the origin
  LED     3 mm bicolour, lens centred on the origin
Run from rings/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("rings_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 14HP
HP = circuit.HP
HOLE = {"pot": 7.5, "jack": 6.5, "ledbutton": 6.5, "led": 3.2}
JACK_BARREL = circuit.JACK_BARREL
POT_SHAFT = circuit.POT_SHAFT
OUT = os.path.join(HERE, "..", "panel")


def features():
    """[(kind, ref, label, origin_x, origin_y, hole_x, hole_y)] in board mm, y up."""
    labels = {r: lbl for r, lbl, *_ in circuit.JACKS + circuit.POTS + circuit.BUTTONS + circuit.LEDS}
    out = []
    for ref, (x, y, rot) in circuit.PLACEMENT.items():
        if ref.startswith("J"):
            out.append(("jack", ref, labels[ref], x, y, x, y + JACK_BARREL))
        elif ref.startswith("RV"):
            ux, uy = circuit.pot_pins(ref)
            out.append(("pot", ref, labels[ref], x, y, x - POT_SHAFT * ux, y - POT_SHAFT * uy))
        elif ref.startswith("SW"):
            out.append(("ledbutton", ref, labels[ref], x, y, x, y))
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
         '<title>Ringsy 14HP panel - drill template (print at 100%)</title>',
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
        if kind != "led":
            s.append(f'<text class="lbl" x="{x:.2f}" y="{y + d / 2 + 2.2:.2f}" text-anchor="middle">{label}</text>')
    s.append('<line x1="10" y1="-8" x2="60" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (10, 60):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="35" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Ringsy 14HP panel, front view. '
             'Red circles: final hole size. Dashed: the faceplate board.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the Marblesy style: black solder mask, white
# silkscreen, bare (ENIG) copper for the ODD / EVEN band (Rings' dark box).
# SVG groups: #copper, #tint (preview only: the LED colour each icon stands
# for), #silk, #holes and #mockup (knobs, nuts, caps, LEDs, preview only).
# Tune ART, run, look at rings-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227",
    "green": "#3fd17a", "yellow": "#f2b33d", "red": "#e0457b",   # Rings prints its icons in these three
    "knob": {"big": 7.5, "mid": 6.0, "att": 5.0},     # radii, mm: Plaitsy's knobs
    "scale": {"big": 9.0, "mid": 7.5},
    "ring": (10.9, 12.3),                             # the two dotted rings round the big knobs
    "cap_led": 2.75, "nut": 4.0, "led": 1.6, "icon": 1.5,
    "title": "Rings", "subtitle": "Resonator", "maker": "Seedable Instruments",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
}
SIZE = {ref: size for ref, _, size in circuit.POTS}
LABEL_SIZE = {"big": 2.7, "mid": 2.4, "jack": 2.2}
CHAR_W = 0.68                       # estimated advance per character (bold sans), x font size
OUTPUTS = ["J9", "J10"]
JACK_LABELS = {"J6": "STRUM", "J7": "V/OCT", "J8": "IN"}        # the five CV jacks are unlabelled, as on Rings
ATT_OF = {"RV3": "RV6", "RV1": "RV7", "RV4": "RV8", "RV2": "RV9", "RV5": "RV10"}   # knob -> its attenuverter
JACK_OF = {"RV6": "J1", "RV7": "J2", "RV8": "J3", "RV9": "J4", "RV10": "J5"}       # attenuverter -> CV jack
BAND_CLEAR = 0.4      # bare board (under black mask) between the copper band and a hole through it; DRC asks 0.3
# The six icons beside the LEDs, left to right in each group as on Rings: green, yellow, red. Polyphony
# (left of centre): 1, 2, 4 voices. Resonator (right): modal, sympathetic strings, string. Silk rings with
# the glyph in silk inside (silk cannot knock a glyph out of a solid disc, as Plaitsy's panel PCB found);
# glyphs in a 2.4 mm box round the centre, Plaitsy's primitives: ("path", d) with M L H V Q C Z only,
# ("circle", cx, cy, r, filled).
GLYPHS = {
    "poly1": [("circle", 0, 0, 0.42, True)],
    "poly2": [("circle", -0.5, 0, 0.32, True), ("circle", 0.5, 0, 0.32, True)],
    "poly4": [("circle", x, y, 0.27, True) for x in (-0.45, 0.45) for y in (-0.45, 0.45)],
    "modal": [("circle", 0, 0, 0.25, True), ("circle", 0, 0, 0.6, False), ("circle", 0, 0, 1.0, False)],
    "sympathetic": [("path", "M -0.75 -0.75 V 0.75 M -0.25 -1.0 V 1.0 M 0.25 -1.0 V 1.0 M 0.75 -0.75 V 0.75")],
    "string": [("path", "M 0 -1.05 V 1.05 M -0.6 -0.9 Q -1.05 0 -0.6 0.9 M 0.6 -0.9 Q 1.05 0 0.6 0.9")],
}
ICONS = [("D1", ["poly1", "poly2", "poly4"], +1), ("D2", ["modal", "sympathetic", "string"], -1)]
ICON_COLOURS = ["green", "yellow", "red"]
ICON_FIRST, ICON_PITCH = 4.6, 4.0   # from the LED to the nearest icon centre, then icon to icon (Rings: 4.6 / 4.0)
# preview only: knob pointers (degrees from 12 o'clock) and the LED colours (both green after a reset:
# one voice, modal resonator)
MOCK_ANGLE = {"RV1": -40, "RV2": 25, "RV3": 50, "RV4": -20, "RV5": 70}
MOCK_LED = {"D1": "green", "D2": "green"}


def icon_xy(pos):
    """[(x, y, glyph, colour)] of the six icons, panel frame."""
    out = []
    for led, glyphs, side in ICONS:
        lx, ly = pos[led][2], pos[led][3]
        xs = [lx + side * (ICON_FIRST + ICON_PITCH * k) for k in range(3)]
        for x, g, c in zip(sorted(xs), glyphs, ICON_COLOURS):
            out.append((x, ly, g, c))
    return out


def band(pos):
    """The bare-copper ODD / EVEN band, (x, y, w, h, rx) from its top-left in the panel frame, and the
    holes through it as clearance circles (x, y, r): copper and mask opening both leave them out."""
    ox, ex, jy = pos[OUTPUTS[0]][2], pos[OUTPUTS[1]][2], pos[OUTPUTS[0]][3]
    x, y, w, h = ox - 4.8, jy - 8.8, ex - ox + 9.6, 14.6
    cuts = []
    for kind, label, hx, hy in pos.values():
        r = HOLE[kind] / 2 + BAND_CLEAR
        if x - r < hx < x + w + r and y - r < hy < y + h + r:
            if not (x + r < hx < x + w - r and y + r < hy < y + h - r):
                raise ValueError(f"the hole at ({hx:.2f}, {hy:.2f}) crosses the edge of the output band")
            cuts.append((hx, hy, r))
    return (x, y, w, h, 1.4), cuts


def _arc(cx, cy, r, a0, a1):
    """SVG path of an arc from angle a0 to a1 (degrees, clockwise from 12 o'clock)."""
    p0 = (cx + r * math.sin(math.radians(a0)), cy - r * math.cos(math.radians(a0)))
    p1 = (cx + r * math.sin(math.radians(a1)), cy - r * math.cos(math.radians(a1)))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M {p0[0]:.2f} {p0[1]:.2f} A {r} {r} 0 {large} 1 {p1[0]:.2f} {p1[1]:.2f}"


def arc_points(cx, cy, r, a0, a1, step=3.0):
    n = max(2, int(abs(a1 - a0) / step) + 1)
    return [(cx + r * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1))),
             cy - r * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1)))) for i in range(n)]


def cubic_points(p0, p1, p2, p3, n=16):
    return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
                  for a, b, c, d in zip(p0, p1, p2, p3)) for t in (i / n for i in range(n + 1))]


def label_xy(pos, ref):
    """Where a big or medium knob's label sits (baseline centre, panel mm)."""
    kind, label, x, y = pos[ref]
    return x, y + ART["scale"][SIZE[ref]] + 3.0


def att_top(pos, att):
    """Top of an attenuverter's noon tick, which the guides from the knob labels end on."""
    return pos[att][3] - ART["knob"]["att"] - 2.3


def layout(pos):
    """Everything the artwork and (later) the panel PCB draw on the silk, in one list:
    ("text", x, y, s, size, anchor), ("serif", x, y, s, size, anchor), ("line", pts, w), ("dots", pts),
    ("arc", cx, cy, r, a0, a1, w), ("icon", x, y, glyph)."""
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
    # the polyphony and resonator icons beside the LEDs
    for x, y, g, c in icon_xy(pos):
        out.append(("icon", x, y, g))
    # big and medium knobs: scale arcs with ticks and the label underneath; the big ones get Rings'
    # ornament as two dotted rings
    for ref, (kind, label, x, y) in pos.items():
        if kind != "pot" or SIZE[ref] == "att":
            continue
        size = SIZE[ref]
        r = A["scale"][size]
        out.append(("arc", x, y, r, -135, 135, 0.3))
        n = {"big": 11, "mid": 7}[size]
        for i in range(n):
            a = math.radians(-135 + 270 * i / (n - 1))
            r1 = r + (1.2 if i in (0, n - 1, (n - 1) // 2) else 0.7)
            out.append(("line", [(x + r * math.sin(a), y - r * math.cos(a)),
                                 (x + r1 * math.sin(a), y - r1 * math.cos(a))], 0.3))
        if size == "big":
            for rr in A["ring"]:
                out.append(("dots", arc_points(x, y, rr, -135, 135)))
        lx, ly = label_xy(pos, ref)
        text(lx, ly, label, LABEL_SIZE[size])
    # attenuverters: a noon tick between - and +, as on Rings
    for ref, (kind, label, x, y) in pos.items():
        if kind != "pot" or SIZE[ref] != "att":
            continue
        top = y - A["knob"]["att"]
        out.append(("line", [(x, top - 0.5), (x, att_top(pos, ref))], 0.35))
        text(x - 2.6, top - 0.9, "–", 2.2)
        text(x + 2.6, top - 0.9, "+", 2.2)
    # dotted guides: FREQUENCY and STRUCTURE labels curve down to their attenuverters (the medium knobs'
    # sit right under their labels), every attenuverter drops to its CV jack
    for knob, side in (("RV1", 1), ("RV2", -1)):
        lx, ly = label_xy(pos, knob)
        ax = pos[ATT_OF[knob]][2]
        sx, sy = lx + side * 1.4, ly + 1.7
        bend = sy + 9.0
        out.append(("dots", cubic_points((sx, sy), (sx, sy + 4.5), (ax, bend - 4.5), (ax, bend))
                    + [(ax, att_top(pos, ATT_OF[knob]) - 0.7)]))
    for att, jack in JACK_OF.items():
        x, y = pos[att][2], pos[att][3]
        out.append(("dots", [(x, y + A["knob"]["att"] + 0.9), (x, pos[jack][3] - A["nut"] - 0.9)]))
    # the input jacks' labels
    for jack, word in JACK_LABELS.items():
        text(pos[jack][2], pos[jack][3] - A["nut"] - 1.6, word, LABEL_SIZE["jack"])
    return out


def copper_layout(pos):
    """What is knocked out of the copper band (drawn in the panel colour): the output labels and the
    dotted normal between ODD and EVEN (an unpatched EVEN is mixed into ODD)."""
    A = ART
    out = []
    jy = pos[OUTPUTS[0]][3]
    for ref in OUTPUTS:
        out.append(("text", pos[ref][2], jy - A["nut"] - 1.6, pos[ref][1], LABEL_SIZE["jack"], "middle"))
    out.append(("dots", [(pos[OUTPUTS[0]][2] + A["nut"] + 0.9, jy), (pos[OUTPUTS[1]][2] - A["nut"] - 0.9, jy)]))
    return out


def glyph_svg(name, colour):
    """The glyph's primitives as SVG elements (inside a translated group)."""
    out = []
    for item in GLYPHS[name]:
        if item[0] == "path":
            out.append(f'<path d="{item[1]}"/>')
        else:
            _, cx, cy, r, filled = item
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}"' + (f' fill="{colour}"' if filled else "") + '/>')
    return "".join(out)


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>Ringsy 14HP panel - artwork</title>',
         f'<style>text{{font-family:{A["font"]};font-weight:bold;fill:{A["silk"]}}} '
         f'.serif{{font-family:{A["serif"]};font-style:italic;font-weight:normal}} '
         f'.silk{{stroke:{A["silk"]};fill:none;stroke-linecap:round;stroke-linejoin:round}} '
         f'.dots{{stroke-dasharray:0.1 1.0;stroke-width:0.45}} '
         f'.copper{{fill:{A["copper"]}}} .cu-text{{fill:{A["panel"]}}} '
         f'.cu-dots{{stroke:{A["panel"]};fill:none;stroke-linecap:round;stroke-dasharray:0.1 1.0;stroke-width:0.45}} '
         '.hole{fill:#ffffff;stroke:none}</style>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="{A["panel"]}"/>']
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}

    def text(x, y, t, size, anchor="middle", cls="", colour=None):
        c = f' class="{cls}"' if cls else ""
        st = f' style="fill:{colour}"' if colour else ""
        s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}"{c}{st}>{t}</text>')

    def polyline(pts, cls, extra=""):
        s.append('<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + f'" class="{cls}"{extra}/>')

    # -- bare copper: the ODD / EVEN band, its labels and the normal knocked out
    s.append('<g id="copper">')
    (bx, by, bw, bh, brx), cuts = band(pos)
    s.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh:.2f}" rx="{brx}" class="copper"/>')
    for x, y, r in cuts:                  # copper clearance round the holes, under black mask
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" class="cu-text"/>')
    for item in copper_layout(pos):
        if item[0] == "text":
            _, x, y, t, size, anchor = item
            text(x, y, t, size, anchor, cls="cu-text")
        else:
            polyline(item[1], "cu-dots")
    s.append('</g>')
    # -- preview tint: the LED colour each icon stands for (the real silk is one colour)
    s.append('<g id="tint">')
    for x, y, g, c in icon_xy(pos):
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["icon"]:.2f}" fill="{A[c]}" opacity="0.6"/>')
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
            polyline(pts, "silk", f' stroke-width="{w}"')
        elif kind == "dots":
            polyline(item[1], "silk dots")
        elif kind == "arc":
            _, x, y, r, a0, a1, w = item
            s.append(f'<path d="{_arc(x, y, r, a0, a1)}" class="silk" stroke-width="{w}"/>')
        elif kind == "icon":
            _, x, y, g = item
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["icon"]}" class="silk" stroke-width="0.3"/>')
            s.append(f'<g transform="translate({x:.2f} {y:.2f})" stroke="{A["silk"]}" fill="none" stroke-width="0.25" '
                     f'stroke-linecap="round" stroke-linejoin="round">' + glyph_svg(g, A["silk"]) + '</g>')
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
            r = A["knob"][SIZE[ref]]
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
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["cap_led"]}" fill="#2b2b2b" stroke="#000" stroke-width="0.4"/>')
        elif kind == "led":
            col = A[MOCK_LED[ref]]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.0" fill="{col}" opacity="0.3"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["led"]}" fill="{col}" stroke="#000" stroke-width="0.2"/>')
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Panel clearances: knob scales and rings, nuts, caps, LEDs and icons must not touch each other or
    the edges, and the knob labels must clear the knobs below them; reports gaps under 1 mm."""
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    items = []
    for ref, (kind, label, x, y) in pos.items():
        if kind == "pot":
            size = SIZE[ref]
            r = {"big": ART["ring"][1] + 0.3, "mid": ART["scale"]["mid"] + 1.2, "att": ART["knob"]["att"]}[size]
        else:
            r = {"jack": ART["nut"], "ledbutton": HOLE["ledbutton"] / 2, "led": ART["led"]}[kind]
        items.append((ref, x, y, r))
    items += [(f"icon {g}", x, y, ART["icon"]) for x, y, g, c in icon_xy(pos)]
    bad = []
    for i, (a, xa, ya, ra) in enumerate(items):
        for b, xb, yb, rb in items[i + 1:]:
            gap = math.hypot(xa - xb, ya - yb) - ra - rb
            if gap < 1.0:
                bad.append(f"{a} - {b}: {gap:.2f} mm")
        edge = min(xa, PANEL_W - xa) - ra
        if edge < 2.0:
            bad.append(f"{a} - panel edge: {edge:.2f} mm")
    # labels: estimated box under each big / medium knob against every round item
    for ref in SIZE:
        if SIZE[ref] == "att":
            continue
        lx, ly = label_xy(pos, ref)
        size = LABEL_SIZE[SIZE[ref]]
        half = CHAR_W * size * len(pos[ref][1]) / 2
        x0, x1, y0, y1 = lx - half, lx + half, ly - 0.75 * size, ly + 0.2 * size
        if x0 < 1.5 or x1 > PANEL_W - 1.5:
            bad.append(f"{pos[ref][1]} label - panel edge")
        for b, xb, yb, rb in items:
            if b == ref:
                continue
            dx = max(x0 - xb, 0, xb - x1)
            dy = max(y0 - yb, 0, yb - y1)
            gap = math.hypot(dx, dy) - rb
            if gap < 1.0:
                bad.append(f"{pos[ref][1]} label - {b}: {gap:.2f} mm")
    return bad


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, "rings-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "rings-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "rings-panel.svg"))
    for b in check(feats):
        print("tight:", b)
    print(f"{len(feats)} features + 4 mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
