"""28HP panel for the stereo mixer: a layout illustration, a 1:1 drill template
and the hole list. Every position comes from FEATURES below, so the three
files always agree. Same conventions as Plaitsy's panel.py.

Layout: channel strips as columns, like a mixing console (SEND, PAN, LEVEL,
MUTE from the top, input jacks at the bottom so cables hang away from the
knobs). The master section on the right reads top to bottom: send and
return (the FX loop), drums, MASTER, outputs.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "..", "panel")

HP = 28
W, H = 141.9, 128.5                     # Eurorack 3U, 28HP (Doepfer: 141.9 mm)
HOLE = {"pot": 7.5, "jack": 6.5, "toggle": 5.0, "mount": 3.2}
KNOB = {"small": 10.0, "big": 14.0}     # knob diameters, for the illustration only

# columns (mm from the left edge) and rows (mm from the top edge)
CH_X = [15.0 + 13.0 * i for i in range(8)]          # channels 1-8
M1, M2 = 120.5, 132.5                                # master section, two columns
MC = (M1 + M2) / 2
ROW = {"send": 23.0, "pan": 38.0, "level": 54.0, "mute": 69.0, "in": 86.0, "in_r": 101.0}


def features():
    """[(kind, label, x, y, ref, knob)]"""
    f = []
    for i, x in enumerate(CH_X):
        k = i + 1
        if k <= 6:
            f += [("pot", f"SEND {k}", x, ROW["send"], f"RV{3 * k}", "small"),
                  ("pot", f"PAN {k}", x, ROW["pan"], f"RV{3 * k - 1}", "small"),
                  ("pot", f"LEVEL {k}", x, ROW["level"], f"RV{3 * k - 2}", "small"),
                  ("toggle", f"MUTE {k}", x, ROW["mute"], f"SW{k}", None),
                  ("jack", f"IN {k}", x, ROW["in"], f"J{k}", None)]
        else:
            s = k - 7
            f += [("pot", f"SEND {k}", x, ROW["send"], f"RV{20 + 2 * s}", "small"),
                  ("pot", f"LEVEL {k}", x, ROW["level"], f"RV{19 + 2 * s} (dual)", "small"),
                  ("toggle", f"MUTE {k}", x, ROW["mute"], f"SW{k} (DPDT)", None),
                  ("jack", f"IN {k} L", x, ROW["in"], f"J{7 + 2 * s}", None),
                  ("jack", f"IN {k} R", x, ROW["in_r"], f"J{8 + 2 * s}", None)]
    f += [("jack", "SEND", M1, ROW["send"], "J15", None),
          ("jack", "FX IN", M2, ROW["send"], "J14", None),
          ("jack", "RETURN L", M1, ROW["pan"], "J11", None),
          ("jack", "RETURN R", M2, ROW["pan"], "J12", None),
          ("pot", "RETURN", MC, ROW["level"], "RV23 (dual)", "small"),
          ("pot", "DRUMS", M1, ROW["mute"], "RV24", "small"),
          ("jack", "DRUMS IN", M2, ROW["mute"], "J13", None),
          ("pot", "MASTER", MC, ROW["in"], "RV25 (dual)", "big"),
          ("jack", "OUT L", M1, ROW["in_r"], "J16", None),
          ("jack", "OUT R", M2, ROW["in_r"], "J17", None)]
    for x in (7.5, 7.5 + (HP - 3) * 5.08):
        for y in (3.0, H - 3.0):
            f.append(("mount", "mounting", x, y, "", None))
    return f


def header(title, pad=(20, 15)):
    px, py = pad
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 2 * px}mm" height="{H + 2 * py}mm" '
            f'viewBox="{-px} {-py} {W + 2 * px} {H + 2 * py}">',
            f'<title>{title}</title>',
            '<style>text{font-family:Arial,Helvetica,sans-serif} .dim{font-size:1.5px;fill:#444}</style>']


def text(s, x, y, t, size=2.2, anchor="middle", weight="bold", fill="#111", extra=""):
    s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" '
             f'font-weight="{weight}" fill="{fill}"{extra}>{t}</text>')


def layout_svg(feats, path):
    """The proposal: holes, knob sizes, labels, output boxes, normals."""
    s = header("Stereo mixer 28HP panel - layout")
    s.append('<rect x="-20" y="-15" width="181.9" height="158.5" fill="#ffffff"/>')
    s.append(f'<rect x="0" y="0" width="{W}" height="{H}" rx="0.6" fill="#e9eae6" stroke="#222" stroke-width="0.3"/>')
    # rail zones (the case rails sit behind these bands)
    for y0 in (0, H - 10):
        s.append(f'<rect x="0" y="{y0}" width="{W}" height="10" fill="#000" opacity="0.04"/>')
    f = {lab: (x, y) for _, lab, x, y, _, _ in feats if lab != "mounting"}

    # outputs boxed (drawn first, under the parts)
    def box(x0, y0, x1, y1, fill="#2a2d2b"):
        s.append(f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" rx="1.2" '
                 f'fill="{fill}"/>')
    sx, sy = f["SEND"]
    box(sx - 5.7, sy - 8.6, sx + 5.7, sy + 5.6)
    ox, oy = f["OUT L"]
    rx_, _ = f["OUT R"]
    box(ox - 5.7, oy - 5.6, rx_ + 5.7, oy + 9.2)

    # separators: mono | stereo | master
    for x in ((CH_X[5] + CH_X[6]) / 2, (CH_X[7] + M1) / 2):
        s.append(f'<line x1="{x:.2f}" y1="12.5" x2="{x:.2f}" y2="108" stroke="#666" stroke-width="0.25"/>')
    for y in (ROW["level"] + 5.9, ROW["mute"] + 5.6):    # master section: FX loop | drums | master
        s.append(f'<line x1="{(CH_X[7] + M1) / 2 + 1.5:.2f}" y1="{y:.2f}" x2="{W - 2:.2f}" y2="{y:.2f}" '
                 'stroke="#666" stroke-width="0.25"/>')

    for kind, lab, x, y, ref, knob in feats:
        if kind == "mount":
            s.append(f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="2.0" ry="1.6" fill="#fff" stroke="#888" stroke-width="0.2"/>')
            continue
        on_dark = lab in ("SEND", "OUT L", "OUT R")
        if kind == "pot":
            r = KNOB[knob] / 2
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="#1d1f1e" stroke="#000" stroke-width="0.2"/>')
            # pointer at 7 o'clock (fully CCW)
            s.append(f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x - 0.64 * r:.2f}" y2="{y + 0.77 * r:.2f}" '
                     'stroke="#eee" stroke-width="0.5" stroke-linecap="round"/>')
        elif kind == "jack":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.1" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.75" fill="#111"/>')
        elif kind == "toggle":
            s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.5" fill="#b9bbb6" stroke="#555" stroke-width="0.2"/>')
            s.append(f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x:.2f}" y2="{y - 3.6:.2f}" stroke="#333" '
                     'stroke-width="1.3" stroke-linecap="round"/>')

    # title and column headers
    text(s, W / 2, 8.6, "STEREO MIXER", 3.6)
    for i, x in enumerate(CH_X):
        text(s, x, 15.0, str(i + 1), 2.8)
    text(s, (CH_X[6] + CH_X[7]) / 2, 11.6, "STEREO", 1.9, weight="normal")
    # row labels, left margin
    for key, lab in (("send", "SEND"), ("pan", "PAN"), ("level", "LEVEL"), ("mute", "MUTE")):
        text(s, 1.6, ROW[key] + 0.7, lab, 1.9, anchor="start")
    text(s, 1.6, ROW["in"] + 0.7, "IN / L", 1.9, anchor="start")
    text(s, 1.6, ROW["in_r"] + 0.7, "R", 1.9, anchor="start")
    # mute toggles: lever up = on
    for x in CH_X:
        text(s, x + 3.2, ROW["mute"] - 3.0, "ON", 1.3, anchor="start", weight="normal", fill="#333")
    # stereo normals: R takes L when unpatched
    for x in CH_X[6:]:
        s.append(f'<line x1="{x:.2f}" y1="{ROW["in"] + 4.6:.2f}" x2="{x:.2f}" y2="{ROW["in_r"] - 4.6:.2f}" '
                 'stroke="#111" stroke-width="0.45" stroke-dasharray="0.1 1.0" stroke-linecap="round"/>')
    lx, ly = f["RETURN L"]
    rxx, _ = f["RETURN R"]
    s.append(f'<line x1="{lx + 4.6:.2f}" y1="{ly:.2f}" x2="{rxx - 4.6:.2f}" y2="{ly:.2f}" stroke="#111" '
             'stroke-width="0.45" stroke-dasharray="0.1 1.0" stroke-linecap="round"/>')
    # master section labels
    text(s, sx, sy - 6.0, "SEND", 2.0, fill="#fff")
    text(s, f["FX IN"][0], sy - 6.0, "FX IN", 2.0)
    text(s, lx, ly - 5.4, "RET L", 2.0)
    text(s, rxx, ly - 5.4, "RET R", 2.0)
    text(s, MC, ROW["level"] - 6.4, "RETURN", 2.0)
    text(s, MC, ROW["mute"] - 5.9, "DRUMS", 2.0)
    text(s, MC, ROW["in"] - 8.0, "MASTER", 2.2)
    text(s, ox, oy + 7.6, "OUT L", 2.0, fill="#fff")
    text(s, rx_, oy + 7.6, "OUT R", 2.0, fill="#fff")
    text(s, W / 2, H - 4.2, "mono 1-6: IN · stereo 7-8: L, R (R follows L) · lever up = on", 1.6,
         weight="normal", fill="#444")

    # dimensions outside the panel
    text(s, W / 2, H + 7.5, f"{HP}HP · {W} × {H} mm · 1:1 when printed at 100 %", 2.2, weight="normal")
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def drill_svg(feats, path):
    s = header("Stereo mixer 28HP panel - drill template (print at 100%)")
    s.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.25"/>')
    for kind, lab, x, y, ref, _ in feats:
        d = HOLE[kind]
        s.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{d / 2:.2f}" fill="none" stroke="#c00" stroke-width="0.2"/>')
        s.append(f'<line x1="{x - 1.5:.2f}" y1="{y:.2f}" x2="{x + 1.5:.2f}" y2="{y:.2f}" stroke="#000" stroke-width="0.12"/>')
        s.append(f'<line x1="{x:.2f}" y1="{y - 1.5:.2f}" x2="{x:.2f}" y2="{y + 1.5:.2f}" stroke="#000" stroke-width="0.12"/>')
        if kind != "mount":
            s.append(f'<text class="dim" x="{x + d / 2 + 0.5:.2f}" y="{y - d / 2 - 0.2:.2f}">Ø{d}</text>')
            s.append(f'<text class="dim" x="{x:.2f}" y="{y + d / 2 + 1.9:.2f}" text-anchor="middle">{ref.split(" ")[0]}</text>')
    s.append('<line x1="5" y1="-8" x2="55" y2="-8" stroke="#000" stroke-width="0.3"/>')
    for x in (5, 55):
        s.append(f'<line x1="{x}" y1="-9.5" x2="{x}" y2="-6.5" stroke="#000" stroke-width="0.3"/>')
    s.append('<text x="30" y="-10" font-size="2.2" text-anchor="middle">50 mm - print at 100 %, check this</text>')
    s.append(f'<text x="{W / 2}" y="{H + 8}" font-size="2" text-anchor="middle">Stereo mixer 28HP panel, front view. '
             'Red circles: final hole size. Centre-punch the crosses, pilot-drill 2 mm, then step up.</text>')
    s.append(f'<text x="{W / 2}" y="{H + 11}" font-size="2" text-anchor="middle">Toggles (ATE1D/ATE2D) have no '
             'panel nut: the board holds them. Check the lever swings freely in 5 mm; open up if it rubs.</text>')
    s.append('</svg>')
    open(path, "w", encoding="utf-8").write("\n".join(s))


def check(feats):
    """Clearances between neighbouring parts, using knob and nut sizes."""
    size = {"pot": None, "jack": 8.5, "toggle": 6.0, "mount": 4.0}
    items = []
    for kind, lab, x, y, ref, knob in feats:
        d = KNOB[knob] if kind == "pot" else size[kind]
        items.append((lab, x, y, d))
    worst = []
    for i, (a, xa, ya, da) in enumerate(items):
        for b, xb, yb, db in items[i + 1:]:
            gap = ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5 - (da + db) / 2
            if gap < 2.0:
                worst.append((round(gap, 2), a, b))
        edge = min(xa, W - xa) - da / 2
        if edge < 2.5 and a != "mounting":
            worst.append((round(edge, 2), a, "panel edge"))
    return sorted(worst)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    feats = features()
    layout_svg(feats, os.path.join(OUTDIR, "stereo-mixer-panel.svg"))
    drill_svg(feats, os.path.join(OUTDIR, "stereo-mixer-panel-drill.svg"))
    with open(os.path.join(OUTDIR, "stereo-mixer-panel-holes.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["part", "label", "ref", "x_mm_from_left", "y_mm_from_top", "hole_mm"])
        for kind, lab, x, y, ref, _ in feats:
            w.writerow([kind, lab, ref, f"{x:.2f}", f"{y:.2f}", HOLE[kind]])
    tight = check(feats)
    for gap, a, b in tight:
        print(f"tight: {a} - {b}: {gap} mm")
    n = {k: sum(1 for f in feats if f[0] == k) for k in HOLE}
    print(f"{HP}HP panel: {n}; {len(tight)} tight spots (< 2 mm between knob/nut edges)")


if __name__ == "__main__":
    main()
