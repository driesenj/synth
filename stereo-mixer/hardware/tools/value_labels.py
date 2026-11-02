"""Add silkscreen value labels to a routed stereo mixer export (copied from side-fx/): every resistor
and capacitor gets its value (100k, 22p, 10u, ...), every diode its part name (1N5819, 1N4148) and
every pot its taper and value (A100k, B10k: the PAN pots are the odd ones out) as a STRING on the
silk layer of its own side, in the first free spot beside it.

Free means: not over any pad, not over another part's housing on that side,
not over a designator, title or earlier label, not over a mounting hole,
inside the board by 0.5 mm. Spots are tried right, left, above, below, then the
corners, first at the designator's size (45 mil) and then smaller. A spot
must read as its own part's: no other labelled part nearer to it, or at
most a near-tie within NEAR; a part without such a spot gets no label.
The patched project keeps every existing record byte for byte; the labels
are appended to each PCB document.

Run from stereo-mixer/hardware/tools:
  python value_labels.py <export.epro2> <patched.epro2>
Also writes stereo-mixer-labels-<board>-<side>.png previews next to the patched file.
"""
import importlib.util
import json
import math
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MIL = 0.0254
CHAR_W = 0.62        # advance per character as a fraction of the font size, default stroke font
SIZES = (45, 38, 32)     # mil; the designators are 45, 32 mil (0.81 mm) is the fab's smallest readable silk
GAP = 0.35               # mm between a label and whatever it sits beside
STEPS = (0, 1.3, 2.6)    # further out from the part when the first ring is taken
EDGE = 0.5
NEAR = 1.0               # mm: a label nearer another labelled part than its own still counts as its own this close
REACH = 20.0             # mm: how far from its parts a legend line may sit
CLUSTER = 10.0           # mm: parts of one value closer than this share a legend line


def _load(name):
    spec = importlib.util.spec_from_file_location("mixer_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ca = _load("copper_audit")
circuit = _load("circuit")


LABELLED = ("R", "C", "CP", "D5819", "D4148", "POT", "POT2")


def values():
    """PCB title word -> {ref: label text} for the resistors, capacitors, diodes and pots, per board."""
    return {board: {p.ref: p.value for p in parts if p.kind in LABELLED}
            for board, parts in (("Main", circuit.main_board_parts()), ("Faceplate", circuit.faceplate_parts()))}


def text_box(x, y, s, size_mil, mirror):
    """Box of a LEFT_BOTTOM string at (x, y) mm; a mirrored one runs to the left of its origin."""
    w, h = CHAR_W * size_mil * MIL * len(s), size_mil * MIL
    return (x - w, y, x, y + h) if mirror else (x, y, x + w, y + h)


def overlaps(a, b, margin=0.0):
    return a[0] < b[2] + margin and b[0] < a[2] + margin and a[1] < b[3] + margin and b[1] < a[3] + margin


def circle_hits(rect, c, r):
    cx = min(max(c[0], rect[0]), rect[2])
    cy = min(max(c[1], rect[1]), rect[3])
    return (cx - c[0]) ** 2 + (cy - c[1]) ** 2 < r * r


def extent(pl):
    """A part's housing box grown to cover its own pads."""
    x1, y1, x2, y2 = pl["body"]
    for pad in pl["pads"].values():
        x1, y1 = min(x1, pad.x - pad.r), min(y1, pad.y - pad.r)
        x2, y2 = max(x2, pad.x + pad.r), max(y2, pad.y + pad.r)
    return x1, y1, x2, y2


def rect_dist(a, b):
    return math.hypot(max(b[0] - a[2], a[0] - b[2], 0), max(b[1] - a[3], a[1] - b[3], 0))


class Labeller:
    def __init__(self, board, doc, labelled=()):
        self.b = board
        self.labelled = set(labelled)          # parts that get a label: a label must not sit nearer another of them
        self.texts = {True: [], False: []}      # existing text boxes per side (bottom: True)
        for h, p in doc["recs"]:
            if h["type"] == "ATTR" and p.get("key") == "Designator" and p.get("valueVisible") and p.get("x") is not None:
                bottom = p["layerId"] == 4
                self.texts[bottom].append(text_box(p["x"] * MIL, p["y"] * MIL, p["value"], p["fontSize"], p.get("mirror", False)))
            elif h["type"] == "STRING" and p.get("layerId") in (3, 4):
                bottom = p["layerId"] == 4
                self.texts[bottom].append(text_box(p["x"] * MIL, p["y"] * MIL, p["text"], p["fontSize"], p.get("mirror", False)))
        self.labels = []                       # (ref, text, rect, bottom, size)

    def free(self, rect, bottom, me):
        x1, y1, x2, y2 = self.b.outline
        if rect[0] < x1 + EDGE or rect[2] > x2 - EDGE or rect[1] < y1 + EDGE or rect[3] > y2 - EDGE:
            return False
        for pad in self.b.pads:
            if circle_hits(rect, (pad.x, pad.y), pad.r + 0.15):
                return False
        for hx, hy, hd in self.b.holes:
            if circle_hits(rect, (hx, hy), hd / 2 + 0.3):
                return False
        for v in self.b.vias:
            if circle_hits(rect, v["c"], v["r"] + 0.1):
                return False
        for ref, pl in self.b.parts.items():
            if pl["bottom"] == bottom and ref != me and overlaps(rect, pl["body"], 0.1):
                return False
        for t in self.texts[bottom]:
            if overlaps(rect, t, 0.15):
                return False
        for _, _, r, side, _ in self.labels:
            if side == bottom and overlaps(rect, r, 0.15):
                return False
        return True

    def nearest_is_own(self, rect, ref):
        """True when no other labelled part on this side is nearer the label than its own part."""
        pl = self.b.parts[ref]
        own = rect_dist(rect, extent(pl))
        return all(rect_dist(rect, extent(o)) >= own - 0.02 for r, o in self.b.parts.items()
                   if r != ref and r in self.labelled and o["bottom"] == pl["bottom"])

    def candidates(self, ref, text):
        pl = self.b.parts[ref]
        bx1, by1, bx2, by2 = extent(pl)       # the part's own pads count as its extent
        cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
        standing = "VERTICAL" in pl["fp"]
        pot = pl["fp"].startswith("POT")
        for size in SIZES:
            w, h = CHAR_W * size * MIL * len(text), size * MIL
            for step in STEPS:
                g = GAP + step
                spots = [("right", (bx2 + g, cy - h / 2)), ("left", (bx1 - g - w, cy - h / 2)),
                         ("above", (cx - w / 2, by2 + g)), ("below", (cx - w / 2, by1 - g - h))]
                if pot:                               # pots: under or over the body, where the lugs are not
                    spots = [spots[3], spots[2], spots[0], spots[1]]
                elif not standing:                    # flat parts: along the body first
                    tall = (by2 - by1) > (bx2 - bx1)
                    spots = spots if tall else spots[2:] + spots[:2]
                if step == 0:
                    spots += [("above right", (bx2 + g, by2 + g)), ("above left", (bx1 - g - w, by2 + g)),
                              ("below right", (bx2 + g, by1 - g - h)), ("below left", (bx1 - g - w, by1 - g - h))]
                for name, (x, y) in spots:
                    yield name, (x, y, x + w, y + h), size

    def place(self, ref, text):
        """The first free spot whose nearest labelled part is its own; failing that, the first free spot
        within NEAR of its own part (a near-tie between two parts); failing that, no label."""
        bottom = self.b.parts[ref]["bottom"]
        own = extent(self.b.parts[ref])
        free = [(name, rect, size) for name, rect, size in self.candidates(ref, text) if self.free(rect, bottom, ref)]
        clear = [c for c in free if self.nearest_is_own(c[1], ref)]
        close = [c for c in free if rect_dist(c[1], own) <= NEAR]
        pick = (clear or close or [None])[0]
        if pick is None:
            return None                               # no spot that reads as this part's: the caller reports it
        name, rect, size = pick
        self.labels.append((ref, text, rect, bottom, size))
        return name if clear else name + " (nearer another part)"

    def legend(self, refs, text):
        """One line for parts that found no spot of their own ("100k: R10 R13 R16 R19"), at the free
        spot nearest their middle, within REACH; returns the line or None."""
        bottom = self.b.parts[refs[0]]["bottom"]
        boxes = [extent(self.b.parts[r]) for r in refs]
        cx = sum((b[0] + b[2]) / 2 for b in boxes) / len(boxes)
        cy = sum((b[1] + b[3]) / 2 for b in boxes) / len(boxes)
        line = f"{text}: {' '.join(refs)}"
        n = int(REACH / 0.5)
        offsets = sorted(((i * 0.5, j * 0.5) for i in range(-n, n + 1) for j in range(-n, n + 1)),
                         key=lambda o: math.hypot(*o))
        for size in SIZES:
            w, h = CHAR_W * size * MIL * len(line), size * MIL
            for dx, dy in offsets:
                x, y = cx + dx - w / 2, cy + dy - h / 2
                rect = (x, y, x + w, y + h)
                if self.free(rect, bottom, None):
                    self.labels.append(("+".join(refs), line, rect, bottom, size))
                    return line
        return None


def string_record(template, rid, ticket, z, text, rect, bottom, size):
    p = dict(template)
    p.update({"layerId": 4 if bottom else 3, "x": round((rect[2] if bottom else rect[0]) / MIL, 4),
              "y": round(rect[1] / MIL, 4), "text": text, "fontFamily": "default", "fontSize": size,
              "strokeWidth": 6, "bold": False, "italic": False, "origin": "LEFT_BOTTOM", "angle": 0,
              "reverse": False, "expansion": 0, "mirror": bool(bottom), "locked": False, "zIndex": z})
    head = {"type": "STRING", "ticket": ticket, "id": rid}
    return (json.dumps(head, separators=(",", ":")) + "||" + json.dumps(p, separators=(",", ":"), ensure_ascii=False) + "|")


def render(board, lab, path, scale=8):
    from PIL import Image, ImageDraw, ImageFont
    board.W, board.H = board.outline[2] - board.outline[0], board.outline[3] - board.outline[1]
    W, H = int(board.W * scale), int(board.H * scale)
    for bottom in (False, True):
        img = Image.new("RGB", (W + 2, H + 40), "white")
        dr = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 9)
        except OSError:
            font = ImageFont.load_default()

        def P(x, y):
            return 1 + x * scale, 1 + (board.H - y) * scale

        dr.rectangle([P(0, board.H), P(board.W, 0)], outline="black", width=2)
        for ref, pl in board.parts.items():
            if pl["bottom"] != bottom:
                continue
            x1, y1, x2, y2 = pl["body"]
            dr.rectangle([P(x1, y2), P(x2, y1)], outline="#b0b0b0")
        for pad in board.pads:
            X, Y = P(pad.x, pad.y)
            r = pad.r * scale
            dr.ellipse([X - r, Y - r, X + r, Y + r], outline="#d0b0b0")
        for t in lab.texts[bottom]:
            dr.rectangle([P(t[0], t[3]), P(t[2], t[1])], outline="#4060c0")
        for ref, text, rect, side, size in lab.labels:
            if side != bottom:
                continue
            dr.rectangle([P(rect[0], rect[3]), P(rect[2], rect[1])], outline="#c02020")
            X, Y = P(rect[0], rect[3])
            dr.text((X + 1, Y), text, fill="#c02020", font=font)
        dr.text((4, H + 8), f"{board.title}, {'bottom' if bottom else 'top'} side (seen from the top): grey = housings, "
                            f"blue = existing text, red = value labels", fill="black", font=font)
        img.save(path.format("bottom" if bottom else "top"))


def main(src, dst):
    with zipfile.ZipFile(src) as z:
        name = next(n for n in z.namelist() if n.endswith(".epru"))
        raw = z.read(name).decode("utf-8")
        entries = [(info, z.read(info.filename)) for info in z.infolist()]     # kept as EasyEDA wrote them
    lines = raw.split("\n")
    docs = ca.read_export(src)
    pcbmod = _load("pcb")
    fps = {u: dict(pcbmod.footprint_geometry(d), title=next(p["title"] for h, p in d["recs"] if h["type"] == "META"))
           for u, d in docs.items() if d["docType"] == "FOOTPRINT"}
    for u, d in docs.items():
        if d["docType"] == "FOOTPRINT":
            for h, p in d["recs"]:
                if h["type"] == "PAD":
                    fps[u]["pads"][str(p["num"])]["shape"] = p["defaultPad"]["padType"]
    vals = values()
    # find each PCB doc's line range, id / ticket / z maxima and a STRING to copy the field set from
    cur, spans = None, {}
    for i, line in enumerate(lines):
        if not line:
            continue
        h = json.loads(line.partition("||")[0])
        if h["type"] == "DOCHEAD":
            p = json.loads(line.partition("||")[2].rstrip("|"))
            cur = p["uuid"]
            spans[cur] = {"type": p["docType"], "start": i, "maxe": 0, "maxticket": 0, "maxz": 0, "string": None}
        s = spans[cur]
        m = re.match(r"^e(\d+)$", str(h.get("id", "")))
        if m:
            s["maxe"] = max(s["maxe"], int(m.group(1)))
        s["maxticket"] = max(s["maxticket"], h.get("ticket", 0))
        body = line.partition("||")[2].rstrip("|")
        if body:
            p = json.loads(body)
            if isinstance(p, dict) and isinstance(p.get("zIndex"), (int, float)):
                s["maxz"] = max(s["maxz"], p["zIndex"])
            if h["type"] == "STRING" and s["string"] is None:
                s["string"] = p
        if h["type"] == "META":
            s["meta"] = i
    inserts = {}         # META line index -> new lines
    report = []
    for u, d in docs.items():
        if d["docType"] != "PCB":
            continue
        title = next(p["title"] for h, p in d["recs"] if h["type"] == "META")
        if "Panel" in title:
            continue
        board = ca.RoutedBoard(title, d, fps)
        mine = vals[title.split()[1]]
        lab = Labeller(board, d, mine)
        parked, unclear = [], []
        for ref in sorted(board.parts, key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0))):
            if ref in mine:
                where = lab.place(ref, mine[ref])
                if where is None:
                    parked.append(ref)
                elif where.endswith("(nearer another part)"):
                    unclear.append(ref)
        # the parts left over: one legend line per value and cluster ("100k: R10 R13 R16 R19") near them;
        # parts of one value further apart than CLUSTER get a line each, so a line stays beside its parts
        groups = []
        for ref in parked:
            key = (mine[ref], board.parts[ref]["bottom"])
            near = [g for g in groups if g[0] == key and any(
                rect_dist(extent(board.parts[ref]), extent(board.parts[r])) <= CLUSTER for r in g[1])]
            if near:
                near[0][1].append(ref)
            else:
                groups.append((key, [ref]))
        legends, parked = [], []
        for (text, _), refs in groups:
            line = lab.legend(refs, text)
            if line:
                legends.append(line)
            else:
                parked += refs
        s = spans[u]
        new = []
        for k, (ref, text, rect, bottom, size) in enumerate(lab.labels):
            new.append(string_record(s["string"], f"e{s['maxe'] + 1 + k}", s["maxticket"] + 1 + k, s["maxz"] + 1 + k,
                                     text, rect, bottom, size))
        inserts[s["meta"]] = new
        report.append((title, len(lab.labels), parked, unclear, legends))
        render(board, lab, os.path.join(os.path.dirname(dst), "stereo-mixer-labels-" + title.split()[1].lower() + "-{}.png"))
    out = []
    for i, line in enumerate(lines):
        if i in inserts:
            out += inserts[i]
        out.append(line)
    with zipfile.ZipFile(dst, "w") as z:
        for info, data in entries:
            z.writestr(info, "\n".join(out).encode("utf-8") if info.filename == name else data,
                       compress_type=info.compress_type)
    for title, n, parked, unclear, legends in report:
        print(f"{title}: {n} labels" + (f", legend lines {legends}" if legends else "")
              + (f", no spot at all for {parked}" if parked else "")
              + (f", a near-tie with another labelled part: {unclear}" if unclear else ""))
    print("written", os.path.normpath(dst))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
