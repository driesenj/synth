"""Tempo PCBs: both boards placed, net-assigned and unrouted, as EasyEDA Pro PCB
documents inside Tempo.epro2 (easyeda_export.py calls this). The Board class,
checks and writer are Senay's (sena/hardware/tools/pcb.py: SMD pads, greedy
placer) with what the display needs from Side FXy's
(side-fx/hardware/tools/pcb.py): a keep-out where the module sits, the
cutout for its cable and its outline on the faceplate's silk.

Frame. Each PCB is drawn the way EasyEDA shows it, looking at the top layer.
On both boards the top layer is the REAR of the stack (away from the panel):
x to the right, y up, origin at the board's bottom-left corner, millimetres.
The front view that circuit.PLACEMENT and panel.py use is the mirror image:
x_front = BOARD_W - x. Both boards share one frame, so a header pair has the
same x/y on both PCBs (checked below).

Faceplate board: jacks, encoders, LED buttons and LEDs on the bottom layer
(towards the panel) at their panel positions; on the top layer the four male
headers in columns between the encoders and in the margins, CN1's wire pads
beside the display, and the SMD logic (74HC165, two 74HC595, pull-ups, LED
resistors) wherever it lands nearest its pins, behind the display included:
SMD parts have no leads through the board. Nothing with leads behind the
module, nothing on the cutout or on the strip where the cable's wires run.
Main board: the four female sockets on the bottom layer, everything else on
the top layer. The breakout stands along the left edge (rear view), USB end
up, D7-D13 in its outer row beside H4 in its channel and D20-D30 in its
inner row beside H3. The four DACs fill the top, the two output op-amps the
middle either side of H2, the CV inputs, the reference and the CLOCK / RESET
inputs the bottom by H1, the ±12 V entry beside the breakout's J1 / J3.

Placer. Chips and the breakout are anchored by hand. Every other SMD part
goes, in netlist order, to the free spot nearest the pads it shares a signal
net with (power nets do not pull; a decoupling cap is pulled to its chip's
supply pin), trying the four angles and keeping 0.3 mm between courtyards.
The user routes by hand and will move parts; the point is that each part
starts beside what it connects to.

Bottom-layer parts: EasyEDA Pro mirrors the footprint about its own X axis
(y -> -y) and then rotates it. Nothing here is routed.
"""
import collections
import json
import math
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "..", "..", "marbles", "hardware", "easyeda", "pcb-template.epru")
MIL = 1 / 0.0254
CLEAR = 0.25          # mm, pad to pad / pad to hole, what the checker insists on
EDGE = 0.5            # mm, pad to board edge
STANDOFF_R = 3.0      # M3 standoff / screw head radius
HOLE_D = 3.2
TEMPLATE_TYPES = ("CANVAS", "LAYER", "ACTIVE_LAYER", "RULE_TEMPLATE", "PRIMITIVE", "SILK_OPTS", "PREFERENCE",
                  "LAYER_PHYS", "RULE", "PANELIZE")
SEED_FP = "DAISY-SEED-POWER-OPAMPS-2.54"   # stands on its sockets: screw heads fit under it
POWER_NETS = {"GND", "+12V", "-12V", "3V3A", "3V3D", "GND_F", "GND_D_F", "3V3D_F"}
SHORT_NETS, SHORT_WEIGHT = ("IN_", "B_"), 3     # summing nodes and transistor bases pull harder


def mil(v):
    return round(v * MIL, 4)


def rot(x, y, a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return x * c - y * s, x * s + y * c


def _seg_dist(p, a, b):
    """Distance from point p to the segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0 if n == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def rounded(x, y, w, h, r):
    """EasyEDA path of a rounded rectangle from its top-left (y up), lines and clockwise 90-degree arcs
    (Side FXy's). The "R" path form's trailing parameters are not corner radii, so rounded shapes are drawn out."""
    r = min(r, w / 2, h / 2)
    path = [mil(x + r), mil(y)]
    for kind, px, py in (("L", x + w - r, y), ("ARC", x + w, y - r), ("L", x + w, y - h + r), ("ARC", x + w - r, y - h),
                         ("L", x + r, y - h), ("ARC", x, y - h + r), ("L", x, y - r), ("ARC", x + r, y)):
        if kind == "L" and (mil(px), mil(py)) == (path[-2], path[-1]):
            continue
        path += ["L", mil(px), mil(py)] if kind == "L" else ["ARC", -90, mil(px), mil(py)]
    return path


# ------------------------------------------------------------- template
def load_template(ee):
    """The canvas, layer, rule and preference records of one of your PCBs, cached in the repo (Marblesy's)."""
    recs = []
    for line in open(TEMPLATE, encoding="utf-8").read().split("\n"):
        if line:
            h, _, p = line.partition("||")
            recs.append((json.loads(h), json.loads(p[:-1] if p.endswith("|") else p)))
    return recs


# ------------------------------------------------------------ footprints
def _path_points(path, out):
    i, mode = 0, "L"
    while i < len(path):
        t = path[i]
        if isinstance(t, str):
            mode, i = t, i + 1
            if mode == "ARC":
                i += 1
            elif mode == "CIRCLE":
                cx, cy, r = path[i:i + 3]
                out += [(cx - r, cy - r), (cx + r, cy + r)]
                i, mode = i + 3, "L"
            elif mode == "R":
                x, y, w, h = path[i:i + 4]
                out += [(x, y), (x + w, y - h)]
                i, mode = i + 6, "L"
            continue
        out.append((path[i], path[i + 1]))
        i += 2


def footprint_geometry(doc):
    """Pads {num: {id, x, y, w, h, smd}} in mm and the body box (silk, document and courtyard layers) of a
    FOOTPRINT doc."""
    pads, pts = {}, []
    for h, p in doc["recs"]:
        t = h["type"]
        if t == "PAD":
            dp = p["defaultPad"]
            pads[str(p["num"])] = {"id": h["id"], "x": p["centerX"] * 0.0254, "y": p["centerY"] * 0.0254,
                                   "w": dp["width"] * 0.0254, "h": dp["height"] * 0.0254,
                                   "angle": p.get("padAngle") or 0, "smd": p.get("hole") is None}
        elif t in ("POLY", "FILL") and p.get("layerId") in (3, 13, 48):
            path = p["path"]
            paths = path if (path and isinstance(path[0], list)) else [path]
            raw = []
            for pa in paths:
                _path_points(pa, raw)
            pts += [(x * 0.0254, y * 0.0254) for x, y in raw]
    title = next(p["title"] for h, p in doc["recs"] if h["type"] == "META")
    padpts = []
    for pd in pads.values():
        padpts += [(pd["x"] - pd["w"] / 2, pd["y"] - pd["h"] / 2), (pd["x"] + pd["w"] / 2, pd["y"] + pd["h"] / 2)]
    body = pts or padpts
    xs, ys = [x for x, _ in body], [y for _, y in body]
    return {"pads": pads, "bbox": (min(xs), min(ys), max(xs), max(ys)), "title": title}


# ---------------------------------------------------------------- boards
class Board:
    """One PCB: parts placed in the shared rear-view frame."""

    def __init__(self, title, pr, parts, info, W, H):
        self.title, self.pr, self.info, self.W, self.H = title, pr, info, W, H
        self.P = {p.ref: p for p in parts}
        self.placed, self.holes, self.strings = [], [], []
        self.keepouts, self.rear_keepouts, self.cutouts, self.outlines = [], [], [], []

    # -- placing
    def place(self, ref, x, y, angle=0, bottom=False):
        if ref not in self.P:
            raise KeyError(f"{ref} is not a {self.title} part")
        dev = self.info[ref]["dev"]
        fp = self.pr.device_attrs(dev)["Footprint"]
        self.placed.append({"ref": ref, "x": x, "y": y, "angle": angle % 360, "bottom": bottom, "fp": fp,
                            "geo": self.pr.footprint_geo(fp)})
        return self.placed[-1]

    def place_front(self, ref, xf, y, angle=0, bottom=False):
        """Place by front-view coordinates (circuit.PLACEMENT / panel.py)."""
        return self.place(ref, self.W - xf, y, angle, bottom)

    def hole_front(self, xf, y, d=HOLE_D):
        self.holes.append((self.W - xf, y, d))

    def text(self, x, y, s, size=1.5, bottom=False):
        self.strings.append((x, y, s, size, bottom))

    def box_front(self, x1, y1, x2, y2):
        """A front-view box in this board's frame."""
        return self.W - x2, y1, self.W - x1, y2

    def keepout_front(self, x1, y1, x2, y2, what):
        """Something in the panel gap (front side) that no lead may sit under."""
        self.keepouts.append((self.box_front(x1, y1, x2, y2), what))

    def keepout_rear(self, x1, y1, x2, y2, what):
        """A strip of the rear (top layer) that stays free of parts."""
        self.rear_keepouts.append((self.box_front(x1, y1, x2, y2), what))

    def cutout_front(self, x1, y1, x2, y2, r):
        self.cutouts.append((*self.box_front(x1, y1, x2, y2), r))

    def outline_front(self, x1, y1, x2, y2, label, bottom=True):
        self.outlines.append((self.box_front(x1, y1, x2, y2), label, bottom))

    # -- geometry
    @staticmethod
    def pad_xy(pl, px, py):
        if pl["bottom"]:
            py = -py
        dx, dy = rot(px, py, pl["angle"])
        return pl["x"] + dx, pl["y"] + dy

    def pads(self, pl):
        return {num: (*self.pad_xy(pl, pd["x"], pd["y"]), max(pd["w"], pd["h"]) / 2)
                for num, pd in pl["geo"]["pads"].items()}

    def get(self, ref):
        return next(p for p in self.placed if p["ref"] == ref)

    def pin(self, ref, num):
        return self.pads(self.get(ref))[num][:2]

    def pad_shapes(self, pl):
        """Pads as capsules {num: (end, end, r, layers)}: the spine along the long side; layers 'TB' for a
        through-hole pad, 'T' or 'B' for an SMD pad on the side the part sits on."""
        out = {}
        for num, pd in pl["geo"]["pads"].items():
            half = abs(pd["w"] - pd["h"]) / 2
            dx, dy = rot(half, 0, pd["angle"] + (90 if pd["h"] > pd["w"] else 0))
            side = "TB" if not pd["smd"] else ("B" if pl["bottom"] else "T")
            out[num] = (self.pad_xy(pl, pd["x"] - dx, pd["y"] - dy), self.pad_xy(pl, pd["x"] + dx, pd["y"] + dy),
                        min(pd["w"], pd["h"]) / 2, side)
        return out

    def body(self, pl):
        x1, y1, x2, y2 = pl["geo"]["bbox"]
        cs = [self.pad_xy(pl, x, y) for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
        return (min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs))

    def extent(self, pl):
        """Body box grown to cover the pads: what the part occupies on its own side."""
        x1, y1, x2, y2 = self.body(pl)
        for x, y, r in self.pads(pl).values():
            x1, y1, x2, y2 = min(x1, x - r), min(y1, y - r), max(x2, x + r), max(y2, y + r)
        return x1, y1, x2, y2

    def smd(self, pl):
        return all(pd["smd"] for pd in pl["geo"]["pads"].values())

    def front_pads(self, ref):
        return {num: (round(self.W - x, 3), round(y, 3)) for num, (x, y, r) in self.pads(self.get(ref)).items()}

    def orient(self, ref, want):
        """Pick the angle of a bottom-layer panel part so that want(front_pads) holds; want gets
        {num: (x_front, y)} relative to the part origin."""
        pl = self.get(ref)
        for a in (0, 90, 180, 270):
            pl["angle"] = a
            rel = {n: (pl["x"] - x, y - pl["y"]) for n, (x, y, r) in self.pads(pl).items()}
            if want(rel):
                return a
        raise ValueError(f"no orientation satisfies the rule for {ref}")

    # -- checks
    def check(self, gap_side):
        """Problems: unplaced parts, pads too close to each other (on a shared layer), to a hole, a cutout or
        the edge, bodies overlapping on one side, an SMD body over a through-hole pad, parts on a rear
        keep-out, bodies under a standoff (gap side) or a screw head (the other side) or over a cutout.
        gap_side: 'top' or 'bottom', the side that faces the other board."""
        bad = []
        refs = collections.Counter(pl["ref"] for pl in self.placed)
        for ref in self.P:
            if refs[ref] != 1:
                bad.append(f"{self.title}: {ref} placed {refs[ref]} times")
        shapes = []
        for pl in self.placed:
            for num, (x, y, r) in self.pads(pl).items():
                if x - r < EDGE or x + r > self.W - EDGE or y - r < EDGE or y + r > self.H - EDGE:
                    bad.append(f"{self.title}: {pl['ref']}.{num} pad at ({x:.2f}, {y:.2f}) is at the board edge")
                for hx, hy, hd in self.holes:
                    if math.hypot(x - hx, y - hy) < r + hd / 2 + CLEAR:
                        bad.append(f"{self.title}: {pl['ref']}.{num} pad is {math.hypot(x - hx, y - hy):.2f} "
                                   f"from the hole at ({hx:.1f}, {hy:.1f})")
                for x1, y1, x2, y2, _ in self.cutouts:
                    if x1 - r - CLEAR < x < x2 + r + CLEAR and y1 - r - CLEAR < y < y2 + r + CLEAR:
                        bad.append(f"{self.title}: {pl['ref']}.{num} pad at ({x:.2f}, {y:.2f}) is at the cutout")
            shapes += [(pl["ref"], num, *s) for num, s in self.pad_shapes(pl).items()]
        cells = collections.defaultdict(list)
        for s in shapes:
            cells[(int(s[2][0] // 4), int(s[2][1] // 4))].append(s)
        for ra, na, a1, a2, r1, la in shapes:
            cx, cy = int(a1[0] // 4), int(a1[1] // 4)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for rb, nb, b1, b2, r2, lb in cells[(cx + dx, cy + dy)]:
                        if (rb, nb) <= (ra, na) or ra == rb or not set(la) & set(lb):
                            continue
                        gap = min(_seg_dist(a1, b1, b2), _seg_dist(a2, b1, b2), _seg_dist(b1, a1, a2),
                                  _seg_dist(b2, a1, a2)) - r1 - r2
                        if gap < CLEAR:
                            bad.append(f"{self.title}: pads {ra}.{na} and {rb}.{nb} are {gap:.2f} mm apart")
        th = [(pl["ref"], num, x, y, r) for pl in self.placed for num, (a, c, r, side) in self.pad_shapes(pl).items()
              if side == "TB" for x, y in (a,)]
        for pl in self.placed:
            if not self.smd(pl):
                continue
            x1, y1, x2, y2 = self.body(pl)
            for ref, num, x, y, r in th:
                if ref != pl["ref"] and x1 - r < x < x2 + r and y1 - r < y < y2 + r:
                    bad.append(f"{self.title}: body of {pl['ref']} lies over {ref}.{num}")
        for (kx1, ky1, kx2, ky2), what in self.rear_keepouts:
            for pl in self.placed:
                if not pl["bottom"] and _overlap(self.extent(pl), (kx1, ky1, kx2, ky2)):
                    bad.append(f"{self.title}: {pl['ref']} sits on the {what}")
        for side in (False, True):
            bodies = [(pl["ref"], self.body(pl), pl["geo"]["title"]) for pl in self.placed if pl["bottom"] == side]
            for i, (ra, a, _) in enumerate(bodies):
                for rb, b, _ in bodies[i + 1:]:
                    if _overlap(a, b):
                        ov = min(a[2] - b[0], b[2] - a[0], a[3] - b[1], b[3] - a[1])
                        bad.append(f"{self.title}: bodies of {ra} and {rb} overlap by {ov:.2f} mm on the "
                                   f"{'bottom' if side else 'top'} side")
            gap = (side and gap_side == "bottom") or (not side and gap_side == "top")
            what = "standoff" if gap else "screw head"
            for ref, (x1, y1, x2, y2), title in bodies:
                if title == SEED_FP and not gap:
                    continue                 # the breakout stands on its sockets, over the screw heads
                for hx, hy, hd in self.holes:
                    cx, cy = min(max(hx, x1), x2), min(max(hy, y1), y2)
                    if math.hypot(cx - hx, cy - hy) < STANDOFF_R:
                        bad.append(f"{self.title}: body of {ref} sits under the {what} at ({hx:.1f}, {hy:.1f})")
                for cx1, cy1, cx2, cy2, _ in self.cutouts:
                    if not side and _overlap((x1, y1, x2, y2), (cx1, cy1, cx2, cy2)):
                        bad.append(f"{self.title}: body of {ref} lies over the cutout")
        return bad

    # -- EasyEDA document
    def doc(self, ee, template, board_uuid, title):
        d = ee.Doc("PCB")
        nets = sorted({n for p in self.P.values() for n in p.nets.values()})
        first = [r for r in template if r[0]["type"] in ("CANVAS", "LAYER", "ACTIVE_LAYER")]
        rules = [r for r in template if r[0]["type"] in ("RULE_TEMPLATE", "PRIMITIVE", "SILK_OPTS", "PREFERENCE",
                                                           "LAYER_PHYS", "RULE")]
        panel = [r for r in template if r[0]["type"] == "PANELIZE"]
        for h, p in first:
            d.add(h["type"], h["id"], p)
        for n in nets:
            d.add("NET", json.dumps(["NET", n], separators=(",", ":")),
                  {"netType": None, "specialColor": None, "retLine": False, "differentialName": None,
                   "isPositiveNet": False, "equalLengthGroupName": None})
        for h, p in rules:
            d.add(h["type"], h["id"], p)
        for n in nets:
            d.add("RULE_SELECTOR", json.dumps(["RULE_SELECTOR", ["NET", n]], separators=(",", ":")),
                  {"ruleOrder": 4, "ruleKeyValue": {}, "copperValue": {"COPPER": "Copper_copperRegion"},
                   "innerPlaneValue": {"PLANE": "Plane_innerPlane"}})
        for h, p in panel:
            d.add(h["type"], h["id"], p)

        def fill(layer, path):
            d.add("FILL", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": layer, "width": 1,
                                    "fillStyle": "SOLID", "path": [path], "locked": False, "zIndex": d.zi(),
                                    "isBridgingCopper": False, "networkList": [], "refs": []})

        for hx, hy, hd in self.holes:
            fill(12, ["CIRCLE", mil(hx), mil(hy), mil(hd / 2)])
        for x1, y1, x2, y2, r in self.cutouts:      # a non-plated region: the fab mills it out
            fill(12, rounded(x1, y2, x2 - x1, y2 - y1, r))
        d.add("POLY", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 11, "width": 10,
                                "path": ["R", 0, mil(self.H), mil(self.W), mil(self.H), 0, 0], "locked": False,
                                "zIndex": d.zi(), "polyType": "BOARD_OUTLINE"})
        strings = list(self.strings)
        for (x1, y1, x2, y2), label, bottom in self.outlines:
            d.add("POLY", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 4 if bottom else 3,
                                    "width": mil(0.2), "path": [mil(x1), mil(y1), "L", mil(x2), mil(y1), "L", mil(x2),
                                                                mil(y2), "L", mil(x1), mil(y2), "L", mil(x1), mil(y1)],
                                    "locked": False, "zIndex": d.zi(), "polyType": "NORMAL"})
            strings.append((x2 - 1.0, y2 - 3.0, label, 1.3, bottom))
        for x, y, s, size, bottom in strings:
            d.add("STRING", d.nid(), {"partitionId": "", "groupId": 0, "layerId": 4 if bottom else 3, "x": mil(x),
                                      "y": mil(y), "text": s, "fontFamily": "default", "fontSize": mil(size),
                                      "strokeWidth": mil(size / 8), "bold": False, "italic": False,
                                      "origin": "LEFT_BOTTOM", "angle": 0, "reverse": False, "expansion": 0,
                                      "mirror": bottom, "locked": False, "zIndex": d.zi()})
        for pl in self.placed:
            ref, inf = pl["ref"], self.info[pl["ref"]]
            cid = d.nid()
            d.add("COMPONENT", cid, {"partitionId": "", "groupId": 0, "layerId": 2 if pl["bottom"] else 1,
                                     "x": mil(pl["x"]), "y": mil(pl["y"]), "angle": pl["angle"],
                                     "attrs": {"Unique ID": inf["uid"], "Reuse Block": "", "Group ID": "",
                                               "Channel ID": inf["channel"]},
                                     "locked": False, "zIndex": d.zi()})
            for num, net in self.P[ref].nets.items():
                pd = pl["geo"]["pads"].get(num)
                if pd is None:
                    raise KeyError(f"{ref} pin {num} has no pad in its footprint")
                d.add("PAD_NET", json.dumps(["PAD_NET", cid, num, pd["id"]], separators=(",", ":")),
                      {"partitionId": "", "padNet": net, "padLen": 0})
            layer = 4 if pl["bottom"] else 3
            x1, y1, x2, y2 = self.body(pl)
            tx, ty = (x1 if not pl["bottom"] else x2), y2 + 0.3
            big = self.P[ref].kind in ("JACK", "ENC", "SWLED", "SEED")
            for key, val, vis, x, y in (("Footprint", pl["fp"], False, None, None),
                                        ("Designator", ref, True, mil(tx), mil(ty)),
                                        ("Device", self.pr.dev_uuid(inf["dev"]), False, None, None)):
                d.add("ATTR", f"{cid}-{d.nid()}", {"partitionId": "", "groupId": 0, "parentId": cid, "layerId": layer,
                                                   "x": x, "y": y, "key": key, "value": val, "keyVisible": False,
                                                   "valueVisible": vis, "fontFamily": "default",
                                                   "fontSize": 45 if big else 30, "strokeWidth": 5, "bold": False,
                                                   "italic": False, "origin": "LEFT_BOTTOM", "angle": 0,
                                                   "reverse": False, "expansion": 0, "mirror": bool(pl["bottom"]),
                                                   "locked": False, "zIndex": None})
        return d.lines({"title": title, "parent": "", "board": board_uuid, "zIndex": None})

    # -- preview
    def ratsnest(self):
        """Per signal net, the shortest tree joining its pads (Prim): [(net, (x, y), (x, y))]."""
        where = collections.defaultdict(list)
        for pl in self.placed:
            pads = self.pads(pl)
            for num, net in self.P[pl["ref"]].nets.items():
                if net not in POWER_NETS:
                    where[net].append(pads[num][:2])
        lines = []
        for net, pts in where.items():
            done, rest = [pts[0]], pts[1:]
            while rest:
                d, a, b = min((math.dist(a, b), a, b) for a in done for b in rest)
                lines.append((net, a, b))
                done.append(b)
                rest.remove(b)
        return lines

    def render(self, path, scale=10, ratsnest=False):
        from PIL import Image, ImageDraw, ImageFont
        W, H = int(self.W * scale), int(self.H * scale)
        img = Image.new("RGB", (W + 40, H + 60), "white")
        dr = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 9)
            big = ImageFont.truetype("arial.ttf", 13)
        except OSError:
            font = big = ImageFont.load_default()

        def P(x, y):
            return 20 + x * scale, 20 + (self.H - y) * scale

        dr.rectangle([P(0, self.H), P(self.W, 0)], outline="#000000", width=2)
        for (x1, y1, x2, y2), what in self.keepouts:
            dr.rectangle([P(x1, y2), P(x2, y1)], fill="#f2f2f2", outline="#909090")
            dr.text((P(x1, y2)[0] + 4, P(x1, y2)[1] + 4), what, fill="#707070", font=big)
        for (x1, y1, x2, y2), what in self.rear_keepouts:
            dr.rectangle([P(x1, y2), P(x2, y1)], fill="#fff4dc", outline="#c09040")
        for x1, y1, x2, y2, r in self.cutouts:
            dr.rounded_rectangle([P(x1, y2), P(x2, y1)], radius=r * scale, fill="#404040")
        for bottom in (True, False):   # bottom first, top on top
            col = "#2060c0" if bottom else "#c02020"
            for pl in self.placed:
                if pl["bottom"] != bottom:
                    continue
                x1, y1, x2, y2 = self.body(pl)
                dr.rectangle([P(x1, y2), P(x2, y1)], outline=col, width=1)
                for num, (a, b, r, side) in self.pad_shapes(pl).items():
                    A, B = P(*a), P(*b)
                    rr = r * scale
                    dr.rounded_rectangle([min(A[0], B[0]) - rr, min(A[1], B[1]) - rr, max(A[0], B[0]) + rr,
                                          max(A[1], B[1]) + rr], radius=rr, outline=col,
                                         fill="#f0d0d0" if not bottom else "#d0d8f0")
                    if num == "1":
                        dr.rectangle([A[0] - 1, A[1] - 1, A[0] + 1, A[1] + 1], fill=col)
                X, Y = P(x1, y2)
                dr.text((X + 1, Y - 10), pl["ref"], fill=col, font=font)
        for hx, hy, hd in self.holes:
            X, Y = P(hx, hy)
            r = hd / 2 * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], outline="#000000", width=2)
            r = STANDOFF_R * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], outline="#808080")
        if ratsnest:
            for net, a, b in self.ratsnest():
                dr.line([P(*a), P(*b)], fill="#30a030", width=1)
        dr.text((20, H + 26), f"{self.title}: rear view (EasyEDA top layer). red = top layer, blue = bottom layer, "
                              f"grey = M3 standoff, dark = cutout", fill="#000000", font=big)
        img.save(path)


# ---------------------------------------------------------------- placer
class Placer:
    """Greedy placement of a board's SMD parts on its top layer (Senay's; see the module docstring)."""

    MARGIN = 0.3          # courtyard gap
    STEP = 0.5

    def __init__(self, b, region=None):
        self.b = b
        self.region = region or (EDGE, EDGE, b.W - EDGE, b.H - EDGE)
        self.pulls = {}                        # ref -> pull, kept for improve()
        self.rects = []                        # occupied boxes on the top layer (and through-hole pads)
        for pl in b.placed:
            if not pl["bottom"]:
                self.rects.append(b.extent(pl))
            else:
                for num, (a, c, r, side) in b.pad_shapes(pl).items():
                    if "T" in side:
                        self.rects.append((min(a[0], c[0]) - r, min(a[1], c[1]) - r, max(a[0], c[0]) + r,
                                           max(a[1], c[1]) + r))
        for hx, hy, hd in b.holes:
            self.rects.append((hx - STANDOFF_R, hy - STANDOFF_R, hx + STANDOFF_R, hy + STANDOFF_R))
        for x1, y1, x2, y2, r in b.cutouts:
            self.rects.append((x1 - CLEAR, y1 - CLEAR, x2 + CLEAR, y2 + CLEAR))
        for box, what in b.rear_keepouts:
            self.rects.append(box)

    def free(self, box, region):
        x1, y1, x2, y2 = box
        rx1, ry1, rx2, ry2 = region
        if x1 < rx1 or y1 < ry1 or x2 > rx2 or y2 > ry2:
            return False
        m = self.MARGIN
        return not any(x1 - m < b[2] and b[0] < x2 + m and y1 - m < b[3] and b[1] < y2 + m for b in self.rects)

    def targets(self, ref, pull=None):
        """Pads of placed parts sharing a signal net with ref: {pin: [(x, y)]}."""
        b = self.b
        want = collections.defaultdict(list)
        done = {pl["ref"]: pl for pl in b.placed}
        for pin, net in b.P[ref].nets.items():
            if net in POWER_NETS and not (pull and pin in pull):
                continue
            for other, part in b.P.items():
                if other == ref or other not in done:
                    continue
                for opin, onet in part.nets.items():
                    if onet == net:
                        want[pin].append(b.pads(done[other])[opin][:2])
        if pull:
            for pin, xy in pull.items():
                want[pin] = [xy]
        return want

    def put(self, ref, region=None, pull=None, near=None, radius=30):
        """Place ref at the free spot (0.5 mm grid, four angles) nearest the pads it connects to. Summing nodes
        and transistor bases (IN_*, B_*) count three times, as on Offset: they are the nodes to keep short."""
        b = self.b
        region = region or self.region
        want = self.targets(ref, pull)
        weight = {pin: SHORT_WEIGHT if b.P[ref].nets[pin].startswith(SHORT_NETS) else 1 for pin in want}
        if near:
            cx, cy = near
        elif want:
            tot = sum(weight.values())
            cx = sum(weight[p] * sum(x for x, _ in ps) / len(ps) for p, ps in want.items()) / tot
            cy = sum(weight[p] * sum(y for _, y in ps) / len(ps) for p, ps in want.items()) / tot
        else:
            cx, cy = (region[0] + region[2]) / 2, (region[1] + region[3]) / 2
        pl = b.place(ref, cx, cy, 0)
        n = int(radius / self.STEP)
        cands = sorted(((i * self.STEP, j * self.STEP) for i in range(-n, n + 1) for j in range(-n, n + 1)),
                       key=lambda d: d[0] ** 2 + d[1] ** 2)
        best = None
        for dx, dy in cands:
            dist = math.hypot(dx, dy)
            if best and dist > best[0] + 1.5:
                break
            for a in (0, 90, 180, 270):
                pl["x"], pl["y"], pl["angle"] = cx + dx, cy + dy, a
                box = b.extent(pl)
                if not self.free(box, region):
                    continue
                pads = b.pads(pl)
                cost = dist + sum(weight[pin] * min(math.hypot(pads[pin][0] - x, pads[pin][1] - y) for x, y in ps)
                                  for pin, ps in want.items())
                if best is None or cost < best[1]:
                    best = (dist, cost, pl["x"], pl["y"], a)
        if best is None:
            raise ValueError(f"no room for {ref} in {region}")
        _, _, pl["x"], pl["y"], pl["angle"] = best
        self.rects.append(b.extent(pl))
        return pl

    def fix(self, ref, x, y, angle=0):
        """An anchored part: placed where asked and then an obstacle like the rest."""
        pl = self.b.place(ref, x, y, angle)
        self.rects.append(self.b.extent(pl))
        return pl

    def decouple(self, ref, chip, pin):
        """A decoupling cap pulled to its chip's supply pin by the pad on that pin's net."""
        net = self.b.P[chip].nets[pin]
        cpin = next(n for n, v in self.b.P[ref].nets.items() if v == net)
        self.pulls[ref] = {cpin: self.b.pin(chip, pin)}
        return self.put(ref, pull=self.pulls[ref], radius=12)

    def improve(self, refs, rounds=8):
        """Greedy placement depends on the order (the S&H's lesson): lift each part in turn and put it back at
        its cheapest spot now that everything else is down, until a round moves nothing. Returns the rounds run."""
        b = self.b
        for k in range(rounds):
            moved = 0
            for ref in refs:
                pl = b.get(ref)
                before = (round(pl["x"], 3), round(pl["y"], 3), pl["angle"])
                self.rects.remove(b.extent(pl))
                b.placed.remove(pl)
                pl = self.put(ref, pull=self.pulls.get(ref))
                moved += (round(pl["x"], 3), round(pl["y"], 3), pl["angle"]) != before
            if not moved:
                return k + 1
        return rounds


# ------------------------------------------------------------- the boards
def headers(b, circuit, refs, bottom):
    """The board-to-board headers at circuit.HEADERS_FRONT, pin 1 at the top (male on the faceplate's top
    layer, female on the main board's bottom layer: the same pad positions)."""
    for ref, kind, pins in circuit.HEADERS:
        xf, y, a = circuit.HEADERS_FRONT[ref]
        b.place_front(refs(ref), xf, y, a, bottom)


def faceplate_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Faceplate", pr, parts, info, W, H)
    for xf, y in circuit.HOLES_FRONT:      # the same three on the main board
        b.hole_front(xf, y)
    # panel parts on the bottom layer, at the PLACEMENT origins, oriented by rule
    for ref, (xf, y, _) in circuit.PLACEMENT.items():
        if ref in b.P:
            b.place_front(ref, xf, y, 0, bottom=True)
    for ref, *_ in circuit.JACKS:          # sleeve pad above the tip pad, pins in a column
        b.orient(ref, lambda r: abs(r["1"][0] - r["3"][0]) < 0.01 and r["1"][1] > r["3"][1])
    for ref, *_ in circuit.BUTTONS:        # LED pins in a row along x, anode on the right
        b.orient(ref, lambda r: abs(r["5"][1] - r["6"][1]) < 0.01 and r["5"][0] > r["6"][0] and r["1"][1] > r["3"][1])
    for ref, _ in circuit.ENCODERS:        # phase row below the shaft, switch pins above
        b.orient(ref, lambda r: r["C"][1] < -5 and r["S1"][1] > 5)
    for ref, jack in circuit.OUTPUT_LEDS:  # anode on the left
        b.orient(ref, lambda r: abs(r["1"][1] - r["2"][1]) < 0.01 and r["1"][0] < r["2"][0])
    # the display module in the panel gap, its outline on the bottom silk, the cable's cutout and the strip
    # its wires take to CN1 on the rear
    b.keepout_front(*circuit.DISPLAY_MODULE, "display module (front)")
    b.outline_front(*circuit.DISPLAY_MODULE, "DISPLAY")
    b.cutout_front(*circuit.DISPLAY_CUTOUT)
    b.keepout_rear(*circuit.CABLE_PATH, "display cable's path")
    # top (rear) layer: the male headers and CN1's wire pads, then the SMD logic
    headers(b, circuit, circuit.fb_ref, False)
    b.place_front("CN1", *circuit.CN1_FRONT)
    pc = Placer(b)

    def centroid(pts):
        return sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)

    pc.put("U10")                          # the switches' 165, between its six switches and H3
    pc.put("U11", near=centroid([b.pin(ref, "1") for ref, _ in circuit.OUTPUT_LEDS]))
    pc.put("U12", near=centroid([b.pin(ref, "5") for ref, *_ in circuit.BUTTONS]))
    for k, u in enumerate(("U10", "U11", "U12")):
        pc.decouple(f"C{k + 1}", u, "16")
    pc.decouple("C4", "CN1", "1")
    loose = [p.ref for p in parts if p.kind == "R"]
    for ref in loose:
        pc.put(ref)
    pc.improve(loose + ["C1", "C2", "C3", "C4"])
    b.text(8.0, 103.5, "Tempo faceplate", 1.6)
    return b


# Main board, top (rear) layer, PCB frame: x = BOARD_W - x_front, so the front view's right edge is on the
# left. The breakout stands along that edge, USB end up: pins 1-20 (D0-D14: clock, DACs, display, reset) in
# its outer row at x 2.08 with pin 1 at the top, pins 21-40 (3V3A, ADC, gates, encoders, chain, 3V3D) in
# its inner row at x 17.32 with pin 21 at the bottom, J1 / J3 (+-12 V) below the pins.
SEED_XY = (9.7, 66.0, 90)
# DACs at the top, two per output op-amp; the op-amps either side of H2; under the holes U9 (RUN / RESET
# gates) by the Seed's gate pins and U8 (CV inputs, the -2.5 V inverter) between the ADC pins and H1.
CHIPS = {
    "U2": (30.0, 101.5, 0), "U3": (30.0, 90.5, 0), "U4": (48.5, 101.5, 0), "U5": (48.5, 90.5, 0),
    "U6": (29.5, 68.0, 90), "U7": (47.5, 68.0, 90),
    "U9": (27.0, 39.0, 0), "U8": (40.5, 37.0, 0),
}


def main_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Main board", pr, parts, info, W, H)
    for xf, y in circuit.HOLES_FRONT:
        b.hole_front(xf, y)
    headers(b, circuit, lambda ref: ref, True)          # female sockets, bottom layer, same spot
    b.place("U1", *SEED_XY)
    pc = Placer(b)
    for ref, (x, y, a) in CHIPS.items():
        pc.fix(ref, x, y, a)
    for k, u in enumerate(("U6", "U7", "U8", "U9")):
        pc.decouple(f"C{15 + 2 * k}", u, "4")
        pc.decouple(f"C{16 + 2 * k}", u, "11")
    for k, u in enumerate(circuit.DAC_CS):
        pc.decouple(f"C{23 + k}", u, "1")
    # the bulk caps by the breakout's +12 V (J3) and -12 V (J1) pins
    pc.pulls["C27"] = {"1": b.pin("U1", "J3-2")}
    pc.pulls["C28"] = {"2": b.pin("U1", "J1-2")}
    for ref in ("C27", "C28"):
        pc.put(ref, pull=pc.pulls[ref])
    loose = [p.ref for p in parts if p.ref not in {pl["ref"] for pl in b.placed}]
    for ref in loose:
        pc.put(ref)
    pc.improve(loose + list(pc.pulls))
    b.text(22.0, 1.2, "Tempo main board", 1.6)
    return b


def header_check(fb, mb, circuit):
    bad = []
    for ref, kind, pins in circuit.HEADERS:
        a, c = fb.front_pads(circuit.fb_ref(ref)), mb.front_pads(ref)
        for num in a:
            if a[num] != c.get(num):
                bad.append(f"header {ref} pin {num}: faceplate {a[num]} vs main board {c.get(num)}")
    return bad


def placement_check(fb, circuit):
    bad = []
    for ref, (xf, y, _) in circuit.PLACEMENT.items():
        if ref not in fb.P:              # DS1: the display module, not a part of this board
            continue
        pl = fb.get(ref)
        if abs(fb.W - pl["x"] - xf) > 0.001 or abs(pl["y"] - y) > 0.001:
            bad.append(f"{ref} not at its PLACEMENT origin")
    return bad


def front_housing_check(fb):
    """Through-hole pads of rear-side parts must not sit under a panel part's housing or the display module:
    they are soldered on the panel side, where the jack, encoder and button bodies and the module lie."""
    bad = []
    boxes = [(pl["ref"], fb.body(pl)) for pl in fb.placed if pl["bottom"]] + [(w, box) for box, w in fb.keepouts]
    for pl in fb.placed:
        if pl["bottom"]:
            continue
        for num, (a, c, r, side) in fb.pad_shapes(pl).items():
            if side != "TB":
                continue
            x, y = a
            for ref, (x1, y1, x2, y2) in boxes:
                if x1 - r < x < x2 + r and y1 - r < y < y2 + r:
                    bad.append(f"{fb.title}: {pl['ref']}.{num} pad lies under {ref}")
    return bad
