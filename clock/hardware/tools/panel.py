"""12HP panel for Tempo: hole list (CSV), a 1:1 drill template (SVG) and the
panel artwork (SVG, as a PCB panel). Everything is computed from PLACEMENT
in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the faceplate board is seen from the
front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack     sleeve pad towards the top of the board; the barrel sits 0.78 mm
           below the WQP518MA footprint origin
  button   Thonk low-profile LED button, 5.5 mm cap centred on the origin
  encoder  EC11 with an M7 bushing, shaft on the origin
  led      3 mm LED, body centred on the origin
  window   the display's active area plus a margin, centred on the origin
Run from clock/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("tempo_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 12HP
HP = circuit.HP
BOARD_X0 = (PANEL_W - circuit.BOARD_W) / 2
BOARD_Y0 = (PANEL_H - circuit.BOARD_H) / 2   # board centred on the panel
HOLE = {"jack": 6.5, "ledbutton": 6.5, "encoder": 7.5, "led": 3.2}
WINDOW_MARGIN, WINDOW_R = 0.5, 1.0           # window = active area + margin each side; corner radius (fab: >= 0.5)
WINDOW = (circuit.DISPLAY_ACTIVE[0] + 2 * WINDOW_MARGIN, circuit.DISPLAY_ACTIVE[1] + 2 * WINDOW_MARGIN)
JACK_BARREL = circuit.JACK_BARREL
OUT = os.path.join(HERE, "..", "panel")


def features():
    """[(kind, ref, label, origin_x, origin_y, hole_x, hole_y)] in board mm, y up."""
    labels = {r: lbl for r, lbl, *_ in circuit.JACKS + circuit.BUTTONS + circuit.ENCODERS}
    labels.update({led: f"output {labels[jack]} LED" for led, jack in circuit.OUTPUT_LEDS})
    labels[circuit.DISPLAY[0]] = circuit.DISPLAY[1]
    out = []
    for ref, (x, y, rot) in circuit.PLACEMENT.items():
        if ref.startswith("J"):
            out.append(("jack", ref, labels[ref], x, y, x, y + JACK_BARREL))
        elif ref.startswith("SW"):
            out.append(("ledbutton", ref, labels[ref], x, y, x, y))
        elif ref.startswith("ENC"):
            out.append(("encoder", ref, labels[ref], x, y, x, y))
        elif ref.startswith("DS"):
            out.append(("window", ref, labels[ref], x, y, x, y))
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


def window_rect(x, y, cls=None, stroke=None):
    """The display window round its centre (x, y), panel frame."""
    w, h = WINDOW
    c = f' class="{cls}"' if cls else ""
    st = f' fill="none" stroke="{stroke}" stroke-width="0.2"' if stroke else ""
    return f'<rect x="{x - w / 2:.2f}" y="{y - h / 2:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{WINDOW_R}"{c}{st}/>'


def hole_text(kind):
    if kind == "window":
        return f"{WINDOW[0]:.2f} x {WINDOW[1]:.2f} window r{WINDOW_R}"
    return HOLE[kind]


def write_csv(feats, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "ref", "label", "board_origin_x", "board_origin_y", "panel_x_from_left",
                    "panel_y_from_top", "hole_mm"])
        for kind, ref, label, ox, oy, hx, hy in feats:
            px, py = panel_xy(hx, hy)
            w.writerow([kind, ref, label, f"{ox:.2f}", f"{oy:.2f}", f"{px:.2f}", f"{py:.2f}", hole_text(kind)])
        for x, y in MOUNTS:
            w.writerow(["mount", "", "mounting slot", "", "", f"{x:.2f}", f"{y:.2f}", f"{SLOT_W} x {SLOT_H} slot"])


def write_svg(feats, path):
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 40}mm" height="{H + 30}mm" '
         f'viewBox="-20 -15 {W + 40} {H + 30}">',
         '<title>Tempo 12HP panel - drill template (print at 100%)</title>',
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
        if kind == "window":
            w, h = WINDOW
            s.append(window_rect(x, y, stroke="#c00"))
            s.append(f'<text class="dim" x="{x - w / 2:.2f}" y="{y - h / 2 - 0.4:.2f}">{w:.2f} x {h:.2f}, r{WINDOW_R}</text>')
            s.append(f'<text class="lbl" x="{x:.2f}" y="{y:.2f}" text-anchor="middle">{label}</text>')
            continue
        d = HOLE[kind]
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{d / 2:.2f}" fill="none" stroke="#c00" stroke-width="0.2"/>')
        s.append(f'<line x1="{x - 1.5:.2f}" y1="{y:.2f}" x2="{x + 1.5:.2f}" y2="{y:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<line x1="{x:.2f}" y1="{y - 1.5:.2f}" x2="{x:.2f}" y2="{y + 1.5:.2f}" stroke="#000" stroke-width="0.12"/>')
        if kind != "led":
            s.append(f'<text class="dim" x="{x + d / 2 + 0.4:.2f}" y="{y - d / 2 - 0.2:.2f}">Ø{d}</text>')
            s.append(f'<text class="lbl" x="{x:.2f}" y="{y + d / 2 + 2.2:.2f}" text-anchor="middle">{label}</text>')
    s.append('<line x1="5" y1="-8" x2="55" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (5, 55):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="30" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Tempo 12HP panel, front view. '
             'Red: final hole size (LEDs 3.2). Dashed: the faceplate board.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the house style: black solder mask, white silkscreen,
# bare (ENIG) copper for the output band. SVG groups: #copper, #silk, #holes
# and #mockup (knobs, nuts, caps, LEDs, a sample screen; preview only).
# Tune ART, run, look at tempo-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227", "unlit": "#d9d9d6",
    "button": {"green": "#57d26c", "white": "#f7f7f2", "red": "#d42a20"},
    "knob": 5.3, "cap_led": 2.75, "nut": 4.0, "ring": 4.35, "led": 1.6,
    "title": "Tempo", "subtitle": "Clock + LFO", "maker": "Seedable Instruments",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
    "mono": "Consolas, Courier New, monospace",
    "label": 2.0,                             # button and jack labels
    "number": 3.4,                            # output numbers on the band (serif italic, Marblesy's size)
}
OUTPUTS = [ref for ref, lbl, net, d in circuit.JACKS if d == "out"]
LED_OF = {jack: led for led, jack in circuit.OUTPUT_LEDS}
BAND_CLEAR = 0.4      # bare board (under black mask) between copper and a hole through it; DRC asks 0.3


def jack_label_y(pos, ref):
    return pos[ref][3] - ART["nut"] - 1.6


def band(pos):
    """The bare-copper output band under the two lower jack rows, (x, y, w, h, rx) in the panel frame,
    and the holes through it as clearance circles (x, y, r). As Marblesy's: 2.6 mm from the sides and
    9.4 mm above the upper jack row, so the LED clearances keep copper outside them."""
    top = pos["J6"][3] - 9.4
    bottom = pos["J11"][3] + ART["nut"] + 1.2
    x, w = 2.6, PANEL_W - 5.2
    cuts = []
    for kind, label, hx, hy in pos.values():
        if kind == "window":
            continue
        r = HOLE[kind] / 2 + BAND_CLEAR
        if x - r < hx < x + w + r and top - r < hy < bottom + r:
            if not (x + r < hx < x + w - r and top + r < hy < bottom - r):
                raise ValueError(f"the hole at ({hx:.2f}, {hy:.2f}) crosses the edge of the output band")
            cuts.append((hx, hy, r))
    return (x, top, w, bottom - top, 1.4), cuts


def layout(pos):
    """Everything the artwork (and later the panel PCB) draws on the silkscreen, in one list:
    ("text", x, y, s, size, anchor), ("serif", x, y, s, size, anchor), ("line", pts, w), ("dots", pts),
    ("ring", cx, cy, r, w)."""
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
    # soft knobs: a short dotted guide from the screen's lower edge to each knob, where the screen names it
    wy = pos["DS1"][3] + WINDOW[1] / 2
    for ref, _ in circuit.ENCODERS:
        x, y = pos[ref][2], pos[ref][3]
        out.append(("dots", [(x, wy + 1.0), (x, y - A["knob"] - 0.9)]))
    # buttons: ring and word under each
    for ref, label, colour in circuit.BUTTONS:
        x, y = pos[ref][2], pos[ref][3]
        out.append(("ring", x, y, A["ring"], 0.35))
        text(x, y + A["ring"] + 2.8, label, A["label"])
    # input labels over the jacks (the outputs' go on the copper)
    for ref, label, net, d in circuit.JACKS:
        if d == "in":
            text(pos[ref][2], jack_label_y(pos, ref), label, A["label"])
    return out


def wave_icon(x, y, kind, w=3.0, h=1.6):
    """A small waveform as SVG polyline points, left end at (x, y) = mid-height (panel mm)."""
    n = 24
    pts = []
    for i in range(n + 1):
        t = i / n
        if kind == "sine":
            v = math.sin(2 * math.pi * t)
        elif kind == "saw":
            v = 1 - 2 * ((t * 2) % 1)
        elif kind == "pump":
            v = -1 + 2 * (1 - math.exp(-5 * ((t * 2) % 1)))
        elif kind == "sh":
            v = (0.2, -0.8, 0.9, -0.3)[min(int(t * 4), 3)]
        elif kind == "rnd":
            v = 0.8 * math.sin(2 * math.pi * t * 1.3 + 0.5) * math.cos(2 * math.pi * t * 0.4)
        else:                                  # clock: pulses
            v = 1 if (t * 4) % 1 < 0.35 else -1
        pts.append((x + w * t, y - v * h / 2))
    if kind in ("sh", "clock"):              # stepped: hold each value to the next sample
        stepped = [pts[0]]
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            stepped += [(xb, ya), (xb, yb)]
        pts = stepped
    return " ".join(f"{px:.2f},{py:.2f}" for px, py in pts)


def screen(pos, x, y):
    """A sample of the home page for the mockup: tempo and transport on top, the eight outputs as tiles
    laid out like their jacks (output 3 selected), and the three soft knobs' names and values above them."""
    w, h = WINDOW
    x0, y0 = x - w / 2, y - h / 2
    fg, dim, hi = "#f4f4f0", "#9a9a96", "#e8b33a"
    s = []

    def t(xx, yy, txt, size=1.9, anchor="start", fill=fg):
        s.append(f'<text x="{xx:.2f}" y="{yy:.2f}" font-size="{size}" text-anchor="{anchor}" '
                 f'style="font-family:{ART["mono"]};font-weight:normal;fill:{fill}">{txt}</text>')

    t(x0 + 1.4, y0 + 3.0, "128.0 BPM", 2.1)
    t(x0 + w / 2 + 2.0, y0 + 3.0, "INT", 1.7, "middle", dim)
    t(x0 + w - 1.4, y0 + 3.0, "&#9654; 03.2.1", 2.1, "end")
    tiles = [("1", "clock", "1/16"), ("2", "clock", "1/4"), ("3", "sine", "1/8T"), ("4", "clock", "E5:16"),
             ("5", "pump", "1/4"), ("6", "sh", "1/16"), ("7", "rnd", "4 BAR"), ("8", "saw", "2 BAR")]
    tw, th = (w - 2.4) / 4, 5.2
    for k, (num, kind, val) in enumerate(tiles):
        tx, ty = x0 + 1.2 + tw * (k % 4), y0 + 4.6 + (th + 0.6) * (k // 4)
        sel = num == "3"
        s.append(f'<rect x="{tx + 0.2:.2f}" y="{ty:.2f}" width="{tw - 0.4:.2f}" height="{th:.2f}" rx="0.4" '
                 f'fill="{hi if sel else "#1d1d1d"}"/>')
        ink = "#111" if sel else fg
        t(tx + 0.8, ty + 2.0, num, 1.8, fill="#111" if sel else hi)
        s.append(f'<polyline points="{wave_icon(tx + 3.2, ty + 1.45, kind, 5.0, 1.5)}" fill="none" '
                 f'stroke="{ink}" stroke-width="0.22"/>')
        t(tx + tw / 2, ty + 4.4, val, 1.7, "middle", ink)
    # the soft knobs' cells, centred over the knobs
    cells = [("OUTPUT", "3"), ("SHAPE", "SINE"), ("RATE", "1/8T")]
    for (ref, _), (cap, val) in zip(circuit.ENCODERS, cells):
        kx = pos[ref][2]
        t(kx, y0 + h - 3.6, cap, 1.4, "middle", dim)
        t(kx, y0 + h - 1.1, val, 2.0, "middle")
    return s


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>Tempo 12HP panel - artwork</title>',
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

    # -- bare copper: the output band, its labels knocked out; numbers right of their LEDs
    s.append('<g id="copper">')
    (bx, by, bw, bh, brx), cuts = band(pos)
    s.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh:.2f}" rx="{brx}" class="copper"/>')
    for x, y, r in cuts:
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" class="cu-text"/>')
    jl = {r: lbl for r, lbl, *_ in circuit.JACKS}
    for ref in OUTPUTS:
        x = pos[ref][2]
        if ref in LED_OF:
            ly = pos[LED_OF[ref]][3]
            text(x + 1.0, ly + 1.2, jl[ref], A["number"], cls="serif cu-text")
        else:
            text(x, jack_label_y(pos, ref), jl[ref], A["label"], cls="cu-text")
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
        elif kind == "ring":
            _, x, y, r, w = item
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" class="silk" stroke-width="{w}"/>')
    s.append('</g>')
    # -- holes
    s.append('<g id="holes">')
    for ref, (kind, label, x, y) in pos.items():
        if kind == "window":
            s.append(window_rect(x, y, cls="hole"))
        else:
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{HOLE[kind] / 2:.2f}" class="hole"/>')
    for x, y in MOUNTS:
        s.append(slot(x, y, cls="hole"))
    s.append('</g>')
    # -- mockup of the fitted parts (preview only): running, TAP on the beat, SHIFT off; output LEDs at
    #    the levels of the sample screen's outputs
    s.append('<g id="mockup">')
    colours = {ref: c for ref, lbl, c in circuit.BUTTONS}
    lit = {"SW1": True, "SW2": True, "SW3": False}
    led_level = {"D1": 1.0, "D2": 0.0, "D3": 0.7, "D4": 1.0, "D5": 0.35, "D6": 0.85, "D7": 0.5, "D8": 0.15}
    for ref, (kind, label, x, y) in pos.items():
        if kind == "encoder":
            r = A["knob"]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="#1b1b1b" stroke="#000" stroke-width="0.3"/>')
            s.append(f'<circle cx="{x - 0.15 * r:.2f}" cy="{y - 0.2 * r:.2f}" r="{r * 0.7:.2f}" fill="#262626"/>')
            s.append(f'<circle cx="{x + 0.55 * r * math.sin(0.6):.2f}" cy="{y - 0.55 * r * math.cos(0.6):.2f}" '
                     f'r="0.35" fill="#000"/>')
        elif kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["nut"]}" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "ledbutton":
            fill = A["button"][colours[ref]] if lit[ref] else A["unlit"]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["cap_led"]}" fill="{fill}" stroke="#000" stroke-width="0.4"/>')
        elif kind == "led":
            v = led_level[ref]
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["led"]}" fill="#3a1414" stroke="#000" stroke-width="0.2"/>')
            if v:
                s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["led"]}" fill="#ff4a3d" opacity="{v:.2f}"/>')
        elif kind == "window":
            s.append(window_rect(x, y, cls=None).replace("/>", ' fill="#050505" stroke="#2c2c2c" stroke-width="0.3"/>'))
            s.extend(screen(pos, x, y))
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Panel clearances: knobs, button rings, jack nuts and LEDs must not touch each other, the window or
    the edges; reports gaps under 1 mm."""
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    items, bad = [], []
    win = None
    for ref, (kind, label, x, y) in pos.items():
        if kind == "window":
            win = (x - WINDOW[0] / 2, y - WINDOW[1] / 2, x + WINDOW[0] / 2, y + WINDOW[1] / 2)
            continue
        r = {"encoder": ART["knob"], "jack": ART["nut"], "ledbutton": ART["ring"], "led": ART["led"]}[kind]
        items.append((ref, x, y, r))
    for i, (a, xa, ya, ra) in enumerate(items):
        for b, xb, yb, rb in items[i + 1:]:
            gap = math.hypot(xa - xb, ya - yb) - ra - rb
            if gap < 1.0:
                bad.append(f"{a} - {b}: {gap:.2f} mm")
        edge = min(xa, PANEL_W - xa) - ra
        if edge < 2.0:
            bad.append(f"{a} - panel edge: {edge:.2f} mm")
        if win:
            dx = max(win[0] - xa, 0, xa - win[2])
            dy = max(win[1] - ya, 0, ya - win[3])
            gap = math.hypot(dx, dy) - ra
            if gap < 1.0:
                bad.append(f"{a} - display window: {gap:.2f} mm")
    return bad


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, "tempo-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "tempo-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "tempo-panel.svg"))
    for b in check(feats):
        print("tight:", b)
    print(f"{len(feats)} features + 4 mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
