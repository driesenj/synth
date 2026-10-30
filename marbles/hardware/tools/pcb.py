"""Marblesy PCBs: both boards placed, net-assigned and unrouted, as EasyEDA
Pro PCB documents inside Marbles.epro2 (easyeda_export.py calls this).

The boards were then routed by hand in EasyEDA Pro (Marblesy-routed.epro2),
moving most rear-side parts and all headers. That export is now the master
for the layout: the rear sides and headers are placed where it has them, the
panel parts still come from circuit.PLACEMENT, and routed_check() compares
the generated boards with it pad by pad, position and net.

Frame. Each PCB is drawn the way EasyEDA shows it, looking at the top layer.
On both boards the top layer is the REAR of the stack (away from the panel):
x to the right, y up, origin at the board's bottom-left corner, millimetres.
The front view that circuit.PLACEMENT and panel.py use is the mirror image:
x_front = BOARD_W - x. Both boards share one frame, so a header pair has the
same x/y on both PCBs and the stack lines up pin for pin (checked below).

Faceplate board: jacks, pots, buttons and LEDs on the bottom layer (towards
the panel) in the Marbles arrangement; the mux, shift registers, their
resistors and the male headers on the top layer, inside the board-to-board
gap.
Main board: the five female sockets on the bottom layer; everything else on
the top layer, the Seed breakout along the left edge.

Bottom-layer parts: EasyEDA Pro mirrors the footprint about its own X axis
(y -> -y) and then rotates it (verified against every routed track in the
MorrisSynth export). The pad records (PAD_NET) carry the net names, so the
ratsnest, DRC and the netlist check are live as soon as the project opens.

Nothing generated here is routed; the copper lives in the routed export.
"""
import collections
import functools
import json
import math
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "easyeda", "pcb-template.epru")
ROUTED = os.path.join(HERE, "..", "easyeda", "Marblesy-routed.epro2")
ROUTED_TITLES = {"Faceplate": "Marblesy Faceplate PCB", "Main board": "Marblesy Main PCB"}
VERTICAL_FP = "1/4W-RESISTOR-VERTICAL"    # the routed main board stands most of its resistors up
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
        if p is None:                    # a record deleted in EasyEDA (routed exports keep them, empty)
            continue
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
# footprint's own frame). The library PTV09A carries Alpha 9 mm pots: pins at
# y = -3.5, the shaft 7.5 mm from them at y = +4.0, the housing 9.5 mm wide
# from 1 mm off the pin row to 4.85 mm past the shaft (KiCad RD901F).
BODY = {"SW-TH_PTV09A-4015F-B502": (-4.75, -2.5, 4.75, 8.85)}
# Bodies allowed to overlap: the Seed breakout stands on 8.5 mm sockets, and
# these horizontal resistors (2.3 mm tall) sit under its power end.
STACKED = {frozenset(("U2", r)) for r in ("R33", "R36", "R39")}


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
        to a hole or to the edge, bodies overlapping on one side, bodies on
        the gap side under a standoff. gap_side: 'top' or 'bottom', the side
        that faces the other board (where the standoffs are)."""
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
                    if frozenset((ra, rb)) in STACKED:
                        continue
                    if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                        ov = min(a[2] - b[0], b[2] - a[0], a[3] - b[1], b[3] - a[1])
                        bad.append(f"{self.title}: bodies of {ra} and {rb} overlap by {ov:.2f} mm on the "
                                   f"{'bottom' if side else 'top'} side")
            if (side and gap_side == "bottom") or (not side and gap_side == "top"):
                for ref, (x1, y1, x2, y2) in bodies:
                    for hx, hy, hd in self.holes:
                        cx, cy = min(max(hx, x1), x2), min(max(hy, y1), y2)
                        if math.hypot(cx - hx, cy - hy) < STANDOFF_R:
                            bad.append(f"{self.title}: body of {ref} sits under the standoff at ({hx}, {hy})")
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


# ---------------------------------------------------------- routed project
@functools.lru_cache(maxsize=None)
def routed_boards():
    """The routed export, read once: {PCB title: {"parts": {ref: placement}, "holes": [(x, y, d)]}} in
    Board's frame (mm). A placement has x, y, angle, bottom, the footprint geometry, its pads' board
    positions and their nets."""
    with zipfile.ZipFile(ROUTED) as z:
        name = next(n for n in z.namelist() if n.endswith(".epru"))
        lines = z.read(name).decode("utf-8").split("\n")
    docs, cur = {}, None
    for line in lines:
        if not line:
            continue
        h, _, p = line.partition("||")
        h, p = json.loads(h), p[:-1] if p.endswith("|") else p
        p = json.loads(p) if p else None          # EasyEDA keeps deleted records with an empty payload
        if h["type"] == "DOCHEAD":
            cur = docs[p["uuid"]] = {"docType": p["docType"], "recs": []}
        cur["recs"].append((h, p))
    fps = {u: footprint_geometry(d) for u, d in docs.items() if d["docType"] == "FOOTPRINT"}
    boards = {}
    for d in docs.values():
        if d["docType"] != "PCB":
            continue
        comps, attrs, nets, holes = {}, collections.defaultdict(dict), collections.defaultdict(dict), []
        for h, p in d["recs"]:
            if p is None:
                continue
            if h["type"] == "COMPONENT":
                comps[h["id"]] = p
            elif h["type"] == "ATTR" and p.get("parentId"):
                attrs[p["parentId"]][p["key"]] = p["value"]
            elif h["type"] == "PAD_NET":
                _, cid, num, _ = json.loads(h["id"])
                nets[cid][num] = p["padNet"]
            elif h["type"] == "FILL" and p["layerId"] == 12 and p["path"][0][0] == "CIRCLE":
                _, x, y, r = p["path"][0]
                holes.append((x * 0.0254, y * 0.0254, 2 * r * 0.0254))
        parts = {}
        for cid, p in comps.items():
            pl = {"x": p["x"] * 0.0254, "y": p["y"] * 0.0254, "angle": p["angle"] % 360, "bottom": p["layerId"] == 2,
                  "geo": fps[attrs[cid]["Footprint"]]}
            pl["pads"] = {num: Board.pad_xy(pl, pd["x"], pd["y"]) for num, pd in pl["geo"]["pads"].items()}
            pl["nets"] = {num: n for num, n in nets[cid].items() if n}
            parts[attrs[cid]["Designator"]] = pl
        meta = next(p for h, p in d["recs"] if h["type"] == "META")
        boards[meta["title"]] = {"parts": parts, "holes": holes}
    return boards


def standing_resistors(title):
    """Resistors the routed board stands up (VERTICAL_FP); the exporter gives them a vertical footprint."""
    return {ref for ref, pl in routed_boards()[ROUTED_TITLES[title]]["parts"].items()
            if pl["geo"]["title"] == VERTICAL_FP}


# ------------------------------------------------------------- placement
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
    for ref, *_ in circuit.POTS:         # the pin row on the side circuit.pot_pins says (-x unless turned)
        b.orient(ref, lambda r, u=circuit.pot_pins(ref): r["2"][0] * u[0] + r["2"][1] * u[1] > 3)
    for ref, *_ in circuit.BUTTONS:
        if ref in circuit.LED_BUTTONS:   # LED button: LED pins in a row along x, anode on the right
            b.orient(ref, lambda r: abs(r["5"][1] - r["6"][1]) < 0.01 and r["5"][0] > r["6"][0] and r["1"][1] > r["3"][1])
        else:                            # contact pairs 1+4 and 2+3 as rows, pad 1 bottom left
            b.orient(ref, lambda r: abs(r["1"][1] - r["4"][1]) < 0.01 and r["1"][0] < r["4"][0] and r["1"][1] < r["2"][1])
    for ref, _, kind, _ in circuit.LEDS:  # leads in a row along x, pad 1 on the left
        if ref not in b.P:
            continue
        last = "3" if kind == "RG" else "2"
        b.orient(ref, lambda r, last=last: abs(r["1"][1] - r[last][1]) < 0.01 and r["1"][0] < r[last][0])
    # the rear side (logic, resistors, male headers) where the routed board has it
    for ref, pl in sorted(routed_boards()[ROUTED_TITLES[b.title]]["parts"].items()):
        if not pl["bottom"]:
            b.place(ref, pl["x"], pl["y"], pl["angle"])
    b.text(2, H - 3.5, "Marblesy faceplate board", 2.0)
    return b


def main_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Main board", pr, parts, info, W, H)
    for xf, y in HOLES_FRONT:
        b.hole_front(xf, y)
    # everything where the routed board has it: female sockets on the bottom, the rest on top
    for ref, pl in sorted(routed_boards()[ROUTED_TITLES[b.title]]["parts"].items()):
        b.place(ref, pl["x"], pl["y"], pl["angle"], bottom=pl["bottom"])
    b.text(23, H - 3.5, "Marblesy main board", 2.0)
    return b


# Front-view coordinates (x from the left as seen from the panel, y up).
# Holes: two on the centre line between the knobs, one each side between the
# BIAS knob and the mode button; on the main board the side holes land
# between the breakout's pad rows and beside the clock stages.
HOLES_FRONT = [(45, 82), (45, 33), (79, 69), (11, 69)]


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


def routed_check(fb, mb):
    """The generated boards against the routed export: the same parts, every pad at the same spot (0.01 mm)
    with the same net, the same holes. A difference means circuit.py, a footprint or PLACEMENT no longer
    describes the routed boards."""
    bad = []
    for b in (fb, mb):
        routed = routed_boards()[ROUTED_TITLES[b.title]]
        mine = {pl["ref"]: pl for pl in b.placed}
        for ref in sorted(set(routed["parts"]) ^ set(mine)):
            side = "routed" if ref in routed["parts"] else "generated"
            bad.append(f"{b.title}: {ref} is only on the {side} board")
        for ref in sorted(set(routed["parts"]) & set(mine)):
            rp, pads = routed["parts"][ref], b.pads(mine[ref])
            for num in sorted(set(pads) | set(rp["pads"])):
                if num not in pads or num not in rp["pads"]:
                    side = "routed" if num in rp["pads"] else "generated"
                    bad.append(f"{b.title}: {ref} pad {num} is only in the {side} footprint")
                elif math.hypot(pads[num][0] - rp["pads"][num][0], pads[num][1] - rp["pads"][num][1]) > 0.01:
                    bad.append(f"{b.title}: {ref}.{num} at ({pads[num][0]:.2f}, {pads[num][1]:.2f}), routed at "
                               f"({rp['pads'][num][0]:.2f}, {rp['pads'][num][1]:.2f})")
            nets = b.P[ref].nets
            for num in sorted(set(nets) | set(rp["nets"])):
                if nets.get(num) != rp["nets"].get(num):
                    bad.append(f"{b.title}: {ref}.{num} is {nets.get(num)} here, {rp['nets'].get(num)} on the routed board")
        def key(h):
            return round(h[0], 2), round(h[1], 2), round(h[2], 2)
        if sorted(map(key, b.holes)) != sorted(map(key, routed["holes"])):
            bad.append(f"{b.title}: mounting holes differ from the routed board")
    return bad
