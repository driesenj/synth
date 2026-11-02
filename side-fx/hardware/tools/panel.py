"""14HP panel for Side FXy: hole list (CSV), a 1:1 drill template (SVG) and
the panel artwork (SVG, as a PCB panel). Everything is computed from
PLACEMENT in circuit.py, so board and panel agree.

Conventions (the Marblesy ones): the faceplate board is seen from the
front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack     sleeve pad towards the top of the board; the barrel sits 0.78 mm
           below the WQP518MA footprint origin
  button   Thonk low-profile LED button, 5.5 mm cap centred on the origin
  encoder  EC11 with an M7 bushing, shaft on the origin
  window   the display's active area plus a margin, centred on the origin
Run from side-fx/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sidefx_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)
_spec = importlib.util.spec_from_file_location("sidefx_mushroom", os.path.join(HERE, "mushroom.py"))
mushroom = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mushroom)

PANEL_W, PANEL_H = circuit.PANEL_W, circuit.PANEL_H     # Eurorack 3U, 14HP
HP = circuit.HP
BOARD_X0 = (PANEL_W - circuit.BOARD_W) / 2
BOARD_Y0 = (PANEL_H - circuit.BOARD_H) / 2   # board centred on the panel
HOLE = {"jack": 6.5, "ledbutton": 6.5, "encoder": 7.5}
WINDOW_MARGIN, WINDOW_R = 0.5, 1.0           # window = active area + margin each side; corner radius (fab: >= 0.5)
WINDOW = (circuit.DISPLAY_ACTIVE[0] + 2 * WINDOW_MARGIN, circuit.DISPLAY_ACTIVE[1] + 2 * WINDOW_MARGIN)
JACK_BARREL = circuit.JACK_BARREL
OUT = os.path.join(HERE, "..", "panel")


def features():
    """[(kind, ref, label, origin_x, origin_y, hole_x, hole_y)] in board mm, y up."""
    labels = {r: lbl for r, lbl, *_ in circuit.JACKS}
    labels.update({r: lbl for r, lbl, *_ in circuit.BUTTONS + circuit.ENCODERS})
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
         '<title>Side FXy 14HP panel - drill template (print at 100%)</title>',
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
        s.append(f'<text class="dim" x="{x + d / 2 + 0.4:.2f}" y="{y - d / 2 - 0.2:.2f}">Ø{d}</text>')
        s.append(f'<text class="lbl" x="{x:.2f}" y="{y + d / 2 + 2.2:.2f}" text-anchor="middle">{label}</text>')
    s.append('<line x1="5" y1="-8" x2="55" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (5, 55):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="30" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Side FXy 14HP panel, front view. '
             'Red: final hole size. Dashed: the faceplate board.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


# ------------------------------------------------------------------ artwork
# The panel as a PCB, in the Marblesy style: black solder mask, white
# silkscreen, bare (ENIG) copper for the outputs and for the block stack the
# soft knobs sit on (SIDE FX has it in white). SVG groups: #copper, #silk,
# #holes and #mockup (knobs, nuts, caps, a sample screen; preview only).
# Tune ART, run, look at side-fx-panel.svg.
ART = {
    "panel": "#121212", "silk": "#f0efe9", "copper": "#c9a227", "lit": "#ff6f6f", "unlit": "#d9d9d6",
    "shift": "#d42a20", "knob": 5.3, "cap_led": 2.75, "nut": 4.0, "ring": 4.35,
    "title": "Moss", "subtitle": "Quad effects",
    "font": "Arial, Helvetica, sans-serif", "serif": "Georgia, Times New Roman, serif",
    "mono": "Consolas, Courier New, monospace",
    "label": 2.0,                             # button and jack labels
}
SENDS = ["SW1", "SW2", "SW3", "SW4"]
OUTPUTS = ["J2", "J7"]
BAND_CLEAR = 0.4      # bare board (under black mask) between copper and a hole through it; DRC asks 0.3
GAP = 0.6             # black between two blocks of the stack


def blocks(pos):
    """The copper block stack behind the soft knobs: rectangles (x, y, w, h) in the panel frame, built on
    the knob columns so the knobs sit on its edges, and the SHIFT button on its top right corner. Rows:
    two squares, a strip, K2's block, a narrow pair on the left (the notch beside it is K3's side), and
    K4's block along the bottom."""
    xl, xr = pos["ENC1"][2], pos["ENC2"][2]
    xm = (xl + xr) / 2
    y1, y2, y3, y4 = (pos[f"ENC{k}"][3] for k in range(1, 5))
    top = pos["SW5"][3] - 4.0
    rows = [  # (y0, y1, [(x0, x1), ...])
        (top, y1 - 0.9, [(xl, xm - GAP / 2), (xm + GAP / 2, xr)]),
        (y1 - 0.9 + GAP, (y1 + y2) / 2, [(xl, xr)]),
        ((y1 + y2) / 2 + GAP, (y2 + y3) / 2, [(xl, xr)]),
        ((y2 + y3) / 2 + GAP, y3, [(xl, xm - GAP / 2)]),
        (y3 + GAP, (y3 + y4) / 2, [(xl, xm - GAP / 2)]),
        ((y3 + y4) / 2 + GAP, y4 + 5.5, [(xl, xr)]),
    ]
    return [(x0, y0, x1 - x0, y1_ - y0) for y0, y1_, xs in rows for x0, x1 in xs]


def copper(pos):
    """[(rect (x, y, w, h, rx), cuts [(x, y, r)])]: the output band round OUT 1 / OUT 2 and the blocks.
    A hole that touches a copper area gets a clearance circle; under a knob or nut nobody sees it."""
    ox, y1, y2 = pos["J2"][2], pos["J2"][3], pos["J7"][3]
    rects = [(ox - 6.0, jack_label_y(pos, "J2") - 3.0, 12.0, y2 + ART["nut"] + 1.0 - (jack_label_y(pos, "J2") - 3.0),
              1.4)]
    rects += [(x, y, w, h, 0.4) for x, y, w, h in blocks(pos)]
    out = []
    for x, y, w, h, rx in rects:
        cuts = []
        for kind, label, hx, hy in pos.values():
            if kind == "window":
                continue
            r = HOLE[kind] / 2 + BAND_CLEAR
            if x - r < hx < x + w + r and y - r < hy < y + h + r:
                cuts.append((hx, hy, r))
        out.append(((x, y, w, h, rx), cuts))
    return out


def jack_label_y(pos, ref):
    return pos[ref][3] - ART["nut"] - 1.6


def layout(pos):
    """Everything the artwork (and later the panel PCB) draws on the silkscreen, in one list:
    ("text", x, y, s, size, anchor), ("serif", x, y, s, size, anchor), ("line", pts, w), ("dots", pts),
    ("ring", cx, cy, r, w)."""
    A = ART
    W = PANEL_W
    out = []

    def text(x, y, s, size, anchor="middle"):
        out.append(("text", x, y, s, size, anchor))

    # title band, rule and mushroom mark: the same spots on every module's panel
    out.append(("serif", 12.0, 7.4, A["title"], 5.2, "start"))
    text(W - 12.0, 6.6, A["subtitle"], 2.1, "end")
    out.append(("dots", [(3, 9.6), (W - 3, 9.6)]))
    out.append(("dots", [(3, 10.6), (W - 3, 10.6)]))
    out.append(("gold", mushroom.polygons(W)))     # the mushroom mark under the rule, bare gold
    out.append(("line", [(3, 118.6), (W - 3, 118.6)], 0.3))
    # the send buttons: ring and word under each; SHIFT sits bare on the block stack's corner (no silk on
    # the copper)
    labels = {r: lbl for r, lbl, *_ in circuit.BUTTONS}
    for ref in SENDS:
        x, y = pos[ref][2], pos[ref][3]
        out.append(("ring", x, y, A["ring"], 0.35))
        text(x, y + A["ring"] + 2.8, labels[ref], A["label"])
    # jack labels over the jacks (the outputs' go on their copper)
    jl = {r: lbl for r, lbl, *_ in circuit.JACKS}
    for ref, (kind, label, x, y) in pos.items():
        if kind == "jack" and ref not in OUTPUTS:
            text(x, jack_label_y(pos, ref), jl[ref], A["label"])
    # IN 2 is normalled to IN 1: dotted line between them
    ax, ay = pos["J1"][2], pos["J1"][3]
    out.append(("dots", [(ax, ay + A["nut"] + 0.9), (ax, jack_label_y(pos, "J6") - 2.6)]))
    return out


def screen(pos, x, y):
    """A sample of the preset page for the mockup: each knob's name and value on the display row
    beside it (SIDE FX does the same), the page name up the left edge and the chain algorithm."""
    w, h = WINDOW
    xr = x + w / 2 - 1.2
    s = []

    def t(xx, yy, txt, size=2.1, anchor="end", extra=""):
        s.append(f'<text x="{xx:.2f}" y="{yy:.2f}" font-size="{size}" text-anchor="{anchor}" '
                 f'style="font-family:{ART["mono"]};font-weight:normal;fill:#f4f4f0"{extra}>{txt}</text>')

    rows = [("LOAD 37", "DARK DUB"), ("SAVE", "USER 04"), ("ALGO", "3"), ("MIX", "60%")]
    for k, (a, b) in enumerate(rows):
        ky = pos[f"ENC{k + 1}"][3]
        dy = 1.2 if k == 0 else (-1.6 if k == 3 else 0)    # keep the top and bottom pairs inside the glass
        t(xr, ky - 0.5 + dy, a)
        t(xr, ky + 2.4 + dy, b)
    x0, y0 = x - w / 2 + 2.6, y + h / 2 - 1.6
    s.append(f'<text x="{x0:.2f}" y="{y0:.2f}" font-size="2.0" transform="rotate(-90 {x0:.2f} {y0:.2f})" '
             f'style="font-family:{ART["mono"]};font-weight:normal;fill:#a8a8a4">PRESET</text>')
    # algorithm 3: 1 -> 2 -> (3 | 4)
    bx, by, b = x - 4.0, y + 5.0, 2.2
    boxes = [(bx, by), (bx + 3.0, by + 4.0), (bx + 3.0, by + 7.5), (bx + 3.0, by + 11.0)]
    for cx, cy in boxes:
        s.append(f'<rect x="{cx - b / 2:.2f}" y="{cy - b / 2:.2f}" width="{b}" height="{b}" '
                 f'fill="none" stroke="#f4f4f0" stroke-width="0.25"/>')
    s.append(f'<polyline points="{bx:.2f},{by + b / 2:.2f} {bx:.2f},{by + 11.0:.2f} {bx + 3.0 - b / 2:.2f},{by + 11.0:.2f}" '
             f'fill="none" stroke="#f4f4f0" stroke-width="0.25"/>')
    for cy in (by + 4.0, by + 7.5):
        s.append(f'<line x1="{bx:.2f}" y1="{cy:.2f}" x2="{bx + 3.0 - b / 2:.2f}" y2="{cy:.2f}" '
                 f'stroke="#f4f4f0" stroke-width="0.25"/>')
    return s


def write_artwork(feats, path):
    A = ART
    W, H = PANEL_W, PANEL_H
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
         '<title>Side FXy 14HP panel - artwork</title>',
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

    # -- bare copper: the output band and the block stack; labels knocked out
    s.append('<g id="copper">')
    for (bx, by, bw, bh, brx), cuts in copper(pos):
        s.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh:.2f}" rx="{brx}" class="copper"/>')
        for x, y, r in cuts:
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" class="cu-text"/>')
    jl = {r: lbl for r, lbl, *_ in circuit.JACKS}
    for ref in OUTPUTS:
        text(pos[ref][2], jack_label_y(pos, ref), jl[ref], A["label"], cls="cu-text")
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
    # -- mockup of the fitted parts (preview only): PITCH, DELAY and REVERB sends on, TEXTURE off
    s.append('<g id="mockup">')
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
            fill = A["shift"] if ref == "SW5" else (A["unlit"] if ref == "SW3" else A["lit"])
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{A["cap_led"]}" fill="{fill}" stroke="#000" stroke-width="0.4"/>')
        elif kind == "window":
            s.append(window_rect(x, y, cls=None).replace("/>", ' fill="#050505" stroke="#2c2c2c" stroke-width="0.3"/>'))
            s.extend(screen(pos, x, y))
    for x, y in MOUNTS:                  # M3 screw head
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="#cfd0cc" stroke="#777" stroke-width="0.2"/>')
    s.append('</g>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Panel clearances: knobs, button rings and jack nuts must not touch each other, the window or the
    edges; reports gaps under 1 mm."""
    pos = {ref: (kind, label, *panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
    items, bad = [], []
    win = None
    for ref, (kind, label, x, y) in pos.items():
        if kind == "window":
            win = (x - WINDOW[0] / 2, y - WINDOW[1] / 2, x + WINDOW[0] / 2, y + WINDOW[1] / 2)
            continue
        r = {"encoder": ART["knob"], "jack": ART["nut"], "ledbutton": ART["ring"]}[kind]
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
    write_csv(feats, os.path.join(OUT, "side-fx-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "side-fx-panel-drill.svg"))
    write_artwork(feats, os.path.join(OUT, "side-fx-panel.svg"))
    for b in check(feats):
        print("tight:", b)
    print(f"{len(feats)} features + 4 mounting slots written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
