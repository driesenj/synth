"""Audit a routed EasyEDA Pro export of the Plaitsy boards.

Reads an .epro2 the user exported after routing and checks, per PCB:
  netlist      every pad's net against circuit.py (swaps made while routing show up here)
  placement    every pad against the generator's boards (parts moved while routing)
  copper       tracks (LINE), vias, pads and the computed pours (POURED) joined
               into one graph per net: nets split into islands, nets shorted
               together, the smallest gap between copper of different nets,
               copper inside a mounting hole's keepout or a jack barrel
  headers      the faceplate's male pins over the main board's sockets
  panel        the panel board's holes against panel_pcb.py
  footprints   the pot and DIP-14 footprints are the corrected ones
and prints per-net track length, via count and layers for the nets that
matter (summing nodes, ADC lines, SPI, probe, audio).

Run from plaits/hardware/tools:  python copper_audit.py <export.epro2>
Geometry is approximate where it has to be (pads as rotated rectangles or
stadiums, arcs flattened); anything it reports under the rule's clearance
deserves a look in EasyEDA, not an automatic verdict.
"""
import collections
import importlib.util
import json
import math
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MIL = 0.0254
TEN_MIL = 0.254
CLEARANCE = 0.152       # the rule the user's boards carry (1 oz default)
HOLE_KEEPOUT = 3.0      # standoff / screw head around a mounting hole
BARREL_KEEPOUT = 3.0    # the Thonkiconn's metal barrel, panel side


def _load(name):
    spec = importlib.util.spec_from_file_location("plaits_" + name, os.path.join(HERE, name + ".py"))
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
                a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y - cy, x - cx)
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


class Island:
    def __init__(self, outline, holes, layer, net):
        self.outline, self.holes, self.layer, self.net = outline, holes, layer, net

    def contains(self, p):
        return point_in_poly(p, self.outline) and not any(point_in_poly(p, h) for h in self.holes)


class Pad:
    """A through-hole pad: rectangle or stadium in the board frame."""

    def __init__(self, ref, num, x, y, w, h, shape, angle, net):
        self.ref, self.num, self.x, self.y, self.w, self.h, self.shape, self.angle, self.net = \
            ref, num, x, y, w, h, shape, angle, net
        self.r = max(w, h) / 2

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
                self.tracks.append({"a": (p["startX"] * MIL, p["startY"] * MIL), "b": (p["endX"] * MIL, p["endY"] * MIL),
                                    "w": p["width"] * MIL, "layer": p["layerId"], "net": p["netName"]})
            elif t == "VIA":
                self.vias.append({"c": (p["centerX"] * MIL, p["centerY"] * MIL), "r": p["viaDiameter"] * MIL / 2,
                                  "net": p["netName"]})
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
            pl = {"x": p["x"] * MIL, "y": p["y"] * MIL, "angle": p["angle"] % 360, "bottom": p["layerId"] == 2,
                  "fp": geo["title"], "pads": {}, "nets": {n: v for n, v in nets[cid].items() if v}}
            for num, pd in geo["pads"].items():
                px, py = pd["x"], -pd["y"] if pl["bottom"] else pd["y"]
                dx, dy = rot(px, py, pl["angle"])
                pad = Pad(ref, num, pl["x"] + dx, pl["y"] + dy, pd["w"], pd["h"], pd["shape"], pl["angle"], pl["nets"].get(num))
                pl["pads"][num] = pad
                self.pads.append(pad)
            self.parts[ref] = pl

    # -- connectivity
    def connectivity(self):
        """{net: number of copper islands}, plus the list of (net A, net B, where) copper contacts."""
        parent = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            parent[find(a)] = find(b)

        items = []       # (key, net, layer or None (through), kind, data)
        for pad in self.pads:
            if pad.net:
                items.append((("pad", pad.ref, pad.num), pad.net, None, "pad", pad))
        for i, v in enumerate(self.vias):
            items.append((("via", i), v["net"], None, "via", v))
        for i, t in enumerate(self.tracks):
            items.append((("track", i), t["net"], t["layer"], "track", t))
        for i, isl in enumerate(self.islands):
            items.append((("island", i), isl.net, isl.layer, "island", isl))
        for key, *_ in items:
            find(key)
        contacts = []

        def touching(a, b):
            ka, na, la, ta, da = a
            kb, nb, lb, tb, db = b
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

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if touching(a, b):
                    if a[1] == b[1]:
                        union(a[0], b[0])
                    else:
                        contacts.append((a[1], b[1], f"{a[3]} {a[0][1:]} / {b[3]} {b[0][1:]}"))
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
                    if a["net"] == b["net"]:
                        continue
                    d = d_seg_seg(a["a"], a["b"], b["a"], b["b"]) - (a["w"] + b["w"]) / 2
                    if d < limit:
                        out.append((d, f"track {a['net']} / track {b['net']} on layer {layer} near "
                                       f"({(a['a'][0] + a['b'][0]) / 2:.1f}, {(a['a'][1] + a['b'][1]) / 2:.1f})"))
            for t in ts:
                for p in self.pads:
                    if p.net == t["net"]:
                        continue
                    d = p.d_seg(t["a"], t["b"]) - t["w"] / 2
                    if d < limit:
                        out.append((d, f"track {t['net']} ({t['a'][0]:.1f}, {t['a'][1]:.1f})-({t['b'][0]:.1f}, {t['b'][1]:.1f}) "
                                       f"/ pad {p.ref}.{p.num} ({p.net}) at ({p.x:.1f}, {p.y:.1f}) on layer {layer}"))
                for v in self.vias:
                    if v["net"] == t["net"]:
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
                if v["net"] == p.net:
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
        for hx, hy, hd in self.holes:
            for t in self.tracks:
                d = d_point_seg((hx, hy), t["a"], t["b"]) - t["w"] / 2
                if d < HOLE_KEEPOUT:
                    out.append(f"track {t['net']} on layer {t['layer']} {d:.2f} mm from the hole at ({hx:.1f}, {hy:.1f})")
            for v in self.vias:
                d = math.hypot(v["c"][0] - hx, v["c"][1] - hy) - v["r"]
                if d < HOLE_KEEPOUT:
                    out.append(f"via {v['net']} {d:.2f} mm from the hole at ({hx:.1f}, {hy:.1f})")
            for p in self.pads:
                d = p.d_point((hx, hy))
                if d < HOLE_KEEPOUT:
                    out.append(f"pad {p.ref}.{p.num} {d:.2f} mm from the hole at ({hx:.1f}, {hy:.1f})")
        for bx, by, ref in barrels:         # panel side (layer 2): non-ground copper under the metal barrel
            for t in self.tracks:
                if t["layer"] != 2 or t["net"].startswith("GND"):
                    continue
                d = d_point_seg((bx, by), t["a"], t["b"]) - t["w"] / 2
                if d < BARREL_KEEPOUT:
                    out.append(f"track {t['net']} on the panel side {d:.2f} mm from {ref}'s barrel")
            for v in self.vias:
                d = math.hypot(v["c"][0] - bx, v["c"][1] - by) - v["r"]
                if d < BARREL_KEEPOUT and not v["net"].startswith("GND"):
                    out.append(f"via {v['net']} {d:.2f} mm from {ref}'s barrel")
            for p in self.pads:
                if p.ref != ref and p.net and not p.net.startswith("GND") and p.d_point((bx, by)) < BARREL_KEEPOUT:
                    out.append(f"pad {p.ref}.{p.num} ({p.net}) {p.d_point((bx, by)):.2f} mm from {ref}'s barrel")
        x1, y1, x2, y2 = self.outline
        edge = 1e9
        for t in self.tracks:
            for px, py in (t["a"], t["b"]):
                edge = min(edge, px - x1 - t["w"] / 2, x2 - px - t["w"] / 2, py - y1 - t["w"] / 2, y2 - py - t["w"] / 2)
        for v in self.vias:
            edge = min(edge, v["c"][0] - x1 - v["r"], x2 - v["c"][0] - v["r"], v["c"][1] - y1 - v["r"], y2 - v["c"][1] - v["r"])
        return out, edge

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
    """The generator's two boards (pcb.Board) and the circuit module."""
    ex = _load("easyeda_export")
    pr = ex.MProject()
    mb, fb = ex.circuit.main_board_parts(), ex.circuit.faceplate_parts()
    pages = [ex.main_page(pr, mb), ex.faceplate_page(pr, fb)]
    info = ex.part_info(pages)
    return ex.pcb.faceplate_board(pr, fb, info, ex.circuit), ex.pcb.main_board(pr, mb, info, ex.circuit), ex


def compare(routed, gen):
    """Pads of the routed board against the generated one: missing parts, moved pads, other nets."""
    bad = []
    mine = {pl["ref"]: pl for pl in gen.placed}
    for ref in sorted(set(routed.parts) ^ set(mine)):
        bad.append(f"{ref} only on the {'routed' if ref in routed.parts else 'generated'} board")
    for ref in sorted(set(routed.parts) & set(mine)):
        rp, gp = routed.parts[ref], gen.pads(mine[ref])
        if rp["fp"] != mine[ref]["geo"]["title"]:
            bad.append(f"{ref}: footprint {rp['fp']} on the routed board, {mine[ref]['geo']['title']} generated")
        for num in sorted(set(rp["pads"]) | set(gp)):
            if num not in rp["pads"] or num not in gp:
                continue
            a, b = rp["pads"][num], gp[num]
            if math.hypot(a.x - b[0], a.y - b[1]) > 0.01:
                bad.append(f"{ref}.{num} at ({a.x:.2f}, {a.y:.2f}) routed, ({b[0]:.2f}, {b[1]:.2f}) generated")
        nets = gen.P[ref].nets
        for num in sorted(set(nets) | set(rp["nets"])):
            if nets.get(num) != rp["nets"].get(num):
                bad.append(f"{ref}.{num}: net {rp['nets'].get(num)} routed, {nets.get(num)} in circuit.py")
    return bad


def main(path):
    docs = read_export(path)
    pcbmod = _load("pcb")
    fps = {u: dict(pcbmod.footprint_geometry(d), title=next(p["title"] for h, p in d["recs"] if h["type"] == "META"))
           for u, d in docs.items() if d["docType"] == "FOOTPRINT"}
    for u, d in docs.items():            # pad shapes, which footprint_geometry does not keep
        if d["docType"] == "FOOTPRINT":
            for h, p in d["recs"]:
                if h["type"] == "PAD":
                    fps[u]["pads"][str(p["num"])]["shape"] = p["defaultPad"]["padType"]
    boards = {}
    for u, d in docs.items():
        if d["docType"] == "PCB":
            title = next(p["title"] for h, p in d["recs"] if h["type"] == "META")
            if "Panel" in title:
                boards["panel"] = d
            else:
                boards[title] = RoutedBoard(title, d, fps)
    fb_gen, mb_gen, ex = generated_boards()
    circuit = ex.circuit
    problems = collections.OrderedDict()
    for title, b in boards.items():
        if title == "panel":
            continue
        gen = fb_gen if "Faceplate" in title else mb_gen
        print(f"\n=== {title}: {len(b.parts)} parts, {len(b.tracks)} tracks, {len(b.vias)} vias, "
              f"{len(b.islands)} pour islands, {len(b.holes)} holes")
        print("footprints:", sorted({pl['fp'] for pl in b.parts.values()}))
        diffs = compare(b, gen)
        print(f"-- against the generator: {len(diffs)} differences")
        for d in diffs:
            print("   ", d)
        groups, contacts = b.connectivity()
        split = {net: len(g) for net, g in groups.items() if len(g) > 1}
        print(f"-- connectivity: {len(groups)} nets, {len(split)} split, {len(contacts)} other-net contacts")
        for net, n in sorted(split.items()):
            parts = sorted(groups[net].values(), key=len)
            small = [k for k in parts[0] if k[0] in ("pad", "via")][:4]
            print(f"    {net} in {n} pieces; smallest piece: {small or sorted(parts[0])[:3]}")
        for a, bnet, where in contacts:
            print(f"    SHORT {a} - {bnet}: {where}")
        clear = b.clearances(0.25)
        under = [c for c in clear if c[0] < CLEARANCE]
        print(f"-- clearance: {len(under)} gaps under {CLEARANCE} mm, {len(clear) - len(under)} between {CLEARANCE} and 0.25 mm")
        for d, where in clear[:25]:
            print(f"    {d:.3f}  {where}")
        barrels = []
        if "Faceplate" in title:
            for ref, *_ in circuit.JACKS:
                pl = b.parts[ref]
                s, t = pl["pads"]["1"], pl["pads"]["3"]      # sleeve and tip: the barrel is 6.48 mm from the sleeve
                d = math.hypot(t.x - s.x, t.y - s.y)
                barrels.append((s.x + (t.x - s.x) / d * 6.48, s.y + (t.y - s.y) / d * 6.48, ref))
        ko, edge = b.keepouts(barrels)
        print(f"-- keepouts: {len(ko)} items near a mounting hole or barrel; copper {edge:.2f} mm from the edge")
        for k in ko[:30]:
            print("   ", k)
        st = b.net_stats()
        watch = [n for n in st if n.startswith(("IN_", "ADC_", "SPI", "SCK", "MOSI", "LED_LATCH", "PROBE", "OUT", "AUX",
                                                "BIAS", "MUX"))]
        print("-- net lengths (mm) / vias / layers:")
        for n in sorted(watch):
            s = st[n]
            print(f"    {n:14} {s['length']:6.1f}  {s['vias']}  {s['layers']}")
        problems[title] = (diffs, split, contacts, under, ko)
    # headers: faceplate male pins over the main board's sockets
    fbr = next(b for t, b in boards.items() if t != "panel" and "Faceplate" in t)
    mbr = next(b for t, b in boards.items() if t != "panel" and "Main" in t)
    hdr = []
    for ref, kind, pins in circuit.HEADERS:
        a, m = fbr.parts[circuit.fb_ref(ref)]["pads"], mbr.parts[ref]["pads"]
        for num in a:
            if math.hypot(a[num].x - m[num].x, a[num].y - m[num].y) > 0.01:
                hdr.append(f"{ref}.{num}: faceplate ({a[num].x:.2f}, {a[num].y:.2f}), main board ({m[num].x:.2f}, {m[num].y:.2f})")
            if a[num].net != (m[num].net if m[num].net in ("GND",) else m[num].net):
                pass
    print(f"\n=== headers: {len(hdr)} pins out of line")
    for h in hdr:
        print("   ", h)
    if sorted(map(lambda h: tuple(round(v, 2) for v in h), fbr.holes)) != sorted(map(lambda h: tuple(round(v, 2) for v in h), mbr.holes)):
        print("    mounting holes differ between the boards")
    # the panel board's holes against panel_pcb.py
    pp = _load("panel_pcb").PanelBoard()
    want = sorted((round(x, 2), round(y, 2), round(d, 2)) for x, y, d in pp.holes)
    got = []
    for h, p in boards["panel"]["recs"]:
        if h["type"] == "FILL" and p["layerId"] == 12 and p["path"][0][0] == "CIRCLE":
            _, x, y, r = p["path"][0]
            got.append((round(x * MIL, 2), round(y * MIL, 2), round(2 * r * MIL, 2)))
    got.sort()
    print(f"\n=== panel: {len(got)} round holes in the export, {len(want)} generated; "
          f"{'identical' if got == want else 'DIFFERENT'}")
    if got != want:
        for a, b in zip(got, want):
            if a != b:
                print("   ", a, "vs", b)
    return problems


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "easyeda", "Plaitsy-routed.epro2"))
