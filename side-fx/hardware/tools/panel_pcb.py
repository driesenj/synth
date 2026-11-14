"""The Side FXy panel as an EasyEDA Pro PCB (the third board in SideFXy.epro2).
The mixer's panel writer (stereo-mixer/hardware/tools/panel_pcb.py), drawing
from panel.layout() and panel.copper(), the same lists the SVG artwork is
made from, so the two never drift apart. Seen from the front, the PCB's top
layer: x to the right, y up, origin at the panel's bottom-left corner.

  outline        70.8 x 128.5 mm (14HP)
  holes          non-plated: jacks, buttons, encoders; mounting slots 5.5 x 3.2;
                 the display window as a milled cutout with rounded corners
  silkscreen     title, labels, button rings, the IN 1 -> IN 2 dots
  copper         the OUT 1 / 2 band and the block stack behind the knobs: copper
                 fills on the top layer under solder-mask openings of the same
                 shape (bare ENIG gold), cleared 0.4 mm round each hole. A knob
                 sits on a block's edge or corner, so its clearance bites into the
                 block's outline (an arc in place of the edge); holes inside a
                 fill are counter-clockwise cutouts, as on the mixer

Text uses EasyEDA's default stroke font, placed with its measured metrics (INK_*, ink_width), so the letters sit where the artwork has them. Nothing electrical: no nets, no parts.
"""
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location("sidefx_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


panel = _load("panel")
pcb = _load("pcb")
mil = pcb.mil
SILK_W = 0.3          # mm, line width on silk
CHAR_W = 0.62         # estimated advance per character, as a fraction of the font size (default stroke font)

# EasyEDA Pro's default stroke font, measured on its own Gerbers (2026-11-14: Gerber_Compressor_PCB and
# Gerber_Sequencer_PCB against the strings and designators in their project). For fontSize F (0.9 x size here)
# and stroke w, a LEFT_BOTTOM string's ink runs from its origin x to x + w + the advances of all but its last
# character + that one's extent, and from 0.2 F to 0.885 F above the origin: the origin sits below the
# baseline. text() places strings with these numbers, so the letters land where the artwork has them.
INK_BOTTOM, INK_TOP = 0.2, 0.885
ADVANCE = {"1": 0.40, ".": 0.23, "I": 0.30}      # x F; any other character 0.64
EXTENT = {"1": 0.14, ".": 0.0, "I": 0.0}         # x F; any other character 0.38
MIN_STROKE = 0.16      # mm; JLCPCB's minimum is 0.153
# Labels on a gold area can't be silk: fabs clip silk inside solder-mask openings. They are knocked out of the
# mask instead: the area's mask opening gets a hole round the letters, and a reverse STRING on the mask layer (an
# opening with the letters left masked, its box KNOCK_EXPANSION round them) fills the hole again but for the
# letters, which read dark on the gold, as in the artwork. The hole sits inside that box with room for the
# metrics' error.
KNOCK_MARGIN = 0.35    # mm round the letters: the hole in the gold area's mask opening
KNOCK_EXPANSION = 0.8  # mm round the letters: the reverse string's box


def ink_width(s, size, w):
    F = 0.9 * size
    return w + sum(ADVANCE.get(c, 0.64) * F for c in s[:-1]) + EXTENT.get(s[-1], 0.38) * F


def ink_box(x, y, s, size, w, angle=0):
    """The letters' box (x1, y1, x2, y2), PCB frame, of a STRING with its origin at (x, y), angle 0 or 90."""
    F = 0.9 * size
    L, B, T = ink_width(s, size, w), INK_BOTTOM * F, INK_TOP * F
    if angle == 90:                       # reading bottom to top: the letters' up is -x
        return x - T, y, x - B, y + L
    return x, y + B, x + L, y + T


def inside(p, poly):
    """Point in polygon (ray casting)."""
    x, y = p
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def _rect_boundary(x, y, w, h, r, step=0.1):
    """Points round a rounded rectangle (panel frame, y down), clockwise on the panel, closed implicitly."""
    pts = []

    def line(x1, y1, x2, y2):
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / step))
        pts.extend((x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n))

    def corner(cx, cy, a0):
        for i in range(18):                   # 90 degrees in 5-degree steps
            a = math.radians(a0 + 5 * i)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    line(x + r, y, x + w - r, y)
    if r:
        corner(x + w - r, y + r, -90)
    line(x + w, y + r, x + w, y + h - r)
    if r:
        corner(x + w - r, y + h - r, 0)
    line(x + w - r, y + h, x + r, y + h)
    if r:
        corner(x + r, y + h - r, 90)
    line(x, y + h - r, x, y + r)
    if r:
        corner(x + r, y + r, 180)
    return pts


def rect_minus_discs(x, y, w, h, r, discs):
    """A rounded rectangle with the discs (cx, cy, radius) taken out, panel frame. Discs that cross the
    outline bite into it: the boundary inside the disc is replaced by the disc's arc that runs inside the
    rectangle. Returns (outline points, discs wholly inside, which stay circular cutouts)."""
    pts = _rect_boundary(x, y, w, h, r)

    def in_disc(p, d):
        return math.hypot(p[0] - d[0], p[1] - d[1]) < d[2]

    def in_rect(p):
        return x <= p[0] <= x + w and y <= p[1] <= y + h

    crossing = [d for d in discs if any(in_disc(p, d) for p in pts)]
    inner = [d for d in discs if d not in crossing and in_rect(d[:2])]
    if not crossing:
        return pts, inner

    def which(p):
        return next((d for d in crossing if in_disc(p, d)), None)

    def edge(a, b, d):                         # a outside d, b inside: the crossing by bisection
        for _ in range(30):
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            a, b = (m, b) if not in_disc(m, d) else (a, m)
        return a

    def arc(d, p0, p1):
        a0 = math.atan2(p0[1] - d[1], p0[0] - d[0])
        a1 = math.atan2(p1[1] - d[1], p1[0] - d[0])
        for sweep in ((a1 - a0) % (2 * math.pi), -((a0 - a1) % (2 * math.pi))):
            mid = a0 + sweep / 2
            if in_rect((d[0] + d[2] * math.cos(mid), d[1] + d[2] * math.sin(mid))):
                n = max(2, int(abs(math.degrees(sweep)) / 5))
                return [(d[0] + d[2] * math.cos(a0 + sweep * i / n), d[1] + d[2] * math.sin(a0 + sweep * i / n))
                        for i in range(n + 1)]
        raise ValueError(f"no arc of the disc at ({d[0]:.2f}, {d[1]:.2f}) runs inside the block")

    n = len(pts)
    start = next(i for i, p in enumerate(pts) if which(p) is None)
    out, i, done = [], start, 0
    while done < n:
        p = pts[i % n]
        d = which(p)
        if d is None:
            out.append(p)
            i, done = i + 1, done + 1
            continue
        entry = edge(pts[(i - 1) % n], p, d)
        j = i
        while which(pts[j % n]) is d:
            j, done = j + 1, done + 1
        out += arc(d, entry, edge(pts[j % n], pts[(j - 1) % n], d))
        i = j
    return _simplify(out), inner


def _simplify(pts, tol=1e-4):
    """Drop points that sit on the straight line between their neighbours."""
    out = []
    for k, p in enumerate(pts):
        a, b = pts[k - 1], pts[(k + 1) % len(pts)]
        if abs((p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])) > tol:
            out.append(p)
    return out


class PanelBoard:
    """Collects silk, holes and copper, then writes the PCB doc (same call as pcb.Board.doc)."""

    def __init__(self):
        self.W, self.H = panel.PANEL_W, panel.PANEL_H
        self.silk_lines, self.strings, self.holes, self.slots, self.windows, self.arcs = [], [], [], [], [], []
        self.gold = []        # the mushroom mark's polygons, PCB frame
        self.fills = []       # (outline points, cutout circles), PCB frame
        self.placed = []      # so the project writer can count parts (none)
        self.build()

    # -- frame: panel mm from the top-left, y down -> PCB mm, y up
    def P(self, x, y):
        return x, self.H - y

    # -- primitives (panel frame)
    def line(self, pts, w=SILK_W):
        self.silk_lines.append(([self.P(x, y) for x, y in pts], w))

    def text(self, x, y, s, size, anchor="middle", w=None):
        """x, y: baseline point in the panel frame; anchor middle / start / end. Placed with EasyEDA's font
        metrics (ink_width, INK_BOTTOM), so the letters sit on the baseline and centre as in the artwork."""
        w = w or max(size / 9, MIN_STROKE)
        width = ink_width(s, size, w)
        x0 = {"middle": x - width / 2, "start": x, "end": x - width}[anchor]
        self.strings.append((*self.P(x0, y + INK_BOTTOM * 0.9 * size), s, size, w, 0))

    def dots(self, pts, pitch=1.0, dash=0.12, w=0.45):
        """A dotted polyline as short dashes (EasyEDA has no dashed silk)."""
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            d = math.hypot(x2 - x1, y2 - y1)
            n = max(1, int(d / pitch))
            for i in range(n + 1):
                t = i / n
                px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                ux, uy = ((x2 - x1) / d, (y2 - y1) / d) if d else (1, 0)
                self.line([(px - ux * dash / 2, py - uy * dash / 2), (px + ux * dash / 2, py + uy * dash / 2)], w)

    def arc(self, cx, cy, r, a0, a1, w=SILK_W):
        """Arc clockwise (on the panel) from a0 to a1, degrees from 12 o'clock; split into <= 90 deg pieces."""
        pieces = max(1, math.ceil((a1 - a0) / 90))
        for i in range(pieces):
            b0 = a0 + (a1 - a0) * i / pieces
            b1 = a0 + (a1 - a0) * (i + 1) / pieces
            p0 = self.P(cx + r * math.sin(math.radians(b0)), cy - r * math.cos(math.radians(b0)))
            p1 = self.P(cx + r * math.sin(math.radians(b1)), cy - r * math.cos(math.radians(b1)))
            self.arcs.append((p0, -(b1 - b0), p1, w, (cx, cy, r, b0, b1)))   # negative sweep = clockwise (y up)

    def ring(self, cx, cy, r, w=SILK_W):
        self.arc(cx, cy, r, 0, 360, w)

    # -- the artwork, from panel.layout() and panel.copper() like the SVG
    def build(self):
        feats = panel.features()
        pos = {ref: (kind, label, *panel.panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
        for item in panel.layout(pos):
            kind = item[0]
            if kind in ("text", "serif"):
                _, x, y, s, size, anchor = item
                self.text(x, y, s, size, anchor)
            elif kind == "gold":
                self.gold += [[self.P(x, y) for x, y in poly] for poly in item[1]]
            elif kind == "line":
                self.line(item[1], item[2])
            elif kind == "dots":
                self.dots(item[1])
            elif kind == "ring":
                _, x, y, r, w = item
                self.ring(x, y, r, w)
        # copper: the output band and the blocks, each with the holes through it taken out
        for (x, y, w, h, rx), cuts in panel.copper(pos):
            outline, inner = rect_minus_discs(x, y, w, h, rx, cuts)
            self.fills.append(([self.P(px, py) for px, py in outline], [(*self.P(cx, cy), r) for cx, cy, r in inner]))
        jl = {r: lbl for r, lbl, *_ in panel.circuit.JACKS}
        for ref in panel.OUTPUTS:
            self.text(pos[ref][2], panel.jack_label_y(pos, ref), jl[ref], panel.ART["label"])
        # holes and the display window
        for ref, (kind, label, x, y) in pos.items():
            if kind == "window":
                w, h = panel.WINDOW
                self.windows.append((*self.P(x - w / 2, y - h / 2), w, h, panel.WINDOW_R))
            else:
                self.holes.append((*self.P(x, y), panel.HOLE[kind]))
        for x, y in panel.MOUNTS:
            self.slots.append((*self.P(x, y), panel.SLOT_W, panel.SLOT_H))


    # -- labels on the gold areas, knocked out of the mask (see KNOCK_MARGIN)
    def gold_regions(self):
        """The gold fills' outlines, PCB frame."""
        return [outline for outline, inner in self.fills]

    def string_box(self, st):
        return ink_box(st[0], st[1], st[2], st[3], st[4], st[5] if len(st) > 5 else 0)

    def knocked(self):
        """{string index: gold area index} for the strings whose letters lie inside a gold area."""
        out = {}
        regions = self.gold_regions()
        for i, st in enumerate(self.strings):
            x1, y1, x2, y2 = self.string_box(st)
            for k, poly in enumerate(regions):
                if all(inside(p, poly) for p in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))):
                    out[i] = k
        return out

    def knock_expansion(self, i):
        """The reverse box's expansion for knocked string i: KNOCK_EXPANSION, or less where EasyEDA's box, if it
        is the font's em box (origin to origin + F tall, all advances wide), would leave the gold area."""
        st, poly = self.strings[i], self.gold_regions()[self.knocked()[i]]
        x, y, s, size, w = st[:5]
        F = 0.9 * size
        L = w + sum(ADVANCE.get(c, 0.64) * F for c in s)
        e = KNOCK_EXPANSION
        while e > KNOCK_MARGIN + 0.2:
            if (st[5] if len(st) > 5 else 0) == 90:
                r = (x - F - e, y - e, x + e, y + L + e)
            else:
                r = (x - e, y - e, x + L + e, y + F + e)
            if all(inside(p, poly) for p in ((r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3]))):
                break
            e -= 0.05
        return round(e, 2)

    def knock_paths(self, k):
        """Counter-clockwise rectangles round the letters on gold area k: holes in its mask opening."""
        paths = []
        for i, kk in self.knocked().items():
            if kk == k:
                x1, y1, x2, y2 = self.string_box(self.strings[i])
                x1, y1, x2, y2 = x1 - KNOCK_MARGIN, y1 - KNOCK_MARGIN, x2 + KNOCK_MARGIN, y2 + KNOCK_MARGIN
                paths.append([mil(x1), mil(y1), "L", mil(x2), mil(y1), "L", mil(x2), mil(y2), "L", mil(x1), mil(y2),
                              "L", mil(x1), mil(y1)])
        return paths

    # -- EasyEDA document
    def doc(self, ee, template, board_uuid, title):
        d = ee.Doc("PCB")
        knocked = self.knocked()
        for h, p in template:
            if h["type"] in pcb.TEMPLATE_TYPES:
                d.add(h["type"], h["id"], p)

        def fill(layer, *paths):
            d.add("FILL", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": layer, "width": 1,
                                    "fillStyle": "SOLID", "path": list(paths), "locked": False, "zIndex": d.zi(),
                                    "isBridgingCopper": False, "networkList": [], "refs": []})

        def cutout(x, y, r):
            """A counter-clockwise circle: inside a clockwise outline, EasyEDA's nonzero rule makes it a hole."""
            path = [mil(x + r), mil(y)]
            for px, py in ((x, y + r), (x - r, y), (x, y - r), (x + r, y)):
                path += ["ARC", 90, mil(px), mil(py)]
            return path

        def polygon(pts):
            """Closed L path, wound clockwise in the PCB frame (y up) like rounded()."""
            area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
            if area > 0:
                pts = pts[::-1]
            path = [mil(pts[0][0]), mil(pts[0][1])]
            for x, y in pts[1:] + pts[:1]:
                path += ["L", mil(x), mil(y)]
            return path

        for x, y, dia in self.holes:
            fill(12, ["CIRCLE", mil(x), mil(y), mil(dia / 2)])
        for x, y, w, h in self.slots:
            fill(12, pcb.rounded(x - w / 2, y + h / 2, w, h, h / 2))
        for x, y, w, h, r in self.windows:      # (x, y) the window's top-left in the PCB frame
            fill(12, pcb.rounded(x, y, w, h, r))
        for k_, (outline, inner) in enumerate(self.fills):       # top copper and its solder-mask opening: bare ENIG gold
            for layer in (1, 5):
                fill(layer, polygon(outline), *(cutout(*c) for c in inner), *(self.knock_paths(k_) if layer == 5 else []))
        for poly in self.gold:                    # the mushroom mark: top copper under a mask opening (ENIG)
            path = [mil(poly[0][0]), mil(poly[0][1])]
            for x, y in poly[1:]:
                path += ["L", mil(x), mil(y)]
            for layer in (1, 5):
                fill(layer, path)
        d.add("POLY", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 11, "width": 10,
                                "path": ["R", 0, mil(self.H), mil(self.W), mil(self.H), 0, 0], "locked": False,
                                "zIndex": d.zi(), "polyType": "BOARD_OUTLINE"})
        for pts, w in self.silk_lines:
            path = [mil(pts[0][0]), mil(pts[0][1])]
            for x, y in pts[1:]:
                path += ["L", mil(x), mil(y)]
            d.add("POLY", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 3, "width": mil(w),
                                    "path": path, "locked": False, "zIndex": d.zi(), "polyType": "NORMAL"})
        for p0, sweep, p1, w, _ in self.arcs:
            d.add("POLY", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 3, "width": mil(w),
                                    "path": [mil(p0[0]), mil(p0[1]), "ARC", round(sweep, 3), mil(p1[0]), mil(p1[1])],
                                    "locked": False, "zIndex": d.zi(), "polyType": "NORMAL"})
        for i_, (x, y, s, size, w, angle) in enumerate(self.strings):
            d.add("STRING", d.nid(), {"partitionId": "", "groupId": 0, "layerId": 5 if i_ in knocked else 3, "x": mil(x), "y": mil(y),
                                      "text": s, "fontFamily": "default", "fontSize": mil(size * 0.9),
                                      "strokeWidth": mil(w), "bold": False, "italic": False, "origin": "LEFT_BOTTOM",
                                      "angle": angle, "reverse": i_ in knocked, "expansion": mil(self.knock_expansion(i_)) if i_ in knocked else 0, "mirror": False, "locked": False,
                                      "zIndex": d.zi()})
        return d.lines({"title": title, "parent": "", "board": board_uuid, "zIndex": None})

    def render(self, path, scale=8):
        """Preview of what went into the PCB document (not EasyEDA's rendering)."""
        from PIL import Image, ImageDraw, ImageFont
        W, H = int(self.W * scale), int(self.H * scale)
        img = Image.new("RGB", (W + 2, H + 2), "#141414")
        dr = ImageDraw.Draw(img)

        def P(x, y):
            return 1 + x * scale, 1 + (self.H - y) * scale

        for outline, inner in self.fills:
            dr.polygon([P(*p) for p in outline], fill="#c9a227")
            for x, y, r in inner:
                X, Y = P(x, y)
                dr.ellipse([X - r * scale, Y - r * scale, X + r * scale, Y + r * scale], fill="#141414")
        for poly in self.gold:
            dr.polygon([P(*p) for p in poly], fill="#c9a227")
        for pts, w in self.silk_lines:
            dr.line([P(*p) for p in pts], fill="#f0efe9", width=max(1, int(w * scale)), joint="curve")
        for p0, sweep, p1, w, (cx, cy, r, b0, b1) in self.arcs:   # panel frame, from 12 o'clock
            pts = []
            for i in range(25):
                b = math.radians(b0 + (b1 - b0) * i / 24)
                pts.append(P(*self.P(cx + r * math.sin(b), cy - r * math.cos(b))))
            dr.line(pts, fill="#f0efe9", width=max(1, int(w * scale)))
        knocked = self.knocked()
        try:
            fonts = {}

            def font(size):
                return fonts.setdefault(size, ImageFont.truetype("arial.ttf", max(6, int(size * scale * 0.9))))
        except OSError:
            def font(size):
                return ImageFont.load_default()
        for i_, (x, y, s, size, w, angle) in enumerate(self.strings):
            X, Y = P(x, y)
            dr.text((X, Y - size * scale * 0.9), s, fill="#141414" if i_ in knocked else "#f0efe9", font=font(size))
        for x, y, dia in self.holes:
            X, Y = P(x, y)
            r = dia / 2 * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], fill="#ffffff")
        for x, y, w, h in self.slots:
            dr.rounded_rectangle([P(x - w / 2, y + h / 2), P(x + w / 2, y - h / 2)], radius=h / 2 * scale, fill="#ffffff")
        for x, y, w, h, r in self.windows:
            dr.rounded_rectangle([P(x, y), P(x + w, y - h)], radius=r * scale, fill="#ffffff")
        img.save(path)
