"""Stereo mixer PCBs: both boards placed, net-assigned and unrouted, as
EasyEDA Pro PCB documents inside StereoMixer.epro2 (easyeda_export.py calls
this). The board class, checks and writer are Plaitsy's (plaits/hardware/
tools/pcb.py); the placement below is the mixer's.

Frame. Each PCB is drawn the way EasyEDA shows it, looking at the top layer.
On both boards the top layer is the REAR of the stack (away from the panel):
x to the right, y up, origin at the board's bottom-left corner, millimetres.
The front view that circuit.PLACEMENT and panel.py use is the mirror image:
x_front = BOARD_W - x. Both boards share one frame, so a header pair has the
same x/y on both PCBs and the stack lines up pin for pin (checked below).

Faceplate board: jacks, pots and LED buttons on the bottom layer (towards
the panel) in the panel's arrangement, pots pins-down; the nine male
headers on the top layer, standing in the strips between the columns.
Main board: the nine female sockets on the bottom layer; everything else
on the top layer, every resistor standing up.

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
# footprint's own frame). None needed here: the generated Alpha footprints
# draw the real housing (9.5 mm wide, from 1 mm off the pin row to 4.85 mm
# past the shaft, which is 7.5 mm from the pins).
BODY = {}


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


def place_pins(b, ref, targets, bottom=False):
    """Place ref so that the first of two pins lands exactly on its target and the
    second points the same way as its target (angles 0 / 90 / 180 / 270 tried).
    targets: {pin: (x, y)} with two entries, PCB frame."""
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
    for xf, y in circuit.HOLES_FRONT:      # the same four on the main board
        b.hole_front(xf, y)
    # panel parts on the bottom layer, at the PLACEMENT origins, oriented by rule
    for ref, (xf, y, _) in circuit.PLACEMENT.items():
        b.place_front(ref, xf, y, 0, bottom=True)
    for ref, *_ in circuit.JACKS:          # sleeve pad above the tip pad, pins in a column
        b.orient(ref, lambda r: abs(r["1"][0] - r["3"][0]) < 0.01 and r["1"][1] > r["3"][1])
    for ref, *_ in circuit.POTS + circuit.POTS2:   # pins below the shaft, pin 1 (CCW end) on the left
        b.orient(ref, lambda r: r["1"][1] < 0 and abs(r["1"][1] - r["3"][1]) < 0.01 and r["1"][0] < r["3"][0])
    for ref, *_ in circuit.BUTTONS:        # LED button: LED pins in a row along x, anode on the right
        b.orient(ref, lambda r: abs(r["5"][1] - r["6"][1]) < 0.01 and r["5"][0] > r["6"][0] and r["1"][1] > r["3"][1])
    for ref, (xf, y, a) in circuit.HEADERS_FRONT.items():   # male headers on the top (rear) layer
        b.place_front(circuit.fb_ref(ref), xf, y, a)
    b.text(W - 30, H - 2.6, "Stereo mixer faceplate", 1.8)
    return b


# Main board, top (rear) layer, PCB frame: x = BOARD_W - x_front, so channel 1
# is on the right and the master section on the left. Every TL074 stands
# vertical (angle 90: pins 1-7 in the +x column, pin 1 at the bottom), each
# section's parts clustered at its corner the Plaitsy way:
#   follower   10k mute resistor beside IN+ (pad 2 = FI on the chip side), the
#              PhotoMOS switch pins under it, the pan feeds (mono) or the send
#              average (stereo) beyond the chip's end, pad 1 = CH
#   summer     Rf on IN- / OUT, Cf one column out, the bus resistors in a 2 x 5
#              block beyond the chip's end, their summing pads (2) facing
#              each other in the middle
#   output     Rf on IN- / OUT, Rin and Rs one column out
# and the 100 n for each rail beside its supply pin. The latch logic, the
# power entry and the headers' sockets fill the lower half.
DIPX = 3.81                    # half the 7.62 mm row pitch
X_U = {"U1": 111.5, "U2": 70.0, "U3": 40.0, "U4": 13.0}
Y_U = 81.0
VR_P1 = 0.48006                # a standing resistor's pad 1 (the body) sits this far above its origin


def _stand(ref, p1, p2):
    """A standing resistor with pad 1 (the body) at p1 and pad 2 one pitch from it, towards p2."""
    a = math.degrees(math.atan2(p2[0] - p1[0], -(p2[1] - p1[1])))
    dx, dy = rot(0, VR_P1, a)
    return ref, p1[0] - dx, p1[1] - dy, round(a) % 360


def _two(ref, p1, p2):
    """A two-lead part lying flat (capacitor, diode), pad 1 at p1, pad 2 at p2."""
    return ref, (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, round(math.degrees(math.atan2(p2[1] - p1[1],
                                                                                         p2[0] - p1[0]))) % 360


def _corner(u, sec):
    """x0, y0, sx, sy of a TL074 section: sx = +1 on the pin 1-7 column, sy = -1 at the pin 1 / 14 end."""
    return X_U[u], Y_U, (1 if sec in (1, 2) else -1), (-1 if sec in (1, 4) else 1)


def _follower(P, u, sec, side_net, feeds):
    """Parts of one follower: the mute resistor, the PhotoMOS switch (as pin targets), the feed resistors."""
    x0, y0, sx, sy = _corner(u, sec)
    c1, c2 = x0 + sx * 6.35, x0 + sx * 8.89
    rmute = next(p.ref for p in P.values() if p.kind == "R" and p.nets.get("2") == f"FI{side_net}")
    kref = next(p.ref for p in P.values() if p.kind == "PHOTOMOS" and p.nets["3"] == f"FI{side_net}")
    top = [_stand(rmute, (c2, y0 + sy * 2.54), (c1, y0 + sy * 2.54))]
    # the PhotoMOS can't be mirrored on the top layer: where its LED side would face the chip (corners with
    # sx * sy > 0) it turns over and pin 4 (GND) comes first; FI then runs under its body to pin 3
    near, far = ("3", "4") if sx * sy < 0 else ("4", "3")
    pins = [(kref, {near: (c1, y0 + sy * 5.08), far: (c1, y0 + sy * 7.62)})]
    for ref, slot in feeds:          # slot 0 = x0 + 2.54, slot 1 = x0 + 5.08 (outward)
        x = x0 + sx * 2.54 * (slot + 1)
        top.append(_stand(ref, (x, y0 + sy * 11.43), (x, y0 + sy * 13.97)))
    return top, pins


def _summer(u, sec, rf, cf, bus):
    """An inverting summer: Rf on IN- / OUT, Cf one column out, the bus resistors in a block beyond the
    chip's end (two rows; summing pads 2 in the middle rows, inputs on the outside)."""
    x0, y0, sx, sy = _corner(u, sec)
    c1, c2 = x0 + sx * 6.35, x0 + sx * 8.89
    top = [_stand(rf, (c1, y0 + sy * 5.08), (c1, y0 + sy * 7.62)),
           _two(cf, (c2, y0 + sy * 2.54), (c2, y0 + sy * 7.62))]
    xs = [x0 + sx * (-2.5 + 2.54 * i) for i in range(5)]
    ya = y0 + sy * 11.5
    for i, ref in enumerate(bus):
        row, col = divmod(i, 5)
        x = xs[col]
        if row == 0:                 # pad 1 towards the chip, pad 2 away
            top.append(_stand(ref, (x, ya), (x, ya + sy * 2.54)))
        else:                        # pad 2 towards row 0's pads 2, pad 1 outside
            top.append(_stand(ref, (x, ya + sy * 7.62), (x, ya + sy * 5.08)))
    return top


def _output(u, sec, rin, rf, rs):
    """An inverting output stage (Plaitsy's CV-stage cluster without Cf)."""
    x0, y0, sx, sy = _corner(u, sec)
    c1, c2 = x0 + sx * 6.35, x0 + sx * 8.89
    y = [y0 + sy * 2.54 * k for k in range(5)]           # y[1] IN+, y[2] IN-, y[3] OUT
    return [_stand(rf, (c1, y[2]), (c1, y[3])),          # pad 1 IN-, pad 2 OUT
            _stand(rin, (c2, y[1]), (c2, y[2])),         # pad 1 the input, pad 2 IN-
            _stand(rs, (c2, y[3]), (c2, y[4]))]          # pad 1 OUT, pad 2 the jack line


def _decoupling(u, cp, cn):
    """The 100 n of each rail beside its supply pin (4 = +12 V on the +x column, 11 = -12 V), lying outward."""
    x0, y0 = X_U[u], Y_U
    return [_two(cp, (x0 + 6.35, y0), (x0 + 11.43, y0)),      # C pad 1 = +12 V next to pin 4
            _two(cn, (x0 - 11.43, y0), (x0 - 6.35, y0))]      # C pad 2 = -12 V next to pin 11


# the latch logic: CD4013 row and CD4093 row (horizontal, angle 0), the per-channel parts between them
X_FLOP = {"U7": 129.0, "U8": 102.5, "U9": 75.5, "U10": 48.5}
X_NAND = {"U5": 115.75, "U6": 62.0}
Y_FLOP, Y_NAND = 12.0, 25.5


def _main_top(circuit, P):
    top, pins = [], []
    for u in X_U:
        top.append((u, X_U[u], Y_U, 90))
    for (u, sec), (kind, name) in circuit.OPAMPS.items():
        if kind == "FOL":
            if name.isdigit():                      # mono: the two pan feeds
                k = int(name)
                feeds = [(f"R{100 * k + 2}", 0), (f"R{100 * k + 3}", 1)]
            else:                                   # stereo: its send-average resistor in the outer slot
                c, side = int(name[0]), name[1]
                feeds = [(f"R{100 * c + (5 if side == 'L' else 6)}", 1)]
            t, p = _follower(P, u, sec, name, feeds)
            top += t
            pins += p
    bus = {"L": [f"R{100 * k + 4}" for k in circuit.MONO] + ["R703", "R803", "R913", "R915"],
           "R": [f"R{100 * k + 5}" for k in circuit.MONO] + ["R704", "R804", "R914", "R916"],
           "S": [f"R{100 * k + 6}" for k in circuit.MONO] + ["R707", "R807", "R917"]}
    fb = {"L": ("R901", "C901"), "R": ("R902", "C902"), "S": ("R903", "C903")}
    for side in "LRS":
        u, sec = circuit.opamp_of("SUM", side)
        top += _summer(u, sec, *fb[side], bus[side])
    for side, refs in (("L", ("R904", "R905", "R906")), ("R", ("R907", "R908", "R909")),
                       ("S", ("R910", "R911", "R912"))):
        u, sec = circuit.opamp_of("OUT", side)
        top += _output(u, sec, *refs)
    for i, u in enumerate(("U1", "U2", "U3", "U4")):
        top += _decoupling(u, f"C{911 + 2 * i}", f"C{912 + 2 * i}")
    # logic chips and their 100 n at the pin 14 (VDD) end
    for i, u in enumerate(("U5", "U6", "U7", "U8", "U9", "U10")):
        x0, y0 = (X_NAND[u], Y_NAND) if u in X_NAND else (X_FLOP[u], Y_FLOP)
        top.append((u, x0, y0, 0))
        top.append(_two(f"C{921 + i}", (x0 - 10.9, y0 + 3.81), (x0 - 10.9, y0 - 1.27)))
    # per channel, in its cell under the header's bottom pins (BTN, LED): pull-up, debounce R and C, LED resistor
    for k in circuit.MONO + circuit.STEREO:
        xh = circuit.BOARD_W - circuit.HEADERS_FRONT[f"H{k}"][0]
        rp = next(p.ref for p in P.values() if p.kind == "R" and p.nets.get("2") == f"BTN{k}")
        rd = next(p.ref for p in P.values() if p.kind == "R" and p.nets.get("1") == f"BTN{k}")
        cd = next(p.ref for p in P.values() if p.kind == "C" and p.nets.get("1") == f"DB{k}")
        rl = next(p.ref for p in P.values() if p.kind == "R" and p.nets.get("1") == f"QK{k}")
        top += [_stand(rp, (xh - 2.5, 36.2), (xh - 2.5, 33.66)), _stand(rd, (xh - 5.04, 33.66), (xh - 5.04, 36.2)),
                _stand(rl, (xh - 7.58, 36.2), (xh - 7.58, 33.66)),
                _two(cd, (xh - 10.5, 37.0), (xh - 10.5, 31.92))]
    # power-on reset beside U10
    top += [_two("C906", (32.0, 24.5), (32.0, 19.42)), _stand("R920", (35.5, 24.5), (35.5, 21.96)),
            _two("D903", (31.0, 9.5), (31.0, 17.5))]
    # power entry in the lower-left corner: the box header standing along the left edge, pin 1 (-12 V) at the
    # bottom; the diodes, 10R and 10 u between it and the master header
    top += [("J18", 6.6, 21.5, 90),
            _two("D901", (14.0, 35.0), (22.7, 35.0)), _two("D902", (22.7, 29.0), (14.0, 29.0)),
            _stand("R918", (24.5, 25.0), (24.5, 22.46)), _stand("R919", (21.0, 25.0), (21.0, 22.46)),
            _two("C904", (16.0, 16.0), (16.0, 18.5)), _two("C905", (16.0, 10.0), (16.0, 12.5))]
    return top, pins


def main_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Main board", pr, parts, info, W, H)
    P = {p.ref: p for p in parts}
    for xf, y in circuit.HOLES_FRONT:
        b.hole_front(xf, y)
    for ref, (xf, y, a) in circuit.HEADERS_FRONT.items():   # female sockets, bottom layer, same spot
        b.place_front(ref, xf, y, a, bottom=True)
    top, pins = _main_top(circuit, P)
    for ref, x, y, a in top:
        b.place(ref, x, y, a)
    for ref, targets in pins:
        place_pins(b, ref, targets)
    b.text(56, H - 2.6, "Stereo mixer main board", 1.8)
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
