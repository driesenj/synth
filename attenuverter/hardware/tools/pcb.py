"""Offset PCB: the one board, placed, net-assigned and unrouted, as an EasyEDA Pro
PCB document inside Offset.epro2 (easyeda_export.py calls this). The board
class, checks and writer are the mixer's and Side FXy's
(stereo-mixer/hardware/tools/pcb.py, side-fx/hardware/tools/pcb.py), cut down
to one board.

Frame. The PCB is drawn the way EasyEDA shows it, looking at the top layer,
and the top layer is the REAR (away from the panel): x to the right, y up,
origin at the board's bottom-left corner, millimetres. The front view that
circuit.PLACEMENT and panel.py use is the mirror image: x_front = BOARD_W - x.

Front (bottom layer): the jacks, pots, LEDs and RANGE toggles at their panel
positions, oriented by rule. Rear (top layer): everything else, every
resistor standing. A rear part's leads come through to the front and are
soldered there, so no rear pad may sit under a front part's body
(front_housing_check). In 10HP those bodies cover most of the board; what
is left decides the layout:
  - the strip above the ATTEN pots: U1 and U2 (TL074) side by side; a third
    DIP-14 does not fit (3 x 16.8 mm of pads in 49.3 mm), so channel 3 has two
    TL072s
  - the strip between the IN and OUT jacks: U3 and U4 (TL072), one between
    each pair of LEDs
  - the strip under the OUT jacks: the power header; the reverse-protection
    diodes and the 10 uF capacitors stand in the side margins beside it
  - the strip between the OFFSET and ATTEN pots: the two LM4040s
  - everything else (resistors, capacitors) on a 2.54 mm grid in the gaps:
    the margins, the channels between the pot columns and the strips between
    the rows. place_grid() puts each part on the free grid spot nearest to the
    pads it connects to (its op-amp pins, pot wipers, jack tips), decoupling
    first.

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
TEMPLATE_TYPES = ("CANVAS", "LAYER", "ACTIVE_LAYER", "RULE_TEMPLATE", "PRIMITIVE", "SILK_OPTS", "PREFERENCE",
                  "LAYER_PHYS", "RULE", "PANELIZE")


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


def rounded(x, y, w, h, r):
    """EasyEDA path of a rounded rectangle from its top-left (y up), lines and clockwise 90-degree arcs.
    The "R" path form's trailing parameters are not corner radii, so rounded shapes are drawn out."""
    r = min(r, w / 2, h / 2)
    path = [mil(x + r), mil(y)]
    for kind, px, py in (("L", x + w - r, y), ("ARC", x + w, y - r), ("L", x + w, y - h + r), ("ARC", x + w - r, y - h),
                         ("L", x + r, y - h), ("ARC", x, y - h + r), ("L", x, y - r), ("ARC", x + r, y)):
        if kind == "L" and (mil(px), mil(py)) == (path[-2], path[-1]):
            continue                      # a slot has no straight piece between its two end arcs
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
    """Pads {num: {id, x, y, w, h}} in mm and the body box (silk, document and courtyard layers) of a
    FOOTPRINT doc."""
    pads, pts = {}, []
    for h, p in doc["recs"]:
        t = h["type"]
        if t == "PAD":
            dp = p["defaultPad"]
            pads[str(p["num"])] = {"id": h["id"], "x": p["centerX"] * 0.0254, "y": p["centerY"] * 0.0254,
                                   "w": dp["width"] * 0.0254, "h": dp["height"] * 0.0254,
                                   "angle": p.get("padAngle") or 0}
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
    body = pts or padpts             # the housing as drawn; pads are checked on their own
    xs, ys = [x for x, _ in body], [y for _, y in body]
    return {"pads": pads, "bbox": (min(xs), min(ys), max(xs), max(ys)), "title": title}


# ---------------------------------------------------------------- the board
class Board:
    """One PCB: parts placed in the rear-view frame."""

    def __init__(self, title, pr, parts, info, W, H):
        self.title, self.pr, self.info, self.W, self.H = title, pr, info, W, H
        self.P = {p.ref: p for p in parts}
        self.placed, self.strings = [], []

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

    def text(self, x, y, s, size=1.5, bottom=False):
        self.strings.append((x, y, s, size, bottom))

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

    def pin(self, ref, num):
        """(x, y) of a placed part's pad."""
        pl = next(p for p in self.placed if p["ref"] == ref)
        return self.pads(pl)[num][:2]

    def pad_shapes(self, pl):
        """Pads as capsules {num: (end, end, r)}: an oval's spine along its long side, a round or
        square pad a point (a square counts as its inscribed circle, as in pads())."""
        out = {}
        for num, pd in pl["geo"]["pads"].items():
            half = abs(pd["w"] - pd["h"]) / 2
            dx, dy = rot(half, 0, pd["angle"] + (90 if pd["h"] > pd["w"] else 0))
            out[num] = (self.pad_xy(pl, pd["x"] - dx, pd["y"] - dy), self.pad_xy(pl, pd["x"] + dx, pd["y"] + dy),
                        min(pd["w"], pd["h"]) / 2)
        return out

    def body(self, pl):
        x1, y1, x2, y2 = pl["geo"]["bbox"]
        cs = [self.pad_xy(pl, x, y) for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
        return (min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs))

    def orient(self, ref, want):
        """Pick the angle of a bottom-layer panel part so that want(front_pads) holds; want gets
        {num: (x_front, y)} relative to the part origin."""
        pl = next(p for p in self.placed if p["ref"] == ref)
        for a in (0, 90, 180, 270):
            pl["angle"] = a
            rel = {n: (self.W - x - (self.W - pl["x"]), y - pl["y"]) for n, (x, y, r) in self.pads(pl).items()}
            if want(rel):
                return a
        raise ValueError(f"no orientation satisfies the rule for {ref}")

    # -- checks
    def check(self):
        """Problems: unplaced or unknown parts, pads too close to each other or the edge, bodies
        overlapping on one side or reaching past the board's edge."""
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
            shapes += [(pl["ref"], num, *s) for num, s in self.pad_shapes(pl).items()]
            x1, y1, x2, y2 = self.body(pl)
            if x1 < -0.01 or y1 < -0.01 or x2 > self.W + 0.01 or y2 > self.H + 0.01:
                bad.append(f"{self.title}: body of {pl['ref']} reaches past the board's edge")
        for i, (ra, na, a1, a2, r1) in enumerate(shapes):
            for rb, nb, b1, b2, r2 in shapes[i + 1:]:
                if ra != rb and abs(a1[0] - b1[0]) < 6 and abs(a1[1] - b1[1]) < 6:
                    gap = min(_seg_dist(a1, b1, b2), _seg_dist(a2, b1, b2), _seg_dist(b1, a1, a2),
                              _seg_dist(b2, a1, a2)) - r1 - r2
                    if gap < CLEAR:
                        bad.append(f"{self.title}: pads {ra}.{na} and {rb}.{nb} are {gap:.2f} mm apart")
        for side in (False, True):
            bodies = [(pl["ref"], self.body(pl)) for pl in self.placed if pl["bottom"] == side]
            for i, (ra, a) in enumerate(bodies):
                for rb, b in bodies[i + 1:]:
                    if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                        ov = min(a[2] - b[0], b[2] - a[0], a[3] - b[1], b[3] - a[1])
                        bad.append(f"{self.title}: bodies of {ra} and {rb} overlap by {ov:.2f} mm on the "
                                   f"{'bottom' if side else 'top'} side")
        return bad

    # -- EasyEDA document
    def doc(self, ee, template, board_uuid, title):
        Doc = ee.Doc
        d = Doc("PCB")
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
        d.add("POLY", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 11, "width": 10,
                                "path": ["R", 0, mil(self.H), mil(self.W), mil(self.H), 0, 0], "locked": False,
                                "zIndex": d.zi(), "polyType": "BOARD_OUTLINE"})
        for x, y, s, size, bottom in self.strings:
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
            for key, val, vis, x, y in (("Footprint", pl["fp"], False, None, None),
                                        ("Designator", ref, True, mil(tx), mil(ty)),
                                        ("Device", self.pr.dev_uuid(inf["dev"]), False, None, None)):
                d.add("ATTR", f"{cid}-{d.nid()}", {"partitionId": "", "groupId": 0, "parentId": cid, "layerId": layer,
                                                   "x": x, "y": y, "key": key, "value": val, "keyVisible": False,
                                                   "valueVisible": vis, "fontFamily": "default", "fontSize": 45,
                                                   "strokeWidth": 6, "bold": False, "italic": False,
                                                   "origin": "LEFT_BOTTOM", "angle": 0, "reverse": False,
                                                   "expansion": 0, "mirror": bool(pl["bottom"]), "locked": False,
                                                   "zIndex": None})
        return d.lines({"title": title, "parent": "", "board": board_uuid, "zIndex": None})

    # -- preview
    def render(self, path, scale=10):
        from PIL import Image, ImageDraw, ImageFont
        W, H = int(self.W * scale), int(self.H * scale)
        img = Image.new("RGB", (W + 40, H + 60), "white")
        dr = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 10)
            big = ImageFont.truetype("arial.ttf", 13)
        except OSError:
            font = big = ImageFont.load_default()

        def P(x, y):
            return 20 + x * scale, 20 + (self.H - y) * scale

        dr.rectangle([P(0, self.H), P(self.W, 0)], outline="#000000", width=2)
        for bottom in (True, False):   # bottom first, top on top
            col = "#2060c0" if bottom else "#c02020"
            for pl in self.placed:
                if pl["bottom"] != bottom:
                    continue
                x1, y1, x2, y2 = self.body(pl)
                dr.rectangle([P(x1, y2), P(x2, y1)], outline=col, width=1)
                for num, (x, y, r) in self.pads(pl).items():
                    X, Y = P(x, y)
                    dr.ellipse([X - r * scale, Y - r * scale, X + r * scale, Y + r * scale], outline=col,
                               fill="#f0d0d0" if not bottom else "#d0d8f0")
                    if num == "1":
                        dr.rectangle([X - 2, Y - 2, X + 2, Y + 2], fill=col)
                X, Y = P(x1, y2)
                dr.text((X + 1, Y - 11), pl["ref"], fill=col, font=font)
        dr.text((20, H + 26), f"{self.title}: rear view (EasyEDA top layer). red = top layer (rear), "
                              "blue = bottom layer (panel side)", fill="#000000", font=big)
        img.save(path)


# ------------------------------------------------------------- placement
def place_pins(b, ref, targets, bottom=False):
    """Place ref so that the first of two pins lands exactly on its target and the second points the
    same way as its target (angles 0 / 90 / 180 / 270 tried). targets: {pin: (x, y)}, PCB frame."""
    (pa, ta), (pb, tb) = list(targets.items())
    b.place(ref, 0, 0, 0, bottom)
    pl = b.placed[-1]
    want = math.atan2(tb[1] - ta[1], tb[0] - ta[0])
    best = None
    for a in (0, 90, 180, 270):
        pl["angle"] = a
        pads = b.pads(pl)
        got = math.atan2(pads[pb][1] - pads[pa][1], pads[pb][0] - pads[pa][0])
        err = abs((got - want + math.pi) % (2 * math.pi) - math.pi)
        if best is None or err < best[0]:
            best = (err, a, pads[pa])
    _, a, (px, py, _) = best
    pl["angle"], pl["x"], pl["y"] = a, ta[0] - px, ta[1] - py
    return pl


# the grid the small parts sit on, front view (board mm): resistors stand on two neighbouring points, the
# 5.08 mm capacitors take three (pads on the ends, the body over the middle one)
GRID_X = [1.9 + 2.54 * i for i in range(19)]
GRID_Y = [1.4 + 2.54 * j for j in range(42)]
PAD_R = 0.9           # the largest small-part pad (FG28: 1.8 mm)
BODY_R = 1.2          # how far a small part's body reaches past a pad (standing resistor 1.1, FG28 1.13)


class Grid:
    """The free points of GRID_X x GRID_Y once the fixed parts are down: none at the board's edge, under a
    front part's body (the leads of a rear part are soldered on the front), within clearance of a fixed
    pad or under a fixed rear part's body."""

    def __init__(self, b):
        self.b = b
        fixed = [(x, y, r) for pl in b.placed for x, y, r in b.pads(pl).values()]
        front = [b.body(pl) for pl in b.placed if pl["bottom"]]
        rear = [b.body(pl) for pl in b.placed if not pl["bottom"]]
        self.free = set()
        for i, xf in enumerate(GRID_X):
            for j, y in enumerate(GRID_Y):
                x, r = b.W - xf, PAD_R
                if x - r < EDGE or x + r > b.W - EDGE or y - r < EDGE or y + r > b.H - EDGE:
                    continue
                if any(x1 - r < x < x2 + r and y1 - r < y < y2 + r for x1, y1, x2, y2 in front):
                    continue
                if any(x1 - BODY_R < x < x2 + BODY_R and y1 - BODY_R < y < y2 + BODY_R for x1, y1, x2, y2 in rear):
                    continue
                if any(math.hypot(x - fx, y - fy) < r + fr + CLEAR for fx, fy, fr in fixed):
                    continue
                self.free.add((i, j))

    def xy(self, i, j):
        return self.b.W - GRID_X[i], GRID_Y[j]


def net_weight(net):
    """How much a pin's distance to its net counts: an op-amp's summing node (high impedance, picks up
    hum) three times, GND a fifth (it is everywhere and will be a pour), the rest once."""
    if net.startswith(("NA", "NB", "SUM", "ND")):
        return 3.0
    return 0.2 if net == "GND" else 1.0


def place_grid(b, refs, homes=None):
    """Put each part (two pins, standing) on the free grid points that cost least: the summed, weighted
    distance from each pin to the nearest pad already on its net, or to the points homes gives for a net
    ({ref: {net: [(x, y)]}}, PCB frame; an empty list makes the net free). Parts go down in the order
    given; a resistor takes two neighbouring points in a column, a 5.08 mm capacitor three."""
    homes = homes or {}
    g = Grid(b)
    for ref in refs:
        part = b.P[ref]
        span = 2 if b.info[ref]["dev"].startswith("C") else 1          # FG28 caps: 5.08 mm
        anchors = {}
        for net in set(part.nets.values()):
            anchors[net] = [xy[:2] for pl in b.placed for n, xy in b.pads(pl).items()
                            if b.P[pl["ref"]].nets.get(n) == net]
        anchors.update(homes.get(ref, {}))
        best = None
        for i, j in sorted(g.free):
            pts = [(i, j - k) for k in range(span + 1)]
            if not all(p in g.free for p in pts):
                continue
            top, bot = g.xy(*pts[0]), g.xy(*pts[-1])
            for order in (("1", "2"), ("2", "1")):
                cost = 0.0
                for pin, at in zip(order, (top, bot)):
                    net = part.nets[pin]
                    w = net_weight(net)
                    if anchors[net]:
                        cost += w * min(math.hypot(at[0] - ax, at[1] - ay) for ax, ay in anchors[net])
                if best is None or cost < best[0]:
                    best = (cost, pts, order, top, bot)
        if best is None:
            raise ValueError(f"no free grid spot left for {ref}")
        _, pts, order, top, bot = best
        place_pins(b, ref, {order[0]: top, order[1]: bot})
        g.free -= set(pts)


def one_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Offset", pr, parts, info, W, H)

    def F(x, y):                          # front view -> this board's frame
        return W - x, y

    # panel parts on the bottom layer, at the PLACEMENT origins, oriented by rule
    for ref, (xf, y, _) in circuit.PLACEMENT.items():
        b.place_front(ref, xf, y, 0, bottom=True)
    for ref, *_ in circuit.JACKS:          # sleeve pad above the tip pad, pins in a column
        b.orient(ref, lambda r: abs(r["1"][0] - r["3"][0]) < 0.01 and r["1"][1] > r["3"][1])
    for ref, *_ in circuit.POTS:           # pins below the shaft, pin 1 on the left (CW turns towards pin 3)
        b.orient(ref, lambda r: r["1"][1] < 0 and abs(r["1"][1] - r["3"][1]) < 0.01 and r["1"][0] < r["3"][0])
    for ref, *_ in circuit.LEDS:           # pads along x, pad 1 (green anode) on the left
        b.orient(ref, lambda r: abs(r["1"][1] - r["2"][1]) < 0.01 and r["1"][0] < r["2"][0])
    for ref, *_ in circuit.TOGGLES:        # pins in a column, pin 3 at the bottom: lever up joins 2-3
        b.orient(ref, lambda r: abs(r["1"][0] - r["3"][0]) < 0.01 and r["3"][1] < r["1"][1])
    # the op-amps: two TL074 in the strip above the ATTEN pots, two TL072 between the LEDs, pins on the grid
    # where the strips allow it
    b.place_front("U1", (GRID_X[1] + GRID_X[7]) / 2, (GRID_Y[38] + GRID_Y[41]) / 2)
    b.place_front("U2", (GRID_X[11] + GRID_X[17]) / 2, (GRID_Y[38] + GRID_Y[41]) / 2)
    led_y = circuit.PLACEMENT["D1"][1]
    for u, (a, c) in (("U3", ("D1", "D2")), ("U4", ("D2", "D3"))):
        b.place_front(u, (circuit.PLACEMENT[a][0] + circuit.PLACEMENT[c][0]) / 2, led_y + 0.25)
    # the references in the strip between the OFFSET and ATTEN pots, between the pot columns
    for ref, xf in (("D4", (circuit.CH_X[0] + circuit.CH_X[1]) / 2 - 0.6),
                    ("D5", (circuit.CH_X[1] + circuit.CH_X[2]) / 2 - 0.6)):
        b.place_front(ref, xf, 78.0)
    # power: the header in the strip under the OUT jacks, pin 1 (-12 V, red stripe) on the left seen from
    # the front; the diodes standing in the side margins, the 10 uF above them. The DO-41 drawing reaches
    # 2.84 mm to one side of the diode, so each diode stands on the side where that points inwards: -12 V
    # (cathode at the bottom) on the left, +12 V (anode at the bottom) on the right
    b.place_front("J7", W / 2, 4.6, 180)
    place_pins(b, "D7", {"1": F(2.6, 2.0), "2": F(2.6, 10.7)})
    place_pins(b, "D6", {"2": F(W - 2.6, 2.0), "1": F(W - 2.6, 10.7)})
    place_pins(b, "C904", {"2": F(2.6, 14.3), "1": F(2.6, 16.8)})
    place_pins(b, "C903", {"1": F(W - 2.6, 14.3), "2": F(W - 2.6, 16.8)})
    # everything else on the grid: decoupling first, each pair drawn to its own chip's supply pins, then the
    # feedback parts round the op-amps, then the rest
    homes = {}
    for i, (u, kind) in enumerate(circuit.OPAMPS.items(), start=1):
        vp, vn = circuit.SUPPLY[kind]
        homes[f"C{903 + 2 * i}"] = {"+12V": [b.pin(u, vp)], "GND": []}
        homes[f"C{904 + 2 * i}"] = {"-12V": [b.pin(u, vn)], "GND": []}
    place_grid(b, list(homes), homes)
    small = [p.ref for p in parts if p.ref not in {pl["ref"] for pl in b.placed}]
    first = [r for r in small if b.P[r].label in ("summer feedback", "A feedback", "B feedback", "cascade feedback")]
    place_grid(b, first + [r for r in small if r not in first])
    b.text(W - 12.0, H - 2.4, "Offset", 1.6)
    return b


def placement_check(b, circuit):
    bad = []
    for ref, (xf, y, _) in circuit.PLACEMENT.items():
        pl = next(p for p in b.placed if p["ref"] == ref)
        if abs(b.W - pl["x"] - xf) > 0.001 or abs(pl["y"] - y) > 0.001:
            bad.append(f"{ref} not at its PLACEMENT origin")
    return bad


def front_housing_check(b):
    """Rear-side pads must not sit under a panel part's body: those pads are soldered on the panel side,
    where the jack, pot and toggle bodies lie on the board."""
    bad = []
    boxes = [(pl["ref"], b.body(pl)) for pl in b.placed if pl["bottom"]]
    for pl in b.placed:
        if pl["bottom"]:
            continue
        for num, (x, y, r) in b.pads(pl).items():
            for ref, (x1, y1, x2, y2) in boxes:
                if x1 - r < x < x2 + r and y1 - r < y < y2 + r:
                    bad.append(f"{b.title}: {pl['ref']}.{num} pad lies under {ref}")
    return bad
