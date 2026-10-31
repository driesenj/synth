"""Six PCBs: both boards placed, net-assigned and unrouted, as EasyEDA Pro PCB
documents inside Six.epro2 (easyeda_export.py calls this). The Board class,
checks, writer and greedy placer are Envy's (envelope/hardware/tools/pcb.py,
Senay's before that), copied so a change there cannot move these boards.

Frame. Each PCB is drawn the way EasyEDA shows it, looking at the top layer.
On both boards the top layer is the REAR of the stack (away from the panel):
x to the right, y up, origin at the board's bottom-left corner, millimetres.
The front view that circuit.PLACEMENT and panel.py use is the mirror image:
x_front = BOARD_W - x. Both boards share one frame, so a header pair has the
same x/y on both PCBs (checked below).

Faceplate board (18.8 x 108): the eight jacks, lying on their sides with the
sleeve lug to the right (front view), and the two LEDs on the bottom layer at
their panel positions. Behind them only the four male headers: the 1x4s in
the left strip (front view) by the tip pads, the 1x2s in the right strip
between two sleeve pads, level with each LED. No other through-hole part fits:
its pads would lie under a jack or LED body. No mounting holes either: an M3
standoff's 6 mm circle does not fit beside a 10.5 mm jack body on an 18.8 mm
board, so the four headers hold the boards together.

Main board: the female sockets on the bottom layer at the headers' spots,
everything else on the top layer. The power header stands at the bottom, the
TL074s in the middle of the board's width (group 2's above the power entry,
group 1's at the top); the placer then puts every other part, power entry
first, at the free spot nearest the pads it shares a signal net with
(decoupling caps pulled to their chip's supply pins), each group's parts in
its own band. The user routes by hand and will move parts; the point is that
each part starts beside what it connects to.
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
POWER_NETS = {"GND", "+12V", "-12V"}


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

    def hole(self, x, y, d=HOLE_D):
        self.holes.append((x, y, d))

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
        pl = next(p for p in self.placed if p["ref"] == ref)
        return self.pads(pl)[num][:2]

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

    def front_pads(self, ref):
        pl = next(p for p in self.placed if p["ref"] == ref)
        return {num: (round(self.W - x, 3), round(y, 3)) for num, (x, y, r) in self.pads(pl).items()}

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
    def check(self, gap_side):
        """Problems: unplaced parts, pads too close to each other (on a shared layer), to a hole or the edge,
        bodies overlapping on one side, bodies under a standoff (gap side) or a screw head (other side)."""
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
            shapes += [(pl["ref"], num, *s) for num, s in self.pad_shapes(pl).items()]
        cells = collections.defaultdict(list)
        for s in shapes:
            cells[(int(s[2][0] // 4), int(s[2][1] // 4))].append(s)
        for i, (ra, na, a1, a2, r1, la) in enumerate(shapes):
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
        for side in (False, True):
            bodies = [(pl["ref"], self.body(pl)) for pl in self.placed if pl["bottom"] == side]
            for i, (ra, a) in enumerate(bodies):
                for rb, b in bodies[i + 1:]:
                    if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                        ov = min(a[2] - b[0], b[2] - a[0], a[3] - b[1], b[3] - a[1])
                        bad.append(f"{self.title}: bodies of {ra} and {rb} overlap by {ov:.2f} mm on the "
                                   f"{'bottom' if side else 'top'} side")
            gap = (side and gap_side == "bottom") or (not side and gap_side == "top")
            what = "standoff" if gap else "screw head"
            for ref, (x1, y1, x2, y2) in bodies:
                for hx, hy, hd in self.holes:
                    cx, cy = min(max(hx, x1), x2), min(max(hy, y1), y2)
                    if math.hypot(cx - hx, cy - hy) < STANDOFF_R:
                        bad.append(f"{self.title}: body of {ref} sits under the {what} at ({hx:.1f}, {hy:.1f})")
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
        for hx, hy, hd in self.holes:
            d.add("FILL", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 12, "width": 1,
                                    "fillStyle": "SOLID", "path": [["CIRCLE", mil(hx), mil(hy), mil(hd / 2)]],
                                    "locked": False, "zIndex": d.zi(), "isBridgingCopper": False,
                                    "networkList": [], "refs": []})
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
                                                   "valueVisible": vis, "fontFamily": "default",
                                                   "fontSize": 30 if not self.P[ref].kind in ("JACK", "POT") else 45,
                                                   "strokeWidth": 5, "bold": False, "italic": False,
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
            font = ImageFont.truetype("arial.ttf", 9)
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
                for num, (a, b, r, side) in self.pad_shapes(pl).items():
                    A, B = P(*a), P(*b)
                    rr = r * scale
                    dr.rounded_rectangle([min(A[0], B[0]) - rr, min(A[1], B[1]) - rr, max(A[0], B[0]) + rr,
                                          max(A[1], B[1]) + rr], radius=rr, outline=col,
                                         fill="#f0d0d0" if not bottom else "#d0d8f0")
                X, Y = P(x1, y2)
                dr.text((X + 1, Y - 10), pl["ref"], fill=col, font=font)
        for hx, hy, hd in self.holes:
            X, Y = P(hx, hy)
            r = hd / 2 * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], outline="#000000", width=2)
            r = STANDOFF_R * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], outline="#808080")
        dr.text((20, H + 26), f"{self.title}: rear view (EasyEDA top layer). red = top layer, blue = bottom layer, "
                              f"grey = M3 standoff", fill="#000000", font=big)
        img.save(path)


# ---------------------------------------------------------------- placer
class Placer:
    """Greedy placement of a board's free parts on its top layer (see the module docstring)."""

    MARGIN = 0.3          # courtyard gap
    STEP = 0.5

    def __init__(self, b, region=None):
        self.b = b
        self.region = region or (EDGE, EDGE, b.W - EDGE, b.H - EDGE)
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
        nets = b.P[ref].nets
        want = collections.defaultdict(list)
        done = {pl["ref"]: pl for pl in b.placed}
        for pin, net in nets.items():
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
        """Place ref at the free spot (0.5 mm grid, four angles) nearest the pads it connects to."""
        b = self.b
        region = region or self.region
        want = self.targets(ref, pull)
        pts = [p for ps in want.values() for p in ps]
        if near:
            cx, cy = near
        elif pts:
            cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
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
                cost = dist + sum(min(math.hypot(pads[pin][0] - x, pads[pin][1] - y) for x, y in ps)
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


# ------------------------------------------------------------- the boards
def _header_rule(r):
    """Pins in a column, pin 1 at the top."""
    return abs(r["1"][0] - r["2"][0]) < 0.01 and r["1"][1] > r["2"][1]


def _jack_rule(r):
    """On its side: the pads in a row through the barrel, the sleeve (1) right of the tip (3)."""
    return abs(r["1"][1] - r["3"][1]) < 0.01 and r["1"][0] > r["3"][0]


def _led_rule(r):
    """Pads in a row, pad 1 (GND) on the left."""
    return abs(r["1"][1] - r["2"][1]) < 0.01 and r["1"][0] < r["2"][0]


def faceplate_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Faceplate", pr, parts, info, W, H)
    for ref, (xf, y, _) in circuit.PLACEMENT.items():        # panel parts on the bottom layer, oriented by rule
        b.place_front(ref, xf, y, 0, bottom=True)
    for ref, *_ in circuit.JACKS:
        b.orient(ref, _jack_rule)
    for ref, *_ in circuit.LEDS:
        b.orient(ref, _led_rule)
    for ref, (xf, y) in circuit.HEADERS_FRONT.items():        # male headers, top (rear) layer, pin 1 up
        b.place_front(circuit.fb_ref(ref), xf, y, 0)
        b.orient(circuit.fb_ref(ref), _header_rule)
    b.text(2.0, H - 2.6, "Six faceplate", 1.6)
    return b


# Main-board anchors (rear view, board mm, angle): the chips stand in the middle of the width, pin 1 at the
# top (angle 270 puts the DIP's long side along y), the power header at the bottom, keyed towards the edge.
# The bands each group's parts go into, and the power entry's.
CHIPS = {"U1": (9.4, 89.0, 270), "U2": (9.4, 55.0, 270)}
POWER_HEADER = ("J9", 5.5, 15.4, 90)
BANDS = {1: (0.5, 71.0, 18.3, 107.5), 2: (0.5, 34.0, 18.3, 73.0), 9: (0.5, 0.5, 18.3, 40.0)}


def main_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Main board", pr, parts, info, W, H)
    for ref, (xf, y) in circuit.HEADERS_FRONT.items():        # female sockets, bottom layer, same spot
        b.place_front(ref, xf, y, 0, bottom=True)
        b.orient(ref, _header_rule)
    pc = Placer(b)
    for ref, (x, y, a) in CHIPS.items():
        pc.fix(ref, x, y, a)
    ref, x, y, a = POWER_HEADER
    pc.fix(ref, x, y, a)
    decoupling = {}
    for g in circuit.GROUPS:
        decoupling[f"C{901 + 2 * g}"] = (f"U{g}", "4")
        decoupling[f"C{902 + 2 * g}"] = (f"U{g}", "11")
    placed = {pl["ref"] for pl in b.placed}
    order = [p.ref for p in parts if p.ref not in placed]
    order.sort(key=lambda r: (0 if r in decoupling else 1 if r[-3:-2] == "9" or r[0] == "D" else 2))
    for ref in order:
        if ref in decoupling:
            u, pin = decoupling[ref]
            net = b.P[u].nets[pin]
            cpin = next(n for n, v in b.P[ref].nets.items() if v == net)
            pc.put(ref, pull={cpin: b.pin(u, pin)}, radius=12)
            continue
        digits = "".join(c for c in ref if c.isdigit())
        g = int(digits) // 100 if ref[0] in "RC" and len(digits) == 3 else 9
        pc.put(ref, region=BANDS[g if g in BANDS else 9])
    b.text(2.0, H - 2.6, "Six main board", 1.6)
    return b


def barrel_check(fb, circuit, holes):
    """Each jack's barrel, worked out from its placed pads (6.48 mm from the sleeve pad towards the tip), must
    be the panel hole: holes = {ref: (x, y)} in front-view board mm."""
    bad = []
    for ref, *_ in circuit.JACKS:
        p = fb.front_pads(ref)
        (sx, sy), (tx, ty) = p["1"], p["3"]
        d = math.hypot(tx - sx, ty - sy)
        bx, by = sx + (tx - sx) * 6.48 / d, sy + (ty - sy) * 6.48 / d
        hx, hy = holes[ref]
        if math.hypot(bx - hx, by - hy) > 0.01:
            bad.append(f"{ref}: barrel at ({bx:.2f}, {by:.2f}), panel hole at ({hx:.2f}, {hy:.2f})")
    return bad


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
        pl = next(p for p in fb.placed if p["ref"] == ref)
        if abs(fb.W - pl["x"] - xf) > 0.001 or abs(pl["y"] - y) > 0.001:
            bad.append(f"{ref} not at its PLACEMENT origin")
    return bad


def front_housing_check(fb):
    """Through-hole pads of rear-side parts must not sit under a panel part's housing: they are soldered on
    the panel side, where the jack, pot and toggle bodies lie."""
    bad = []
    boxes = [(pl["ref"], fb.body(pl)) for pl in fb.placed if pl["bottom"]]
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


def panel_pad_check(fb):
    """A panel part's pads must not sit under another panel part's body either (a jack's sleeve lug under
    the toggle above it, a tip pad on the next jack's sleeve pad)."""
    bad = []
    front = [pl for pl in fb.placed if pl["bottom"]]
    for pl in front:
        for num, (x, y, r) in fb.pads(pl).items():
            for other in front:
                if other is pl:
                    continue
                x1, y1, x2, y2 = fb.body(other)
                if x1 < x < x2 and y1 < y < y2:
                    bad.append(f"{fb.title}: {pl['ref']}.{num} pad lies under the body of {other['ref']}")
    return bad
