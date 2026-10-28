"""The Plaitsy panel as an EasyEDA Pro PCB (the third board in Plaits.epro2).

Built from the same positions, labels and glyphs as panel.py's artwork, so
the SVG and the PCB panel never drift apart. Seen from the front, the PCB's
top layer: x to the right, y up, origin at the panel's bottom-left corner.

  outline        60.6 x 128.5 mm
  holes          non-plated: pots, jacks, buttons, LEDs; mounting slots 5.5 x 3.2
  silkscreen     titles, labels, scale arcs and ticks, - / + marks, dotted
                 guides (short dashes), the wrench and "levels" marks, the
                 LPG icons, the sixteen model icons as rings with their glyph
                 (thick ring = green bank, thin ring = red bank: one colour on
                 a silkscreen, so the solid discs of the artwork become rings)
  copper band    a copper fill on the top layer under a solder-mask opening of
                 the same shape (bare ENIG gold); OUT and AUX sit on it as
                 silkscreen

Text uses EasyEDA's default stroke font; centring is estimated, so nudge a
label in the editor if it sits off. Nothing electrical: the panel has no
nets, no parts.
"""
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location("plaits_" + name, os.path.join(HERE, name + ".py"))
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
        self.silk_lines, self.strings, self.holes, self.slots, self.copper, self.arcs = [], [], [], [], [], []
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

    def glyph(self, x, y, name, scale=1.0, rotate=0, w=SILK_W):
        """A panel.GLYPHS entry as silk lines, rings, dots and text around (x, y)."""
        c, s = math.cos(math.radians(rotate)), math.sin(math.radians(rotate))

        def T(px, py):
            px, py = px * scale, py * scale
            return x + px * c - py * s, y + px * s + py * c

        for item in panel.GLYPHS[name]:
            if item[0] == "path":
                for pts in panel.flatten_path(item[1]):
                    self.line([T(px, py) for px, py in pts], w)
            elif item[0] == "circle":
                _, cx, cy, r, filled = item
                if filled:
                    self.dot(*T(cx, cy), 2 * r * scale)
                else:
                    self.ring(*T(cx, cy), r * scale, w)
            else:
                _, s_, size, dy = item
                self.text(x, y + dy * scale, s_, size * scale)

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
        icon_x = {"green": pos["SW1"][2], "red": pos["SW2"][2]}

        def scale_r(ref):
            return A["scale"][panel.KNOB_SIZE[ref]]

        # titles, the dotted band under them, the maker line and the rule above it
        self.text(12.0, 7.4, A["title"], 5.2, "start")
        self.text(W - 12.0, 6.6, A["subtitle"], 2.1, "end")
        self.dots([(3, 9.6), (W - 3, 9.6)])
        self.dots([(3, 10.6), (W - 3, 10.6)])
        self.text(W / 2, 122.4, A["maker"], 2.2)
        self.line([(3, 118.6), (W - 3, 118.6)])
        # the marks beside the model buttons and their dotted lines
        bx1, by = pos["SW1"][2], pos["SW1"][3]
        bx2 = pos["SW2"][2]
        self.glyph(bx1 - A["cap_led"] - 3.6, by, "wrench", rotate=-40)
        dx = bx2 + A["cap_led"] + 3.4
        self.ring(dx, by, 1.5)
        for k in (-1, 0, 1):
            self.dot(dx + 0.6 * k, by - 0.6 * k, 0.44)
        hx, hy = pos["RV2"][2], pos["RV2"][3]
        self.dots([(dx + 2.1, by), (hx, by), (hx, hy - scale_r("RV2") - 1.4)])
        icon_top = pos["D1"][3] - A["icon"]
        for bx in (bx1, bx2):
            self.dots([(bx, by + A["cap_led"] + 0.7), (bx, icon_top - 0.5)])
        # model icons: green bank as thick rings, red bank as thin rings, glyph inside
        for k in range(8):
            y = pos[f"D{k + 1}"][3]
            self.ring(icon_x["green"], y, A["icon"], 0.5)
            self.glyph(icon_x["green"], y, panel.MODELS_GREEN[k][1], w=0.25)
            self.ring(icon_x["red"], y, A["icon"], 0.25)
            self.glyph(icon_x["red"], y, panel.MODELS_RED[k][1], w=0.25)
        # knobs: scale arcs, ticks, labels, - / + on the attenuverters
        for ref, (kind, label, x, y) in pos.items():
            if kind != "pot":
                continue
            size = panel.KNOB_SIZE[ref]
            r = scale_r(ref)
            self.arc(x, y, r, -135, 135)
            n = {"big": 11, "mid": 7, "small": 3}[size]
            for i in range(n):
                a = math.radians(-135 + 270 * i / (n - 1))
                r1 = r + (1.2 if i in (0, n - 1, (n - 1) // 2) else 0.7)
                self.line([(x + r * math.sin(a), y - r * math.cos(a)), (x + r1 * math.sin(a), y - r1 * math.cos(a))])
            if size == "small":
                self.line([(x - 7.2, y - 5.7), (x - 6.0, y - 5.7)], 0.35)                        # minus
                self.line([(x + 6.0, y - 5.7), (x + 7.2, y - 5.7)], 0.35)                        # plus
                self.line([(x + 6.6, y - 6.3), (x + 6.6, y - 5.1)], 0.35)
            else:
                lx, ly = panel.label_xy(pos, ref)
                self.text(lx, ly, label, 2.7 if size == "big" else 2.4)
        # LPG icons beside TIMBRE and MORPH
        for ref, side, name in (("RV3", -1, "lpg_colour"), ("RV4", 1, "lpg_decay")):
            ix, iy = panel.alt_icon_xy(pos, ref, side)
            self.ring(ix, iy, 1.45)
            self.glyph(ix, iy, name)
        # FM over its attenuverter
        fx, fy = pos["RV6"][2], pos["RV6"][3]
        self.text(fx, fy - scale_r("RV6") - 1.7, "FM", 2.4)
        # dotted guides
        for knob, att in panel.KNOB_TO_ATT.items():
            lx, ly = panel.label_xy(pos, knob)
            ax, ay = pos[att][2], pos[att][3]
            top = ay - scale_r(att) - 1.0
            self.dots([(lx, ly + 1.2), (lx, ly + 3.2), (ax, ly + 5.0), (ax, top)])
        for att, jack in panel.ATT_TO_JACK.items():
            ax, ay = pos[att][2], pos[att][3]
            jx, jy = pos[jack][2], pos[jack][3]
            y0 = ay + A["knob"]["small"] + 0.9
            top = jy - A["nut"] - 0.9
            if abs(jx - ax) < 0.3:
                self.dots([(ax, y0), (ax, top)])
            else:
                self.dots([(ax, y0), (ax, y0 + 1.8), (jx, top - 1.6), (jx, top)])
        # jack labels, TRIG .. LEVEL
        for jack, word in panel.JACK_LABELS.items():
            self.text(pos[jack][2], pos[jack][3] - A["nut"] - 1.6, word, 2.2)
        tx, ty = pos["J6"][2], pos["J6"][3]
        self.dots([(tx + A["nut"] + 0.9, ty), (pos["J7"][2] - A["nut"] - 0.9, ty)])
        # copper band and the output labels on it
        ox, ax_, jy = pos["J9"][2], pos["J10"][2], pos["J9"][3]
        self.band(ox - 4.8, jy - 8.8, ax_ - ox + 9.4, 14.6, 1.4)
        for ref in panel.OUTPUTS:
            self.text(pos[ref][2], jy - A["nut"] - 1.6, pos[ref][1], 2.2)
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

        def fill(layer, path):
            d.add("FILL", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": layer, "width": 1,
                                    "fillStyle": "SOLID", "path": [path], "locked": False, "zIndex": d.zi(),
                                    "isBridgingCopper": False, "networkList": [], "refs": []})

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
            for layer in (1, 5):                  # top copper, top solder mask opening
                fill(layer, rounded(x, y, w, h, rx))
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
