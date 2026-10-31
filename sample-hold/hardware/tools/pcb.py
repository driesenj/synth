"""S&H PCB: the one board, placed, net-assigned and unrouted, as an EasyEDA Pro
PCB document inside SampleHold.epro2 (easyeda_export.py calls this). The
Board class, its checks and writer are the Offset's
(attenuverter/hardware/tools/pcb.py), copied, not imported; the placer is new.

Frame. The PCB is drawn the way EasyEDA shows it, looking at the top layer,
and the top layer is the REAR (away from the panel): x to the right, y up,
origin at the board's bottom-left corner, millimetres. The front view that
circuit.PLACEMENT and panel.py use is the mirror image: x_front = BOARD_W - x.

Front (bottom layer): the nine jacks, three pots and the clock LED at their
panel positions, oriented by rule. Rear (top layer): everything else, every
resistor standing. A rear part's leads come through to the front and are
soldered there, so no rear pad may sit under a front part's body
(front_housing_check). What the panel parts leave free decides the layout
(front view, board mm):
  - the strip above the RATE and SLEW pots (y 94-108): the power header, its
    diodes, 10R and 47u beside it
  - between the RATE and SLEW pots, above LEVEL: U2 (clock, trigger, S&H)
  - left of LEVEL, above the CLOCK jack: U1 (noise, gate)
  - right of LEVEL, under SLEW: U3 (slew)
  - between and beside the jacks: the strips between the rows and the gaps
    between the columns, for standing parts
place_auto() puts every other part, one by one, at the cheapest spot that
fits: its first pad on a 2.54 mm grid point, turned 0 / 90 / 180 / 270, the
cost the weighted distance from each pin to the nearest pad already on its
net. "Fits" is tested on the real footprint: pads clear of all pads, the
edge and the front parts' bodies, the body clear of the other rear bodies.
That copes with the 8 mm diodes, the TO-92s and the fat film caps the
Offset's grid placer could not.

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


# the grid the small parts' first pads sit on, front view (board mm)
GRID_X = [1.9 + 2.54 * i for i in range(19)]
GRID_Y = [1.4 + 2.54 * j for j in range(42)]
# nets that pick up hum or clock bleed: high impedance, or the x148 noise amp's input; pulled in hard
SENSITIVE = {"NE", "NIN", "WFB", "BFB", "PFB", "BLN", "PKN", "BL1", "BL2", "BL3", "PK1", "PK2", "PK3", "HOLD",
             "JG", "OSC_C", "OSC_P", "RT", "TRG", "THR", "DIFF", "GTP", "SLC", "LV"}


def net_weight(net):
    """How much a pin's distance to its net counts: sensitive nodes three times, the rails half (they will
    be buses), GND a fifth (it will be a pour), the rest once."""
    if net in SENSITIVE:
        return 3.0
    if net in ("+12V", "-12V"):
        return 0.5
    return 0.2 if net == "GND" else 1.0


# parts that must stay in one area, front view (x1, y1, x2, y2): the power entry in the strip beside the
# header, the trigger chain in U2's pocket between the top pots (else they swap places and push U2's
# decoupling away)
TOP_STRIP = [(0.0, 94.2, 49.3, 108.0), (0.0, 82.0, 6.6, 108.0), (42.7, 82.0, 49.3, 108.0)]   # and the margins
U2_POCKET = [(12.0, 71.2, 33.1, 96.4)]          # pads stay out from under the pots anyway
REGION = {**{r: TOP_STRIP for r in ("D901", "D902", "R901", "R902", "C901", "C902")},
          **{r: U2_POCKET + TOP_STRIP[:1] for r in ("R208", "D201", "R207", "C202", "R209", "R210")}}


def fits(b, pl):
    """Can pl (a rear part, already in b.placed) stay where it is?"""
    W, H = b.W, b.H
    mine = b.pads(pl)
    if pl["ref"] in REGION:
        if not all(any(x1 <= W - x <= x2 and y1 <= y <= y2 for x1, y1, x2, y2 in REGION[pl["ref"]])
                   for x, y, r in mine.values()):
            return False
    for x, y, r in mine.values():
        if x - r < EDGE or x + r > W - EDGE or y - r < EDGE or y + r > H - EDGE:
            return False
    bx1, by1, bx2, by2 = b.body(pl)
    if bx1 < 0 or by1 < 0 or bx2 > W or by2 > H:
        return False
    for other in b.placed:
        if other is pl:
            continue
        ox1, oy1, ox2, oy2 = b.body(other)
        if other["bottom"]:                       # a panel part: no rear pad under its body
            if any(ox1 - r < x < ox2 + r and oy1 - r < y < oy2 + r for x, y, r in mine.values()):
                return False
        elif bx1 < ox2 and ox1 < bx2 and by1 < oy2 and oy1 < by2:
            return False
        if abs(ox1 + ox2 - bx1 - bx2) / 2 > 25 and abs(oy1 + oy2 - by1 - by2) / 2 > 25:
            continue
        for ox, oy, orr in b.pads(other).values():
            for x, y, r in mine.values():
                if math.hypot(x - ox, y - oy) < r + orr + CLEAR:
                    return False
    return True


# clock-carrying nets and the noise amp's input: a clock pad within QUIET_R of a quiet pad costs extra, so the
# square waves stay out of the x148 amp's neighbourhood
NOISY = {"CLK", "CLK_INT", "OSC", "SAMP", "LED_A", "LED_B", "LED_K", "GTO", "GTD", "GATE"}
QUIET = {"NE", "NIN", "WFB"}
QUIET_R, QUIET_COST = 8.0, 20.0


def _anchors(b, ref, homes):
    part = b.P[ref]
    anchors = {}
    for net in set(part.nets.values()):
        anchors[net] = [xy[:2] for pl in b.placed if pl["ref"] != ref for n, xy in b.pads(pl).items()
                        if b.P[pl["ref"]].nets.get(n) == net]
    anchors.update(homes.get(ref, {}))
    return anchors


def _spot(b, pl, homes):
    """Move pl (already in b.placed) to its cheapest fitting spot; returns that spot's cost."""
    part = b.P[pl["ref"]]
    anchors = _anchors(b, pl["ref"], homes)
    own = set(part.nets.values())
    quiet = [xy[:2] for o in b.placed if o is not pl for n, xy in b.pads(o).items()
             if b.P[o["ref"]].nets.get(n) in QUIET] if own & NOISY else []
    noisy = [xy[:2] for o in b.placed if o is not pl for n, xy in b.pads(o).items()
             if b.P[o["ref"]].nets.get(n) in NOISY] if own & QUIET else []
    first = sorted(pl["geo"]["pads"], key=lambda n: (len(n), n))[0]
    cands = []
    for a in (0, 90, 180, 270):
        pl["angle"], pl["x"], pl["y"] = a, 0, 0
        rel = b.pads(pl)
        fx, fy = rel[first][:2]
        for xf in GRID_X:
            for gy in GRID_Y:
                ox, oy = b.W - xf - fx, gy - fy
                cost = 0.0
                for num, net in part.nets.items():
                    x, y = rel[num][0] + ox, rel[num][1] + oy
                    if anchors.get(net):
                        cost += net_weight(net) * min(math.hypot(x - ax, y - ay) for ax, ay in anchors[net])
                    away = quiet if net in NOISY else noisy if net in QUIET else ()
                    for ax, ay in away:
                        d = math.hypot(x - ax, y - ay)
                        if d < QUIET_R:
                            cost += QUIET_COST * (QUIET_R - d) / QUIET_R
                cands.append((round(cost, 6), a, ox, oy))
    cands.sort()
    for cost, a, ox, oy in cands:
        pl["angle"], pl["x"], pl["y"] = a, ox, oy
        if fits(b, pl):
            return cost
    raise ValueError(f"no free spot left for {pl['ref']}")


def place_auto(b, refs, homes=None):
    """Place each part at the cheapest spot that fits (see the module docstring). homes: {ref: {net:
    [(x, y)]}} replaces the anchors of a net (PCB frame); an empty list makes that net free."""
    homes = homes or {}
    for ref in refs:
        _spot(b, b.place(ref, 0, 0), homes)


def improve(b, refs, homes=None, rounds=6):
    """Greedy placement depends on the order; this pass lifts each part in turn and puts it back at its
    cheapest spot now that everything else is down, until a round moves nothing. Returns the rounds run."""
    homes = homes or {}
    for k in range(rounds):
        moved = 0
        for ref in refs:
            pl = next(p for p in b.placed if p["ref"] == ref)
            before = (pl["x"], pl["y"], pl["angle"])
            _spot(b, pl, homes)
            if (round(pl["x"], 3), round(pl["y"], 3), pl["angle"]) != tuple(round(v, 3) for v in before[:2]) + (before[2],):
                moved += 1
        if not moved:
            return k + 1
    return rounds


def chip_homes(b, circuit, u, cp, cn):
    """Decoupling pair of op-amp u: each cap drawn to its supply pin, GND free."""
    vp, vn = {"TL074": ("4", "11"), "TL072": ("8", "4")}[circuit.CHIPS[u]]
    return {cp: {"+12V": [b.pin(u, vp)], "GND": []}, cn: {"-12V": [b.pin(u, vn)], "GND": []}}


# The power entry claims the corners beside the header first, then the decoupling, then the LED driver
# grows out from the LED (before the noise parts fill the pocket round it). Each block then grows out from
# its op-amp's pins: the noise source and white amp first (the x148 input wants the shortest, quietest
# spot), the trigger chain from U2's TRG and THR pins (not from the CLOCK jack, so the sensitive pulse node
# stays short).
POWER = ["D901", "D902", "R901", "R902"]
LED = ["R206", "Q2", "R205"]
ORDER = ["R104", "R105", "C102", "R103", "Q1", "R102", "R101", "C101", "R106",
         "R111", "R112", "C103", "R107", "C104", "R108", "C105", "R109", "R110", "R113",
         "R118", "R119", "R114", "C106", "R115", "C107", "R116", "C108", "R117", "R120",
         "C201", "D201", "R208", "R207", "C202", "R209", "R210",
         "R201", "R202", "R203", "R204",
         "Q3", "R301", "D301", "C301", "R302",
         "C401", "R401",
         "R501", "R502", "D501", "R503", "R504"]
BULK = {"C901": ("R901", "+12V"), "C902": ("R902", "-12V")}    # right after the power entry, at their 10R's rail end
# the op-amps standing (pins in two columns), front view: U2 between the top pots with its clock pins towards
# RATE; U1 left of LEVEL turned so that the noise input (pin 5) faces the middle, away from the clock LED; U3
# right of LEVEL. Pins on the grid
CHIP_AT = {"U2": (24.65, GRID_Y[29] + 7.62, 90), "U1": (GRID_X[2] + 1.27, GRID_Y[21], 270),
           "U3": (GRID_X[16] - 1.27, GRID_Y[20] + 1.27, 90)}


def one_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("S&H", pr, parts, info, W, H)

    # panel parts on the bottom layer, at the PLACEMENT origins, oriented by rule
    for ref, (xf, y, _) in circuit.PLACEMENT.items():
        b.place_front(ref, xf, y, 0, bottom=True)
    for ref, *_ in circuit.JACKS:          # sleeve pad above the tip pad, pins in a column
        b.orient(ref, lambda r: abs(r["1"][0] - r["3"][0]) < 0.01 and r["1"][1] > r["3"][1])
    for ref, *_ in circuit.POTS:           # pins below the shaft, pin 1 on the left (CW turns towards pin 3)
        b.orient(ref, lambda r: r["1"][1] < 0 and abs(r["1"][1] - r["3"][1]) < 0.01 and r["1"][0] < r["3"][0])
    for ref, *_ in circuit.LEDS:           # pads along x, pad 1 (anode) on the left
        b.orient(ref, lambda r: abs(r["1"][1] - r["2"][1]) < 0.01 and r["1"][0] < r["2"][0])
    # the power header in the strip above the top pots, pin 1 (-12 V, red stripe) on the left seen from the
    # front; the op-amps in their pockets
    b.place_front("J10", W / 2, 101.0, 180)
    for u, (xf, y, a) in CHIP_AT.items():
        b.place_front(u, xf, y, a)
    # the power entry, its bulk caps, the decoupling, the LED driver, then each block from its op-amp outwards
    place_auto(b, POWER)
    for c, (r, rail) in BULK.items():
        rail_pin = next(n for n, net in b.P[r].nets.items() if net == rail)
        place_auto(b, [c], {c: {rail: [b.pin(r, rail_pin)], "GND": []}})
    homes = {}
    for i, u in enumerate(circuit.CHIPS):
        homes.update(chip_homes(b, circuit, u, f"C{903 + 2 * i}", f"C{904 + 2 * i}"))
    order = list(homes) + LED + ORDER
    left = [p.ref for p in parts if p.ref not in {pl["ref"] for pl in b.placed} and p.ref not in order]
    place_auto(b, order + left, homes)
    for c, (r, rail) in BULK.items():
        rail_pin = next(n for n, net in b.P[r].nets.items() if net == rail)
        homes[c] = {rail: [b.pin(r, rail_pin)], "GND": []}
    b.improve_rounds = improve(b, POWER + list(BULK) + order + left, homes)
    b.text(W - 9.0, H - 2.4, "S&H", 1.6)
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
