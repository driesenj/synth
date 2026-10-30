#!/usr/bin/env python3
"""VirtualDJ control panel: layout, 1:1 drill template, hole table, DXF.

    python make_panel.py [--svg DIR]

Writes vdj-panel.html (three A4 landscape pages; print it, or save it as PDF,
at 100 %) and vdj-panel.dxf (outline, holes, slots in mm) next to this file.
--svg also writes each page as its own SVG into DIR.

Coordinates everywhere are mm from the panel's top-left corner, front view,
x to the right, y down. Only the DXF flips y (its origin is bottom-left).
Edit the part constants or the positions below and re-run; the script warns
when two parts get too close, front or back.
"""
import math
import os
import sys
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- panel and parts --------------------------------------------------------
W, H = 297.0, 210.0             # A4
CX = W / 2

POT_HOLE = 7.0                  # cheap 16 mm pot (WH148 type), M7 bushing
BTN_HOLE = 16.0                 # TinyTronics AB6Y-M-BLACK, M16x1
FIX_HOLE = 3.2                  # M3 panel fixing
TRAVEL = 45.0                   # Bourns PTA4543
SLOT_W, SLOT_L = 3.0, 50.0      # lever 0.9 thick, ~3 long at panel height
M2_PITCH, M2_HOLE = 56.0, 2.4   # PTA4543 dim. B: M2x0.4 tapped, on the slot axis

# envelopes for the clearance check
KNOB_D = 20.0                   # biggest knob planned for
BEZEL_D = 18.0                  # AB6Y head
CAP_ALONG, CAP_ACROSS = 12.0, 22.0    # fader cap
POT_BODY_D = 17.0               # behind the panel
NUT_D = 24.0                    # M16 plastic nut, across corners
BODY_ALONG, BODY_ACROSS = 62.0, 10.0  # PTA body incl. pins
MIN_GAP = 5.0                   # finger room between front envelopes
EDGE = 10.0                     # front envelope to panel edge (enclosure wall)

# ---- positions --------------------------------------------------------------
parts = []


def add(kind, pid, label, x, y, vertical=False):
    parts.append(dict(kind=kind, id=pid, label=label, x=float(x), y=float(y),
                      vertical=vertical))


ROW_TOP, ROW_FX, ROW_LOOP, ROW_TRANSPORT = 26, 82, 130, 178
DECK_X = {"A": (24, 56, 88), "B": (W - 88, W - 56, W - 24)}
MIX_DX = 19                     # mixer columns at CX -/+ this
DIVIDER = (DECK_X["A"][2] + CX - MIX_DX) / 2    # deck | mixer, A side


def deck(d):
    """Keeps the skin's left-to-right order; MATCH sits next to the mixer,
    the channel's phones button beside it."""
    xs = DECK_X[d]
    add("btn", f"{d}-MATCH", "MATCH", xs[2] if d == "A" else xs[0], ROW_TOP)
    add("btn", f"{d}-PHONES", "PHONES", xs[1], ROW_TOP)
    for x, name in zip(xs, ("FILTER", "FLANGER", "CUT")):
        add("pot", f"{d}-{name}", name, x, ROW_FX)
    for x, (pid, name) in zip(xs, (("LOOP-HALF", "LOOP ÷2"), ("LOOP", "LOOP"),
                                   ("LOOP-DBL", "LOOP ×2"))):
        add("btn", f"{d}-{pid}", name, x, ROW_LOOP)
    for x, name in zip(xs, ("CUE", "PLAY", "SYNC")):
        add("btn", f"{d}-{name}", name, x, ROW_TRANSPORT)


def mixer():
    """One column per channel, EQ over the volume fader as on a hardware
    mixer; the fader is centred on the loop row, the crossfader on the
    transport row."""
    for d, side in (("A", -1), ("B", 1)):
        x = CX + side * MIX_DX
        for y, name in zip((ROW_TOP, (ROW_TOP + ROW_FX) / 2, ROW_FX), ("VOCAL", "INSTRU", "BEAT")):
            add("pot", f"M-{name}-{d}", name, x, y)
        add("fader", f"M-VOL-{d}", f"VOLUME {d}", x, ROW_LOOP, vertical=True)
    add("fader", "M-XFADER", "CROSSFADER", CX, ROW_TRANSPORT)


deck("A")
mixer()
deck("B")

for n, (x, y) in enumerate(((7, 7), (CX, 7), (W - 7, 7),
                            (7, H - 7), (CX, H - 7), (W - 7, H - 7)), 1):
    add("fix", f"FIX-{n}", "M3 fixing", x, y)


# ---- geometry ---------------------------------------------------------------
def _rect(p, along, across):
    w, h = (across, along) if p["vertical"] else (along, across)
    return ("r", p["x"], p["y"], w, h)


def front(p):
    k = p["kind"]
    if k == "fader":
        return _rect(p, TRAVEL + CAP_ALONG, CAP_ACROSS)
    r = {"pot": KNOB_D, "btn": BEZEL_D, "fix": 6.0}[k] / 2
    return ("c", p["x"], p["y"], r)


def rear(p):
    k = p["kind"]
    if k == "fader":
        return _rect(p, BODY_ALONG, BODY_ACROSS)
    r = {"pot": POT_BODY_D, "btn": NUT_D, "fix": 6.0}[k] / 2
    return ("c", p["x"], p["y"], r)


def gap(a, b):
    if a[0] == "r" and b[0] == "c":
        a, b = b, a
    if a[0] == "c" and b[0] == "c":
        return math.hypot(a[1] - b[1], a[2] - b[2]) - a[3] - b[3]
    if a[0] == "c":
        dx = max(abs(a[1] - b[1]) - b[3] / 2, 0)
        dy = max(abs(a[2] - b[2]) - b[4] / 2, 0)
        return math.hypot(dx, dy) - a[3]
    dx = abs(a[1] - b[1]) - (a[3] + b[3]) / 2
    dy = abs(a[2] - b[2]) - (a[4] + b[4]) / 2
    return math.hypot(dx, dy) if dx > 0 and dy > 0 else max(dx, dy)


def bbox(s):
    if s[0] == "c":
        return s[1] - s[3], s[2] - s[3], s[1] + s[3], s[2] + s[3]
    return s[1] - s[3] / 2, s[2] - s[4] / 2, s[1] + s[3] / 2, s[2] + s[4] / 2


def check():
    warnings = []
    for side, shape, need in (("front", front, MIN_GAP), ("rear", rear, 1.0)):
        worst = None
        for i, a in enumerate(parts):
            for b in parts[i + 1:]:
                if a["kind"] == b["kind"] == "fix":
                    continue
                g = gap(shape(a), shape(b))
                if worst is None or g < worst[0]:
                    worst = (g, a["id"], b["id"])
                if g < need:
                    warnings.append(f"{side}: {a['id']} / {b['id']} gap {g:.1f} mm")
        print(f"tightest {side} gap: {worst[0]:.1f} mm ({worst[1]} / {worst[2]})")
    for p in parts:
        if p["kind"] == "fix":
            continue
        x0, y0, x1, y1 = bbox(front(p))
        m = min(x0, y0, W - x1, H - y1)
        if m < EDGE:
            warnings.append(f"edge: {p['id']} {m:.1f} mm from the panel edge")
    for w in warnings:
        print("WARNING", w)
    return warnings


def holes(p):
    """(kind, x, y, size) per hole: ("hole", x, y, d) or ("slot", x, y, vertical)."""
    x, y = p["x"], p["y"]
    if p["kind"] == "fader":
        dx, dy = (0, M2_PITCH / 2) if p["vertical"] else (M2_PITCH / 2, 0)
        return [("slot", x, y, p["vertical"]),
                ("hole", x - dx, y - dy, M2_HOLE), ("hole", x + dx, y + dy, M2_HOLE)]
    d = {"pot": POT_HOLE, "btn": BTN_HOLE, "fix": FIX_HOLE}[p["kind"]]
    return [("hole", x, y, d)]


# ---- svg helpers ------------------------------------------------------------
def f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def text(x, y, s, size=2.6, anchor="middle", weight="normal", fill="#222", rotate=None):
    t = f' transform="rotate({rotate} {f(x)} {f(y)})"' if rotate is not None else ""
    return (f'<text x="{f(x)}" y="{f(y)}" font-size="{f(size)}" text-anchor="{anchor}" '
            f'font-weight="{weight}" fill="{fill}"{t}>{escape(s)}</text>')


def line(x1, y1, x2, y2, w=0.15, color="#000", extra=""):
    return (f'<line x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" '
            f'stroke="{color}" stroke-width="{f(w)}"{extra}/>')


def circle(x, y, r, stroke="#000", w=0.25, fill="none"):
    return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" stroke="{stroke}" '
            f'stroke-width="{f(w)}" fill="{fill}"/>')


def slot_rect(x, y, vertical, fill="none", stroke="#000", w=0.25):
    sw, sh = (SLOT_W, SLOT_L) if vertical else (SLOT_L, SLOT_W)
    return (f'<rect x="{f(x - sw / 2)}" y="{f(y - sh / 2)}" width="{f(sw)}" height="{f(sh)}" '
            f'rx="{f(SLOT_W / 2)}" fill="{fill}" stroke="{stroke}" stroke-width="{f(w)}"/>')


def page(body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(W)}mm" height="{f(H)}mm" '
            f'viewBox="0 0 {f(W)} {f(H)}" font-family="Arial, Helvetica, sans-serif">'
            f'<rect width="{f(W)}" height="{f(H)}" fill="#fff"/>{body}</svg>')


def wrap(s, width):
    out, cur = [], ""
    for word in s.split():
        if cur and len(cur) + 1 + len(word) > width:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return out + [cur] if cur else out


# ---- page 1: layout ---------------------------------------------------------
ORANGE, GREEN, PURPLE = "#E8772E", "#2E9E4F", "#8E44AD"


def layout_page():
    o = [f'<rect x="0.2" y="0.2" width="{f(W - 0.4)}" height="{f(H - 0.4)}" '
         f'fill="#fafafa" stroke="#222" stroke-width="0.4"/>']
    for x in (DIVIDER, W - DIVIDER):
        o.append(line(x, 16, x, 194, 0.25, "#bbb", ' stroke-dasharray="1.5 1.5"'))
    o.append(text(DECK_X["A"][0], ROW_TOP + 4.5, "A", 13, weight="bold", fill="#ccc"))
    o.append(text(DECK_X["B"][2], ROW_TOP + 4.5, "B", 13, weight="bold", fill="#ccc"))
    for p in parts:
        x, y, k = p["x"], p["y"], p["kind"]
        if k == "pot":
            r = KNOB_D / 2
            o.append(circle(x, y, r, ORANGE, 0.6, "#FDE9DA"))
            o.append(circle(x, y, r - 2.5, ORANGE, 0.3, "#fff"))
            o.append(line(x, y - 1.5, x, y - r + 1, 0.9, "#7a3a10", ' stroke-linecap="round"'))
            o.append(text(x, y + r + 3.6, p["label"], 2.7, weight="bold"))
        elif k == "btn":
            r = BEZEL_D / 2
            o.append(circle(x, y, r, PURPLE, 0.6, "#EFE3F8"))
            o.append(circle(x, y, r - 2, PURPLE, 0.3, "#fff"))
            o.append(text(x, y + r + 3.6, p["label"], 2.7, weight="bold"))
        elif k == "fader":
            o.append(slot_rect(x, y, p["vertical"], "#444", "#444", 0.1))
            for hk, hx, hy, hd in holes(p)[1:]:
                o.append(circle(hx, hy, hd / 2, "#999", 0.2))
            cw, ch = (CAP_ACROSS, CAP_ALONG) if p["vertical"] else (CAP_ALONG, CAP_ACROSS)
            cy = y - TRAVEL / 4 if p["vertical"] else y      # volume shown at 3/4
            o.append(f'<rect x="{f(x - cw / 2)}" y="{f(cy - ch / 2)}" width="{f(cw)}" '
                     f'height="{f(ch)}" rx="1.5" fill="#DDF3E3" stroke="{GREEN}" stroke-width="0.6"/>')
            if p["vertical"]:
                o.append(line(x - cw / 2 + 2, cy, x + cw / 2 - 2, cy, 0.5, GREEN))
                o.append(text(x, y + (TRAVEL + CAP_ALONG) / 2 + 3.6, p["label"], 2.7, weight="bold"))
            else:
                o.append(line(x, cy - ch / 2 + 2, x, cy + ch / 2 - 2, 0.5, GREEN))
                o.append(text(x, y + CAP_ACROSS / 2 + 3.6, p["label"], 2.7, weight="bold"))
        elif k == "fix":
            o.append(circle(x, y, FIX_HOLE / 2, "#999", 0.25))
    o.append(text(16, 202, "VDJ CONTROLLER  ·  PANEL LAYOUT 1:1  ·  297 × 210 mm (A4)  ·  front view",
                  2.6, "start", fill="#555"))
    lx = 200
    for color, fill, s in ((ORANGE, "#FDE9DA", "rotary pot ×12"), (GREEN, "#DDF3E3", "slide pot ×3"),
                           (PURPLE, "#EFE3F8", "button ×16")):
        o.append(circle(lx, 201.1, 1.6, color, 0.5, fill))
        o.append(text(lx + 2.8, 202, s, 2.6, "start", fill="#555"))
        lx += 26
    return page("".join(o))


# ---- page 2: drill template -------------------------------------------------
def crosshair(x, y, r, ext=3.0):
    return (line(x - r - ext, y, x + r + ext, y) + line(x, y - r - ext, x, y + r + ext) +
            circle(x, y, r) + f'<circle cx="{f(x)}" cy="{f(y)}" r="0.35" fill="#000"/>')


def drill_page():
    o = [f'<rect x="0.15" y="0.15" width="{f(W - 0.3)}" height="{f(H - 0.3)}" '
         f'fill="none" stroke="#000" stroke-width="0.3"/>']
    for p in parts:
        for kind, x, y, s in holes(p):
            if kind == "slot":
                o.append(slot_rect(x, y, s))
                half = SLOT_L / 2 - SLOT_W / 2
                ext = M2_PITCH / 2 + 4
                if s:
                    o.append(line(x, y - ext, x, y + ext, 0.12, "#000", ' stroke-dasharray="2 1"'))
                    ends = ((x, y - half), (x, y + half))
                    o.append(text(x + 4.5, y, f"SLOT {f(SLOT_W)} × {f(SLOT_L)}", 2.2, rotate=90))
                else:
                    o.append(line(x - ext, y, x + ext, y, 0.12, "#000", ' stroke-dasharray="2 1"'))
                    ends = ((x - half, y), (x + half, y))
                    o.append(text(x, y - 4, f"SLOT {f(SLOT_L)} × {f(SLOT_W)}", 2.2))
                for ex, ey in ends:
                    o.append(line(ex - 3.5, ey, ex + 3.5, ey) +
                             f'<circle cx="{f(ex)}" cy="{f(ey)}" r="0.35" fill="#000"/>')
                o.append(text(x - 4.5 if s else x, y if s else y + 6.2, p["id"], 2.0,
                              fill="#666", rotate=-90 if s else None))
            else:
                r = s / 2
                o.append(crosshair(x, y, r, 3.0 if s > 3 else 2.0))
                if p["kind"] == "fader":
                    o.append(text(x + 3.2, y + 0.8 if p["vertical"] else y - 3, "M2", 2.0, "start", fill="#666"))
                    continue
                lx = r * 0.71 + 0.8
                if x > W - 20:      # keep it on the paper
                    o.append(text(x - lx, y - lx, f"Ø{f(s)}", 2.4, "end", "bold"))
                else:
                    o.append(text(x + lx, y - lx, f"Ø{f(s)}", 2.4, "start", "bold"))
                if p["kind"] != "fix":
                    o.append(text(x, y + r + 5.6, p["id"], 2.0, fill="#666"))
    # scale bars
    x0, yb = 20, 197
    o.append(line(x0, yb, x0 + 100, yb, 0.25))
    for i in range(11):
        t = 2.5 if i in (0, 5, 10) else 1.2
        o.append(line(x0 + i * 10, yb - t, x0 + i * 10, yb, 0.2))
    o.append(text(x0 + 50, yb + 3.4, "must measure 100.0 mm", 2.2))
    xv, y0 = DIVIDER, ROW_LOOP - 35
    o.append(line(xv, y0, xv, y0 + 50, 0.25))
    for i in range(6):
        t = 2.5 if i in (0, 5) else 1.2
        o.append(line(xv - t, y0 + i * 10, xv, y0 + i * 10, 0.2))
    o.append(text(xv + 3, y0 + 25, "50.0 mm", 2.2, rotate=90))
    # the free band between the top row and the FX row, one block per deck
    ty = (ROW_TOP + ROW_FX) / 2 - 4
    for i, (s, size, weight) in enumerate((
            ("VDJ CONTROLLER", 3.2, "bold"), ("DRILL TEMPLATE 1:1", 3.2, "bold"),
            ("front view · print at 100 % / actual size", 2.4, "normal"))):
        o.append(text(14, ty + i * 4.6, s, size, "start", weight))
    for i, s in enumerate(("check both scale bars before drilling", "tape to the FRONT face",
                           "centre-punch every dot, pilot Ø3, open up",
                           "M3 marks: 7 mm from both edges")):
        o.append(text(W - 14, ty + i * 4.4, s, 2.4, "end"))
    return page("".join(o))


# ---- page 3: hole table and notes -------------------------------------------
def describe(p):
    k = p["kind"]
    if k == "pot":
        return "rotary pot", f"Ø{f(POT_HOLE)}"
    if k == "btn":
        return "button", f"Ø{f(BTN_HOLE)}"
    if k == "fix":
        return "panel fixing", f"Ø{f(FIX_HOLE)}"
    return "slide pot", f"slot {f(SLOT_W)}×{f(SLOT_L)} {'vert.' if p['vertical'] else 'horiz.'}"


NOTES = [
    ("PARTS", [
        "12 × rotary pot, cheap 16 mm (WH148 type), 10 k lin, M7 bushing: Ø7. "
        "Twist off the anti-rotation tab, or drill a Ø3 for it using the pot as a jig. Knobs up to Ø20.",
        "3 × Bourns PTA4543-2015DPB103 (45 mm travel, 15 mm metal lever, 10 k lin). "
        "Hangs under the panel on 2 × M2 countersunk screws, 56 mm apart on the slot axis; "
        "screw length = panel + 2 mm at most, the tapped holes are shallow.",
        "16 × TinyTronics AB6Y-M-BLACK, 16 mm momentary (not AB6Y-A: that one latches). "
        "Ø16, M16×1 nut, panel up to 7 mm, 2.8 mm spade terminals, 32 mm deep.",
        "6 × M3 panel fixing — optional, move them to suit the enclosure.",
    ]),
    ("PANEL", [
        "297 × 210 mm (A4), 2–4 mm aluminium or acrylic. The pots' M7 thread is the "
        "thickness limit; on 3 mm the fader levers stand 12 mm proud for the caps.",
        "Leave ≥ 35 mm inside the enclosure (buttons are 32 mm deep). Behind the panel "
        "nothing comes within 12 mm of the edge, so walls up to ~11 mm thick clear everything.",
        "Spacing: deck columns 32 mm, mixer columns 38 mm, EQ rows 28 mm, deck rows ~50 mm. "
        "Every row lines up across the whole panel.",
    ]),
    ("DRILLING", [
        "Print page 2 at 100 % (\"actual size\", no fit-to-page). Check the 100 mm and 50 mm "
        "bars with a ruler — printers can scale x and y differently. The M3 marks are 7 mm "
        "from both edges: align the sheet by those if the printer shifted the image.",
        "Tape it to the FRONT face. Centre-punch every dot (slot ends included), pilot Ø3 everywhere.",
        "Ø16 and Ø7: step drill. Slots: Ø3 at both end marks, cut between with a fret/coping saw, "
        "file to the lines; that gives the lever 1 mm spare at each end of travel.",
        "Drill the M2 holes before the slots: there is only 1.8 mm of web between them.",
    ]),
]


def table_page():
    o = [text(12, 14, "HOLE TABLE", 4.2, "start", "bold"),
         text(52, 14, "mm from the panel's top-left corner, front view (y down)", 2.8, "start", fill="#555")]
    rows = []
    for p in parts:
        what, hole = describe(p)
        rows.append((p["id"], p["label"] if p["kind"] != "fix" else "", what, hole, p["x"], p["y"]))
        if p["kind"] == "fader":
            for i, (_, hx, hy, _) in enumerate(holes(p)[1:], 1):
                rows.append((f"{p['id']}.{i}", "", "fader screw", f"Ø{f(M2_HOLE)} (M2)", hx, hy))
    per_col = math.ceil(len(rows) / 2)
    cols = ((12, rows[:per_col]), (155, rows[per_col:]))
    for x0, chunk in cols:
        y = 22
        for hdr, dx, anchor in (("ID", 0, "start"), ("CONTROL", 25, "start"), ("PART", 50, "start"),
                                ("HOLE", 72, "start"), ("X", 116, "end"), ("Y", 130, "end")):
            o.append(text(x0 + dx, y, hdr, 2.4, anchor, "bold", "#555"))
        o.append(line(x0, y + 1.2, x0 + 131, y + 1.2, 0.2, "#555"))
        for i, (pid, label, what, hole, x, yy) in enumerate(chunk):
            ry = y + 5 + i * 4.3
            if i % 2:
                o.append(f'<rect x="{f(x0 - 1)}" y="{f(ry - 3)}" width="133" height="4.3" fill="#f2f2f2"/>')
            for s, dx, anchor in ((pid, 0, "start"), (label, 25, "start"), (what, 50, "start"),
                                  (hole, 72, "start"), (f"{x:.1f}", 116, "end"), (f"{yy:.1f}", 130, "end")):
                o.append(text(x0 + dx, ry, s, 2.4, anchor))
    top = 22 + 5 + per_col * 4.3 + 6
    for c, (title, paras) in enumerate(NOTES):
        x0 = 12 + c * 94
        y = top
        o.append(text(x0, y, title, 3.0, "start", "bold"))
        y += 4.6
        for para in paras:
            for ln in wrap(para, 64):
                o.append(text(x0, y, ln, 2.35, "start"))
                y += 3.3
            y += 1.4
    return page("".join(o))


# ---- dxf --------------------------------------------------------------------
def dxf():
    out = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009",
           "9", "$INSUNITS", "70", "4", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]

    def ent(kind, layer, *codes):
        out.extend(["0", kind, "8", layer])
        for code, value in codes:
            out.extend([str(code), f"{value:.4f}" if isinstance(value, float) else str(value)])

    def seg(x1, y1, x2, y2, layer):
        ent("LINE", layer, (10, x1), (20, H - y1), (30, 0.0), (11, x2), (21, H - y2), (31, 0.0))

    def arc(x, y, r, a0, a1, layer):
        ent("ARC", layer, (10, x), (20, H - y), (30, 0.0), (40, r), (50, float(a0)), (51, float(a1)))

    for x1, y1, x2, y2 in ((0, 0, W, 0), (W, 0, W, H), (W, H, 0, H), (0, H, 0, 0)):
        seg(float(x1), float(y1), float(x2), float(y2), "OUTLINE")
    r, half = SLOT_W / 2, SLOT_L / 2 - SLOT_W / 2
    for p in parts:
        for kind, x, y, s in holes(p):
            if kind == "hole":
                ent("CIRCLE", "HOLES", (10, x), (20, H - y), (30, 0.0), (40, s / 2))
            elif s:   # vertical: top end is the smaller panel y
                arc(x, y - half, r, 0, 180, "SLOTS")
                arc(x, y + half, r, 180, 360, "SLOTS")
                seg(x - r, y - half, x - r, y + half, "SLOTS")
                seg(x + r, y - half, x + r, y + half, "SLOTS")
            else:
                arc(x + half, y, r, 270, 90, "SLOTS")
                arc(x - half, y, r, 90, 270, "SLOTS")
                seg(x - half, y - r, x + half, y - r, "SLOTS")
                seg(x - half, y + r, x + half, y + r, "SLOTS")
    out.extend(["0", "ENDSEC", "0", "EOF"])
    return "\n".join(out) + "\n"


# ---- main -------------------------------------------------------------------
def main():
    check()
    pages = [layout_page(), drill_page(), table_page()]
    html = ('<!doctype html><html><head><meta charset="utf-8"><title>VDJ panel</title><style>'
            '@page{size:297mm 210mm;margin:0}html,body{margin:0;padding:0}'
            '.page{width:297mm;height:210mm;overflow:hidden;break-after:page}'
            '.page:last-child{break-after:auto}svg{display:block}</style></head><body>' +
            "".join(f'<div class="page">{p}</div>' for p in pages) + "</body></html>")
    with open(os.path.join(HERE, "vdj-panel.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    with open(os.path.join(HERE, "vdj-panel.dxf"), "w", encoding="ascii", newline="\r\n") as fh:
        fh.write(dxf())
    if "--svg" in sys.argv:
        d = sys.argv[sys.argv.index("--svg") + 1]
        os.makedirs(d, exist_ok=True)
        for i, p in enumerate(pages, 1):
            with open(os.path.join(d, f"page-{i}.svg"), "w", encoding="utf-8") as fh:
                fh.write(p)
    print(f"{len(parts)} parts, {sum(len(holes(p)) for p in parts)} holes/slots")


if __name__ == "__main__":
    main()
