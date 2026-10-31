"""Side FXy PCBs: both boards placed, net-assigned and unrouted, as EasyEDA Pro
PCB documents inside SideFXy.epro2 (easyeda_export.py calls this). The board
class, checks and writer are the mixer's (stereo-mixer/hardware/tools/pcb.py)
plus what the display needs: a keep-out where the module sits, the cutout
for its cable and its outline on the faceplate's silk.

Frame. Each PCB is drawn the way EasyEDA shows it, looking at the top layer.
On both boards the top layer is the REAR of the stack (away from the panel):
x to the right, y up, origin at the board's bottom-left corner, millimetres.
The front view that circuit.PLACEMENT and panel.py use is the mirror image:
x_front = BOARD_W - x. Both boards share one frame, so a header pair has the
same x/y on both PCBs and the stack lines up pin for pin (checked below).

Faceplate board: jacks, encoders and LED buttons on the bottom layer
(towards the panel) at their panel positions; the two 74HC165s in the strip
above the jacks, the pull-up networks between the encoder columns, the
display cable's header under the send buttons, the four male headers; and
nothing with leads behind the display module.
Main board: the four female sockets on the bottom layer; everything else on
the top layer, every resistor standing up. The breakout stands in the middle
with its pin rows either side of the sockets of H3 / H4; the TL074 and its
four CV stages, the bias, MIDI and clock stages and the 74HC595 fill the
side towards H2 (the rear view's left).

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
    if title in BODY:
        pts = [BODY[title][:2], BODY[title][2:]]
    padpts = []
    for pd in pads.values():
        padpts += [(pd["x"] - pd["w"] / 2, pd["y"] - pd["h"] / 2), (pd["x"] + pd["w"] / 2, pd["y"] + pd["h"] / 2)]
    body = pts or padpts             # the housing as drawn; pads are checked on their own
    xs, ys = [x for x, _ in body], [y for _, y in body]
    return {"pads": pads, "bbox": (min(xs), min(ys), max(xs), max(ys)), "title": title}


# Body boxes that override a footprint's drawn outline (x1, y1, x2, y2 in the footprint's own frame).
BODY = {}


# ---------------------------------------------------------------- boards
class Board:
    """One PCB: parts placed in the shared rear-view frame."""

    def __init__(self, title, pr, parts, info, W, H):
        self.title, self.pr, self.info, self.W, self.H = title, pr, info, W, H
        self.P = {p.ref: p for p in parts}
        self.placed, self.holes, self.strings = [], [], []
        self.keepouts, self.cutouts, self.outlines = [], [], []

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

    def hole_front(self, xf, y, d=HOLE_D):
        self.hole(self.W - xf, y, d)

    def text(self, x, y, s, size=1.5, bottom=False):
        self.strings.append((x, y, s, size, bottom))

    def box_front(self, x1, y1, x2, y2):
        """A front-view box in this board's frame."""
        return self.W - x2, y1, self.W - x1, y2

    def keepout_front(self, x1, y1, x2, y2, what):
        """Something in the panel gap (front side) that no pad may sit under."""
        self.keepouts.append((self.box_front(x1, y1, x2, y2), what))

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
        """Problems: unplaced or unknown parts, pads too close to each other, to a hole, a cutout or the
        edge, bodies overlapping on one side, bodies under a standoff (gap side) or a screw head (the
        other side) or over a cutout. gap_side: 'top' or 'bottom', the side that faces the other board."""
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
        for i, (ra, na, a1, a2, r1) in enumerate(shapes):
            for rb, nb, b1, b2, r2 in shapes[i + 1:]:
                if ra != rb and abs(a1[0] - b1[0]) < 6 and abs(a1[1] - b1[1]) < 6:
                    gap = min(_seg_dist(a1, b1, b2), _seg_dist(a2, b1, b2), _seg_dist(b1, a1, a2),
                              _seg_dist(b2, a1, a2)) - r1 - r2
                    if gap < CLEAR:
                        bad.append(f"{self.title}: pads {ra}.{na} and {rb}.{nb} are {gap:.2f} mm apart")
        for side in (False, True):
            bodies = [(pl["ref"], self.body(pl), pl["geo"]["title"]) for pl in self.placed if pl["bottom"] == side]
            for i, (ra, a, _) in enumerate(bodies):
                for rb, b, _ in bodies[i + 1:]:
                    if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
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
                    if x1 < cx2 and cx1 < x2 and y1 < cy2 and cy1 < y2:
                        bad.append(f"{self.title}: body of {ref} lies over the cutout")
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
        for (x1, y1, x2, y2), label, bottom in self.outlines:
            d.add("POLY", d.nid(), {"partitionId": "", "groupId": 0, "netName": "", "layerId": 4 if bottom else 3,
                                    "width": mil(0.2), "path": [mil(x1), mil(y1), "L", mil(x2), mil(y1), "L", mil(x2),
                                                                mil(y2), "L", mil(x1), mil(y2), "L", mil(x1), mil(y1)],
                                    "locked": False, "zIndex": d.zi(), "polyType": "NORMAL"})
            self.strings.append((x2 - 1.0, y2 - 3.0, label, 1.3, bottom))
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
    def render(self, path, scale=8):
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
        for (x1, y1, x2, y2), what in self.keepouts:
            dr.rectangle([P(x1, y2), P(x2, y1)], fill="#f2f2f2", outline="#909090")
            dr.text((P(x1, y2)[0] + 4, P(x1, y2)[1] + 4), what, fill="#707070", font=big)
        for x1, y1, x2, y2, r in self.cutouts:
            dr.rounded_rectangle([P(x1, y2), P(x2, y1)], radius=r * scale, fill="#404040")
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
                dr.text((X + 1, Y - 11), pl["ref"], fill=col, font=font)
        for hx, hy, hd in self.holes:
            X, Y = P(hx, hy)
            r = hd / 2 * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], outline="#000000", width=2)
            r = STANDOFF_R * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], outline="#808080")
        dr.text((20, H + 26), f"{self.title}: rear view (EasyEDA top layer). red = top layer, blue = bottom layer, "
                              f"grey = M3 standoff, dark = cutout", fill="#000000", font=big)
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


def faceplate_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Faceplate", pr, parts, info, W, H)

    def F(x, y):                          # front view -> this board's frame
        return W - x, y

    for xf, y in circuit.HOLES_FRONT:      # the same four on the main board
        b.hole_front(xf, y)
    # panel parts on the bottom layer, at the PLACEMENT origins, oriented by rule
    for ref, (xf, y, _) in circuit.PLACEMENT.items():
        if ref in b.P:
            b.place_front(ref, xf, y, 0, bottom=True)
    for ref, *_ in circuit.JACKS:          # sleeve pad above the tip pad, pins in a column
        b.orient(ref, lambda r: abs(r["1"][0] - r["3"][0]) < 0.01 and r["1"][1] > r["3"][1])
    for ref, *_ in circuit.BUTTONS:        # LED button: LED pins in a row along x, anode on the right
        b.orient(ref, lambda r: abs(r["5"][1] - r["6"][1]) < 0.01 and r["5"][0] > r["6"][0] and r["1"][1] > r["3"][1])
    rules = {"below": lambda r: r["C"][1] < -5 and r["S1"][1] > 5, "left": lambda r: r["C"][0] < -5 and r["S1"][0] > 5}
    for ref, _ in circuit.ENCODERS:
        b.orient(ref, rules[circuit.ENC_PINS[ref]])
    # the display module in the panel gap, its outline on the bottom silk, the cable's cutout
    b.keepout_front(*circuit.DISPLAY_MODULE, "display module (front)")
    b.outline_front(*circuit.DISPLAY_MODULE, "DISPLAY")
    b.cutout_front(*circuit.DISPLAY_CUTOUT)
    # rear (top layer): the 74HC165s in the strip above the jacks, a 100 n at each
    b.place_front("U1", 10.4, 33.1, 0)
    b.place_front("U2", 44.0, 33.1, 0)
    place_pins(b, "C1", {"1": F(22.0, 35.64), "2": F(22.0, 30.56)})
    place_pins(b, "C2", {"1": F(39.0, 39.6), "2": F(44.08, 39.6)})
    # pull-up networks in the channel between the encoder columns, pin 1 (common) at the lower end
    place_pins(b, "RN1", {"1": F(50.3, 53.5), "9": F(50.3, 73.82)})
    place_pins(b, "RN2", {"1": F(50.3, 77.0), "9": F(50.3, 97.32)})
    # the display cable's right-angle header under the send buttons, its plug lying over the empty strip
    # behind the module; pin 1 (VCC) on the right
    place_pins(b, "CN1", {"1": F(21.78, 92.6), "8": F(4.0, 92.6)})
    place_pins(b, "C4", {"1": F(24.5, 92.6), "2": F(29.58, 92.6)})
    for ref, (xf, y, a) in circuit.HEADERS_FRONT.items():   # male headers on the top (rear) layer
        b.place_front(circuit.fb_ref(ref), xf, y, a)
    b.text(W - 20, H - 2.6, "Side FXy faceplate", 1.6)
    return b


# Main board, top (rear) layer, PCB frame: x = BOARD_W - x_front, so H2 (the right edge seen from the
# front) is on the left. The breakout stands in the middle, USB end down, pins 21-40 (3V3A, the ADC
# inputs, the chain, 3V3D) in its left row and pins 1-20 (clock, display, MIDI) in its right row; H3 and
# H4 sit in the channel between the rows. Left of it, bottom to top: the 74HC595 with its LED resistors,
# H1's sockets, the clock stage, the MIDI opto, the bias, the TL074 with its four CV stages clustered at
# its corners (the Plaitsy way) and a 100 n per rail beside its supply pins.
SEED_XY = (37.2, 41.0, 270)
TL074_XY = (14.5, 83.0, 90)
HC595_XY = (16.0, 17.0, 90)
H11L1_XY = (12.0, 58.8, 90)


def _cv_cluster(b, sec, rin, rf, rs, cf):
    """Rf on IN- / OUT one column out from the chip, Rin and Rs the next column, Cf lying in the third."""
    out, inm, inp = (b.pin("U6", n) for n in {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"),
                                                4: ("14", "13", "12")}[sec])
    sx = 1 if out[0] > TL074_XY[0] else -1
    step = out[1] - inm[1]                 # +-2.54: the way the section's rows run from the chip's middle
    c1, c2, c3 = (inm[0] + sx * 2.54 * k for k in (1, 2, 3))
    y4 = out[1] + step
    place_pins(b, rf, {"1": (c1, inm[1]), "2": (c1, out[1])})
    place_pins(b, rin, {"1": (c2, inp[1]), "2": (c2, inm[1])})
    place_pins(b, rs, {"1": (c2, out[1]), "2": (c2, y4)})
    place_pins(b, cf, {"1": (c3, inm[1]), "2": (c3, y4)})


def main_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Main board", pr, parts, info, W, H)
    for xf, y in circuit.HOLES_FRONT:
        b.hole_front(xf, y)
    for ref, (xf, y, a) in circuit.HEADERS_FRONT.items():   # female sockets, bottom layer, same spot
        b.place_front(ref, xf, y, a, bottom=True)
    b.place("U5", *SEED_XY)
    # TL074, its four CV stages and a 100 n per rail beside pins 4 / 11
    b.place("U6", *TL074_XY)
    for i, (name, sec) in enumerate(circuit.CV_CHANNELS):
        _cv_cluster(b, sec, f"R{10 + 3 * i}", f"R{11 + 3 * i}", f"R{12 + 3 * i}", f"C{10 + i}")
    (x4, y4), (x11, y11) = b.pin("U6", "4"), b.pin("U6", "11")
    place_pins(b, "C15", {"1": (x4 + 2.54, y4), "2": (x4 + 7.62, y4)})
    place_pins(b, "C16", {"2": (x11 - 2.54, y11), "1": (x11 - 7.62, y11)})
    # bias divider and its 1 u under the TL074
    place_pins(b, "R22", {"1": (5.0, 69.5), "2": (5.0, 66.96)})
    place_pins(b, "R23", {"1": (7.54, 66.96), "2": (7.54, 69.5)})
    place_pins(b, "C14", {"1": (10.5, 68.6), "2": (15.58, 68.6)})
    # MIDI: H11L1 standing, the 220R at pin 1, the 1N4148 lying under it, the pull-up at pin 4, a 100 n at pin 6
    b.place("U7", *H11L1_XY)
    (x1, y1), (x2, y2) = b.pin("U7", "1"), b.pin("U7", "2")
    (x4, y4), (x6, y6) = b.pin("U7", "4"), b.pin("U7", "6")
    place_pins(b, "R26", {"1": (x1 + 5.08, y1), "2": (x1 + 2.54, y1)})
    place_pins(b, "D2", {"1": (x1 + 9.0, y1 - 2.54), "2": (x1 + 1.0, y1 - 2.54)})
    place_pins(b, "R27", {"1": (x4 - 2.54, y4 + 2.54), "2": (x4 - 2.54, y4)})
    place_pins(b, "C17", {"1": (x6 - 2.54, y6), "2": (x6 - 2.54, y6 - 5.08)})
    # clock input: the 2N3904 with its base resistor below it, the clamp lying under that, the pull-up
    place_pins(b, "Q1", {"1": (18.46, 41.5), "3": (23.54, 41.5)})
    place_pins(b, "R24", {"1": (21.0, 35.0), "2": (21.0, 37.54)})
    place_pins(b, "D1", {"1": (24.5, 32.4), "2": (16.5, 32.4)})
    place_pins(b, "R25", {"1": (26.08, 44.04), "2": (23.54, 44.04)})
    # the 74HC595 near the chain's pins, its LED resistors beside QA..QE, a 100 n at pin 16
    b.place("U3", *HC595_XY)
    for k, ref in enumerate(circuit.LED_ORDER):
        x, y = b.pin("U3", circuit.HC595_OUT[k])
        sx = 1 if x > HC595_XY[0] else -1
        place_pins(b, f"R{k + 1}", {"1": (x + sx * 2.54, y), "2": (x + sx * 5.08, y)})
    x, y = b.pin("U3", "16")
    sx = 1 if x > HC595_XY[0] else -1
    sy = 1 if y > HC595_XY[1] else -1
    place_pins(b, "C3", {"1": (x + sx * 2.54, y), "2": (x + sx * 2.54, y + sy * 5.08)})
    b.text(48.0, H - 2.6, "Side FXy main board", 1.6)
    return b


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
        if ref not in fb.P:              # DS1: the display module, not a part of this board
            continue
        pl = next(p for p in fb.placed if p["ref"] == ref)
        if abs(fb.W - pl["x"] - xf) > 0.001 or abs(pl["y"] - y) > 0.001:
            bad.append(f"{ref} not at its PLACEMENT origin")
    return bad


def front_housing_check(fb):
    """Rear-side pads must not sit under a panel part's housing or under the display module: those pads
    are soldered on the panel side, where the jack, encoder and button bodies and the module lie."""
    bad = []
    boxes = [(pl["ref"], fb.body(pl)) for pl in fb.placed if pl["bottom"]] + [(w, box) for box, w in fb.keepouts]
    for pl in fb.placed:
        if pl["bottom"]:
            continue
        for num, (x, y, r) in fb.pads(pl).items():
            for ref, (x1, y1, x2, y2) in boxes:
                if x1 - r < x < x2 + r and y1 - r < y < y2 + r:
                    bad.append(f"{fb.title}: {pl['ref']}.{num} pad lies under {ref}")
    return bad
