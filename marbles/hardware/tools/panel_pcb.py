"""The Marblesy panel as an EasyEDA Pro PCB (the third board in Marbles.epro2).

Built from the same positions and labels as panel.py's artwork, so the SVG
and the PCB panel never drift apart. Seen from the front, the PCB's top
layer: x to the right, y up, origin at the panel's bottom-left corner.

  outline        91.3 x 128.5 mm
  holes          non-plated: pots, jacks, buttons, LEDs; mounting slots 5.5 x 3.2
  silkscreen     titles, labels, scale arcs and ticks, LENGTH graduations,
                 STEPS / JITTER marks, dotted guides (short dashes), LED-colour
                 dots as small rings, X-mode bar icons, button rings
  copper band    a copper fill on the top layer under a solder-mask opening of
                 the same shape (bare ENIG gold); the output labels sit on it
                 as silkscreen. Both leave a 0.4 mm ring of masked board
                 around each hole through the band (DRC: copper 0.3 mm from
                 a slot region)

Text uses EasyEDA's default stroke font; centring is estimated, so nudge a
label in the editor if it sits off. Nothing electrical: the panel has no
nets, no parts.
"""
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location("marbles_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


panel = _load("panel")
circuit = panel.circuit
pcb = _load("pcb")
mil = pcb.mil
SILK_W = 0.3          # mm, line width on silk
CHAR_W = 0.62         # estimated advance per character, as a fraction of the font size (default stroke font)


class PanelBoard:
    """Collects silk, holes and copper, then writes the PCB doc (same call as pcb.Board.doc)."""

    def __init__(self):
        self.W, self.H = panel.PANEL_W, panel.PANEL_H
        self.silk_lines, self.strings, self.holes, self.slots, self.copper = [], [], [], [], []
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
        self.arcs = getattr(self, "arcs", [])
        pieces = max(1, math.ceil((a1 - a0) / 90))
        for i in range(pieces):
            b0 = a0 + (a1 - a0) * i / pieces
            b1 = a0 + (a1 - a0) * (i + 1) / pieces
            p0 = self.P(cx + r * math.sin(math.radians(b0)), cy - r * math.cos(math.radians(b0)))
            p1 = self.P(cx + r * math.sin(math.radians(b1)), cy - r * math.cos(math.radians(b1)))
            self.arcs.append((p0, -(b1 - b0), p1, w, (cx, cy, r, b0, b1)))   # negative sweep = clockwise (y up)

    def ring(self, cx, cy, r, w=SILK_W):
        self.arc(cx, cy, r, 0, 360, w)

    def hole(self, x, y, d):
        self.holes.append((*self.P(x, y), d))

    def slot(self, x, y, w, h):
        self.slots.append((*self.P(x, y), w, h))

    def band(self, x, y, w, h, rx):
        self.copper.append((*self.P(x, y), w, h, rx))

    # -- the artwork, mirroring panel.write_artwork
    def build(self):
        A, HOLE = panel.ART, panel.HOLE
        feats = panel.features()
        pos = {ref: (kind, label, *panel.panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
        W = self.W

        def label_below(ref):
            kind, label, x, y = pos[ref]
            r = A["scale_big"] if ref in panel.BIG_POTS else A["scale_small"]
            return x, y + r + 3.0

        # titles, the dotted band under them, the maker line and the rule above it (as on every module)
        self.text(12.0, 7.4, A["title"], 5.2, "start")
        self.text(W - 12.0, 6.6, A["subtitle"], 2.1, "end")
        self.dots([(3, 9.6), (W - 3, 9.6)])
        self.dots([(3, 10.6), (W - 3, 10.6)])
        self.text(W / 2, 122.4, A["maker"], 2.2)
        self.line([(3, 118.6), (W - 3, 118.6)])
        # t / X beside the deja vu buttons, rings around them
        self.text(pos["SW1"][2] - A["cap_led"] - 4.6, pos["SW1"][3] + 2.2, "t", 7.0)
        self.text(pos["SW4"][2] + A["cap_led"] + 4.6, pos["SW4"][3] + 2.2, "X", 7.0)
        for sw in ("SW1", "SW4"):
            self.ring(pos[sw][2], pos[sw][3], A["cap_led"] + 1.6, 0.35)
        # knobs: scale arcs, ticks, labels
        for ref, (kind, label, x, y) in pos.items():
            if kind != "pot":
                continue
            big = ref in panel.BIG_POTS
            r = A["scale_big"] if big else A["scale_small"]
            self.arc(x, y, r, -135, 135)
            n = 11 if big else 5
            for i in range(n):
                a = math.radians(-135 + 270 * i / (n - 1))
                r1 = r + (1.2 if i in (0, n - 1, (n - 1) // 2) else 0.7)
                self.line([(x + r * math.sin(a), y - r * math.cos(a)), (x + r1 * math.sin(a), y - r1 * math.cos(a))])
            lab = {"BIAS (t)": "BIAS", "BIAS (X)": "BIAS"}.get(label, label)
            lx, ly = label_below(ref)
            self.text(lx, ly, lab, 2.7 if big else 2.4)
        # dotted guides knob -> CV jack
        for pot, jack in panel.KNOB_TO_JACK.items():
            lx, ly = label_below(pot)
            jx, jy = pos[jack][2], pos[jack][3]
            top = jy - A["nut"] - 0.9
            if abs(jx - lx) < 0.3:
                self.dots([(lx, ly + 1.2), (lx, top)])
            else:
                self.dots([(lx, ly + 1.2), (lx, ly + 3.5), (jx, ly + 6.0), (jx, top)])
        # button words
        for sw, word in (("SW2", "MODE"), ("SW5", "MODE"), ("SW3", "RANGE"), ("SW6", "RANGE"), ("SW7", "EXT")):
            x, y = pos[sw][2], pos[sw][3]
            self.text(x, y + A["cap_led"] + 2.6, word, 1.8)
        # three-state labels: a small ring stands for the LED colour (one colour on silk)
        def labels_above(sw, words):
            x, y = pos[sw][2], pos[sw][3]
            for i, w in enumerate(words):
                yy = y - A["cap_led"] - 9.4 + 3.4 * i
                self.ring(x - 4.6, yy - 0.6, 0.6, 0.25)
                self.text(x + 0.6, yy, w, 1.7)

        def labels_beside(sw, words, side):
            x, y = pos[sw][2], pos[sw][3]
            for i, w in enumerate(words):
                x0, yy = x + side * (A["cap_led"] + 1.6), y - 3.9 + 3.4 * i
                self.ring(x0 + side * 0.8, yy - 0.6, 0.6, 0.25)
                self.text(x0 + side * 2.4, yy, w, 1.7, "start" if side > 0 else "end")

        labels_above("SW2", panel.MODE_LABELS["SW2"])
        labels_beside("SW3", panel.MODE_LABELS["SW3"], 1)
        labels_beside("SW6", panel.MODE_LABELS["SW6"], -1)
        x, y0 = pos["SW5"][2], pos["SW5"][3] - A["cap_led"] - 10.6
        for i, bars in enumerate(((2, 2, 2), (2.6, 1.2, 2.6), (1.0, 1.8, 2.6))):
            y = y0 + 3.4 * i
            self.ring(x - 4.0, y + 0.6, 0.6, 0.25)
            for j, h in enumerate(bars):
                bx = x - 0.7 + 1.3 * j
                self.line([(bx, y + 1.3), (bx, y + 1.3 - h)], 0.55)
        # LENGTH graduations
        lx, ly = pos["RV5"][2], pos["RV5"][3]
        for i, n in enumerate(panel.LENGTHS):
            a = math.radians(-135 + 270 * i / 7)
            self.text(lx + 8.6 * math.sin(a), ly - 8.6 * math.cos(a) + 0.6, n, 1.5)
        # STEPS marks: smoothed step, S&H steps, quantized steps; JITTER: steady / random
        sx, sy = pos["RV8"][2], pos["RV8"][3]
        x0, y0 = sx - 9.6, sy + 7.8
        self.line([(x0, y0), (x0 + 1.0, y0), (x0 + 1.4, y0 - 0.3), (x0 + 1.8, y0 - 1.0), (x0 + 2.2, y0 - 1.7),
                   (x0 + 2.6, y0 - 2.0), (x0 + 3.6, y0 - 2.0)], 0.4)
        x0, y0 = sx - 1.8, sy - 8.0
        self.line([(x0, y0), (x0 + 0.9, y0), (x0 + 0.9, y0 - 0.9), (x0 + 1.8, y0 - 0.9), (x0 + 1.8, y0 - 1.8),
                   (x0 + 2.7, y0 - 1.8), (x0 + 2.7, y0 - 2.7), (x0 + 3.6, y0 - 2.7)], 0.4)
        x0, y0 = sx + 5.6, sy + 7.6
        self.line([(x0, y0), (x0 + 1.2, y0), (x0 + 1.2, y0 - 1.6), (x0 + 2.4, y0 - 1.6), (x0 + 2.4, y0 - 3.2),
                   (x0 + 3.6, y0 - 3.2)], 0.4)
        jx, jy = pos["RV3"][2], pos["RV3"][3]
        self.line([(jx - 9.2, jy + 7.2), (jx - 5.8, jy + 7.2)], 0.4)
        x0, y0 = jx + 5.8, jy + 7.6
        self.line([(x0, y0), (x0 + 0.6, y0 - 2.2), (x0 + 1.3, y0 - 0.6), (x0 + 1.9, y0 - 3.0), (x0 + 2.6, y0 - 1.2),
                   (x0 + 3.4, y0 - 2.4)], 0.4)
        # jack labels
        for jack in ("J1", "J12"):
            self.text(pos[jack][2], pos[jack][3] - A["nut"] - 1.6, "CLOCK", 2.2)
        self.text(pos["J5"][2], pos["J5"][3] - A["nut"] - 1.6, "DEJA VU", 2.2)
        # copper band, cleared around the holes through it, and the output labels on it
        jy = pos["J9"][3]
        (x, y, w, h, rx), cuts = panel.band(pos)
        self.band(x, y, w, h, rx)
        self.cuts = [(*self.P(cx, cy), r) for cx, cy, r in cuts]
        for ref in panel.OUTPUTS:
            x = pos[ref][2]
            main, sub = panel.OUT_LABELS[ref]
            self.text(x + 2.6, jy - A["nut"] - 1.2, main + sub, 3.0)
        # holes
        for ref, (kind, label, x, y) in pos.items():
            self.hole(x, y, HOLE[kind])
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
        for p0, sweep, p1, w, _ in getattr(self, "arcs", []):
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
            dr.line([P(*p) for p in pts], fill="#f0efe9", width=max(1, int(w * scale)))
        for p0, sweep, p1, w, (cx, cy, r, b0, b1) in getattr(self, "arcs", []):   # panel frame, from 12 o'clock
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
