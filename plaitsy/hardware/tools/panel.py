"""12HP panel for Plaitsy: a 1:1 drill template and a labelling guide for
hand-drawing on a spray-painted aluminium panel. Every hole position is
computed from the faceplate board layout, so board and panel always agree."""
import csv

import faceplate as fp
from sb import PITCH, JACK_BUSHING_MM, POT_SHAFT_MM, _font

W, H = 60.6, 128.5  # Eurorack 3U, 12HP (Doepfer: 60.6 mm wide)
HOLE = {"pot": 7.5, "jack": 6.5, "led": 3.2, "button": 5.2, "mount": 3.2}

# Plaits model banks, top LED to bottom LED (firmware 1.2 names)
GREEN = ["VA", "WSHP", "FM", "GRAIN", "ADD", "WTBL", "CHORD", "SPEECH"]
RED = ["SWARM", "NOISE", "PART", "STRING", "MODAL", "BD", "SD", "HH"]
YELLOW = ["VA-VCF", "PD", "6OP-1", "6OP-2", "6OP-3", "WTRN", "STRMC", "CHIP"]


def features():
    """[(kind, name, x_mm, y_mm)] measured from the panel's top-left corner, front view."""
    b = fp.build()
    out = []

    def xy(r, c):
        return fp.X0 + c * PITCH, fp.Y0 + r * PITCH

    pot_names = {"RV1": "FREQUENCY", "RV2": "HARMONICS", "RV3": "TIMBRE", "RV4": "MORPH",
                 "RV5": "TIMBRE att.", "RV6": "FM att.", "RV7": "MORPH att."}
    for ref, name in pot_names.items():
        p = b.parts[ref]
        legs = sorted(pos for _, pos in p.pin_positions())
        (r0, c0), (r1, _), _ = legs
        x, y = xy(r1, c0)
        body = sorted(p.body_cells())
        x += POT_SHAFT_MM if body[0][1] > c0 else -POT_SHAFT_MM
        out.append(("pot", name, x, y))
    for k in range(8):
        r, _ = fp.RIGID[f"D{k + 1}"][0]
        x, y = xy(r + 0.5, 11)
        out.append(("led", f"LED{k + 1}", x, y))
    for ref, name in (("SW1", "left button"), ("SW2", "right button")):
        legs = [pos for _, pos in b.parts[ref].pin_positions()]
        r = sum(p[0] for p in legs) / 4
        c = sum(p[1] for p in legs) / 4
        out.append(("button", name, *xy(r, c)))
    for ref in [f"J{i}" for i in range(1, 11)]:
        p = b.parts[ref]
        s = dict(p.pin_positions())["1"]
        x, y = xy(*s)
        out.append(("jack", p.value, x, y + JACK_BUSHING_MM))
    for x in (7.5, 7.5 + 9 * 5.08):
        for y in (3.0, H - 3.0):
            out.append(("mount", "mounting", x, y))
    return out


def svg_header(title):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 40}mm" height="{H + 30}mm" '
            f'viewBox="-20 -15 {W + 40} {H + 30}">',
            f'<title>{title}</title>',
            '<style>text{font-family:Arial,Helvetica,sans-serif} .dim{font-size:1.6px;fill:#444}</style>',
            f'<rect x="0" y="0" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.25"/>']


def drill_svg(feats, path):
    s = svg_header("Plaitsy 12HP panel - drill template (print at 100%)")
    for kind, name, x, y in feats:
        d = HOLE[kind]
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{d / 2:.2f}" fill="none" stroke="#c00" stroke-width="0.2"/>')
        s.append(f'<line x1="{x - 1.5:.2f}" y1="{y:.2f}" x2="{x + 1.5:.2f}" y2="{y:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<line x1="{x:.2f}" y1="{y - 1.5:.2f}" x2="{x:.2f}" y2="{y + 1.5:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<text class="dim" x="{x + d / 2 + 0.6:.2f}" y="{y - d / 2 - 0.3:.2f}">Ø{d}</text>')
    # scale bar: 50 mm, check with a ruler after printing
    s.append('<line x1="5" y1="-8" x2="55" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (5, 55):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="30" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Plaitsy 12HP panel, front view. '
             'Red circles: final hole size. Centre-punch the crosses, pilot-drill 2 mm, then step up.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def artwork_svg(feats, path):
    f = {(k, n): (x, y) for k, n, x, y in feats}
    s = svg_header("Plaitsy 12HP panel - labels to hand-draw")

    def text(x, y, t, size=2.6, anchor="middle", weight="bold", fill="#111"):
        s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" '
                 f'font-weight="{weight}" fill="{fill}">{t}</text>')

    def dotted(pts):
        d = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        s.append(f'<polyline points="{d}" fill="none" stroke="#111" stroke-width="0.45" stroke-dasharray="0.1 1.1" stroke-linecap="round"/>')

    for (kind, name), (x, y) in f.items():
        d = HOLE[kind]
        if kind != "mount":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{d / 2:.2f}" fill="none" stroke="#bbb" stroke-width="0.2"/>')
    # title band
    text(W / 2, 9.0, "PLAITSY", 4.2)
    # big and medium knobs
    for name in ("FREQUENCY", "HARMONICS"):
        x, y = f[("pot", name)]
        text(x, y + 13.0, name, 2.7)
    for name in ("TIMBRE", "MORPH"):
        x, y = f[("pot", name)]
        text(x, y + 10.5, name, 2.7)
    # attenuverters: - / + either side, label above the middle one
    for name in ("TIMBRE att.", "FM att.", "MORPH att."):
        x, y = f[("pot", name)]
        text(x - 6.2, y - 4.6, "−", 3.0)
        text(x + 6.2, y - 4.6, "+", 3.0)
        s.append(f'<line x1="{x:.2f}" y1="{y - 7.2:.2f}" x2="{x:.2f}" y2="{y - 5.0:.2f}" stroke="#111" stroke-width="0.6"/>')
    text(f[("pot", "FM att.")][0], f[("pot", "FM att.")][1] - 8.3, "FM", 2.7)
    # LEDs: green bank left, red bank right (yellow bank: see manual)
    for k in range(8):
        x, y = f[("led", f"LED{k + 1}")]
        text(x - 3.0, y + 0.7, GREEN[k], 1.7, anchor="end", fill="#0a7a5a")
        text(x + 3.0, y + 0.7, RED[k], 1.7, anchor="start", fill="#c0262d")
    # buttons and the dotted lines to their LED banks
    (bx1, by1), (bx2, by2) = f[("button", "left button")], f[("button", "right button")]
    lx, ly = f[("led", "LED1")]
    dotted([(bx1, by1 + 3.4), (bx1, ly - 1.6)])
    dotted([(bx2, by2 + 3.4), (bx2, ly - 1.6)])
    # jack labels
    for kind, name, x, y in feats:
        if kind == "jack":
            text(x, y - 5.0, name, 2.3)
    # dotted links attenuverter -> its CV jack, TRIG -- LEVEL
    for att, jack in (("TIMBRE att.", "TIMBRE"), ("FM att.", "FM"), ("MORPH att.", "MORPH")):
        ax, ay = f[("pot", att)]
        jx, jy = f[("jack", jack)]
        if abs(ax - jx) < 1:
            dotted([(ax, ay + 5.0), (ax, jy - 7.4)])
        else:
            dotted([(ax, ay + 5.0), (ax, ay + 8.0), (jx, ay + 8.0), (jx, jy - 7.4)])
    tx, ty = f[("jack", "TRIG")]
    lx2, _ = f[("jack", "LEVEL")]
    dotted([(tx + 4.2, ty), (lx2 - 4.2, ty)])
    # outputs box, like Plaits
    ox, oy = f[("jack", "OUT")]
    ax2, _ = f[("jack", "AUX")]
    s.append(f'<rect x="{ox - 5.6:.2f}" y="{oy - 8.6:.2f}" width="{ax2 - ox + 11.2:.2f}" height="14.6" rx="1.2" '
             'fill="none" stroke="#111" stroke-width="0.35"/>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def preview_png(feats, path, scale=7):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (int(W * scale) + 40, int(H * scale) + 40), "white")
    d = ImageDraw.Draw(img)
    o = 20
    d.rectangle([o, o, o + W * scale, o + H * scale], outline="black", width=2)
    fnt = _font(13)
    for kind, name, x, y in feats:
        r = HOLE[kind] / 2 * scale
        X, Y = o + x * scale, o + y * scale
        d.ellipse([X - r, Y - r, X + r, Y + r], outline="#c00000", width=2)
        if kind in ("pot", "jack"):
            d.text((X - 3 * len(name), Y + r + 2), name, fill="black", font=fnt)
    img.save(path)


def main():
    feats = features()
    drill_svg(feats, "../panel/plaitsy-panel-drill.svg")
    artwork_svg(feats, "../panel/plaitsy-panel-artwork.svg")
    preview_png(feats, "../panel/plaitsy-panel-preview.png")
    with open("../panel/plaitsy-panel-holes.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["part", "name", "x_mm_from_left", "y_mm_from_top", "hole_mm"])
        for kind, name, x, y in feats:
            w.writerow([kind, name, f"{x:.2f}", f"{y:.2f}", HOLE[kind]])
    for kind, name, x, y in feats:
        print(f"{kind:7s} {name:14s} x={x:6.2f}  y={y:6.2f}")


if __name__ == "__main__":
    main()
