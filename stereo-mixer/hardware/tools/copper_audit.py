"""Audit a routed EasyEDA Pro export of the stereo mixer (copied from side-fx/, adapted).

Reads an .epro2 the user exported after routing: the whole project, or one
PCB document on its own ("ProDoc_Mixer Main PCB_<date>.epro2"). For every
routed PCB in it:
  netlist      every pad's net against circuit.py (swaps made while routing show up here)
  placement    every part against the generator's board (parts moved while routing),
               bodies overlapping on one side, bodies at a standoff or screw head,
               parts on the main board's front that are not sockets
  copper       tracks (LINE), vias, pads and the computed pours (POURED) joined
               into one graph per net: nets split into islands, nets shorted
               together, the smallest gap between copper of different nets,
               copper near a mounting hole, track ends that touch nothing
  audio        same-layer runs of the mute latch's switching nets beside audio
               nets, the summing nodes' copper, each 100 n's track path to its
               chip's supply pin
  headers      the main board's sockets under the faceplate's male pins (the
               routed faceplate when the export has one, else the generator's)
  panel        the panel board's holes against panel_pcb.py, when the export has it
and prints per-net track length, via count and layers for every signal net.

Run from stereo-mixer/hardware/tools:  python copper_audit.py <export.epro2> [marked.png]
Geometry is approximate where it has to be (pads as rotated rectangles or
stadiums, arcs flattened); anything it reports under the rule's clearance
deserves a look in EasyEDA, not an automatic verdict.
"""
import collections
import heapq
import importlib.util
import json
import math
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MIL = 0.0254
TEN_MIL = 0.254
CLEARANCE = 0.152       # the rule the user's boards carry for pads and vias (tracks to tracks: 0.102)
FAB_SPACING = 0.127     # JLCPCB's minimum spacing on a 2-layer board
NPTH_TRACK = 0.254      # JLCPCB's minimum from a non-plated hole to a track
HOLE_KEEPOUT = 3.0      # standoff / screw head around a mounting hole
BARREL_KEEPOUT = 3.0    # the Thonkiconn's metal barrel, panel side
THONK_TIP_R = 1.75      # Thonk's datasheet: a 3 mm hole (or no copper) under the barrel, where a plug tip reaches; +0.25
COUPLE_GAP = 0.6        # edge-to-edge gap under which a same-layer run counts as side by side
COUPLE_REPORT = 5.0     # mm of side-by-side run worth listing

# the latch's nets that switch with sharp edges (Schmitt and flip-flop outputs, the LED current), the slow
# ones (button, debounce RC, power-on reset), and the audio nets they should keep away from
FAST = re.compile(r"^(CK|QK|QN|LA|LM|LED)\d+$")
SLOW = re.compile(r"^(BTN|DB)\d+$|^POR$")
AUDIO = re.compile(r"^(LV|FI|CH|PL|PR|SD|AV)\d+[LR]?$|^(SUM|MIX|MST|NO|OA|OUT|RW)_[LRS]$|^(DRW|FXI|SEND)$")
HIGH_Z = re.compile(r"^SUM_[LRS]$|^NO_[LRS]$")     # the inverting stages' virtual-ground nodes


def _load(name):
    spec = importlib.util.spec_from_file_location("mixer_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ parsing
def read_export(path):
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(".epru"))
        lines = z.read(name).decode("utf-8").split("\n")
    docs, cur = {}, None
    for line in lines:
        if not line:
            continue
        h, _, p = line.partition("||")
        h, p = json.loads(h), p[:-1] if p.endswith("|") else p
        p = json.loads(p) if p else None          # deleted records keep an empty payload
        if h["type"] == "DOCHEAD":
            cur = docs[p["uuid"]] = {"docType": p["docType"], "recs": []}
        if p is not None:
            cur["recs"].append((h, p))
    return docs


# ------------------------------------------------------------------ geometry
def rot(x, y, a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return x * c - y * s, x * s + y * c


def d_point_seg(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0 if l2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def d_seg_seg(a, b, c, d):
    """Distance between segments ab and cd (0 when they cross)."""
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0:
        return 0.0
    return min(d_point_seg(a, c, d), d_point_seg(b, c, d), d_point_seg(c, a, b), d_point_seg(d, a, b))


def flatten_path(path, scale):
    """An EasyEDA path (x y L x y ARC sweep x y ...) -> list of (x, y) in mm."""
    pts, i, cur = [], 0, None
    while i < len(path):
        t = path[i]
        if t == "L":
            cur = (path[i + 1] * scale, path[i + 2] * scale)
            pts.append(cur)
            i += 3
        elif t == "ARC":
            sweep, x, y = path[i + 1], path[i + 2] * scale, path[i + 3] * scale
            x0, y0 = cur
            chord = math.hypot(x - x0, y - y0)
            if chord < 1e-9 or abs(sweep) < 1e-6:
                pts.append((x, y))
            else:
                half = math.radians(sweep) / 2
                r = chord / (2 * math.sin(abs(half)))
                mx, my = (x0 + x) / 2, (y0 + y) / 2
                h = math.sqrt(max(r * r - (chord / 2) ** 2, 0))
                nx, ny = -(y - y0) / chord, (x - x0) / chord      # left normal of the chord
                # the centre lies left of the chord for a counter-clockwise (positive) sweep under 180 degrees
                sgn = 1 if (sweep > 0) == (abs(sweep) <= 180) else -1
                cx, cy = mx + sgn * h * nx, my + sgn * h * ny
                a0 = math.atan2(y0 - cy, x0 - cx)
                n = max(2, int(abs(sweep) / 15))
                for k in range(1, n + 1):
                    a = a0 + math.radians(sweep) * k / n
                    pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            cur = (x, y)
            i += 4
        elif t == "CIRCLE":
            cx, cy, r = path[i + 1] * scale, path[i + 2] * scale, path[i + 3] * scale
            pts += [(cx + r * math.cos(2 * math.pi * k / 24), cy + r * math.sin(2 * math.pi * k / 24)) for k in range(24)]
            i += 4
        elif isinstance(t, str):
            raise ValueError(f"path command {t}")
        else:
            cur = (path[i] * scale, path[i + 1] * scale)
            pts.append(cur)
            i += 2
    return pts


def point_in_poly(p, poly):
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xi > x:
                inside = not inside
    return inside


def poly_area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2


def _bbox(pts):
    return min(q[0] for q in pts), min(q[1] for q in pts), max(q[0] for q in pts), max(q[1] for q in pts)


def _inside(p, bb):
    return bb[0] <= p[0] <= bb[2] and bb[1] <= p[1] <= bb[3]


def sat_overlap(p, q):
    """Penetration depth of two convex outlines (separating axes); <= 0 when they do not overlap."""
    best = math.inf
    for poly in (p, q):
        for k in range(len(poly)):
            (ax, ay), (bx, by) = poly[k], poly[(k + 1) % len(poly)]
            nx, ny = by - ay, ax - bx
            n = math.hypot(nx, ny)
            if n < 1e-12:
                continue
            nx, ny = nx / n, ny / n
            pa = [x * nx + y * ny for x, y in p]
            pb = [x * nx + y * ny for x, y in q]
            best = min(best, min(max(pa), max(pb)) - max(min(pa), min(pb)))
    return best


class Island:
    def __init__(self, outline, holes, layer, net):
        self.outline, self.holes, self.layer, self.net = outline, holes, layer, net
        self.bb = _bbox(outline)
        self.hole_bbs = [_bbox(h) for h in holes]
        self.area = poly_area(outline) - sum(poly_area(h) for h in holes)

    def contains(self, p):
        if not _inside(p, self.bb) or not point_in_poly(p, self.outline):
            return False
        return not any(_inside(p, bb) and point_in_poly(p, h) for h, bb in zip(self.holes, self.hole_bbs))


class Pad:
    """A through-hole pad: rectangle or stadium in the board frame."""

    def __init__(self, ref, num, x, y, w, h, shape, angle, net):
        self.ref, self.num, self.x, self.y, self.w, self.h, self.shape, self.angle, self.net = \
            ref, num, x, y, w, h, shape, angle, net
        self.r = math.hypot(w, h) / 2 if shape == "RECT" else max(w, h) / 2

    def _local(self, p):
        return rot(p[0] - self.x, p[1] - self.y, -self.angle)

    def corners(self):
        """A RECT pad's four corners in the board frame."""
        out = []
        for cx, cy in ((-self.w / 2, -self.h / 2), (self.w / 2, -self.h / 2), (self.w / 2, self.h / 2), (-self.w / 2, self.h / 2)):
            dx, dy = rot(cx, cy, self.angle)
            out.append((self.x + dx, self.y + dy))
        return out

    def axis(self):
        """A stadium (ELLIPSE) pad as its axis segment and radius: a circle has a zero-length axis."""
        hw, hh = self.w / 2, self.h / 2
        half = (max(hw, hh) - min(hw, hh))
        dx, dy = rot(half, 0, self.angle) if hw >= hh else rot(0, half, self.angle)
        return (self.x - dx, self.y - dy), (self.x + dx, self.y + dy), min(hw, hh)

    def d_point(self, p):
        if self.shape == "RECT":
            lx, ly = self._local(p)
            return math.hypot(max(abs(lx) - self.w / 2, 0), max(abs(ly) - self.h / 2, 0))
        a, b, r = self.axis()
        return max(d_point_seg(p, a, b) - r, 0.0)

    def d_seg(self, a, b):
        """Distance from the pad to a segment (exact: the minimum between convex shapes is at a vertex)."""
        if self.shape == "RECT":
            best = min(self.d_point(a), self.d_point(b))
            for c in self.corners():
                best = min(best, d_point_seg(c, a, b))
            cs = self.corners()
            for i in range(4):                  # a segment crossing the rectangle touches it
                if d_seg_seg(cs[i], cs[(i + 1) % 4], a, b) == 0:
                    return 0.0
            return max(best, 0.0)
        p0, p1, r = self.axis()
        return max(d_seg_seg(p0, p1, a, b) - r, 0.0)

    def d_pad(self, o):
        """Distance between two pads."""
        if self.shape == "RECT" and o.shape == "RECT":
            best = min(self.d_point(c) for c in o.corners())
            return min(best, min(o.d_point(c) for c in self.corners()))
        if self.shape != "RECT" and o.shape != "RECT":
            a0, a1, ra = self.axis()
            b0, b1, rb = o.axis()
            return max(d_seg_seg(a0, a1, b0, b1) - ra - rb, 0.0)
        rect, stad = (self, o) if self.shape == "RECT" else (o, self)
        s0, s1, r = stad.axis()
        return max(min(rect.d_seg(s0, s1) - r, min(stad.d_point(c) for c in rect.corners())), 0.0)

    def d_circle(self, c, r):
        return max(self.d_point(c) - r, 0.0)


def _near(a_bb, b_bb, margin):
    return a_bb[0] - margin <= b_bb[2] and b_bb[0] - margin <= a_bb[2] and \
        a_bb[1] - margin <= b_bb[3] and b_bb[1] - margin <= a_bb[3]


def _seg_bb(t):
    hw = t["w"] / 2
    return (min(t["a"][0], t["b"][0]) - hw, min(t["a"][1], t["b"][1]) - hw,
            max(t["a"][0], t["b"][0]) + hw, max(t["a"][1], t["b"][1]) + hw)


# ------------------------------------------------------------------ the board model
class RoutedBoard:
    def __init__(self, title, doc, fps):
        self.title = title
        self.parts, self.pads, self.tracks, self.vias, self.islands, self.holes, self.spokes = {}, [], [], [], [], [], []
        attrs, nets, comps, pours = collections.defaultdict(dict), collections.defaultdict(dict), {}, {}
        for h, p in doc["recs"]:
            t = h["type"]
            if t == "COMPONENT":
                comps[h["id"]] = p
            elif t == "ATTR" and p.get("parentId"):
                attrs[p["parentId"]][p["key"]] = p["value"]
            elif t == "PAD_NET":
                _, cid, num, _ = json.loads(h["id"])
                nets[cid][num] = p["padNet"]
            elif t == "LINE" and p.get("layerId") in (1, 2):
                tr = {"a": (p["startX"] * MIL, p["startY"] * MIL), "b": (p["endX"] * MIL, p["endY"] * MIL),
                      "w": p["width"] * MIL, "layer": p["layerId"], "net": p["netName"]}
                tr["bb"] = _seg_bb(tr)
                self.tracks.append(tr)
            elif t == "ARC" and p.get("layerId") in (1, 2):
                raise ValueError("copper arcs are not handled; flatten them first")
            elif t == "VIA":
                self.vias.append({"c": (p["centerX"] * MIL, p["centerY"] * MIL), "r": p["viaDiameter"] * MIL / 2,
                                  "drill": p["holeDiameter"] * MIL, "net": p["netName"]})
            elif t == "FILL" and p["layerId"] == 12 and p["path"][0][0] == "CIRCLE":
                _, x, y, r = p["path"][0]
                self.holes.append((x * MIL, y * MIL, 2 * r * MIL))
            elif t == "POUR":
                pours[h["id"]] = p
            elif t == "POLY" and p.get("polyType") == "BOARD_OUTLINE":
                _, x0, y0, w, hh, *_ = p["path"]
                self.outline = (x0 * MIL, (y0 - hh) * MIL, (x0 + w) * MIL, y0 * MIL)
        for h, p in doc["recs"]:
            if h["type"] != "POURED":
                continue
            pid = json.loads(h["id"])[1]
            if pid not in pours:
                continue                      # stale POURED of a deleted pour
            layer, net = pours[pid]["layerId"], pours[pid]["netName"]
            for item in p["pourFill"]:
                if item.get("fill"):
                    contours = [flatten_path(c, TEN_MIL) for c in item["path"]]
                    self.islands.append(Island(contours[0], contours[1:], layer, net))
                elif item.get("strokeWidth"):
                    pts = flatten_path(item["path"][0] if isinstance(item["path"][0], list) else item["path"], TEN_MIL)
                    self.spokes.append((pts[0], pts[-1], layer, net))
        for cid, p in comps.items():
            geo = fps[attrs[cid]["Footprint"]]
            ref = attrs[cid]["Designator"]
            pl = {"ref": ref, "x": p["x"] * MIL, "y": p["y"] * MIL, "angle": p["angle"] % 360,
                  "bottom": p["layerId"] == 2, "fp": geo["title"], "cid": cid, "pads": {},
                  "nets": {n: v for n, v in nets[cid].items() if v}}
            for num, pd in geo["pads"].items():
                px, py = pd["x"], -pd["y"] if pl["bottom"] else pd["y"]
                dx, dy = rot(px, py, pl["angle"])
                pa = (pl["angle"] + (-pd["angle"] if pl["bottom"] else pd["angle"])) % 360   # the mirror turns a pad's own angle round
                pad = Pad(ref, num, pl["x"] + dx, pl["y"] + dy, pd["w"], pd["h"], pd["shape"], pa, pl["nets"].get(num))
                pl["pads"][num] = pad
                self.pads.append(pad)
            x1, y1, x2, y2 = geo["bbox"]          # the drawn housing, in the board frame
            cs = []
            for px, py in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
                dx, dy = rot(px, -py if pl["bottom"] else py, pl["angle"])
                cs.append((pl["x"] + dx, pl["y"] + dy))
            pl["body"] = _bbox(cs)
            pl["body_poly"] = cs                  # the turned housing, for parts at odd angles
            self.parts[ref] = pl
        for pad in self.pads:
            pad.bb = (pad.x - pad.r, pad.y - pad.r, pad.x + pad.r, pad.y + pad.r)
        for v in self.vias:
            v["bb"] = (v["c"][0] - v["r"], v["c"][1] - v["r"], v["c"][0] + v["r"], v["c"][1] + v["r"])

    # -- connectivity
    def connectivity(self):
        """{net: {root: items}} and the list of (net A, net B, where) copper contacts."""
        parent = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            parent[find(a)] = find(b)

        items = []       # (key, net, layer or None (through), kind, data, bbox)
        for pad in self.pads:
            if pad.net:
                items.append((("pad", pad.ref, pad.num), pad.net, None, "pad", pad, pad.bb))
        for i, v in enumerate(self.vias):
            items.append((("via", i), v["net"], None, "via", v, v["bb"]))
        for i, t in enumerate(self.tracks):
            items.append((("track", i), t["net"], t["layer"], "track", t, t["bb"]))
        for i, isl in enumerate(self.islands):
            items.append((("island", i), isl.net, isl.layer, "island", isl, isl.bb))
        for key, *_ in items:
            find(key)
        contacts = []

        def touching(a, b):
            ka, na, la, ta, da, _ = a
            kb, nb, lb, tb, db, _ = b
            if la is not None and lb is not None and la != lb:
                return False
            kinds = {ta, tb}
            if kinds == {"track"}:
                return d_seg_seg(da["a"], da["b"], db["a"], db["b"]) <= (da["w"] + db["w"]) / 2 + 0.001
            if kinds == {"track", "pad"}:
                t, p = (da, db) if ta == "track" else (db, da)
                return p.d_seg(t["a"], t["b"]) <= t["w"] / 2 + 0.001
            if kinds == {"track", "via"}:
                t, v = (da, db) if ta == "track" else (db, da)
                return d_point_seg(v["c"], t["a"], t["b"]) <= t["w"] / 2 + v["r"] + 0.001
            if kinds == {"pad"}:
                return da.d_pad(db) <= 0.001
            if kinds == {"via"}:
                return math.hypot(da["c"][0] - db["c"][0], da["c"][1] - db["c"][1]) <= da["r"] + db["r"] + 0.001
            if kinds == {"pad", "via"}:
                p, v = (da, db) if ta == "pad" else (db, da)
                return p.d_circle(v["c"], v["r"]) <= 0.001
            if kinds == {"island"}:
                return False                # islands are separate pieces by construction
            if "island" in kinds:
                isl, o, tk = (da, db, tb) if ta == "island" else (db, da, ta)
                if isl.net != (o["net"] if tk != "pad" else o.net):
                    return False            # other-net copper inside a pour is checked separately
                if tk == "track":
                    return isl.contains(o["a"]) or isl.contains(o["b"])
                if tk == "via":
                    return isl.contains(o["c"])
                return False                # pads join through their spokes (below)
            return False

        order = sorted(range(len(items)), key=lambda i: items[i][5][0])     # sweep along x
        active = []
        for i in order:
            a = items[i]
            active = [j for j in active if items[j][5][2] + 0.01 >= a[5][0]]
            for j in active:
                b = items[j]
                if not _near(a[5], b[5], 0.01) or not touching(a, b):
                    continue
                if a[1] == b[1]:
                    union(a[0], b[0])
                else:
                    contacts.append((a[1], b[1], f"{a[3]} {a[0][1:]} / {b[3]} {b[0][1:]}"))
            active.append(i)
        # thermal spokes: a pad or via at the spoke's start joins the island the far end lies in
        for p0, p1, layer, net in self.spokes:
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            d = math.hypot(dx, dy) or 1
            far = (p1[0] + dx / d * 0.15, p1[1] + dy / d * 0.15)
            src = None
            for pad in self.pads:
                if pad.net == net and math.hypot(pad.x - p0[0], pad.y - p0[1]) < 0.3:
                    src = ("pad", pad.ref, pad.num)
            for i, v in enumerate(self.vias):
                if v["net"] == net and math.hypot(v["c"][0] - p0[0], v["c"][1] - p0[1]) < 0.3:
                    src = ("via", i)
            if src is None:
                continue
            for i, isl in enumerate(self.islands):
                if isl.layer == layer and isl.net == net and isl.contains(far):
                    union(src, ("island", i))
        groups = collections.defaultdict(lambda: collections.defaultdict(set))
        for key, net, *_ in items:
            groups[net][find(key)].add(key)
        return groups, contacts

    # -- clearances: the smallest gap between copper of different nets, per layer
    def clearances(self, limit):
        out = []
        tracks_by_layer = collections.defaultdict(list)
        for t in self.tracks:
            tracks_by_layer[t["layer"]].append(t)
        for layer, ts in tracks_by_layer.items():
            for i in range(len(ts)):
                for j in range(i + 1, len(ts)):
                    a, b = ts[i], ts[j]
                    if a["net"] == b["net"] or not _near(a["bb"], b["bb"], limit):
                        continue
                    d = d_seg_seg(a["a"], a["b"], b["a"], b["b"]) - (a["w"] + b["w"]) / 2
                    if d < limit:
                        out.append((d, f"track {a['net']} / track {b['net']} on layer {layer} near "
                                       f"({(a['a'][0] + a['b'][0]) / 2:.1f}, {(a['a'][1] + a['b'][1]) / 2:.1f})"))
            for t in ts:
                for p in self.pads:
                    if p.net == t["net"] or not _near(t["bb"], p.bb, limit):
                        continue
                    d = p.d_seg(t["a"], t["b"]) - t["w"] / 2
                    if d < limit:
                        out.append((d, f"track {t['net']} ({t['a'][0]:.1f}, {t['a'][1]:.1f})-({t['b'][0]:.1f}, {t['b'][1]:.1f}) "
                                       f"/ pad {p.ref}.{p.num} ({p.net}) at ({p.x:.1f}, {p.y:.1f}) on layer {layer}"))
                for v in self.vias:
                    if v["net"] == t["net"] or not _near(t["bb"], v["bb"], limit):
                        continue
                    d = d_point_seg(v["c"], t["a"], t["b"]) - t["w"] / 2 - v["r"]
                    if d < limit:
                        out.append((d, f"track {t['net']} / via {v['net']} on layer {layer} at ({v['c'][0]:.1f}, {v['c'][1]:.1f})"))
        for i in range(len(self.pads)):
            for j in range(i + 1, len(self.pads)):
                a, b = self.pads[i], self.pads[j]
                if a.net == b.net and a.net is not None:
                    continue
                if math.hypot(a.x - b.x, a.y - b.y) > a.r + b.r + limit:
                    continue
                d = a.d_pad(b)
                if d < limit:
                    out.append((d, f"pad {a.ref}.{a.num} ({a.net}) / pad {b.ref}.{b.num} ({b.net})"))
        for p in self.pads:
            for v in self.vias:
                if v["net"] == p.net or not _near(p.bb, v["bb"], limit):
                    continue
                d = p.d_circle(v["c"], v["r"])
                if d < limit:
                    out.append((d, f"pad {p.ref}.{p.num} ({p.net}) / via {v['net']} at ({v['c'][0]:.1f}, {v['c'][1]:.1f})"))
        for i in range(len(self.vias)):
            for j in range(i + 1, len(self.vias)):
                a, b = self.vias[i], self.vias[j]
                if a["net"] == b["net"]:
                    continue
                d = math.hypot(a["c"][0] - b["c"][0], a["c"][1] - b["c"][1]) - a["r"] - b["r"]
                if d < limit:
                    out.append((d, f"via {a['net']} / via {b['net']} at ({a['c'][0]:.1f}, {a['c'][1]:.1f})"))
        # other-net copper sitting inside a pour island (outside its cutouts): a short, unless the pour
        # was not rebuilt after that copper moved (EasyEDA keeps the old POURED until "rebuild copper")
        note = " (or a pour not rebuilt since this moved: rebuild all copper areas and re-export)"
        for isl in self.islands:
            for p in self.pads:
                if p.net != isl.net and isl.contains((p.x, p.y)):
                    out.append((0.0, f"pad {p.ref}.{p.num} ({p.net}) inside the {isl.net} pour on layer {isl.layer}{note}"))
            for v in self.vias:
                if v["net"] != isl.net and isl.contains(v["c"]):
                    out.append((0.0, f"via {v['net']} at ({v['c'][0]:.1f}, {v['c'][1]:.1f}) inside the {isl.net} pour "
                                     f"on layer {isl.layer}{note}"))
            for t in self.tracks:
                if t["net"] != isl.net and t["layer"] == isl.layer and (isl.contains(t["a"]) or isl.contains(t["b"])):
                    out.append((0.0, f"track {t['net']} ({t['a'][0]:.1f}, {t['a'][1]:.1f})-({t['b'][0]:.1f}, {t['b'][1]:.1f}) "
                                     f"inside the {isl.net} pour on layer {isl.layer}{note}"))
        return sorted(out)

    # -- keepouts and edges
    def keepouts(self, barrels=()):
        out = []
        for bx, by, ref in barrels:         # panel side (layer 2): non-ground copper under the metal barrel
            own = {p.net for p in self.pads if p.ref == ref}     # the jack's own tip / switch: a plug tip there is harmless
            for t in self.tracks:
                if t["layer"] != 2 or t["net"].startswith("GND"):
                    continue
                d = d_point_seg((bx, by), t["a"], t["b"]) - t["w"] / 2
                if d < BARREL_KEEPOUT:
                    out.append(f"track {t['net']} on the panel side {d:.2f} mm from {ref}'s barrel"
                               + (" (the jack's own net)" if t["net"] in own else
                                  " (ANOTHER NET INSIDE THONK'S 3 MM PLUG-TIP AREA)" if d < THONK_TIP_R else ""))
            for v in self.vias:
                d = math.hypot(v["c"][0] - bx, v["c"][1] - by) - v["r"]
                if d < BARREL_KEEPOUT and not v["net"].startswith("GND"):
                    out.append(f"via {v['net']} {d:.2f} mm from {ref}'s barrel")
            for p in self.pads:
                if p.ref != ref and p.net and not p.net.startswith("GND") and p.d_point((bx, by)) < BARREL_KEEPOUT:
                    out.append(f"pad {p.ref}.{p.num} ({p.net}) {p.d_point((bx, by)):.2f} mm from {ref}'s barrel")
        for hx, hy, hd in self.holes:
            for t in self.tracks:
                d = d_point_seg((hx, hy), t["a"], t["b"]) - t["w"] / 2
                if d < HOLE_KEEPOUT:
                    edge = d - hd / 2
                    out.append(f"track {t['net']} on layer {t['layer']} {d:.2f} mm from the centre of the hole at "
                               f"({hx:.1f}, {hy:.1f}), {edge:.2f} from its edge"
                               + (" (UNDER THE FAB'S NPTH-TO-TRACK MINIMUM)" if edge < NPTH_TRACK else ""))
            for v in self.vias:
                d = math.hypot(v["c"][0] - hx, v["c"][1] - hy) - v["r"]
                if d < HOLE_KEEPOUT:
                    out.append(f"via {v['net']} {d:.2f} mm from the centre of the hole at ({hx:.1f}, {hy:.1f})")
            for p in self.pads:
                d = p.d_point((hx, hy))
                if d < HOLE_KEEPOUT:
                    out.append(f"pad {p.ref}.{p.num} {d:.2f} mm from the centre of the hole at ({hx:.1f}, {hy:.1f})")
        x1, y1, x2, y2 = self.outline
        edge = 1e9
        for t in self.tracks:
            for px, py in (t["a"], t["b"]):
                edge = min(edge, px - x1 - t["w"] / 2, x2 - px - t["w"] / 2, py - y1 - t["w"] / 2, y2 - py - t["w"] / 2)
        for v in self.vias:
            edge = min(edge, v["c"][0] - x1 - v["r"], x2 - v["c"][0] - v["r"], v["c"][1] - y1 - v["r"], y2 - v["c"][1] - v["r"])
        return out, edge

    # -- placement on the board itself
    def body_checks(self, gap_side):
        """Bodies overlapping on one side; bodies under a standoff (the side facing the other board, gap_side)
        or a screw head (the other side)."""
        out = []
        for side in (False, True):
            bodies = [(ref, pl["body"]) for ref, pl in self.parts.items() if pl["bottom"] == side]
            for i, (ra, a) in enumerate(bodies):
                for rb, b in bodies[i + 1:]:
                    if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                        # the turned outlines, not their boxes (the same as the boxes for 0 / 90 / 180 / 270)
                        ov = sat_overlap(self.parts[ra]["body_poly"], self.parts[rb]["body_poly"])
                        if ov > 0.05:
                            out.append(f"bodies of {ra} and {rb} overlap by {ov:.2f} mm on the "
                                       f"{'bottom' if side else 'top'} side")
            what = "standoff" if (side and gap_side == "bottom") or (not side and gap_side == "top") else "screw head"
            for ref, (x1, y1, x2, y2) in bodies:
                for hx, hy, hd in self.holes:
                    cx, cy = min(max(hx, x1), x2), min(max(hy, y1), y2)
                    if math.hypot(cx - hx, cy - hy) < HOLE_KEEPOUT:
                        out.append(f"body of {ref} sits under the {what} at ({hx:.1f}, {hy:.1f})")
        return out

    # -- track ends that touch nothing
    def dangling(self):
        out = []
        for i, t in enumerate(self.tracks):
            for e in (t["a"], t["b"]):
                ok = False
                for j, o in enumerate(self.tracks):
                    if j != i and o["net"] == t["net"] and o["layer"] == t["layer"] and \
                            _inside(e, (o["bb"][0] - t["w"], o["bb"][1] - t["w"], o["bb"][2] + t["w"], o["bb"][3] + t["w"])) and \
                            d_point_seg(e, o["a"], o["b"]) <= (o["w"] + t["w"]) / 2:
                        ok = True
                        break
                ok = ok or any(p.net == t["net"] and p.d_point(e) <= t["w"] / 2 for p in self.pads
                               if _inside(e, (p.bb[0] - 1, p.bb[1] - 1, p.bb[2] + 1, p.bb[3] + 1)))
                ok = ok or any(v["net"] == t["net"] and math.hypot(e[0] - v["c"][0], e[1] - v["c"][1]) <= v["r"] + t["w"] / 2
                               for v in self.vias)
                ok = ok or any(isl.net == t["net"] and isl.layer == t["layer"] and isl.contains(e) for isl in self.islands)
                if not ok:
                    out.append((t["net"], t["layer"], e))
        return out

    # -- the latch's switching nets beside the audio
    def coupling(self, gap=COUPLE_GAP, step=0.2):
        """{(audio net, logic net, layer): mm of run within gap of each other on the same layer}."""
        runs = collections.Counter()
        audio = [t for t in self.tracks if AUDIO.match(t["net"])]
        logic = [t for t in self.tracks if FAST.match(t["net"]) or SLOW.match(t["net"])]
        for a in audio:
            for b in logic:
                if a["layer"] != b["layer"] or not _near(a["bb"], b["bb"], gap):
                    continue
                if d_seg_seg(a["a"], a["b"], b["a"], b["b"]) - (a["w"] + b["w"]) / 2 > gap:
                    continue
                L = math.hypot(a["b"][0] - a["a"][0], a["b"][1] - a["a"][1])
                n = max(1, int(L / step))
                hits = 0
                for k in range(n):
                    f = (k + 0.5) / n
                    p = (a["a"][0] + f * (a["b"][0] - a["a"][0]), a["a"][1] + f * (a["b"][1] - a["a"][1]))
                    if d_point_seg(p, b["a"], b["b"]) - (a["w"] + b["w"]) / 2 <= gap:
                        hits += 1
                runs[(a["net"], b["net"], a["layer"])] += hits * L / n
        return runs

    # -- shortest copper path between two pads of one net, along tracks and through vias
    def track_path(self, net, src, dst):
        nodes = collections.defaultdict(list)

        def edge(u, v, w):
            nodes[u].append((v, w))
            nodes[v].append((u, w))

        ts = [t for t in self.tracks if t["net"] == net]
        pads = [p for p in self.pads if p.net == net]
        vias = [(i, v) for i, v in enumerate(self.vias) if v["net"] == net]

        def pt(e, layer):
            return ("pt", round(e[0], 3), round(e[1], 3), layer)

        for i, t in enumerate(ts):
            edge(pt(t["a"], t["layer"]), pt(t["b"], t["layer"]), math.hypot(t["b"][0] - t["a"][0], t["b"][1] - t["a"][1]))
            for e in (t["a"], t["b"]):
                for p in pads:
                    if p.d_point(e) <= t["w"] / 2 + 0.001:
                        edge(pt(e, t["layer"]), ("pad", p.ref, p.num), math.hypot(e[0] - p.x, e[1] - p.y))
                for vi, v in vias:
                    dv = math.hypot(e[0] - v["c"][0], e[1] - v["c"][1])
                    if dv <= v["r"] + t["w"] / 2 + 0.001:
                        edge(pt(e, t["layer"]), ("via", vi), dv)
                for j, o in enumerate(ts):           # T-junctions: an end on another track's middle
                    if j != i and o["layer"] == t["layer"] and d_point_seg(e, o["a"], o["b"]) <= (o["w"] + t["w"]) / 2:
                        for q in (o["a"], o["b"]):
                            edge(pt(e, t["layer"]), pt(q, o["layer"]), math.hypot(q[0] - e[0], q[1] - e[1]))
        best = {src: 0.0}
        heap = [(0.0, src)]
        while heap:
            d, u = heapq.heappop(heap)
            if u == dst:
                return d
            if d > best.get(u, 1e18):
                continue
            for v, w in nodes[u]:
                if d + w < best.get(v, 1e18):
                    best[v] = d + w
                    heapq.heappush(heap, (d + w, v))
        return None

    def render(self, path, marks=(), scale=10, window=None):
        """The routed copper as EasyEDA shows it (rear view): pours pale, top tracks red, bottom tracks
        blue, pads grey, holes with their 3 mm keepout, numbered rings at marks [(x, y, label)].
        window = (x1, y1, x2, y2) crops to that part of the board."""
        from PIL import Image, ImageDraw, ImageFont
        x1, y1, x2, y2 = window or self.outline
        W, H = int((x2 - x1) * scale), int((y2 - y1) * scale)
        img = Image.new("RGB", (W + 40, H + 50), "white")
        dr = ImageDraw.Draw(img)
        try:
            font, big = ImageFont.truetype("arial.ttf", 11), ImageFont.truetype("arial.ttf", 16)
        except OSError:
            font = big = ImageFont.load_default()

        def P(x, y):
            return 20 + (x - x1) * scale, 20 + (y2 - y) * scale

        bx1, by1, bx2, by2 = self.outline
        dr.rectangle([P(bx1, by2), P(bx2, by1)], outline="#000000", width=2)
        for isl in self.islands:
            col = "#fbe3e3" if isl.layer == 1 else "#e3e9fb"
            dr.polygon([P(*q) for q in isl.outline], fill=col)
            for hole in isl.holes:
                dr.polygon([P(*q) for q in hole], fill="#ffffff")
        for layer, col in ((2, "#3a6fd0"), (1, "#d03a3a")):
            for t in self.tracks:
                if t["layer"] == layer:
                    w = max(1, int(t["w"] * scale))
                    dr.line([P(*t["a"]), P(*t["b"])], fill=col, width=w)
                    for q in (t["a"], t["b"]):
                        X, Y = P(*q)
                        dr.ellipse([X - w / 2, Y - w / 2, X + w / 2, Y + w / 2], fill=col)
        for p in self.pads:
            X, Y = P(p.x, p.y)
            r = max(p.w, p.h) / 2 * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], fill="#b0b0b0" if p.net else "#e0e0e0", outline="#606060")
        for v in self.vias:
            X, Y = P(*v["c"])
            r = v["r"] * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], fill="#606060")
        for ref, pl in self.parts.items():
            X, Y = P(pl["body"][0], pl["body"][3])
            dr.text((X + 1, Y + 1), ref, fill="#707070", font=font)
        for hx, hy, hd in self.holes:
            X, Y = P(hx, hy)
            for r, w in ((hd / 2, 2), (HOLE_KEEPOUT, 1)):
                dr.ellipse([X - r * scale, Y - r * scale, X + r * scale, Y + r * scale], outline="#000000", width=w)
        for mx, my, label in marks:
            X, Y = P(mx, my)
            r = 2.2 * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], outline="#e000e0", width=3)
            dr.text((X + r + 2, Y - r - 4), str(label), fill="#e000e0", font=big)
        dr.text((20, H + 26), f"{self.title}, rear view: red top, blue bottom, pale = pour, grey = pads, "
                              f"circles = holes and their 3 mm keepout", fill="#000000", font=font)
        img.save(path)

    def net_stats(self):
        st = {}
        for net in {t["net"] for t in self.tracks} | {v["net"] for v in self.vias}:
            ts = [t for t in self.tracks if t["net"] == net]
            st[net] = {"length": sum(math.hypot(t["b"][0] - t["a"][0], t["b"][1] - t["a"][1]) for t in ts),
                       "vias": sum(1 for v in self.vias if v["net"] == net),
                       "layers": sorted({t["layer"] for t in ts})}
        return st


# ------------------------------------------------------------------ against the generator
def generated_boards():
    """The generator's two boards (pcb.Board) and the exporter module."""
    ex = _load("easyeda_export")
    pr = ex.MProject()
    mb, fb = ex.circuit.main_board_parts(), ex.circuit.faceplate_parts()
    PM, PF = {p.ref: p for p in mb}, {p.ref: p for p in fb}
    main_pages = [page(pr, PM) for page in ex.MAIN_PAGES]
    fp_pages = [ex.faceplate_jacks_page(pr, PF), ex.faceplate_controls_page(pr, PF)]
    return (ex.pcb.faceplate_board(pr, fb, ex.part_info(fp_pages), ex.circuit),
            ex.pcb.main_board(pr, mb, ex.part_info(main_pages), ex.circuit), ex)


def compare(routed, gen):
    """The routed board against the generated one: missing parts, moved parts, other footprints, other nets."""
    bad, moved = [], []
    mine = {pl["ref"]: pl for pl in gen.placed}
    for ref in sorted(set(routed.parts) ^ set(mine)):
        bad.append(f"{ref} only on the {'routed' if ref in routed.parts else 'generated'} board")
    for ref in sorted(set(routed.parts) & set(mine)):
        rp, g = routed.parts[ref], mine[ref]
        if rp["fp"] != g["geo"]["title"]:
            bad.append(f"{ref}: footprint {rp['fp']} on the routed board, {g['geo']['title']} generated")
        gp = gen.pads(g)
        off = max((math.hypot(rp["pads"][n].x - gp[n][0], rp["pads"][n].y - gp[n][1]) for n in gp if n in rp["pads"]),
                  default=0)
        if off > 0.01 or rp["bottom"] != g["bottom"]:
            moved.append((ref, g["x"], g["y"], g["angle"], g["bottom"], rp["x"], rp["y"], rp["angle"], rp["bottom"], off))
        nets = gen.P[ref].nets
        for num in sorted(set(nets) | set(rp["nets"])):
            if nets.get(num) != rp["nets"].get(num):
                bad.append(f"{ref}.{num}: net {rp['nets'].get(num)} routed, {nets.get(num)} in circuit.py")
    return bad, moved


def boards_of(docs, fps):
    out = {}
    for u, d in docs.items():
        if d["docType"] == "PCB":
            title = next(p["title"] for h, p in d["recs"] if h["type"] == "META")
            out[title] = d if "Panel" in title else RoutedBoard(title, d, fps)
    return out


def footprints_of(docs):
    pcbmod = _load("pcb")
    fps = {u: dict(pcbmod.footprint_geometry(d), title=next(p["title"] for h, p in d["recs"] if h["type"] == "META"))
           for u, d in docs.items() if d["docType"] == "FOOTPRINT"}
    for u, d in docs.items():            # pad shapes, which footprint_geometry does not keep
        if d["docType"] == "FOOTPRINT":
            for h, p in d["recs"]:
                if h["type"] == "PAD":
                    fps[u]["pads"][str(p["num"])]["shape"] = p["defaultPad"]["padType"]
    return fps


DECOUPLING = ([(f"C{911 + 2 * i}", u, "+12V", "4") for i, u in enumerate(("U1", "U2", "U3", "U4"))] +
              [(f"C{912 + 2 * i}", u, "-12V", "11") for i, u in enumerate(("U1", "U2", "U3", "U4"))] +
              [(f"C{921 + i}", u, "+12V", "14") for i, u in enumerate(("U5", "U6", "U7", "U8", "U9", "U10"))])


def audit_board(b, gen, circuit, marks):
    print(f"\n=== {b.title}: {len(b.parts)} parts, {len(b.tracks)} tracks, {len(b.vias)} vias, "
          f"{len(b.islands)} pour islands, {len(b.holes)} holes")
    widths = collections.Counter(round(t["w"], 3) for t in b.tracks)
    vias = collections.Counter((round(v["drill"], 3), round(2 * v["r"], 3)) for v in b.vias)
    print("track widths (mm: count):", dict(sorted(widths.items())), " vias (drill, pad: count):", dict(vias))
    for net in ("+12V", "-12V", "GND"):
        ws = sorted({round(t["w"], 3) for t in b.tracks if t["net"] == net})
        print(f"    {net} tracks: widths {ws}, vias {sum(1 for v in b.vias if v['net'] == net)}")
    diffs, moved = compare(b, gen)
    print(f"-- against the generator: {len(diffs)} differences, {len(moved)} parts moved")
    for d in diffs:
        print("   ", d)
    for ref, gx, gy, ga, gb, rx, ry, ra, rb, off in moved:
        print(f"    {ref:6} ({gx:6.2f}, {gy:6.2f}) {ga:3.0f}{' bottom' if gb else ''} -> ({rx:6.2f}, {ry:6.2f}) "
              f"{ra:3.0f}{' bottom' if rb else ''}, pads up to {off:.2f} mm away")
    front = [ref for ref, pl in b.parts.items() if pl["bottom"] and not re.match(r"^H\d+$", ref)]
    if "Main" in b.title and front:
        print("    ON THE MAIN BOARD'S FRONT (only sockets belong there):", front)
    bodies = b.body_checks("bottom" if "Main" in b.title else "top")
    print(f"-- bodies: {len(bodies)} overlaps or standoff / screw-head clashes")
    for k in bodies:
        print("   ", k)
    groups, contacts = b.connectivity()
    pads_by_net = collections.Counter(p.net for p in b.pads if p.net)
    unrouted = sorted(n for n, c in pads_by_net.items() if c > 1 and n not in groups)
    split = {net: len(g) for net, g in groups.items() if len(g) > 1}
    print(f"-- connectivity: {len(groups)} nets with copper, {len(split)} split, {len(unrouted)} with no copper at all, "
          f"{len(contacts)} other-net contacts")
    for net in unrouted:
        print(f"    {net}: not routed")
    for net, n in sorted(split.items()):
        parts = sorted(groups[net].values(), key=len)
        for piece in parts[:-1]:
            keys = [k for k in piece if k[0] in ("pad", "via")]
            print(f"    {net}: a piece of {len(piece)} items cut off from the rest: {sorted(keys)[:6] or sorted(piece)[:3]}")
            loc = next((k for k in piece if k[0] == "pad"), None)
            if loc:
                p = b.parts[loc[1]]["pads"][loc[2]]
                marks.append((p.x, p.y, f"{net} open"))
            else:
                k = next(iter(piece))
                if k[0] == "via":
                    marks.append((*b.vias[k[1]]["c"], f"{net} open"))
                elif k[0] == "track":
                    marks.append((*b.tracks[k[1]]["a"], f"{net} open"))
    for a, bnet, where in contacts:
        print(f"    SHORT {a} - {bnet}: {where}")
    clear = b.clearances(0.25)
    under = [c for c in clear if c[0] < CLEARANCE - 0.0005]       # exactly on the rule passes
    fab = [c for c in clear if c[0] < FAB_SPACING]
    print(f"-- clearance: {len(under)} gaps under {CLEARANCE} mm ({len(fab)} under the fab's {FAB_SPACING}), "
          f"{len(clear) - len(under)} between {CLEARANCE} and 0.25 mm")
    for d, where in clear[:25]:
        print(f"    {d:.3f}  {where}")
    barrels = []
    if "Faceplate" in b.title:
        for ref, *_ in circuit.JACKS:
            pl = b.parts[ref]
            s, t = pl["pads"]["1"], pl["pads"]["3"]      # sleeve and tip: the barrel is 6.48 mm from the sleeve
            d = math.hypot(t.x - s.x, t.y - s.y)
            barrels.append((s.x + (t.x - s.x) / d * 6.48, s.y + (t.y - s.y) / d * 6.48, ref))
        for bx, by, ref in barrels:                     # the pour under the plug tip
            under = [isl for isl in b.islands if isl.layer == 2 and isl.contains((bx, by))]
            if under:
                print(f"    {ref}: the {under[0].net} pour covers the plug-tip spot on the panel side")
    ko, edge = b.keepouts(barrels)
    print(f"-- keepouts: {len(ko)} items within {HOLE_KEEPOUT} mm of a mounting hole"
          + (f" or {BARREL_KEEPOUT} mm of a jack barrel" if barrels else "") + f"; copper {edge:.2f} mm from the edge")
    for k in ko[:30]:
        print("   ", k)
    dang = b.dangling()
    print(f"-- track ends touching nothing: {len(dang)}")
    for net, layer, e in dang:
        print(f"    {net} on layer {layer} at ({e[0]:.2f}, {e[1]:.2f})")
        marks.append((e[0], e[1], f"{net} end"))
    by_layer = collections.defaultdict(list)
    for isl in b.islands:
        by_layer[isl.layer].append(isl)
    for layer, isls in sorted(by_layer.items()):
        print(f"-- pour on layer {layer}: {len(isls)} islands, areas (mm2) {sorted(round(i.area, 1) for i in isls)}")
    st = b.net_stats()
    print("-- the summing nodes (virtual ground, high impedance): mm of track / vias / layers")
    for n in sorted(st):
        if HIGH_Z.match(n):
            print(f"    {n:8} {st[n]['length']:6.1f}  {st[n]['vias']}  {st[n]['layers']}")
    runs = b.coupling()
    big = sorted(((v, k) for k, v in runs.items() if v >= COUPLE_REPORT), reverse=True)
    print(f"-- latch nets running beside audio nets on one layer (within {COUPLE_GAP} mm, {COUPLE_REPORT} mm or more): "
          f"{len(big)} pairs")
    for v, (an, ln, layer) in big[:30]:
        kind = "fast" if FAST.match(ln) else "slow"
        print(f"    {v:5.1f} mm  {an:7} beside {ln:6} ({kind}) on layer {layer}"
              + ("  <- summing node" if HIGH_Z.match(an) else ""))
    print("-- each 100 n's track path to its chip's supply pin (straight distance in brackets)")
    for cref, u, net, pin in DECOUPLING:
        if cref not in b.parts or u not in b.parts:
            continue
        cp = next((n for n, v in b.parts[cref]["nets"].items() if v == net), None)
        a, z = b.parts[cref]["pads"][cp], b.parts[u]["pads"][pin]
        L = b.track_path(net, ("pad", cref, cp), ("pad", u, pin))
        gnd = next(n for n, v in b.parts[cref]["nets"].items() if v == "GND")
        g = b.parts[cref]["pads"][gnd]
        spokes = sum(1 for p0, p1, layer, n in b.spokes if n == "GND" and math.hypot(p0[0] - g.x, p0[1] - g.y) < 0.3)
        gv = min((math.hypot(v["c"][0] - g.x, v["c"][1] - g.y) for v in b.vias if v["net"] == "GND"), default=0)
        print(f"    {cref} -> {u}.{pin} ({net}): {'no track path' if L is None else f'{L:5.1f} mm'} "
              f"({math.hypot(a.x - z.x, a.y - z.y):4.1f}); its GND pad has {spokes} spokes, nearest GND via {gv:.1f} mm")
    watch = [n for n in st if not n.startswith(("GND", "+12", "-12"))]
    print("-- net lengths (mm) / vias / layers:")
    for n in sorted(watch):
        s = st[n]
        print(f"    {n:14} {s['length']:6.1f}  {s['vias']}  {s['layers']}")
    return diffs, moved, split, unrouted, contacts, under, ko, dang, bodies


def main(path, png=None):
    docs = read_export(path)
    fps = footprints_of(docs)
    boards = boards_of(docs, fps)
    fb_gen, mb_gen, ex = generated_boards()
    circuit = ex.circuit
    problems = collections.OrderedDict()
    for title, b in boards.items():
        if "Panel" in title:
            continue
        if not b.tracks:
            print(f"\n=== {title}: not routed ({len(b.parts)} parts, no tracks); skipped")
            continue
        marks = []
        problems[title] = audit_board(b, fb_gen if "Faceplate" in title else mb_gen, circuit, marks)
        if png:
            b.render(png if len(boards) == 1 else png.replace(".png", f"-{title.split()[1].lower()}.png"), marks)
    # headers: the faceplate's male pins over the main board's sockets
    fbr = next((b for t, b in boards.items() if "Faceplate" in t), None)
    mbr = next((b for t, b in boards.items() if "Main" in t), None)
    if mbr is not None:
        if fbr is not None:
            fpads, src = {ref: {n: (p.x, p.y) for n, p in pl["pads"].items()} for ref, pl in fbr.parts.items()}, "the export's faceplate"
            fholes = fbr.holes
        else:
            fpads = {pl["ref"]: {n: (x, y) for n, (x, y, r) in fb_gen.pads(pl).items()} for pl in fb_gen.placed}
            src, fholes = "the generator's faceplate", fb_gen.holes
        hdr = []
        for ref, kind, pins in circuit.HEADERS:
            a, m = fpads[circuit.fb_ref(ref)], mbr.parts[ref]["pads"]
            for num in a:
                if math.hypot(a[num][0] - m[num].x, a[num][1] - m[num].y) > 0.01:
                    hdr.append(f"{ref}.{num}: faceplate ({a[num][0]:.2f}, {a[num][1]:.2f}), main board ({m[num].x:.2f}, {m[num].y:.2f})")
        print(f"\n=== headers against {src}: {len(hdr)} pins out of line")
        for h in hdr:
            print("   ", h)
        key = lambda hs: sorted(tuple(round(v, 2) for v in h) for h in hs)
        print("    mounting holes", "identical on both boards" if key(fholes) == key(mbr.holes) else
              f"DIFFER: faceplate {key(fholes)}, main board {key(mbr.holes)}")
    # the panel board's holes against panel_pcb.py
    panel = next((d for t, d in boards.items() if "Panel" in t), None)
    if panel is not None:
        pp = _load("panel_pcb").PanelBoard()
        want = sorted((round(x, 2), round(y, 2), round(d, 2)) for x, y, d in pp.holes)
        got = sorted((round(p["path"][0][1] * MIL, 2), round(p["path"][0][2] * MIL, 2), round(2 * p["path"][0][3] * MIL, 2))
                     for h, p in panel["recs"] if h["type"] == "FILL" and p["layerId"] == 12 and p["path"][0][0] == "CIRCLE")
        print(f"\n=== panel: {len(got)} round holes in the export, {len(want)} generated; "
              f"{'identical' if got == want else 'DIFFERENT'}")
        for a, b in zip(got, want):
            if a != b:
                print("   ", a, "vs", b)
        # the mounting slots: milled regions, compared by their bounding boxes
        want = sorted((round(x - w / 2, 2), round(y - h / 2, 2), round(x + w / 2, 2), round(y + h / 2, 2))
                      for x, y, w, h in pp.slots)
        got = []
        for h, p in panel["recs"]:
            if h["type"] == "FILL" and p["layerId"] == 12 and p["path"][0][0] != "CIRCLE":
                pts = flatten_path(p["path"][0] if isinstance(p["path"][0], list) else p["path"], MIL)
                got.append(tuple(round(v, 2) for v in _bbox(pts)))
        got.sort()
        print(f"    {len(got)} slots in the export, {len(want)} generated; {'identical' if got == want else 'DIFFERENT'}")
        for a, b in zip(got, want):
            if a != b:
                print("   ", a, "vs", b)
    return problems


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "easyeda", "StereoMixer-routed.epro2"),
         sys.argv[2] if len(sys.argv) > 2 else None)
