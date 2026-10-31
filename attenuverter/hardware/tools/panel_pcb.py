"""The Offset panel as an EasyEDA Pro PCB (the second board in Offset.epro2).
The mixer's panel writer (stereo-mixer/hardware/tools/panel_pcb.py), drawing
from panel.layout() and panel.bands(), the same lists the SVG artwork is
made from, so the two never drift apart. Seen from the front, the PCB's top
layer: x to the right, y up, origin at the panel's bottom-left corner.

  outline        50.5 x 128.5 mm (10HP)
  holes          non-plated: pots, jacks, toggles, LEDs; mounting slots 5.5 x 3.2
  silkscreen     title, the row words on their brackets, scale arcs and ticks,
                 - / + at the scale ends, the toggles' 10V / 5V, the IN normals
  copper         the band round the LEDs and OUT jacks: a copper fill on the top
                 layer under a solder-mask opening of the same shape (bare ENIG
                 gold), cleared 0.4 mm round each hole through it; the + signs
                 between the outputs sit on it as silkscreen

Text uses EasyEDA's default stroke font; centring is estimated, so nudge a
label in the editor if it sits off. Nothing electrical: no nets, no parts.
"""
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location("offset_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


panel = _load("panel")
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

    def text(self, x, y, s, size, anchor="middle", w=None):
        """x, y: baseline point in the panel frame; anchor middle / start / end."""
        width = CHAR_W * size * len(s)
        x0 = {"middle": x - width / 2, "start": x, "end": x - width}[anchor]
        self.strings.append((*self.P(x0, y), s, size, w or size / 9, 0))

    def vtext(self, x, y, s, size, w=None):
        """A word reading bottom to top (angle 90, CCW like EasyEDA's component angles), centred on y, with
        its baseline at x; the LEFT_BOTTOM origin is the bottom end of the baseline."""
        width = CHAR_W * size * len(s)
        self.strings.append((*self.P(x, y + width / 2), s, size, w or size / 9, 90))

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

    # -- the artwork, from panel.layout() like the SVG
    def build(self):
        feats = panel.features()
        pos = {ref: (kind, label, *panel.panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
        for item in panel.layout(pos):
            kind = item[0]
            if kind in ("text", "serif"):
                _, x, y, s, size, anchor = item
                self.text(x, y, s.replace("−", "-").replace("×", "x"), size, anchor)
            elif kind == "vtext":
                _, x, y, s, size = item
                self.vtext(x, y, s, size)
            elif kind == "line":
                self.line(item[1], item[2])
            elif kind == "dots":
                self.dots(item[1])
            elif kind == "arc":
                _, x, y, r, a0, a1, w = item
                self.arc(x, y, r, a0, a1, w)
        # the copper band, cleared round the holes through it, with the + signs on it
        self.cuts = []
        for (x, y, w, h, rx), cuts in panel.bands(pos):
            self.copper.append((*self.P(x, y), w, h, rx))
            self.cuts += [(*self.P(cx, cy), r) for cx, cy, r in cuts]
        for a, b in zip(panel.OUTPUTS, panel.OUTPUTS[1:]):
            self.text((pos[a][2] + pos[b][2]) / 2, pos[a][3] + 1.0, "+", 2.8)
        # holes
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
            """A counter-clockwise circle. EasyEDA combines a fill's paths with the nonzero rule, so inside
            the clockwise outline drawn by rounded() it is a hole."""
            path = [mil(x + r), mil(y)]
            for px, py in ((x, y + r), (x - r, y), (x, y - r), (x + r, y)):
                path += ["ARC", 90, mil(px), mil(py)]
            return path

        for x, y, dia in self.holes:
            fill(12, ["CIRCLE", mil(x), mil(y), mil(dia / 2)])
        for x, y, w, h in self.slots:
            fill(12, pcb.rounded(x - w / 2, y + h / 2, w, h, h / 2))
        for x, y, w, h, rx in self.copper:        # (x, y) is the band's top-left in the PCB frame
            for layer in (1, 5):                  # top copper, top solder mask opening; mask stays on the clearances
                fill(layer, pcb.rounded(x, y, w, h, rx), *(cutout(*c) for c in self.cuts))
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
        for x, y, s, size, w, angle in self.strings:
            X, Y = P(x, y)
            if angle == 0:
                dr.text((X, Y - size * scale * 0.9), s, fill="#f0efe9", font=font(size))
                continue
            f = font(size)          # turned text: draw it flat on its own tile, rotate, paste above the origin
            tw, th = int(f.getlength(s)) + 2, int(size * scale * 1.2)
            tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            ImageDraw.Draw(tile).text((0, th - size * scale * 0.9 - 2), s, fill="#f0efe9", font=f)
            tile = tile.rotate(angle, expand=True)
            img.paste(tile, (int(X - tile.width + 2), int(Y - tile.height)), tile)
        for x, y, dia in self.holes:
            X, Y = P(x, y)
            r = dia / 2 * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], fill="#ffffff")
        for x, y, w, h in self.slots:
            dr.rounded_rectangle([P(x - w / 2, y + h / 2), P(x + w / 2, y - h / 2)], radius=h / 2 * scale, fill="#ffffff")
        img.save(path)
