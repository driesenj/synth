"""The Atlasy panel as an EasyEDA Pro PCB (the third board in Atlasy.epro2).
Side FXy's panel writer, drawing from panel.layout() and panel.copper(), the
same lists the SVG artwork is made from, so the two never drift apart. Seen
from the front, the PCB's top layer: x to the right, y up, origin at the
panel's bottom-left corner.

  outline        80.9 x 128.5 mm (16HP)
  holes          non-plated: jacks, toggles 6.5, pots 7.5; mounting slots 5.5 x 3.2
  silkscreen     title, column words, knob scales (arcs in <= 90 degree pieces),
                 switch positions, the IN / FREQ normal dots, the scanner's name
                 and 1-4 marks, the OUT words on the gold
  copper         the OUT column, the scanner OUT patch and the numerals' dots:
                 copper fills on the top layer under solder-mask openings of the
                 same shape (bare ENIG gold), cleared 0.4 mm round each hole

Text uses EasyEDA's default stroke font; centring is estimated, so nudge a
label in the editor if it sits off. Nothing electrical: no nets, no parts.
"""
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location("atlas_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


panel = _load("panel")
pcb = _load("pcb")
mil = pcb.mil
SILK_W = 0.3          # mm, line width on silk
CHAR_W = 0.62         # estimated advance per character, as a fraction of the font size (default stroke font)


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
        self.discs = []       # (x, y, r): the numerals' gold dots, PCB frame
        self.placed = []      # so the project writer can count parts (none)
        self.build()

    # -- frame: panel mm from the top-left, y down -> PCB mm, y up
    def P(self, x, y):
        return x, self.H - y

    # -- primitives (panel frame)
    def line(self, pts, w=SILK_W):
        self.silk_lines.append(([self.P(x, y) for x, y in pts], w))

    def text(self, x, y, s, size, anchor="middle", w=None):
        """x, y: baseline point in the panel frame; anchor middle / start / end."""
        width = CHAR_W * size * len(s)
        x0 = {"middle": x - width / 2, "start": x, "end": x - width}[anchor]
        self.strings.append((*self.P(x0, y), s, size, w or size / 9, 0))

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
            elif kind == "arc":
                _, x, y, r, a0, a1, w = item
                self.arc(x, y, r, a0, a1, w)
        # copper: the OUT column and the scanner OUT patch with the holes through them taken out, the numerals
        for (x, y, w, h, rx), cuts in panel.copper(pos):
            outline, inner = rect_minus_discs(x, y, w, h, rx, cuts)
            self.fills.append(([self.P(px, py) for px, py in outline], [(*self.P(cx, cy), r) for cx, cy, r in inner]))
        for k, x, y in panel.numerals():
            for dx, dy in panel.numeral_dots(k, x, y):
                self.discs.append((*self.P(dx, dy), panel.DOT / 2))
        self.text(panel.circuit.JACK_X[3], panel.HEADER_Y, "OUT", panel.ART["label"])
        self.text(pos["J18"][2], panel.jack_label_y(pos, "J18"), "OUT", panel.ART["label"])
        for ref, (kind, label, x, y) in pos.items():
            self.holes.append((*self.P(x, y), panel.HOLE[kind]))
        for x, y in panel.MOUNTS:
            self.slots.append((*self.P(x, y), panel.SLOT_W, panel.SLOT_H))

    # -- EasyEDA document
    def doc(self, ee, template, board_uuid, title):
        d = ee.Doc("PCB")
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
        for outline, inner in self.fills:       # top copper and its solder-mask opening: bare ENIG gold
            for layer in (1, 5):
                fill(layer, polygon(outline), *(cutout(*c) for c in inner))
        for x, y, r in self.discs:
            for layer in (1, 5):
                fill(layer, ["CIRCLE", mil(x), mil(y), mil(r)])
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
        for x, y, s, size, w, angle in self.strings:
            d.add("STRING", d.nid(), {"partitionId": "", "groupId": 0, "layerId": 3, "x": mil(x), "y": mil(y),
                                      "text": s, "fontFamily": "default", "fontSize": mil(size * 0.9),
                                      "strokeWidth": mil(w), "bold": False, "italic": False, "origin": "LEFT_BOTTOM",
                                      "angle": angle, "reverse": False, "expansion": 0, "mirror": False, "locked": False,
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

        for x, y, r in self.discs:
            X, Y = P(x, y)
            dr.ellipse([X - r * scale, Y - r * scale, X + r * scale, Y + r * scale], fill="#c9a227")
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
        try:
            fonts = {}

            def font(size):
                return fonts.setdefault(size, ImageFont.truetype("arial.ttf", max(6, int(size * scale * 0.9))))
        except OSError:
            def font(size):
                return ImageFont.load_default()
        for x, y, s, size, w, angle in self.strings:
            X, Y = P(x, y)
            dr.text((X, Y - size * scale * 0.9), s, fill="#f0efe9", font=font(size))
        for x, y, dia in self.holes:
            X, Y = P(x, y)
            r = dia / 2 * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], fill="#ffffff")
        for x, y, w, h in self.slots:
            dr.rounded_rectangle([P(x - w / 2, y + h / 2), P(x + w / 2, y - h / 2)], radius=h / 2 * scale, fill="#ffffff")
        for x, y, w, h, r in self.windows:
            dr.rounded_rectangle([P(x, y), P(x + w, y - h)], radius=r * scale, fill="#ffffff")
        img.save(path)
