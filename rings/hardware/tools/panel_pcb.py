"""The Ringsy panel as an EasyEDA Pro PCB (the third board in Ringsy.epro2).

Plaitsy's panel writer (plaits/hardware/tools/panel_pcb.py), drawing from panel.layout(), panel.band()
and panel.copper_layout(), the same lists the SVG artwork is made from, so the two never drift apart.
Seen from the front, the PCB's top layer: x to the right, y up, origin at the panel's bottom-left
corner.

  outline        70.8 x 128.5 mm (14HP)
  holes          non-plated: pots, jacks, buttons, LEDs; mounting slots 5.5 x 3.2
  silkscreen     title, subtitle, dotted band, rule (the mushroom mark is copper); knob scales and ticks, the big knobs' dotted
                 rings, labels, - / + and the noon ticks on the attenuverters, the dotted guides, the
                 six icons beside the LEDs as rings with their glyph inside (one colour on a silkscreen:
                 the artwork's green / yellow / red tint is preview only)
  copper band    ODD / EVEN: a copper fill on the top layer under a solder-mask opening of the same
                 shape (bare ENIG gold), both cleared 0.4 mm round each hole through it (DRC: copper
                 0.3 mm from a slot region). ODD, EVEN and the dotted normal between them are knocked
                 out of the band's mask (KNOCK_*): dark on the gold, as in the artwork

Text uses EasyEDA's default stroke font, not the artwork's sans and serif italic,
placed with its measured metrics (INK_*, ink_width), so the letters sit where the artwork has them. Nothing electrical: the panel has no nets, no parts.
"""
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location("rings_" + name, os.path.join(HERE, name + ".py"))
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


def flatten_path(d, steps=8):
    """An M/L/H/V/Q/C/Z path string -> list of polylines (lists of (x, y))."""
    tokens = d.replace(",", " ").split()
    lines, cur, start, i = [], None, None, 0
    pts = []

    def flush():
        if len(pts) > 1:
            lines.append(list(pts))
        pts.clear()

    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        if cmd == "M":
            flush()
            cur = start = (float(tokens[i]), float(tokens[i + 1]))
            pts.append(cur)
            i += 2
        elif cmd == "L":
            cur = (float(tokens[i]), float(tokens[i + 1]))
            pts.append(cur)
            i += 2
        elif cmd == "H":
            cur = (float(tokens[i]), cur[1])
            pts.append(cur)
            i += 1
        elif cmd == "V":
            cur = (cur[0], float(tokens[i]))
            pts.append(cur)
            i += 1
        elif cmd in ("Q", "C"):
            n = 2 if cmd == "Q" else 3
            cp = [(float(tokens[i + 2 * k]), float(tokens[i + 2 * k + 1])) for k in range(n)]
            i += 2 * n
            p0 = cur
            for k in range(1, steps + 1):
                t = k / steps
                if cmd == "Q":
                    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * cp[0][0] + t ** 2 * cp[1][0]
                    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * cp[0][1] + t ** 2 * cp[1][1]
                else:
                    x = ((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * cp[0][0] + 3 * (1 - t) * t ** 2 * cp[1][0]
                         + t ** 3 * cp[2][0])
                    y = ((1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * cp[0][1] + 3 * (1 - t) * t ** 2 * cp[1][1]
                         + t ** 3 * cp[2][1])
                pts.append((x, y))
            cur = cp[-1]
        elif cmd == "Z":
            pts.append(start)
            cur = start
            flush()
    flush()
    return lines
# model name, glyph; Plaits 1.2 banks: green 1-8, red 9-16 (the yellow bank 17-24 has no icons, as on Plaits)


class PanelBoard:
    """Collects silk, holes and copper, then writes the PCB doc (same call as pcb.Board.doc)."""

    def __init__(self):
        self.W, self.H = panel.PANEL_W, panel.PANEL_H
        self.silk_lines, self.strings, self.holes, self.slots, self.copper, self.arcs = [], [], [], [], [], []
        self.gold = []        # the mushroom mark's polygons, PCB frame
        self.cuts = []
        self.placed = []      # so the project writer can count parts (none)
        self.build()

    # -- frame: panel mm from the top-left, y down -> PCB mm, y up
    def P(self, x, y):
        return x, self.H - y

    # -- primitives (panel frame)
    def line(self, pts, w=SILK_W):
        self.silk_lines.append(([self.P(x, y) for x, y in pts], w))

    def dot(self, x, y, d):
        """A filled dot of diameter d: a zero-length line with round caps."""
        self.line([(x - 0.01, y), (x + 0.01, y)], d)

    def text(self, x, y, s, size, anchor="middle", w=None):
        """x, y: baseline point in the panel frame; anchor middle / start / end. Placed with EasyEDA's font
        metrics (ink_width, INK_BOTTOM), so the letters sit on the baseline and centre as in the artwork."""
        w = w or max(size / 9, MIN_STROKE)
        width = ink_width(s, size, w)
        x0 = {"middle": x - width / 2, "start": x, "end": x - width}[anchor]
        self.strings.append((*self.P(x0, y + INK_BOTTOM * 0.9 * size), s, size, w))

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

    def glyph(self, x, y, name, w=0.25):
        """A panel.GLYPHS entry as silk lines, rings and dots around (x, y)."""
        for item in panel.GLYPHS[name]:
            if item[0] == "path":
                for pts in flatten_path(item[1]):
                    self.line([(x + px, y + py) for px, py in pts], w)
            else:
                _, cx, cy, r, filled = item
                if filled:
                    self.dot(x + cx, y + cy, 2 * r)
                else:
                    self.ring(x + cx, y + cy, r, w)

    def hole(self, x, y, d):
        self.holes.append((*self.P(x, y), d))

    def slot(self, x, y, w, h):
        self.slots.append((*self.P(x, y), w, h))

    def band(self, x, y, w, h, rx):
        self.copper.append((*self.P(x, y), w, h, rx))

    def item(self, it):
        """One entry of panel.layout() / panel.copper_layout()."""
        kind = it[0]
        if kind in ("text", "serif"):
            _, x, y, s, size, anchor = it
            self.text(x, y, s, size, anchor)
        elif kind == "gold":
            self.gold += [[self.P(x, y) for x, y in poly] for poly in it[1]]
        elif kind == "line":
            self.line(it[1], it[2])
        elif kind == "dots":
            self.dots(it[1])
        elif kind == "arc":
            _, x, y, r, a0, a1, w = it
            self.arc(x, y, r, a0, a1, w)
        elif kind == "icon":
            _, x, y, g = it
            self.ring(x, y, panel.ART["icon"])
            self.glyph(x, y, g)
        else:
            raise ValueError(f"no panel PCB drawing for {kind}")

    # -- the artwork, from the lists panel.write_artwork draws
    def build(self):
        feats = panel.features()
        pos = {ref: (kind, label, *panel.panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
        for it in panel.layout(pos):
            self.item(it)
        (x, y, w, h, rx), cuts = panel.band(pos)
        self.band(x, y, w, h, rx)
        self.cuts = [(*self.P(cx, cy), r) for cx, cy, r in cuts]
        for it in panel.copper_layout(pos):
            self.item(it)
        for ref, (kind, label, x, y) in pos.items():
            self.hole(x, y, panel.HOLE[kind])
        for x, y in panel.MOUNTS:
            self.slot(x, y, panel.SLOT_W, panel.SLOT_H)


    # -- labels on the gold areas, knocked out of the mask (see KNOCK_MARGIN)
    def gold_regions(self):
        """The copper bands as polygons, PCB frame (their rounded corners left square)."""
        return [[(c[0], c[1] - c[3]), (c[0] + c[2], c[1] - c[3]), (c[0] + c[2], c[1]), (c[0], c[1])]
                for c in self.copper]

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
        for j, kk in self.knocked_dashes().items():      # the dotted ODD -> EVEN normal: each dash a masked dot
            if kk == k:
                x1, y1, x2, y2 = self.dash_box(self.silk_lines[j])
                paths.append([mil(x1), mil(y1), "L", mil(x2), mil(y1), "L", mil(x2), mil(y2), "L", mil(x1), mil(y2),
                              "L", mil(x1), mil(y1)])
        return paths

    @staticmethod
    def dash_box(line):
        """A short silk dash (round caps) as the box it covers, PCB frame."""
        (a, b), w = line[0], line[1]
        r = w / 2
        return min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r

    def knocked_dashes(self):
        """{silk line index: gold area index} for the dots of dotted lines that lie on a gold area: silk there
        would be clipped like the words, so they are holes in its mask opening (dark dots on the gold)."""
        out, regions = {}, self.gold_regions()
        for j, (pts, w) in enumerate(self.silk_lines):
            if len(pts) != 2 or abs(pts[0][0] - pts[1][0]) + abs(pts[0][1] - pts[1][1]) > 0.2:
                continue
            x1, y1, x2, y2 = self.dash_box((pts, w))
            for k, poly in enumerate(regions):
                if all(inside(p, poly) for p in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))):
                    out[j] = k
        return out

    # -- EasyEDA document
    def doc(self, ee, template, board_uuid, title):
        d = ee.Doc("PCB")
        knocked = self.knocked()
        for h, p in template:
            if h["type"] in ("CANVAS", "LAYER", "ACTIVE_LAYER", "RULE_TEMPLATE", "PRIMITIVE", "SILK_OPTS",
                             "PREFERENCE", "LAYER_PHYS", "RULE", "PANELIZE"):
                d.add(h["type"], h["id"], p)

        def fill(layer, *paths):
            d.add("FILL", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": layer, "width": 1,
                                    "fillStyle": "SOLID", "path": list(paths), "locked": False, "zIndex": d.zi(),
                                    "isBridgingCopper": False, "networkList": [], "refs": []})

        def cutout(x, y, r):
            """A counter-clockwise circle. EasyEDA combines a fill's paths with the nonzero rule, so inside
            the clockwise outline drawn by rounded() it is a hole."""
            path = [mil(x + r), mil(y)]
            for px, py in ((x, y + r), (x - r, y), (x, y - r), (x + r, y)):
                path += ["ARC", 90, mil(px), mil(py)]
            return path

        def rounded(x, y, w, h, r):
            """Rounded rectangle from its top-left (y up) as lines and clockwise 90-degree arcs.
            The "R" path form's trailing parameters are not corner radii (EasyEDA rotated the shape),
            so rounded shapes are drawn explicitly, as the library jack outline does."""
            r = min(r, w / 2, h / 2)
            path = [mil(x + r), mil(y)]
            for seg in (("L", x + w - r, y), ("ARC", x + w, y - r), ("L", x + w, y - h + r), ("ARC", x + w - r, y - h),
                        ("L", x + r, y - h), ("ARC", x, y - h + r), ("L", x, y - r), ("ARC", x + r, y)):
                kind, px, py = seg
                if kind == "L" and (mil(px), mil(py)) == (path[-2], path[-1]):
                    continue                      # a slot has no straight piece between its two end arcs
                path += ["L", mil(px), mil(py)] if kind == "L" else ["ARC", -90, mil(px), mil(py)]
            return path

        for x, y, dia in self.holes:
            fill(12, ["CIRCLE", mil(x), mil(y), mil(dia / 2)])
        for x, y, w, h in self.slots:
            fill(12, rounded(x - w / 2, y + h / 2, w, h, h / 2))
        for k_, (x, y, w, h, rx) in enumerate(self.copper):        # (x, y) is the band's top-left in the PCB frame
            for layer in (1, 5):                  # top copper, top solder mask opening; mask stays on the clearances
                fill(layer, rounded(x, y, w, h, rx), *(cutout(*c) for c in self.cuts), *(self.knock_paths(k_) if layer == 5 else []))
        for poly in self.gold:                    # the mushroom mark: top copper under a mask opening (ENIG)
            path = [mil(poly[0][0]), mil(poly[0][1])]
            for x, y in poly[1:]:
                path += ["L", mil(x), mil(y)]
            for layer in (1, 5):
                fill(layer, path)
        d.add("POLY", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 11, "width": 10,
                                "path": ["R", 0, mil(self.H), mil(self.W), mil(self.H), 0, 0], "locked": False,
                                "zIndex": d.zi(), "polyType": "BOARD_OUTLINE"})
        dashes = self.knocked_dashes()
        for j, (pts, w) in enumerate(self.silk_lines):
            if j in dashes:
                continue                          # a hole in the band's mask instead (knock_paths)
            path = [mil(pts[0][0]), mil(pts[0][1])]
            for x, y in pts[1:]:
                path += ["L", mil(x), mil(y)]
            d.add("POLY", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 3, "width": mil(w),
                                    "path": path, "locked": False, "zIndex": d.zi(), "polyType": "NORMAL"})
        for p0, sweep, p1, w, _ in self.arcs:
            d.add("POLY", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 3, "width": mil(w),
                                    "path": [mil(p0[0]), mil(p0[1]), "ARC", round(sweep, 3), mil(p1[0]), mil(p1[1])],
                                    "locked": False, "zIndex": d.zi(), "polyType": "NORMAL"})
        for i_, (x, y, s, size, w) in enumerate(self.strings):
            d.add("STRING", d.nid(), {"partitionId": "", "groupId": 0, "layerId": 5 if i_ in knocked else 3, "x": mil(x), "y": mil(y),
                                      "text": s, "fontFamily": "default", "fontSize": mil(size * 0.9),
                                      "strokeWidth": mil(w), "bold": False, "italic": False, "origin": "LEFT_BOTTOM",
                                      "angle": 0, "reverse": i_ in knocked, "expansion": mil(self.knock_expansion(i_)) if i_ in knocked else 0, "mirror": False, "locked": False,
                                      "zIndex": d.zi()})
        return d.lines({"title": title, "parent": "", "board": board_uuid, "zIndex": None})

    def render(self, path, scale=6):
        """Preview of what went into the PCB document (not EasyEDA's rendering)."""
        from PIL import Image, ImageDraw, ImageFont
        W, H = int(self.W * scale), int(self.H * scale)
        img = Image.new("RGB", (W + 2, H + 2), "#141414")
        dr = ImageDraw.Draw(img)

        def P(x, y):
            return 1 + x * scale, 1 + (self.H - y) * scale

        for x, y, w, h, rx in self.copper:
            dr.rounded_rectangle([P(x, y), P(x + w, y - h)], radius=rx * scale, fill="#c9a227")
        for x, y, r in self.cuts:
            X, Y = P(x, y)
            dr.ellipse([X - r * scale, Y - r * scale, X + r * scale, Y + r * scale], fill="#141414")
        for poly in self.gold:
            dr.polygon([P(*p) for p in poly], fill="#c9a227")
        dashes = self.knocked_dashes()
        for j, (pts, w) in enumerate(self.silk_lines):
            dr.line([P(*p) for p in pts], fill="#141414" if j in dashes else "#f0efe9", width=max(1, int(w * scale)),
                    joint="curve")
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
        for i_, (x, y, s, size, w) in enumerate(self.strings):
            X, Y = P(x, y)
            dr.text((X, Y - size * scale * 0.9), s, fill="#141414" if i_ in knocked else "#f0efe9", font=font(size))
        for x, y, dia in self.holes:
            X, Y = P(x, y)
            r = dia / 2 * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], fill="#ffffff")
        for x, y, w, h in self.slots:
            dr.rounded_rectangle([P(x - w / 2, y + h / 2), P(x + w / 2, y - h / 2)], radius=h / 2 * scale, fill="#ffffff")
        img.save(path)
