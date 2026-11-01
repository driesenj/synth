"""The Ringsy panel as an EasyEDA Pro PCB (the third board in Ringsy.epro2).

Plaitsy's panel writer (plaits/hardware/tools/panel_pcb.py), drawing from panel.layout(), panel.band()
and panel.copper_layout(), the same lists the SVG artwork is made from, so the two never drift apart.
Seen from the front, the PCB's top layer: x to the right, y up, origin at the panel's bottom-left
corner.

  outline        70.8 x 128.5 mm (14HP)
  holes          non-plated: pots, jacks, buttons, LEDs; mounting slots 5.5 x 3.2
  silkscreen     title, subtitle, dotted band, rule, maker; knob scales and ticks, the big knobs' dotted
                 rings, labels, - / + and the noon ticks on the attenuverters, the dotted guides, the
                 six icons beside the LEDs as rings with their glyph inside (one colour on a silkscreen:
                 the artwork's green / yellow / red tint is preview only)
  copper band    ODD / EVEN: a copper fill on the top layer under a solder-mask opening of the same
                 shape (bare ENIG gold), both cleared 0.4 mm round each hole through it (DRC: copper
                 0.3 mm from a slot region). ODD, EVEN and the dotted normal between them sit on it as
                 silkscreen (the artwork knocks them out of the gold; if you prefer that, move them to
                 the mask layer after import)

Text uses EasyEDA's default stroke font, not the artwork's sans and serif italic; centring is estimated,
so nudge a label in the editor if it sits off. Nothing electrical: the panel has no nets, no parts.
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
        """x, y: baseline point in the panel frame; anchor middle / start / end."""
        width = CHAR_W * size * len(s)
        x0 = {"middle": x - width / 2, "start": x, "end": x - width}[anchor]
        self.strings.append((*self.P(x0, y), s, size, w or size / 9))

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

    # -- EasyEDA document
    def doc(self, ee, template, board_uuid, title):
        d = ee.Doc("PCB")
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
        for x, y, w, h, rx in self.copper:        # (x, y) is the band's top-left in the PCB frame
            for layer in (1, 5):                  # top copper, top solder mask opening; mask stays on the clearances
                fill(layer, rounded(x, y, w, h, rx), *(cutout(*c) for c in self.cuts))
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
        for x, y, s, size, w in self.strings:
            d.add("STRING", d.nid(), {"partitionId": "", "groupId": 0, "layerId": 3, "x": mil(x), "y": mil(y),
                                      "text": s, "fontFamily": "default", "fontSize": mil(size * 0.9),
                                      "strokeWidth": mil(w), "bold": False, "italic": False, "origin": "LEFT_BOTTOM",
                                      "angle": 0, "reverse": False, "expansion": 0, "mirror": False, "locked": False,
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
        for x, y, s, size, w in self.strings:
            X, Y = P(x, y)
            dr.text((X, Y - size * scale * 0.9), s, fill="#f0efe9", font=font(size))
        for x, y, dia in self.holes:
            X, Y = P(x, y)
            r = dia / 2 * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], fill="#ffffff")
        for x, y, w, h in self.slots:
            dr.rounded_rectangle([P(x - w / 2, y + h / 2), P(x + w / 2, y - h / 2)], radius=h / 2 * scale, fill="#ffffff")
        img.save(path)
