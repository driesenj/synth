"""18HP panel for Marblesy: hole list (CSV), a 1:1 drill template (SVG) and
the faceplate footprint origins for the PCB. Everything is computed from
PLACEMENT in circuit.py, so board and panel agree.

Conventions (the same as the Plaitsy PCB): the faceplate board is seen from
the front, x to the right, y up, origin at the board's bottom-left corner.
Panel-facing parts sit on the board's bottom layer.
  jack   angle 0, sleeve pad towards the top of the board; the barrel sits
         6.48 mm from the sleeve pad towards the tip pad (KiCad PJ398SM),
         i.e. 0.78 mm below the footprint origin of the WQP518MA footprint
  pot    angle 90, pins towards -x; the shaft is 7.5 mm from the pin row,
         the PTV09A footprint origin is 6.97 mm from it: shaft = origin + 0.53 in x
  LED    3-lead LED in the generated LED-3MM-3P footprint: body centred on the origin
  switch Thonk Highly Tactile: body centred on the origin, 12 mm round body
Run from marbles/hardware/tools:  python panel.py
"""
import csv
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("marbles_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

PANEL_W, PANEL_H = 91.3, 128.5          # Eurorack 3U, 18HP
BOARD_X0 = (PANEL_W - circuit.BOARD_W) / 2
BOARD_Y0 = (PANEL_H - circuit.BOARD_H) / 2   # board centred on the panel; move it if your rails need it
HOLE = {"pot": 7.5, "jack": 6.5, "led": 3.2, "button": 12.5, "mount": 3.2}
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
            out.append(("button", ref, labels[ref], x, y, x, y))
        elif ref.startswith("D"):
            out.append(("led", ref, labels[ref], x, y, x, y))
    return out


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return BOARD_X0 + bx, PANEL_H - (BOARD_Y0 + by)


def write_csv(feats, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "ref", "label", "board_origin_x", "board_origin_y", "panel_x_from_left",
                    "panel_y_from_top", "hole_mm"])
        for kind, ref, label, ox, oy, hx, hy in feats:
            px, py = panel_xy(hx, hy)
            w.writerow([kind, ref, label, f"{ox:.2f}", f"{oy:.2f}", f"{px:.2f}", f"{py:.2f}", HOLE[kind]])
        for x in (7.5, PANEL_W - 7.5):
            for y in (3.0, PANEL_H - 3.0):
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
    rows += [("mount", "", x, y) for x in (7.5, W - 7.5) for y in (3.0, H - 3.0)]
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
             'Red circles: final hole size. Dashed: the faceplate board. Button holes suit the 12 mm round cap; '
             'check your switch.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def main():
    os.makedirs(OUT, exist_ok=True)
    feats = features()
    write_csv(feats, os.path.join(OUT, "marbles-panel-holes.csv"))
    write_svg(feats, os.path.join(OUT, "marbles-panel-drill.svg"))
    print(f"{len(feats)} features + 4 mounting holes written to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
