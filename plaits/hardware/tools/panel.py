"""12HP panel for Plaitsy: hole list (CSV), a 1:1 drill template (SVG) and
the panel artwork (SVG, as a PCB panel). Everything is computed from
PLACEMENT in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the faceplate board is seen from the
front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack   angle 0, sleeve pad towards the top of the board; the barrel sits
         0.78 mm below the WQP518MA footprint origin
  pot    angle 90, pins towards -x; the shaft is 0.53 mm from the PTV09A
         origin, away from the pins
  LED    3 mm bicolour LED, body centred on the origin
  button Thonk low-profile LED button, 5.5 mm cap centred on the origin
Run from plaits/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("plaits_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 12HP
HP = 12
BOARD_X0 = (PANEL_W - circuit.BOARD_W) / 2
BOARD_Y0 = (PANEL_H - circuit.BOARD_H) / 2   # board centred on the panel
# hole diameters; the Thonk LED button has a 5.5 mm cap
HOLE = {"pot": 7.5, "jack": 6.5, "led": 3.2, "ledbutton": 6.5, "mount": 3.2}
JACK_BARREL = circuit.JACK_BARREL
POT_SHAFT = circuit.POT_SHAFT
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
         '<title>Plaitsy 12HP panel - drill template (print at 100%)</title>',
         '<style>text{font-family:Arial,Helvetica,sans-serif} .dim{font-size:1.6px;fill:#444} '
         '.lbl{font-size:2px;fill:#06c}</style>',
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
        s.append(f'<text class="dim" x="{x + d / 2 + 0.5:.2f}" y="{y - d / 2 - 0.3:.2f}">Ø{d}</text>')
        if label and kind != "led":
            s.append(f'<text class="lbl" x="{x:.2f}" y="{y + d / 2 + 2.4:.2f}" text-anchor="middle">{label}</text>')
    s.append('<line x1="5" y1="-8" x2="55" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (5, 55):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="30" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Plaitsy 12HP panel, front view. '
             'Red circles: final hole size. Dashed: the faceplate board. Button holes suit the Thonk LED button.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the Marblesy style: black solder mask, white
# silkscreen, bare (ENIG) copper for the OUT / AUX band. SVG groups: #tint
# (preview only: the bank colours of the model icons), #silk, #copper,
# #holes and #mockup (knobs, nuts, caps and LEDs, preview only). Tune ART,
# run, look at plaits-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227",
    "knob": {"big": 7.5, "mid": 6.0, "small": 5.0},      # radii, mm: FREQUENCY/HARMONICS, TIMBRE/MORPH, attenuverters
    "scale": {"big": 9.0, "mid": 7.5, "small": 6.3},
    "cap_led": 2.75, "nut": 4.0, "led": 1.6, "icon": 1.7,
    "title": "Plaits", "subtitle": "Macro-oscillator", "maker": "Seedable Instruments",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
    "green": "#3fb95a", "red": "#d94040",                 # the two LED banks (preview tint of the icon discs)
}
KNOB_SIZE = {"RV1": "big", "RV2": "big", "RV3": "mid", "RV4": "mid", "RV5": "small", "RV6": "small", "RV7": "small"}
OUTPUTS = ["J9", "J10"]
JACK_LABELS = {"J1": "MODEL", "J5": "HARMO", "J6": "TRIG", "J7": "LEVEL", "J8": "V/OCT"}
ATT_TO_JACK = {"RV5": "J2", "RV6": "J3", "RV7": "J4"}          # dotted guides attenuverter -> CV jack
KNOB_TO_ATT = {"RV3": "RV5", "RV4": "RV7"}                      # dotted guides TIMBRE / MORPH -> attenuverter
# The sixteen model icons beside the LEDs: green bank left (filled disc, glyph
# knocked out), red bank right (ring, white glyph). Glyphs are drawn in a
# 2.4 mm box around the disc centre; {c} is the glyph colour.
GLYPHS = {
    "va": '<path d="M -1.1 0 C -0.8 -1.4 -0.3 -1.4 0 0 S 0.8 1.4 1.1 0"/>',
    "fold": '<path d="M -1.1 0.7 L -0.55 -0.7 L 0 0.7 L 0.55 -0.7 L 1.1 0.7"/>',
    "fm": '<text x="0" y="0.42" font-size="1.2" text-anchor="middle" style="fill:{c}" stroke="none">FM</text>',
    "formant": '<path d="M -1.1 0.6 Q -0.65 -1.1 -0.2 0.6 Q 0.2 -0.5 0.5 0.6 Q 0.75 0.05 1.1 0.6"/>',
    "harmonic": '<path d="M -0.8 0.8 V -0.9 M 0 0.8 V -0.3 M 0.8 0.8 V 0.2"/>',
    "wavetable": '<path d="M -0.9 -0.35 H 0.9 M -0.9 0.35 H 0.9 M -0.35 -0.9 V 0.9 M 0.35 -0.9 V 0.9"/>',
    "chord": '<circle cx="0" cy="-0.75" r="0.3" fill="{c}"/><circle cx="0" cy="0" r="0.3" fill="{c}"/>'
             '<circle cx="0" cy="0.75" r="0.3" fill="{c}"/>',
    "speech": '<path d="M -1.0 -0.9 H 1.0 V 0.3 H -0.1 L -0.6 0.9 V 0.3 H -1.0 Z"/>',
    "cloud": '<path d="M -0.9 0.6 H 0.75 A 0.45 0.45 0 0 0 0.6 -0.3 A 0.6 0.6 0 0 0 -0.5 -0.4 '
             'A 0.5 0.5 0 0 0 -0.9 0.6 Z"/>',
    "noise": '<path d="M -1.0 0.8 V 0.2 M -0.6 0.8 V -0.7 M -0.2 0.8 V -0.1 M 0.2 0.8 V -0.9 M 0.6 0.8 V 0.3 '
             'M 1.0 0.8 V -0.4"/>',
    "particle": "".join(f'<circle cx="{x}" cy="{y}" r="0.22" fill="{{c}}"/>'
                        for x, y in ((-0.7, -0.5), (0.4, -0.8), (0.8, 0.3), (-0.1, 0.3), (-0.8, 0.8), (0.5, 0.9))),
    "string": '<path d="M 0 -1.1 V 1.1 M -0.7 -0.2 Q 0 0.9 0.7 -0.2"/>',
    "modal": '<circle cx="0" cy="0" r="0.4"/><circle cx="0" cy="0" r="0.95"/>',
    "kick": '<circle cx="0" cy="0" r="0.9"/><path d="M 0 0 L 0.95 -0.95"/><circle cx="0" cy="0" r="0.3" fill="{c}"/>',
    "snare": '<path d="M -0.95 -0.5 H 0.95 V 0.5 H -0.95 Z M -0.95 0 H 0.95"/>',
    "hihat": '<path d="M 0 -1.0 V 1.0 M -0.95 -0.15 L 0 -0.5 L 0.95 -0.15 M -0.95 0.3 L 0 0.65 L 0.95 0.3"/>',
}
# model name, glyph; Plaits 1.2 banks: green 1-8, red 9-16 (the yellow bank 17-24 has no icons, as on Plaits)
MODELS_GREEN = [("pair of classic waveforms", "va"), ("waveshaping oscillator", "fold"),
                ("two-operator FM", "fm"), ("granular formant oscillator", "formant"),
                ("harmonic oscillator", "harmonic"), ("wavetable oscillator", "wavetable"),
                ("chords", "chord"), ("vowel and speech synthesis", "speech")]
MODELS_RED = [("granular cloud", "cloud"), ("filtered noise", "noise"), ("particle noise", "particle"),
              ("inharmonic string", "string"), ("modal resonator", "modal"), ("analog bass drum", "kick"),
              ("analog snare drum", "snare"), ("analog hi-hat", "hihat")]


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
         '<title>Plaitsy 12HP panel - artwork</title>',
         f'<style>text{{font-family:{A["font"]};font-weight:bold;fill:{A["silk"]}}} '
         f'.serif{{font-family:{A["serif"]};font-style:italic;font-weight:normal}} '
         f'.silk{{stroke:{A["silk"]};fill:none;stroke-linecap:round;stroke-linejoin:round}} '
         f'.dots{{stroke-dasharray:0.1 1.0;stroke-width:0.45}} '
         f'.copper{{fill:{A["copper"]}}} .cu-text{{fill:{A["panel"]}}} .hole{{fill:#ffffff;stroke:none}}</style>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="{A["panel"]}"/>']
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    icon_x = {"green": pos["SW1"][2], "red": pos["SW2"][2]}     # the icon columns sit under the buttons

    def text(x, y, t, size, anchor="middle", cls="", extra="", colour=None):
        c = f' class="{cls}"' if cls else ""
        st = f' style="fill:{colour}"' if colour else ""
        s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}"{c}{st}{extra}>{t}</text>')

    def dots(pts):
        s.append('<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + '" class="silk dots"/>')

    def glyph(x, y, name, colour, scale=1.0, rotate=0):
        s.append(f'<g transform="translate({x:.2f} {y:.2f}) rotate({rotate}) scale({scale})" stroke="{colour}" '
                 f'fill="none" stroke-width="0.3" stroke-linecap="round" stroke-linejoin="round">'
                 + GLYPHS[name].format(c=colour) + '</g>')

    def scale_r(ref):
        return A["scale"][KNOB_SIZE[ref]]

    def label_below(ref):
        kind, label, x, y = pos[ref]
        return x, y + scale_r(ref) + 3.0

    # -- preview tint under the icons (the real silk is one colour)
    s.append('<g id="tint">')
    for bank in ("green", "red"):
        for k in range(8):
            if bank == "green":
                continue                     # the green bank's discs are solid silk already
            s.append(f'<circle cx="{icon_x[bank]:.2f}" cy="{pos[f"D{k + 1}"][3]:.2f}" r="{A["icon"]:.2f}" '
                     f'fill="{A[bank]}" opacity="0.55"/>')
    s.append('</g>')

    # -- silkscreen
    s.append('<g id="silk">')
    text(12.0, 7.4, A["title"], 5.2, anchor="start", cls="serif")            # between the screw and the centre
    text(W - 12.0, 6.6, A["subtitle"], 2.1, anchor="end")
    s.append(f'<line x1="3" y1="9.6" x2="{W - 3}" y2="9.6" class="silk dots"/>')   # band under the title
    s.append(f'<line x1="3" y1="10.6" x2="{W - 3}" y2="10.6" class="silk dots"/>')
    text(W / 2, 122.4, A["maker"], 2.2)
    s.append(f'<line x1="3" y1="118.6" x2="{W - 3}" y2="118.6" class="silk" stroke-width="0.3"/>')
    # model buttons: wrench (hold the left one: LPG settings), the "levels" disc (hold the right one and
    # turn HARMONICS: octave range) with its dotted line, and a dotted line from each button to its bank
    bx1, by = pos["SW1"][2], pos["SW1"][3]
    bx2 = pos["SW2"][2]
    wx = bx1 - A["cap_led"] - 3.6
    s.append(f'<g transform="translate({wx:.2f} {by:.2f}) rotate(-40)">'
             f'<path d="M -0.9 -1.7 H 0.9 V -0.5 L 0.4 0 V 1.8 H -0.4 V 0 L -0.9 -0.5 Z" fill="{A["silk"]}"/>'
             f'<path d="M -0.35 -1.7 V -1.05 H 0.35 V -1.7 Z" fill="{A["panel"]}"/></g>')
    dx = bx2 + A["cap_led"] + 3.4
    s.append(f'<circle cx="{dx:.2f}" cy="{by:.2f}" r="1.5" fill="{A["silk"]}"/>')
    for k in (-1, 0, 1):
        s.append(f'<circle cx="{dx + 0.6 * k:.2f}" cy="{by - 0.6 * k:.2f}" r="0.22" fill="{A["panel"]}"/>')
    hx, hy = pos["RV2"][2], pos["RV2"][3]
    dots([(dx + 2.1, by), (hx, by), (hx, hy - scale_r("RV2") - 1.4)])
    icon_top = pos["D1"][3] - A["icon"]
    for bx in (bx1, bx2):
        dots([(bx, by + A["cap_led"] + 0.7), (bx, icon_top - 0.5)])
    # model icons
    for k in range(8):
        y = pos[f"D{k + 1}"][3]
        x = icon_x["green"]
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["icon"]:.2f}" fill="{A["silk"]}"/>')
        glyph(x, y, MODELS_GREEN[k][1], A["panel"])
        x = icon_x["red"]
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["icon"]:.2f}" class="silk" stroke-width="0.3"/>')
        glyph(x, y, MODELS_RED[k][1], A["silk"])
    # knobs: scale arcs with ticks, labels under the four main knobs
    for ref, (kind, label, x, y) in pos.items():
        if kind != "pot":
            continue
        size = KNOB_SIZE[ref]
        r = scale_r(ref)
        s.append(f'<path d="{_arc(x, y, r, -135, 135)}" class="silk" stroke-width="0.3"/>')
        n = {"big": 11, "mid": 7, "small": 3}[size]
        for i in range(n):
            a = math.radians(-135 + 270 * i / (n - 1))
            r1 = r + (1.2 if i in (0, n - 1, (n - 1) // 2) else 0.7)
            s.append(f'<line x1="{x + r * math.sin(a):.2f}" y1="{y - r * math.cos(a):.2f}" '
                     f'x2="{x + r1 * math.sin(a):.2f}" y2="{y - r1 * math.cos(a):.2f}" class="silk" stroke-width="0.3"/>')
        if size == "small":                 # attenuverter: - and + outside the arc, as on Plaits
            text(x - 6.6, y - 5.0, "–", 2.4)
            text(x + 6.6, y - 5.0, "+", 2.4)
        else:
            lx, ly = label_below(ref)
            text(lx, ly, label, 2.7 if size == "big" else 2.4)
    # the alternate functions reached by holding the left button: LPG colour on TIMBRE, decay on MORPH
    for ref, side, d in (("RV3", -1, 'M -0.8 -0.3 H 0 Q 0.45 -0.3 0.8 0.6'), ("RV4", 1, 'M -0.8 -0.6 Q -0.45 0.6 0.8 0.6')):
        lx, ly = label_below(ref)
        half = 0.68 * 2.4 * len(pos[ref][1]) / 2             # rough half-width of the label
        ix = lx + side * (half + 2.4)
        s.append(f'<circle cx="{ix:.2f}" cy="{ly - 0.8:.2f}" r="1.45" fill="{A["silk"]}"/>')
        s.append(f'<path d="{d}" transform="translate({ix:.2f} {ly - 0.8:.2f})" fill="none" stroke="{A["panel"]}" '
                 f'stroke-width="0.3" stroke-linecap="round"/>')
    # FM over its attenuverter
    fx, fy = pos["RV6"][2], pos["RV6"][3]
    text(fx, fy - scale_r("RV6") - 1.7, "FM", 2.4)
    # dotted guides: TIMBRE / MORPH label -> attenuverter, attenuverter -> CV jack
    for knob, att in KNOB_TO_ATT.items():
        lx, ly = label_below(knob)
        ax, ay = pos[att][2], pos[att][3]
        top = ay - scale_r(att) - 1.0
        dots([(lx, ly + 1.2), (lx, ly + 3.2), (ax, ly + 5.0), (ax, top)])
    for att, jack in ATT_TO_JACK.items():
        ax, ay = pos[att][2], pos[att][3]
        jx, jy = pos[jack][2], pos[jack][3]
        y0 = ay + A["knob"]["small"] + 0.9
        top = jy - A["nut"] - 0.9
        if abs(jx - ax) < 0.3:
            dots([(ax, y0), (ax, top)])
        else:
            dots([(ax, y0), (ax, y0 + 1.8), (jx, top - 1.6), (jx, top)])
    # jack labels; TRIG and LEVEL joined by dots (the trigger drives the internal envelope when LEVEL is free)
    for jack, word in JACK_LABELS.items():
        text(pos[jack][2], pos[jack][3] - A["nut"] - 1.6, word, 2.2)
    tx, ty = pos["J6"][2], pos["J6"][3]
    dots([(tx + A["nut"] + 0.9, ty), (pos["J7"][2] - A["nut"] - 0.9, ty)])
    s.append('</g>')
    # -- bare copper: the OUT / AUX band with its labels knocked out
    s.append('<g id="copper">')
    ox, ax_, jy = pos["J9"][2], pos["J10"][2], pos["J9"][3]
    s.append(f'<rect x="{ox - 4.8:.2f}" y="{jy - 8.8:.2f}" width="{ax_ - ox + 9.4:.2f}" height="14.6" rx="1.4" class="copper"/>')
    for ref in OUTPUTS:
        text(pos[ref][2], jy - A["nut"] - 1.6, pos[ref][1], 2.2, cls="cu-text")
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
            r = A["knob"][KNOB_SIZE[ref]]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="#2a2a2a" stroke="#000" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r * 0.62:.2f}" fill="#e8e8e4"/>')
            a = math.radians(-135 if KNOB_SIZE[ref] != "small" else 0)
            s.append(f'<line x1="{x + 0.3 * r * math.sin(a):.2f}" y1="{y - 0.3 * r * math.cos(a):.2f}" '
                     f'x2="{x + 0.95 * r * math.sin(a):.2f}" y2="{y - 0.95 * r * math.cos(a):.2f}" '
                     f'stroke="#555" stroke-width="0.6" stroke-linecap="round"/>')
        elif kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["nut"]}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "ledbutton":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["cap_led"]}" fill="#2b2b2b" stroke="#000" stroke-width="0.4"/>')
        elif kind == "led":
            col = A["green"] if ref == "D1" else "#3a3030"
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["led"]}" fill="{col}"/>')
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, "plaits-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "plaits-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "plaits-panel.svg"))
    print(f"{len(feats)} features + 4 mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
