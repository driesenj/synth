"""Marblesy PCBs: both boards placed, net-assigned and unrouted, as EasyEDA
Pro PCB documents inside Marbles.epro2 (easyeda_export.py calls this).

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

Nothing here is routed; the second pass does that in EasyEDA Pro.
"""
import collections
import json
import math
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "easyeda", "pcb-template.epru")
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
                                   "w": dp["width"] * 0.0254, "h": dp["height"] * 0.0254}
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
    for pd in pads.values():
        pts += [(pd["x"] - pd["w"] / 2, pd["y"] - pd["h"] / 2), (pd["x"] + pd["w"] / 2, pd["y"] + pd["h"] / 2)]
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
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
        allpads = []
        for pl in self.placed:
            for num, (x, y, r) in self.pads(pl).items():
                allpads.append((pl["ref"], num, x, y, r))
                if x - r < EDGE or x + r > self.W - EDGE or y - r < EDGE or y + r > self.H - EDGE:
                    bad.append(f"{self.title}: {pl['ref']}.{num} pad at ({x:.2f}, {y:.2f}) is at the board edge")
                for hx, hy, hd in self.holes:
                    if math.hypot(x - hx, y - hy) < r + hd / 2 + CLEAR:
                        bad.append(f"{self.title}: {pl['ref']}.{num} pad is {math.hypot(x - hx, y - hy):.2f} from the hole at ({hx}, {hy})")
        for i, (ra, na, xa, ya, r1) in enumerate(allpads):
            for rb, nb, xb, yb, r2 in allpads[i + 1:]:
                if ra != rb and math.hypot(xa - xb, ya - yb) < r1 + r2 + CLEAR:
                    bad.append(f"{self.title}: pads {ra}.{na} and {rb}.{nb} are {math.hypot(xa - xb, ya - yb) - r1 - r2:.2f} mm apart")
        for side in (False, True):
            bodies = [(pl["ref"], self.body(pl)) for pl in self.placed if pl["bottom"] == side]
            for i, (ra, a) in enumerate(bodies):
                for rb, b in bodies[i + 1:]:
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


# ------------------------------------------------------------- placement
def _rows(yc, n=6, pitch=2.54):
    return [yc + (i - (n - 1) / 2) * pitch for i in range(n)]


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
    # headers (male, top layer), shared with the main board
    for ref, (xf, y, a) in HEADERS_FRONT.items():
        b.place_front(circuit.fb_ref(ref), xf, y, a)
    # logic on the top (rear) side: front-view coordinates, angle in the PCB frame
    for ref, xf, y, a in FB_REAR:
        b.place_front(ref, xf, y, a)
    b.text(2, H - 3.5, "Marblesy faceplate board", 2.0)
    return b


def main_board(pr, parts, info, circuit):
    W, H = circuit.BOARD_W, circuit.BOARD_H
    b = Board("Main board", pr, parts, info, W, H)
    for xf, y in HOLES_FRONT:
        b.hole_front(xf, y)
    for ref, (xf, y, a) in HEADERS_FRONT.items():   # female sockets, bottom layer, same spot
        b.place_front(ref, xf, y, a, bottom=True)
    for ref, x, y, a in MB_TOP:
        b.place(ref, x, y, a)
    b.text(23, H - 3.5, "Marblesy main board", 2.0)
    return b


# Front-view coordinates (x from the left as seen from the panel, y up).
# Holes: two on the centre line between the knobs, one each side between the
# BIAS knob and the mode button; on the main board the side holes land
# between the breakout's pad rows and beside the clock stages.
HOLES_FRONT = [(45, 82), (45, 33), (79, 69), (11, 69)]
# header: (x, y, angle); 0 = pins along x, 90 = along y. H1/H2 in the strip
# above the big knobs, H3/H4 between the CV jacks and the JITTER/STEPS
# knobs, H5 beside the right range button.
HEADERS_FRONT = {"H1": (33.75, 105.5, 0), "H2": (56.5, 105.5, 0), "H3": (52, 34.5, 90), "H4": (38, 34.5, 90),
                 "H5": (74, 47.5, 90)}

# Faceplate, rear side (top layer): ref, x_front, y, angle. 0 = pins along x, 90 = along y.
# U1/U11 in the strip between the CV jacks and the JITTER/STEPS knobs, U9/U10
# vertical in the pockets beside LENGTH, resistors in rows beside RATE and
# SPREAD and in columns beside the range buttons.
FB_REAR = [
    ("U1", 25, 33.8, 0), ("U11", 65, 33.8, 0), ("U9", 35, 62.5, 90), ("U10", 55, 62.5, 90),
    ("C8", 13.7, 34, 90), ("C11", 76.3, 33.8, 90), ("C9", 35, 74.5, 0), ("C10", 55, 74.5, 0),
]
_ROWS = [77, 79.5, 82, 84.5, 87, 89.5, 92]
FB_REAR += [(f"R{80 + i}", 34.75, y, 0) for i, y in enumerate(_ROWS)]                       # LED resistors
FB_REAR += [(r, 56.3, y, 0) for r, y in zip(("R100", "R101", "R102"), _ROWS)]
FB_REAR += [(r, x, 47.5, 90) for r, x in zip(("R9", "R103", "R104", "R105"), (15.5, 18.5, 21.5, 24.5))]
FB_REAR += [(r, x, 47.5, 90) for r, x in zip(("R10", "R106"), (65.5, 68.5))]

# Main board, top (rear) layer, PCB frame: ref, x, y, angle.
XA, XB, XC = 41.5, 54.5, 67.5      # resistor columns right of the op-amps (horizontal, 10.3 mm pitch)
MB_TOP = [("U2", 11, 64, 90),        # Seed breakout along the left edge, power end down, USB end up
          ("U3", 28, 92, 90), ("U4", 28, 72, 90), ("U5", 28, 52, 90), ("U6", 28, 20, 90),
          ("U7", 70, 20, 90), ("U8", 82, 20, 90)]
# U3: CV stages T_RATE..DEJAVU (R21-R32, C21-C24), decoupling C31/C32
MB_TOP += [(f"R{21 + i}", XA, y, 0) for i, y in enumerate(_rows(92))]
MB_TOP += [(f"R{27 + i}", XB, y, 0) for i, y in enumerate(_rows(92))]
MB_TOP += [("C21", 63.5, 88, 90), ("C22", 63.5, 96, 90), ("C23", 66.5, 88, 90), ("C24", 66.5, 96, 90),
           ("C31", 69.5, 88, 90), ("C32", 69.5, 96, 90)]
# U4: CV stages X_SPREAD..X_STEPS (R33-R41, C25-C27), -2.5 V inverter R42/R43, decoupling C33/C34
MB_TOP += [(f"R{33 + i}", XA, y, 0) for i, y in enumerate(_rows(72))]
MB_TOP += [(f"R{39 + i}", XB, y, 0) for i, y in enumerate(_rows(72)[:5])]
MB_TOP += [("C25", 63.5, 68, 90), ("C26", 63.5, 76, 90), ("C27", 66.5, 68, 90), ("C33", 69.5, 68, 90),
           ("C34", 69.5, 76, 90)]
# U5: DAC output stages (R70-R85), bias R45/R46/C29, decoupling C35/C36
MB_TOP += [(f"R{70 + i}", XA, y, 0) for i, y in enumerate(_rows(52))]
MB_TOP += [(f"R{76 + i}", XB, y, 0) for i, y in enumerate(_rows(52))]
MB_TOP += [(r, XC, y, 0) for r, y in zip(("R82", "R83", "R84", "R85", "R45", "R46"), _rows(52))]
MB_TOP += [("C35", 77, 48, 90), ("C36", 77, 56, 90), ("C29", 81, 52, 90)]
# U6: gate stages (R60-R68), decoupling C37/C38; reference C30 in the same column
MB_TOP += [(f"R{60 + i}", XA, y, 0) for i, y in enumerate(_rows(20))]
MB_TOP += [(f"R{66 + i}", XB, y, 0) for i, y in enumerate(_rows(20)[:3])]
MB_TOP += [("C37", 62.5, 16, 90), ("C38", 62.5, 24, 90), ("C30", 62.5, 33, 90)]
# DAC decoupling and the 2.5 V reference next to the DACs
MB_TOP += [("C39", 66, 33.5, 90), ("C40", 78, 34, 90), ("R47", 70.5, 38.8, 0), ("D21", 85, 38.5, 0)]
# clock input stages in the right strip (vertical parts)
MB_TOP += [("R50", 73.5, 92, 90), ("R51", 75.9, 92, 90), ("Q1", 80, 92, 90), ("D22", 85.3, 92, 90),
           ("R52", 73.5, 72, 90), ("R53", 75.9, 72, 90), ("Q2", 80, 74.5, 90), ("D23", 85.3, 72, 90)]


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
