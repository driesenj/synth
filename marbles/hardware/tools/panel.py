"""18HP panel for Marblesy: hole list (CSV), a 1:1 drill template (SVG), the
panel artwork (SVG, as a PCB panel) and the faceplate footprint origins.
Everything is computed from PLACEMENT in circuit.py, so board and panel agree.

Conventions (the same as the Plaitsy PCB): the faceplate board is seen from
the front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack   angle 0, sleeve pad towards the top of the board; the barrel sits
         6.48 mm from the sleeve pad towards the tip pad (KiCad PJ398SM),
         i.e. 0.78 mm below the footprint origin of the WQP518MA footprint
  pot    angle 90, pins towards -x; the shaft is 7.5 mm from the pin row,
         the PTV09A footprint origin is 6.97 mm from it: shaft = origin + 0.53 in x
  LED    3-lead LED in the generated LED-3MM-3P footprint: body centred on the origin
  switch 6 x 6 mm tactile or Thonk LED button, cap centred on the origin; hole = cap + 1 mm
Run from marbles/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("marbles_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

PANEL_W, PANEL_H = 91.3, 128.5          # Eurorack 3U, 18HP
BOARD_X0 = (PANEL_W - circuit.BOARD_W) / 2
BOARD_Y0 = (PANEL_H - circuit.BOARD_H) / 2   # board centred on the panel; move it if your rails need it
# hole diameters; buttons: cap diameter + 1 mm (6 mm caps; the Thonk LED button has a 5.5 mm cap)
HOLE = {"pot": 7.5, "jack": 6.5, "led": 3.2, "button": 7.0, "ledbutton": 6.5, "mount": 3.2}
JACK_BARREL = -0.78
POT_SHAFT = 0.53
OUT = os.path.join(HERE, "..", "panel")


def features():
    """[(kind, ref, label, origin_x, origin_y, hole_x, hole_y)] in board mm, y up."""
    labels = {r: lbl for r, lbl, *_ in circuit.JACKS}
    labels.update({r: lbl for r, lbl, *_ in circuit.POTS})
    labels.update({r: lbl for r, lbl, *_ in circuit.BUTTONS})
    labels.update({r: lbl for r, lbl, *_ in circuit.LEDS})
    out = []
    for ref, (x, y, rot) in circuit.PLACEMENT.items():
        if ref.startswith("J"):
            out.append(("jack", ref, labels[ref], x, y, x, y + JACK_BARREL))
        elif ref.startswith("RV"):
            out.append(("pot", ref, labels[ref], x, y, x + POT_SHAFT, y))
        elif ref.startswith("SW"):
            out.append(("ledbutton", ref, labels[ref], x, y, x, y))
        elif ref.startswith("D"):
            out.append(("led", ref, labels[ref], x, y, x, y))
    return out


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return BOARD_X0 + bx, PANEL_H - (BOARD_Y0 + by)


MOUNTS = [(x, y) for x in (7.5, PANEL_W - 7.5) for y in (3.0, PANEL_H - 3.0)]


def write_csv(feats, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "ref", "label", "board_origin_x", "board_origin_y", "panel_x_from_left",
                    "panel_y_from_top", "hole_mm"])
        for kind, ref, label, ox, oy, hx, hy in feats:
            px, py = panel_xy(hx, hy)
            w.writerow([kind, ref, label, f"{ox:.2f}", f"{oy:.2f}", f"{px:.2f}", f"{py:.2f}", HOLE[kind]])
        for x, y in MOUNTS:
            w.writerow(["mount", "", "mounting", "", "", f"{x:.2f}", f"{y:.2f}", HOLE["mount"]])


def write_svg(feats, path):
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 40}mm" height="{H + 30}mm" '
         f'viewBox="-20 -15 {W + 40} {H + 30}">',
         '<title>Marblesy 18HP panel - drill template (print at 100%)</title>',
         '<style>text{font-family:Arial,Helvetica,sans-serif} .dim{font-size:1.6px;fill:#444} '
         '.lbl{font-size:2px;fill:#06c}</style>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.25"/>',
         f'<rect x="{BOARD_X0:.2f}" y="{PANEL_H - BOARD_Y0 - circuit.BOARD_H:.2f}" width="{circuit.BOARD_W}" '
         f'height="{circuit.BOARD_H}" fill="none" stroke="#999" stroke-width="0.15" stroke-dasharray="1,1"/>']
    rows = [(k, lbl, *panel_xy(hx, hy)) for k, ref, lbl, ox, oy, hx, hy in feats]
    rows += [("mount", "", x, y) for x, y in MOUNTS]
    for kind, label, x, y in rows:
        d = HOLE[kind]
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{d / 2:.2f}" fill="none" stroke="#c00" stroke-width="0.2"/>')
        s.append(f'<line x1="{x - 1.5:.2f}" y1="{y:.2f}" x2="{x + 1.5:.2f}" y2="{y:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<line x1="{x:.2f}" y1="{y - 1.5:.2f}" x2="{x:.2f}" y2="{y + 1.5:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<text class="dim" x="{x + d / 2 + 0.5:.2f}" y="{y - d / 2 - 0.3:.2f}">Ø{d}</text>')
        if label:
            s.append(f'<text class="lbl" x="{x:.2f}" y="{y + d / 2 + 2.4:.2f}" text-anchor="middle">{label}</text>')
    s.append('<line x1="5" y1="-8" x2="55" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (5, 55):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="30" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Marblesy 18HP panel, front view. '
             'Red circles: final hole size. Dashed: the faceplate board. Button holes suit 6 mm caps and the Thonk LED button; '
             'check yours.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB: black solder mask, white silkscreen, bare (ENIG) copper
# for the output band. SVG groups: #silk, #copper, #holes and #mockup (knobs,
# nuts, caps and LEDs, preview only). Tune ART, run, look at marbles-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227",
    "knob_big": 7.5, "scale_big": 9.0, "knob_small": 5.0, "scale_small": 6.3,   # radii, mm
    "cap": 2.9, "cap_led": 2.75, "nut": 4.0, "led": 1.6,
    "title": "Marbles", "subtitle": "Random sampler", "maker": "Seedable Instruments",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
}
BIG_POTS = {"RV1", "RV4", "RV6"}
OUTPUTS = ["J9", "J10", "J11", "J16", "J13", "J14", "J15"]
OUT_LABELS = {"J9": ("t", "1"), "J10": ("t", "2"), "J11": ("t", "3"), "J16": ("Y", ""), "J13": ("X", "1"),
              "J14": ("X", "2"), "J15": ("X", "3")}
KNOB_TO_JACK = {"RV1": "J2", "RV3": "J4", "RV8": "J8", "RV6": "J6", "RV2": "J3", "RV7": "J7"}   # dotted guides
# labels printed beside the bipolar buttons, in press order (green, orange, red)
MODE_LABELS = {"SW2": ("COIN", "RATIO", "DRUMS"), "SW3": ("\u00f74", "\u00d71", "\u00d74"),
               "SW6": ("+2", "+5", "\u00b15")}
LABEL_COLOURS = ("#4bd36a", "#f0a030", "#e04040")
LENGTHS = ("1", "2", "3", "4", "6", "8", "12", "16")


def _arc(cx, cy, r, a0, a1):
    """SVG path of an arc from angle a0 to a1 (degrees, clockwise from 12 o'clock)."""
    p0 = (cx + r * math.sin(math.radians(a0)), cy - r * math.cos(math.radians(a0)))
    p1 = (cx + r * math.sin(math.radians(a1)), cy - r * math.cos(math.radians(a1)))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M {p0[0]:.2f} {p0[1]:.2f} A {r} {r} 0 {large} 1 {p1[0]:.2f} {p1[1]:.2f}"


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>Marblesy 18HP panel - artwork</title>',
         f'<style>text{{font-family:{A["font"]};font-weight:bold;fill:{A["silk"]}}} '
         f'.serif{{font-family:{A["serif"]};font-style:italic;font-weight:normal}} '
         f'.silk{{stroke:{A["silk"]};fill:none;stroke-linecap:round}} .dots{{stroke-dasharray:0.1 1.0;stroke-width:0.45}} '
         f'.copper{{fill:{A["copper"]}}} .cu-text{{fill:{A["panel"]}}} .hole{{fill:#ffffff;stroke:none}}</style>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="{A["panel"]}"/>']
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}

    def text(x, y, t, size, anchor="middle", cls="", extra="", colour=None):
        c = f' class="{cls}"' if cls else ""
        st = f' style="fill:{colour}"' if colour else ""
        s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}"{c}{st}{extra}>{t}</text>')

    def led_dot(x, y, colour):
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="0.8" fill="{colour}"/>')

    def dots(pts):
        s.append('<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + '" class="silk dots"/>')

    def label_below(ref):
        kind, label, x, y = pos[ref]
        r = A["scale_big"] if ref in BIG_POTS else A["scale_small"]
        return x, y + r + 3.0

    # -- silkscreen
    s.append('<g id="silk">')
    text(12.0, 7.4, A["title"], 5.2, anchor="start", cls="serif")            # between the screw and the centre
    text(W - 12.0, 6.6, A["subtitle"], 2.4, anchor="end")
    text(W / 2, 121.9, A["maker"], 2.4)
    s.append(f'<line x1="3" y1="9.6" x2="{W - 3}" y2="9.6" class="silk dots"/>')   # band under the title
    s.append(f'<line x1="3" y1="10.6" x2="{W - 3}" y2="10.6" class="silk dots"/>')
    text(pos["SW1"][2] - A["cap_led"] - 4.6, pos["SW1"][3] + 2.2, "t", 7.0, cls="serif")
    text(pos["SW4"][2] + A["cap_led"] + 4.6, pos["SW4"][3] + 2.2, "X", 7.0, cls="serif")
    for sw in ("SW1", "SW4"):            # ring around the deja vu buttons, as on Marbles
        s.append(f'<circle cx="{pos[sw][2]:.2f}" cy="{pos[sw][3]:.2f}" r="{A["cap_led"] + 1.6:.2f}" '
                 f'class="silk" stroke-width="0.35"/>')
    # three-state labels beside the bipolar buttons (coloured here; one colour on a silkscreen)
    def labels_above(sw, words):
        x, y = pos[sw][2], pos[sw][3]
        for i, w in enumerate(words):
            yy = y - A["cap_led"] - 9.4 + 3.4 * i
            led_dot(x - 4.6, yy - 0.6, LABEL_COLOURS[i])
            text(x + 0.6, yy, w, 1.7, colour=LABEL_COLOURS[i])

    def labels_beside(sw, words, side):
        x, y = pos[sw][2], pos[sw][3]
        for i, w in enumerate(words):
            x0, yy = x + side * (A["cap_led"] + 1.6), y - 3.9 + 3.4 * i
            led_dot(x0 + side * 0.8, yy - 0.6, LABEL_COLOURS[i])
            text(x0 + side * 2.4, yy, w, 1.7, anchor="start" if side > 0 else "end", colour=LABEL_COLOURS[i])

    labels_above("SW2", MODE_LABELS["SW2"])
    labels_beside("SW3", MODE_LABELS["SW3"], 1)
    labels_beside("SW6", MODE_LABELS["SW6"], -1)
    # X mode: three small bar icons (all channels alike / X2 centre with X1, X3 opposite / X1 low, X2 mid, X3 high)
    x, y0 = pos["SW5"][2], pos["SW5"][3] - A["cap_led"] - 10.6
    for i, bars in enumerate(((2, 2, 2), (2.6, 1.2, 2.6), (1.0, 1.8, 2.6))):
        y = y0 + 3.4 * i
        led_dot(x - 4.0, y + 0.6, LABEL_COLOURS[i])
        for j, h in enumerate(bars):
            bx = x - 0.7 + 1.3 * j
            s.append(f'<line x1="{bx:.2f}" y1="{y + 1.3:.2f}" x2="{bx:.2f}" y2="{y + 1.3 - h:.2f}" '
                     f'stroke="{LABEL_COLOURS[i]}" stroke-width="0.55" stroke-linecap="round"/>')
    # LENGTH graduations
    lx, ly = pos["RV5"][2], pos["RV5"][3]
    for i, n in enumerate(LENGTHS):
        a = math.radians(-135 + 270 * i / 7)
        text(lx + 8.6 * math.sin(a), ly - 8.6 * math.cos(a) + 0.6, n, 1.5)
    # STEPS: smooth curve (CCW), S&H steps (12 o'clock), quantized steps (CW); JITTER: steady / random
    sx, sy = pos["RV8"][2], pos["RV8"][3]
    s.append(f'<path d="M {sx - 9.6:.2f} {sy + 7.8:.2f} h 1.0 c 1.0 0 0.6 -2.0 1.6 -2.0 h 1.0" class="silk" stroke-width="0.4"/>')
    s.append(f'<path d="M {sx - 1.8:.2f} {sy - 8.0:.2f} h 0.9 v -0.9 h 0.9 v -0.9 h 0.9 v -0.9 h 0.9" class="silk" stroke-width="0.4"/>')
    s.append(f'<path d="M {sx + 5.6:.2f} {sy + 7.6:.2f} h 1.2 v -1.6 h 1.2 v -1.6 h 1.2" class="silk" stroke-width="0.4"/>')
    jx, jy = pos["RV3"][2], pos["RV3"][3]
    s.append(f'<path d="M {jx - 9.2:.2f} {jy + 7.2:.2f} h 3.4" class="silk" stroke-width="0.4"/>')
    s.append(f'<path d="M {jx + 5.8:.2f} {jy + 7.6:.2f} l 0.6 -2.2 l 0.7 1.6 l 0.6 -2.4 l 0.7 1.8 l 0.8 -1.2" class="silk" stroke-width="0.4"/>')
    for ref, (kind, label, x, y) in pos.items():
        if kind == "pot":
            big = ref in BIG_POTS
            r = A["scale_big"] if big else A["scale_small"]
            s.append(f'<path d="{_arc(x, y, r, -135, 135)}" class="silk" stroke-width="0.3"/>')
            n = 11 if big else 5
            for i in range(n):
                a = math.radians(-135 + 270 * i / (n - 1))
                r1 = r + (1.2 if i in (0, n - 1, (n - 1) // 2) else 0.7)
                s.append(f'<line x1="{x + r * math.sin(a):.2f}" y1="{y - r * math.cos(a):.2f}" '
                         f'x2="{x + r1 * math.sin(a):.2f}" y2="{y - r1 * math.cos(a):.2f}" class="silk" stroke-width="0.3"/>')
            lab = {"BIAS (t)": "BIAS", "BIAS (X)": "BIAS"}.get(label, label)
            lx, ly = label_below(ref)
            text(lx, ly, lab, 2.7 if big else 2.4)
    # dotted guides from a knob's label down to its CV jack
    for pot, jack in KNOB_TO_JACK.items():
        lx, ly = label_below(pot)
        jx, jy = pos[jack][2], pos[jack][3]
        top = jy - A["nut"] - 0.9
        if abs(jx - lx) < 0.3:
            dots([(lx, ly + 1.2), (lx, top)])
        else:
            dots([(lx, ly + 1.2), (lx, ly + 3.5), (jx, ly + 6.0), (jx, top)])
    # button words
    for sw, word in (("SW2", "MODE"), ("SW5", "MODE"), ("SW3", "RANGE"), ("SW6", "RANGE"), ("SW7", "EXT")):
        x, y = pos[sw][2], pos[sw][3]
        text(x, y + A["cap_led"] + 2.6, word, 1.8)
    # jack labels: CLOCK over the clock jacks, DEJA VU over its CV jack (its knob is far away)
    for jack in ("J1", "J12"):
        text(pos[jack][2], pos[jack][3] - A["nut"] - 1.6, "CLOCK", 2.2)
    text(pos["J5"][2], pos["J5"][3] - A["nut"] - 1.6, "DEJA VU", 2.2)
    s.append('</g>')
    # -- bare copper: the output band with its labels knocked out
    s.append('<g id="copper">')
    jy = pos["J9"][3]
    s.append(f'<rect x="3.6" y="{jy - 8.6:.2f}" width="{W - 7.2:.2f}" height="14.4" rx="1.4" class="copper"/>')
    for ref in OUTPUTS:
        x = pos[ref][2]
        main, sub = OUT_LABELS[ref]
        t = main + (f'<tspan font-size="2.1" dy="0.9">{sub}</tspan>' if sub else "")
        text(x, jy - A["nut"] - 1.2, t, 3.4, cls="serif cu-text")
    s.append('</g>')
    # -- holes
    s.append('<g id="holes">')
    for ref, (kind, label, x, y) in pos.items():
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{HOLE[kind] / 2:.2f}" class="hole"/>')
    for x, y in MOUNTS:
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{HOLE["mount"] / 2:.2f}" class="hole"/>')
    s.append('</g>')
    # -- mockup of the fitted parts (preview only)
    s.append('<g id="mockup">')
    for ref, (kind, label, x, y) in pos.items():
        if kind == "pot":
            r = A["knob_big"] if ref in BIG_POTS else A["knob_small"]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="#2a2a2a" stroke="#000" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r * 0.62:.2f}" fill="#e8e8e4"/>')
            a = math.radians(-135)
            s.append(f'<line x1="{x + 0.3 * r * math.sin(a):.2f}" y1="{y - 0.3 * r * math.cos(a):.2f}" '
                     f'x2="{x + 0.95 * r * math.sin(a):.2f}" y2="{y - 0.95 * r * math.cos(a):.2f}" '
                     f'stroke="#555" stroke-width="0.6" stroke-linecap="round"/>')
        elif kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["nut"]}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "ledbutton":
            col = "#9ccc3c" if ref in ("SW1", "SW4", "SW7") else "#e8c060"
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["cap_led"]}" fill="{col}" stroke="#1a1a1a" stroke-width="0.4"/>')
        elif kind == "button":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["cap"]}" fill="#1d1f1e" stroke="#444" stroke-width="0.3"/>')
        elif kind == "led":
            col = "#e0b03a" if ref in ("D2", "D3", "D5", "D6") else "#4bd36a"
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["led"]}" fill="{col}" opacity="0.9"/>')
    for x, y in MOUNTS:
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, "marbles-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "marbles-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "marbles-panel.svg"))
    print(f"{len(feats)} features + 4 mounting holes written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
