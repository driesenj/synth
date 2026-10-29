"""Plaitsy PCBs: both boards placed, net-assigned and unrouted, as EasyEDA
Pro PCB documents inside Plaits.epro2 (easyeda_export.py calls this).

Frame. Each PCB is drawn the way EasyEDA shows it, looking at the top layer.
On both boards the top layer is the REAR of the stack (away from the panel):
x to the right, y up, origin at the board's bottom-left corner, millimetres.
The front view that circuit.PLACEMENT and panel.py use is the mirror image:
x_front = BOARD_W - x. Both boards share one frame, so a header pair has the
same x/y on both PCBs and the stack lines up pin for pin (checked below).

Faceplate board: jacks, pots, buttons and LEDs on the bottom layer (towards
the panel) in the Plaits arrangement; the mux, the two shift registers,
their resistors, the probe resistors and the male headers on the top
layer, inside the board-to-board gap.
Main board: the three female sockets on the bottom layer; everything else
on the top layer, the Seed breakout along the left edge (the right edge as
seen from the panel), the CV stages clustered on their op-amps with every
resistor standing up (the exporter gives them a vertical footprint).

Bottom-layer parts: EasyEDA Pro mirrors the footprint about its own X axis
(y -> -y) and then rotates it (verified against every routed track in the
MorrisSynth export). The pad records (PAD_NET) carry the net names, so the
ratsnest, DRC and the netlist check are live as soon as the project opens.

Nothing here is routed; the second pass does that in EasyEDA Pro.
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
    """The canvas, layer, rule and preference records of one of your PCBs,
    cached in the repo; taken from the MorrisSynth export the first time."""
    if not os.path.exists(TEMPLATE):
        with zipfile.ZipFile(ee.EXPORT) as z:
            name = next(n for n in z.namelist() if n.endswith(".epru"))
            docs = ee.parse(z.read(name).decode("utf-8").split("\n"))
        pcbs = [d for d in docs.values() if d["docType"] == "PCB"]
        best = max(pcbs, key=lambda d: sum(1 for h, _ in d["recs"] if h["type"] == "LAYER"))
        with open(TEMPLATE, "w", encoding="utf-8", newline="\n") as f:
            for h, p in best["recs"]:
                if h["type"] in TEMPLATE_TYPES:
                    f.write(ee.enc(h, p) + "\n")
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
    """Pads {num: {id, x, y, w, h}} in mm and the body box (silk, document
    and courtyard layers plus the pads) of a FOOTPRINT doc."""
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
    if title in BODY:
        pts = [BODY[title][:2], BODY[title][2:]]
    padpts = []
    for pd in pads.values():
        padpts += [(pd["x"] - pd["w"] / 2, pd["y"] - pd["h"] / 2), (pd["x"] + pd["w"] / 2, pd["y"] + pd["h"] / 2)]
    body = pts or padpts             # the housing as drawn; pads are checked on their own
    xs, ys = [x for x, _ in body], [y for _, y in body]
    return {"pads": pads, "bbox": (min(xs), min(ys), max(xs), max(ys)), "title": title}


# Body boxes that override a footprint's drawn outline (x1, y1, x2, y2 in the
# footprint's own frame). The library PTV09A drawing runs 9 mm beyond the
# origin; the Alpha 9 mm pot's housing ends about 3.3 mm beyond the shaft
# (KiCad RD901F), i.e. 4 mm beyond this footprint's origin.
BODY = {"SW-TH_PTV09A-4015F-B502": (-5.0, -3.5, 5.0, 4.0)}


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

    def place_front(self, ref, xf, y, angle=0, bottom=False):
        """Place by front-view coordinates (circuit.PLACEMENT / panel.py)."""
        self.place(ref, self.W - xf, y, angle, bottom)

    def hole(self, x, y, d=HOLE_D):
        self.holes.append((x, y, d))

    def hole_front(self, xf, y, d=HOLE_D):
        self.hole(self.W - xf, y, d)

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

    def front_pads(self, ref):
        pl = next(p for p in self.placed if p["ref"] == ref)
        return {num: (round(self.W - x, 3), round(y, 3)) for num, (x, y, r) in self.pads(pl).items()}

    def orient(self, ref, want):
        """Pick the angle of a bottom-layer panel part so that want(front_pads)
        holds; want gets {num: (x_front, y)} relative to the part origin."""
        pl = next(p for p in self.placed if p["ref"] == ref)
        for a in (0, 90, 180, 270):
            pl["angle"] = a
            rel = {n: (self.W - x - (self.W - pl["x"]), y - pl["y"]) for n, (x, y, r) in self.pads(pl).items()}
            if want(rel):
                return a
        raise ValueError(f"no orientation satisfies the rule for {ref}")

    # -- checks
    def check(self, gap_side):
        """Problems: unplaced or unknown parts, pads too close to each other,
        to a hole or to the edge, bodies overlapping on one side, bodies under
        a standoff (gap side) or a screw head (the other side). gap_side:
        'top' or 'bottom', the side that faces the other board."""
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
                        bad.append(f"{self.title}: {pl['ref']}.{num} pad is {math.hypot(x - hx, y - hy):.2f} from the hole at ({hx}, {hy})")
            shapes += [(pl["ref"], num, *s) for num, s in self.pad_shapes(pl).items()]
        for i, (ra, na, a1, a2, r1) in enumerate(shapes):
            for rb, nb, b1, b2, r2 in shapes[i + 1:]:
                if ra != rb and abs(a1[0] - b1[0]) < 5 and abs(a1[1] - b1[1]) < 5:
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
            what = "standoff" if (side and gap_side == "bottom") or (not side and gap_side == "top") else "screw head"
            for ref, (x1, y1, x2, y2) in bodies:
                for hx, hy, hd in self.holes:
                    cx, cy = min(max(hx, x1), x2), min(max(hy, y1), y2)
                    if math.hypot(cx - hx, cy - hy) < STANDOFF_R:
                        bad.append(f"{self.title}: body of {ref} sits under the {what} at ({hx}, {hy})")
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
                                                   "valueVisible": vis, "fontFamily": "default", "fontSize": 45,
                                                   "strokeWidth": 6, "bold": False, "italic": False,
                                                   "origin": "LEFT_BOTTOM", "angle": 0, "reverse": False,
                                                   "expansion": 0, "mirror": bool(pl["bottom"]), "locked": False,
                                                   "zIndex": None})
        return d.lines({"title": title, "parent": "", "board": board_uuid, "zIndex": None})

    # -- preview
    def render(self, path, scale=6):
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
                for num, (x, y, r) in self.pads(pl).items():
                    X, Y = P(x, y)
                    dr.ellipse([X - r * scale, Y - r * scale, X + r * scale, Y + r * scale], outline=col,
                               fill="#f0d0d0" if not bottom else "#d0d8f0")
                    if num == "1" or num.endswith("-1"):
                        dr.rectangle([X - 2, Y - 2, X + 2, Y + 2], fill=col)
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


# ------------------------------------------------------------- placement
def _col(x, ys, angle=0):
    return [(x, y, angle) for y in ys]


def faceplate_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Faceplate", pr, parts, info, W, H)
    # mounting holes (front view); the same four on the main board
    for xf, y in HOLES_FRONT:
        b.hole_front(xf, y)
    # panel parts on the bottom layer, at the PLACEMENT origins, oriented by rule
    for ref, (xf, y, _) in circuit.PLACEMENT.items():
        b.place_front(ref, xf, y, 0, bottom=True)
    for ref, *_ in circuit.JACKS:        # sleeve pad above the tip pad, pins in a column
        b.orient(ref, lambda r: abs(r["1"][0] - r["3"][0]) < 0.01 and r["1"][1] > r["3"][1])
    for ref, *_ in circuit.POTS:         # pins in a column towards -x (pin 1 then lands above pin 3)
        b.orient(ref, lambda r: r["1"][0] < r["4"][0] and abs(r["1"][0] - r["3"][0]) < 0.01)
    for ref, *_ in circuit.BUTTONS:      # LED button: LED pins in a row along x, anode on the right
        b.orient(ref, lambda r: abs(r["5"][1] - r["6"][1]) < 0.01 and r["5"][0] > r["6"][0] and r["1"][1] > r["3"][1])
    for ref, _, kind in circuit.LEDS:    # three leads in a row along x, red anode (pad 1) on the left
        b.orient(ref, lambda r: abs(r["1"][1] - r["3"][1]) < 0.01 and r["1"][0] < r["3"][0])
    # headers (male, top layer), shared with the main board
    for ref, (xf, y, a) in HEADERS_FRONT.items():
        b.place_front(circuit.fb_ref(ref), xf, y, a)
    # logic on the top (rear) side: front-view coordinates, angle in the PCB frame
    for ref, xf, y, a in FB_REAR:
        b.place_front(ref, xf, y, a)
    b.text(W - 24, H - 2.6, "Plaitsy faceplate", 1.8)
    return b


def main_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Main board", pr, parts, info, W, H)
    for xf, y in HOLES_FRONT:
        b.hole_front(xf, y)
    for ref, (xf, y, a) in HEADERS_FRONT.items():   # female sockets, bottom layer, same spot
        b.place_front(ref, xf, y, a, bottom=True)
    for ref, x, y, a in _main_top(circuit):
        b.place(ref, x, y, a)
    b.text(24, H - 2.6, "Plaitsy main board", 1.8)
    return b


# Front-view coordinates (x from the left as seen from the panel, y up).
# Holes: two in the top corners above the big knobs, one in the left pocket
# beside the TIMBRE attenuverter, one in the centre of the strip between the
# attenuverters and the lowest LED. On the main board the corner holes sit
# beyond the breakout's ends, the left one in the right margin, the centre
# one below U4.
HOLES_FRONT = [(3.5, 104.5), (55.9, 104.5), (3.5, 40.0), (29.9, 48.5)]
# header: (x, y, angle); 0 = pins along x, 90 = along y. H1 (the eight CVs)
# lies in the strip between the top jack row and the attenuverters; H2 and
# H3 stand in the right margin, outside the pots' lug pads; on the main
# board that margin is the channel between the breakout's pad rows.
HEADERS_FRONT = {"H1": (29.0, 31.2, 0), "H2": (54.3, 42.0, 90), "H3": (54.3, 65.0, 90)}

# Faceplate, rear side (top layer): ref, x_front, y, angle. 0 = pins along x, 90 = along y.
# U1 in the pocket left of the centre hole, U9 / U10 between the big knobs
# and TIMBRE / MORPH, the LED resistors in rows of vertical parts either side
# of the LED column, the probe resistors in the right pocket and one in the
# jack strip, decoupling beside each chip.
FB_REAR = [
    ("U1", 14.5, 49.5, 0), ("C8", 3.5, 57.0, 90),
    ("U9", 15.4, 75.0, 0), ("C9", 3.5, 70.0, 90),
    ("U10", 43.0, 75.0, 0), ("C10", 43.0, 69.0, 0),
    ("R9", 7.55, 31.2, 0),
]
FB_REAR += [(r, x, 48.5, 90) for r, x in zip(("R10", "R11", "R12", "R13"), (36.0, 38.5, 41.0, 43.5))]
_LX, _RX = (17.4, 19.8, 22.2, 24.6), (34.4, 36.8, 39.2, 41.6)
# pad 1 (the 595 side) of every LED resistor faces its 595 between the rows, pad 2 the LEDs
FB_REAR += [(f"R{80 + i}", x, 88.0, 90) for i, x in enumerate(_LX)]     # red D1-D4 (U9 lines)
FB_REAR += [(f"R{84 + i}", x, 62.0, 270) for i, x in enumerate(_LX)]    # red D5-D8
FB_REAR += [(f"R{88 + i}", x, 88.0, 90) for i, x in enumerate(_RX)]     # green D1-D4 (U10 lines)
FB_REAR += [(f"R{92 + i}", x, 62.0, 270) for i, x in enumerate(_RX)]    # green D5-D8

# Main board, top (rear) layer, PCB frame. The routed Marblesy main board
# showed the way: resistors standing up on a 2.54 mm footprint, clustered on
# the op-amp pins they serve, so a summing node is a few mm of copper, and
# each 100 n beside its supply pin. Both TL074s stand vertical (angle 90,
# pins 1-7 in the +x column) in the middle of the space right of the
# breakout, U3 level with the Seed's ADC pins, U4 above it; every stage sits
# at its corner of the chip: Rf right against IN- and OUT, Rin and Rs in the
# next column, Cf in the third. The bias dividers sit below U3, the V/OCT
# clamps and the button-LED resistors in the strip along the breakout.
VR_P1 = 0.48006       # a standing resistor's pad 1 (the body) sits this far above its origin, pad 2 2.54 below that
XO, Y3, Y4 = 39.6, 64.0, 89.0


def _stand(ref, p1, p2):
    """A standing resistor with pad 1 (the body) at p1 and pad 2 one pitch from it, towards p2."""
    a = math.degrees(math.atan2(p2[0] - p1[0], -(p2[1] - p1[1])))
    dx, dy = rot(0, VR_P1, a)
    return ref, p1[0] - dx, p1[1] - dy, round(a) % 360


def _two(ref, p1, p2):
    """A two-lead part lying flat (capacitor, DO-35 diode), pad 1 at p1, pad 2 at p2."""
    return ref, (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, round(math.degrees(math.atan2(p2[1] - p1[1],
                                                                                         p2[0] - p1[0]))) % 360


def _stage(sec, x0, y0, rin, rf, rs, cf):
    """One inverting stage at its corner of a vertical TL074 centred on (x0, y0)."""
    sx = 1 if sec in (1, 2) else -1          # sections 1 / 2 on the pin 1-7 column, 3 / 4 on pins 8-14
    sy = -1 if sec in (1, 4) else 1          # sections 1 / 4 at the pin 1 / pin 14 end
    c1, c2, c3 = x0 + sx * 7.04, x0 + sx * 9.58, x0 + sx * 12.12
    y = [y0 + sy * 2.54 * k for k in range(5)]       # y[1] IN+, y[2] IN-, y[3] OUT
    return [_stand(rf, (c1, y[2]), (c1, y[3])),     # pin 1 IN-, pin 2 OUT
            _stand(rin, (c2, y[1]), (c2, y[2])),    # pin 1 CV, pin 2 IN-
            _stand(rs, (c2, y[3]), (c2, y[4])),     # pin 1 OUT, pin 2 the ADC line
            _two(cf, (c3, y[1]), (c3, y[3]))]       # pin 1 IN-, pin 2 OUT


def _main_top(circuit):
    top = [("U2", 10.0, 64.0, 90),        # Seed breakout along the left edge, power end down, USB end up
           ("U3", XO, Y3, 90), ("U4", XO, Y4, 90)]
    for k, (u, y0) in enumerate((("U3", Y3), ("U4", Y4))):
        top += [_two(f"C{31 + 2 * k}", (XO + 7.04, y0 + 2.54), (XO + 7.04, y0 - 2.54)),   # +12 V, 3.6 mm from pin 4
                _two(f"C{32 + 2 * k}", (XO - 7.04, y0 + 2.54), (XO - 7.04, y0 - 2.54))]   # -12 V, from pin 11
    for i, (name, label, u, sec, *_) in enumerate(circuit.CV_CHANNELS):
        top += _stage(sec, XO, Y3 if u == "U3" else Y4, f"R{21 + 3 * i}", f"R{22 + 3 * i}", f"R{23 + 3 * i}",
                      f"C{21 + i}")
    # bias dividers below U3, clear of the centre mounting hole's screw head: A on the left, V on the right
    top += [_stand("R45", (34.5, 48.0), (34.5, 45.46)), _stand("R46", (37.04, 45.46), (37.04, 42.92)),
            _two("C29", (34.5, 39.5), (39.58, 39.5)),
            _stand("R47", (44.7, 48.0), (44.7, 45.46)), _stand("R48", (47.24, 45.46), (47.24, 42.92)),
            _two("C30", (44.7, 39.5), (49.78, 39.5))]
    # the V/OCT clamps on ADC_VOCT's way to Seed pin 31, the button-LED resistors at the breakout's top end
    top += [_two("D21", (21.0, 75.0), (21.0, 67.0)), _two("D22", (24.0, 67.0), (24.0, 75.0)),
            _stand("R60", (21.5, 101.0), (21.5, 98.46)), _stand("R61", (24.5, 101.0), (24.5, 98.46))]
    return top


def header_check(fb, mb, circuit):
    bad = []
    for ref, kind, pins in circuit.HEADERS:
        a, b = fb.front_pads(circuit.fb_ref(ref)), mb.front_pads(ref)
        for num in a:
            if a[num] != b.get(num):
                bad.append(f"header {ref} pin {num}: faceplate {a[num]} vs main board {b.get(num)}")
    return bad


def placement_check(fb, circuit):
    bad = []
    for ref, (xf, y, _) in circuit.PLACEMENT.items():
        pl = next(p for p in fb.placed if p["ref"] == ref)
        if abs(fb.W - pl["x"] - xf) > 0.001 or abs(pl["y"] - y) > 0.001:
            bad.append(f"{ref} not at its PLACEMENT origin")
    return bad


def front_housing_check(fb, circuit):
    """Rear-side pads must not sit under a panel part's housing: those pads are
    soldered on the panel side, where the pot and jack bodies lie flat."""
    bad = []
    boxes = [(pl["ref"], fb.body(pl)) for pl in fb.placed if pl["bottom"]]
    for pl in fb.placed:
        if pl["bottom"]:
            continue
        for num, (x, y, r) in fb.pads(pl).items():
            for ref, (x1, y1, x2, y2) in boxes:
                if x1 - r < x < x2 + r and y1 - r < y < y2 + r:
                    bad.append(f"{fb.title}: {pl['ref']}.{num} pad lies under the housing of {ref}")
    return bad
