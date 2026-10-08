"""Plaitsy schematic as an EasyEDA Pro project (.epro2).

The netlist is circuit.py, the same one the stripboard projects use. The
parts are your own EasyEDA library parts, copied from the MorrisSynth
project export: TL074ACN, the WQP518MA jack, PTV09A pots, LR1F resistors,
FG28 and SR305 capacitors, the net ports, the ground flag and the sheet
frame. Resistor and capacitor values the library does not have are new
devices on the same symbol and footprint. Four parts are not in that
library and are drawn here in the same style, with their real pin
numbers: the Daisy Seed on its breakout, the 74HC4051, the 3-lead
bicolour LED and the push button.

Two A3 pages: Main board and Faceplate. Every connection to something
outside its block is a net port, so the pages read like the boards.

Run from hardware/tools:  python easyeda_export.py
"""
import collections
import copy
import json
import math
import os
import time
import uuid
import zipfile

from circuit import main_board_parts, faceplate_parts, CHANNELS, SECTION, LED_ORDER, JACKS, POTS

EXPORT = os.path.join(os.path.expanduser("~"), "Downloads", "ProPrj_MorrisSynth_2026-10-01.epro2")
LIBFILE = "../easyeda/morrissynth-parts.epru"
OUT = "../easyeda/Plaitsy.epro2"
PREVIEW = "../easyeda/plaitsy-easyeda-{}.png"
EDIT = "3.2.149"
W, H = 1655, 1170           # A3 sheet in 10 mil units; y runs from -H (top) to 0 (bottom)
NOW = int(time.time() * 1000)
CLIENT = "3ff5e4d6e06f68ed"
USER = {"uuid": "06e698d238954988b8826bcc258aa2f5", "nickname": "driesen.joep",
        "username": "driesen.joep", "avatar": "/images/avatar-default.png"}

# ---------------------------------------------------------------- library
# Devices copied as they are (with their symbols and footprints)
DEV = {
    "R1k": "c82a8167f1d84133bc542e652bd22433",       # LR1F1K0
    "R10k": "a9cc8fbe474242dc9110194515734c75",      # LR1F10K
    "C100n": "2eb0447475ac403680fd2b11e4f4c945",     # FG28X7R1H104KNT00
    "C1u": "bf1fe821a3774bf48d0873f872221180",       # SR305C105KAR
    "TL074": "ad23edee5d134c14aa92ae80bedf6b28",     # TL074ACN
    "JACK": "f4a247c302d346488553de1a1eb440e9",      # WQP-WQP518MA (PJ398SM style)
    "POT": "be9d2c8f5f814271a402f956f18b56f9",       # PTV09A-4025F-B103
    "GND": "eec77ec4c1d94de692d165be3817a3c4",       # Ground-GND
    "IN": "6a70cfa1bc80484e8decf4f8a0b61a9e",        # Netport-IN
    "OUT": "7956696325094941b2d15526d9c13967",       # Netport-OUT
    "FRAME": "93ae535dda0d4cce9b643bf06fbcd5ca",     # Drawing-Symbol_A4
}
# Devices whose symbol or footprint the new devices reuse
SRC = {
    "1N4148": "c0160a3f74384e849dc1cc5a24d54846",    # DO-35 footprint
    "1N5819": "f1e2836d6b9a4bf1bb0838127f6aa231",    # Schottky symbol
    "74HC595N": "0a92c57a01f94d9c9ee2e575c9a56376",  # DIP-16 footprint
}


def enc(head, payload):
    return (json.dumps(head, separators=(",", ":"), ensure_ascii=False) + "||" +
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "|")


def parse(lines):
    """{uuid: {"docType", "lines", "recs": [(head, payload)]}} in file order."""
    docs, cur = {}, None
    for line in lines:
        if not line:
            continue
        h, _, p = line.partition("||")
        h, p = json.loads(h), json.loads(p[:-1] if p.endswith("|") else p)
        if h["type"] == "DOCHEAD":
            cur = docs[p["uuid"]] = {"docType": p["docType"], "lines": [], "recs": []}
        cur["lines"].append(line)
        cur["recs"].append((h, p))
    return docs


def meta(doc):
    return next(p for h, p in doc["recs"] if h["type"] == "META")


def load_library():
    """The MorrisSynth docs this project needs, cached in the repo."""
    if not os.path.exists(LIBFILE):
        with zipfile.ZipFile(EXPORT) as z:
            name = next(n for n in z.namelist() if n.endswith(".epru"))
            docs = parse(z.read(name).decode("utf-8").split("\n"))
        want = set(DEV.values()) | set(SRC.values()) | {"BLOB"}
        for u in DEV.values():
            a = meta(docs[u])["attributes"]
            want |= {a["Symbol"]} | ({a["Footprint"]} if a.get("Footprint") else set())
        attrs = {k: meta(docs[u])["attributes"] for k, u in SRC.items()}
        want |= {attrs["1N5819"]["Symbol"], attrs["1N4148"]["Footprint"], attrs["74HC595N"]["Footprint"]}
        os.makedirs(os.path.dirname(LIBFILE), exist_ok=True)
        with open(LIBFILE, "w", encoding="utf-8", newline="\n") as f:
            for u, d in docs.items():  # keep the export's order
                if u in want:
                    f.write("\n".join(d["lines"]) + "\n")
    return parse(open(LIBFILE, encoding="utf-8").read().split("\n"))


def symbol_geometry(doc):
    """Pins, shapes and the Name attribute of a symbol doc."""
    pins, attrs, shapes, part_ids = {}, collections.defaultdict(dict), [], []
    name_attr = None
    for h, p in doc["recs"]:
        t = h["type"]
        if t == "PART":
            part_ids.append(h["id"])
        elif t == "PIN":
            pins[h["id"]] = {"part": p["partId"], "x": p["x"], "y": p["y"], "rot": p["rotation"], "len": p["length"]}
        elif t == "ATTR":
            if p["parentId"]:
                attrs[p["parentId"]][p["key"]] = p["value"]
            elif p["key"] in ("Name", "Global Net Name"):
                name_attr = p
        elif t in ("POLY", "RECT", "ELLIPSE", "TEXT", "ARC", "CIRCLE"):
            shapes.append((t, p))
    for pid, a in attrs.items():
        if pid in pins:
            pins[pid]["num"] = a.get("Pin Number")
            pins[pid]["name"] = a.get("Pin Name")
    return {"pins": list(pins.values()), "shapes": shapes, "parts": part_ids, "name_attr": name_attr}


# ---------------------------------------------------------------- writers
def new_uuid():
    return uuid.uuid4().hex


class Doc:
    def __init__(self, doc_type, uid=None):
        self.type, self.uuid = doc_type, uid or new_uuid()
        self.recs, self.ticket, self.eid, self.z = [], 0, 0, 0

    def add(self, typ, rid, payload):
        self.ticket += 1
        self.recs.append(({"type": typ, "ticket": self.ticket, "id": rid}, payload))

    def nid(self):
        self.eid += 1
        return f"e{self.eid}"

    def zi(self):
        self.z += 1
        return self.z

    def lines(self, meta_payload):
        head = {"docType": self.type, "client": CLIENT, "uuid": self.uuid, "updateTime": NOW,
                "version": str(NOW), "editVersion": EDIT, "user": USER}
        out = [enc({"type": "DOCHEAD", "ticket": self.ticket + 2}, head)]
        out += [enc(h, p) for h, p in self.recs]
        out.append(enc({"type": "META", "ticket": self.ticket + 1, "id": "META"}, meta_payload))
        return out


def attr_payload(z, parent, key, value, *, kv=False, vv=False, x=None, y=None, rot=0, fs=None,
                 align=None, part=None):
    p = {"partId": part} if part is not None else {}
    p.update({"groupId": "", "locked": False, "zIndex": z, "parentId": parent, "key": key, "value": value,
              "keyVisible": kv, "valueVisible": vv, "x": x, "y": y, "rotation": rot, "color": None,
              "fillColor": None, "fontFamily": None, "fontSize": fs, "strikeout": None, "underline": None,
              "italic": None, "fontWeight": None, "align": align, "version": "2.0"})
    return p


class Symbol:
    """A symbol drawn here, in the style of the EasyEDA library symbols."""

    def __init__(self, title, part_id, designator, tags=()):
        self.title, self.part, self.designator, self.tags = title, part_id, designator, list(tags)
        self.doc = Doc("SYMBOL")
        self.items = []   # ("POLY"/"RECT"/"PIN"/"TEXT", data)

    def poly(self, pts, closed=False, fill=None):
        self.items.append(("POLY", {"points": [{"x": x, "y": y} for x, y in pts], "closed": closed, "fill": fill}))

    def rect(self, x1, y1, x2, y2):
        self.items.append(("RECT", (x1, y1, x2, y2)))

    def text(self, x, y, s, size=None):
        self.items.append(("TEXT", (x, y, s, size)))

    def pin(self, num, name, x, y, rot, length=10, show=False, edge=None):
        self.items.append(("PIN", (num, name, x, y, rot, length, show, edge)))

    def bbox(self):
        xs, ys = [], []
        for t, d in self.items:
            if t == "POLY":
                xs += [p["x"] for p in d["points"]]
                ys += [p["y"] for p in d["points"]]
            elif t == "RECT":
                xs += [d[0], d[2]]
                ys += [d[1], d[3]]
        return [min(xs), min(ys), max(xs), max(ys)]

    def build(self):
        d, part = self.doc, self.part
        d.add("CANVAS", "CANVAS", {"originX": 0, "originY": 0})
        d.add("PART", part, {"BBOX": self.bbox(), "title": part})
        d.add("ATTR", d.nid(), attr_payload(d.zi(), "", "Symbol", self.title, align="LEFT_BOTTOM", part=part))
        d.add("ATTR", d.nid(), attr_payload(d.zi(), "", "Designator", self.designator, align="LEFT_BOTTOM", part=part))
        style = {"strokeColor": None, "strokeStyle": None, "fillColor": None, "strokeWidth": None, "fillStyle": None}
        for t, it in self.items:
            if t == "POLY":
                st = dict(style, fillColor=it["fill"])
                d.add("POLY", d.nid(), {"partId": part, "groupId": "", "locked": False, "zIndex": d.zi(),
                                        "points": it["points"], "closed": it["closed"], **st})
            elif t == "RECT":
                x1, y1, x2, y2 = it
                d.add("RECT", d.nid(), {"partId": part, "groupId": "", "locked": False, "zIndex": d.zi(),
                                        "dotX1": x1, "dotY1": y1, "dotX2": x2, "dotY2": y2, "radiusX": 0,
                                        "radiusY": 0, "rotation": 0, **style})
            elif t == "TEXT":
                x, y, s, size = it
                d.add("TEXT", d.nid(), {"partId": part, "groupId": "", "locked": False, "zIndex": d.zi(), "x": x,
                                        "y": y, "rotation": 0, "value": s, "color": None, "fillColor": None,
                                        "fontFamily": None, "fontSize": size, "strikeout": False, "underline": False,
                                        "italic": False, "fontWeight": False, "align": "LEFT_BOTTOM",
                                        "version": "2.0"})
            elif t == "PIN":
                num, name, x, y, rot, length, show, edge = it
                pid = d.nid()
                d.add("PIN", pid, {"partId": part, "groupId": "", "locked": False, "zIndex": d.zi(), "display": True,
                                   "x": x, "y": y, "length": length, "rotation": rot, "color": None,
                                   "pinShape": "NONE"})
                if edge is not None and rot == 0:      # left side, IC style
                    np, na = (edge + 3.7, y + 5.915), "LEFT_BOTTOM"
                    up, ua = (edge - 0.5, y + 0.915), "RIGHT_BOTTOM"
                elif edge is not None:                 # right side
                    np, na = (edge - 3.7, y + 5.915), "RIGHT_BOTTOM"
                    up, ua = (edge + 0.5, y + 0.915), "LEFT_BOTTOM"
                else:
                    np, na, up, ua = (x, y), "LEFT_BOTTOM", (x, y), "LEFT_BOTTOM"
                d.add("ATTR", d.nid(), attr_payload(d.zi(), pid, "Pin Name", name, vv=show, x=np[0], y=np[1],
                                                    align=na, part=part))
                d.add("ATTR", d.nid(), attr_payload(d.zi(), pid, "Pin Number", num, vv=show, x=up[0], y=up[1],
                                                    align=ua, part=part))
                d.add("ATTR", d.nid(), attr_payload(d.zi(), pid, "Pin Type", "Undefined", x=x, y=y,
                                                    align="LEFT_BOTTOM", part=part))
        source = f"{new_uuid()}|{USER['uuid']}"
        return d.lines({"title": self.title, "description": "", "tags": self.tags, "docType": 2, "source": source})


# Daisy Seed on the breakout, rows as on the main board (0 = USB/audio end).
# circuit pin -> (row, pin number, pin name)
SEED_PINS = {
    "L1": (1, "J5-2", "GND"), "L3": (3, "J5-4", "GND"),
    **{f"L{r}": (r, str(r - 3), f"D{r - 4}") for r in range(4, 19)},
    "L23": (23, "20", "AGND"), "L25": (25, "J1-1", "GND"), "L26": (26, "J1-2", "-12V"),
    "R0": (0, "J4-1", "AOUT1"), "R1": (1, "J4-2", "GND"), "R2": (2, "J4-3", "AOUT2"), "R3": (3, "J4-4", "GND"),
    "R4": (4, "40", "DGND"), "R6": (6, "38", "3V3D"), "R7": (7, "37", "D30"), "R8": (8, "36", "D29"),
    "R9": (9, "35", "D28/A11"), "R10": (10, "34", "D27"), "R11": (11, "33", "D26"),
    "R12": (12, "32", "D25/A10"), "R13": (13, "31", "D24/A9"), "R14": (14, "30", "D23/A8"),
    "R15": (15, "29", "D22/A7"), "R16": (16, "28", "D21/A6"), "R17": (17, "27", "D20/A5"),
    "R18": (18, "26", "D19/A4"), "R19": (19, "25", "D18/A3"), "R20": (20, "24", "D17/A2"),
    "R21": (21, "23", "D16/A1"), "R22": (22, "22", "D15/A0"), "R23": (23, "21", "3V3A"),
    "R25": (25, "J3-1", "GND"), "R26": (26, "J3-2", "+12V"),
}
SEED_TOP = -140      # y of row 0 in the symbol


def seed_symbol():
    left = [(r, n, nm) for pid, (r, n, nm) in SEED_PINS.items() if pid[0] == "L"]
    right = [(r, n, nm) for pid, (r, n, nm) in SEED_PINS.items() if pid[0] == "R"]
    s = Symbol("Daisy Seed on seed_power_opamps", "DaisySeedBreakout.1", "U?", ["Plaitsy"])
    s.rect(-80, SEED_TOP - 10, 80, SEED_TOP + 290)
    s.text(-30, SEED_TOP + 245, "Daisy Seed", 10)
    s.text(-40, SEED_TOP + 258, "seed_power_opamps", 8)
    for row, num, name in left:
        s.pin(num, name, -90, SEED_TOP + 10 * row, 0, show=True, edge=-80)
    for row, num, name in right:
        s.pin(num, name, 90, SEED_TOP + 10 * row, 180, show=True, edge=80)
    return s


MUX_LEFT = [(0, "13", "Y0"), (1, "14", "Y1"), (2, "15", "Y2"), (3, "12", "Y3"),
            (4, "1", "Y4"), (5, "5", "Y5"), (6, "2", "Y6"), (7, "4", "Y7")]
MUX_RIGHT = [(0, "16", "VCC"), (1, "3", "Z"), (2, "11", "S0"), (3, "10", "S1"),
             (4, "9", "S2"), (5, "6", "/E"), (6, "7", "VEE"), (7, "8", "GND")]


def mux_symbol():
    s = Symbol("74HC4051", "74HC4051.1", "U?", ["Plaitsy"])
    s.rect(-50, -45, 50, 45)
    for row, num, name in MUX_LEFT:
        s.pin(num, name, -60, -35 + 10 * row, 0, show=True, edge=-50)
    for row, num, name in MUX_RIGHT:
        s.pin(num, name, 60, -35 + 10 * row, 180, show=True, edge=50)
    return s


def led_symbol():
    """Two LEDs, red on top and green below, with a common cathode."""
    s = Symbol("LED 3mm bicolour R/G common cathode", "LED_RG_CC.1", "D?", ["Plaitsy"])
    for yc, colour, letter in ((-10, "#FF0000", "R"), (10, "#00A000", "G")):
        s.poly([(-20, yc), (-6, yc)])
        s.poly([(-6, yc - 6), (6, yc), (-6, yc + 6), (-6, yc - 6)], closed=True, fill=colour)
        s.poly([(6, yc - 6), (6, yc + 6)])
        s.poly([(6, yc), (14, yc)])
        s.text(-16, yc - 2, letter, 7)
    s.poly([(14, -10), (14, 10)])
    s.poly([(14, 0), (20, 0)])
    for x0 in (-1, 4):  # light arrows
        s.poly([(x0, -19), (x0 + 5, -24)])
        s.poly([(x0 + 5, -24), (x0 + 1, -23), (x0 + 4, -20), (x0 + 5, -24)], closed=True, fill="#FF0000")
    s.pin("1", "A_R", -30, -10, 0)
    s.pin("3", "A_G", -30, 10, 0)
    s.pin("2", "K", 30, 0, 180)
    return s


def button_symbol():
    s = Symbol("Push button (momentary)", "PUSHBUTTON.1", "SW?", ["Plaitsy"])
    s.poly([(-20, 0), (-12, 0)])
    s.poly([(12, 0), (20, 0)])
    s.poly([(-12, 0), (-12, -3)])
    s.poly([(12, 0), (12, -3)])
    s.poly([(-15, -7), (15, -7)])
    s.poly([(0, -7), (0, -15)])
    s.poly([(-4, -15), (4, -15)])
    s.pin("1", "1", -30, 0, 0)
    s.pin("2", "2", 30, 0, 180)
    return s


# ---------------------------------------------------------------- geometry
def tf(sx, sy, rot):
    c, s = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
    return sx * c + sy * s, -sx * s + sy * c


def Y(v):
    """Page y for a distance v from the top of the sheet."""
    return v - H


class Placed:
    def __init__(self, ref, x, y, rot, pins):
        self.ref, self.x, self.y, self.rot, self.pins = ref, x, y, rot, pins

    def __getitem__(self, num):
        return self.pins[num]


class Page:
    def __init__(self, project, title, number):
        self.pr, self.title, self.number = project, title, number
        self.doc = Doc("SCH_PAGE")
        self.doc.add("CANVAS", "CANVAS", {"originX": 0, "originY": 0})
        self.comps = []       # (ref, device key, x, y, rot, part id, {pin num: (x, y)}, label/flag net)
        self.wires = []       # (net, [((x1, y1), (x2, y2))])
        self.texts = []
        self.frame()

    # -- frame: same attributes your schematics use, A3
    def frame(self):
        d, pr = self.doc, self.pr
        cid = d.nid()
        sym = pr.sym_of("FRAME")
        d.add("COMPONENT", cid, {"locked": False, "zIndex": d.zi(), "partId": pr.symgeo[sym]["parts"][0],
                                 "groupId": "", "x": 0, "y": 0, "rotation": 0, "isMirror": False, "attrs": {}})
        today = time.strftime("%Y-%m-%d")
        vals = [("Symbol", sym), ("@Project Name", "Plaitsy"), ("@Page Count", "2"), ("@Update Date", today),
                ("@Create Date", today), ("@Schematic Name", "Plaitsy"), ("@Page No", str(self.number)),
                ("@Page Name", self.title), ("Company", ""), ("Reviewed", ""), ("Version", "V1.0"),
                ("Page Size", "A3"), ("Drawn", ""), ("Name", ""), ("@Create Time", ""), ("@Update Time", ""),
                ("Border", "1"), ("Width", W), ("Height", H), ("Region Start", "1"), ("X Region Count", "6"),
                ("Y Region Count", "4"), ("Blade Width", "10"), ("Color", ""), ("Title Block Position", "3"),
                ("Title Block", "1"), ("@Board Name", "Plaitsy"), ("Footprint", ""), ("Description", ""),
                ("Device", DEV["FRAME"])]
        for k, v in vals:
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, k, v))

    # -- components
    def place(self, ref, dev_key, x, y, rot=0, des=None, value_at=None, unit=1, name=True, uid=None,
              mirror=False):
        """Place a part. des / value_at: (dx, dy, align) for the Designator and Name texts."""
        pr, d = self.pr, self.doc
        sym = pr.sym_of(dev_key)
        geo = pr.symgeo[sym]
        part_id = geo["parts"][unit - 1]
        pins = {}
        for p in geo["pins"]:
            if p["part"] == part_id:
                dx, dy = tf(-p["x"] if mirror else p["x"], p["y"], rot)
                pins[p["num"]] = (round(x + dx, 3), round(y + dy, 3))
        cid = d.nid()
        d.add("COMPONENT", cid, {"locked": False, "zIndex": d.zi(), "partId": part_id, "groupId": "", "x": x,
                                 "y": y, "rotation": rot, "isMirror": mirror, "attrs": {}})
        fp = pr.device_attrs(dev_key).get("Footprint")
        if fp:
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Footprint", fp, kv=None, vv=None, rot=None))
        d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Symbol", sym, kv=None, vv=None, rot=None,
                                            align="LEFT_BOTTOM"))
        dx, dy, al = des or (0, -15, "LEFT_BOTTOM")
        d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Designator", ref, kv=None, vv=True, x=x + dx, y=y + dy,
                                            rot=None, align=al))
        nx, ny, nal = value_at or (dx, dy + 10, al)
        d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Name", None, kv=None, vv=bool(name), x=x + nx, y=y + ny,
                                            rot=None, align=nal))
        d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Device", pr.dev_uuid(dev_key)))
        for k in ("Reuse Block", "Group ID", "Channel ID"):
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, k, ""))
        d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Unique ID", uid or pr.unique_id(ref)))
        self.comps.append({"ref": ref, "dev": dev_key, "x": x, "y": y, "rot": rot, "mirror": mirror,
                           "part": part_id, "pins": pins,
                           "des": (x + dx, y + dy, al, ref), "name": (x + nx, y + ny, nal) if name else None})
        return Placed(ref, x, y, rot, pins)

    def _flag(self, dev_key, x, y, rot, net, name_visible):
        pr, d = self.pr, self.doc
        sym = pr.sym_of(dev_key)
        geo = pr.symgeo[sym]
        cid = d.nid()
        d.add("COMPONENT", cid, {"locked": False, "zIndex": d.zi(), "partId": geo["parts"][0], "groupId": "",
                                 "x": x, "y": y, "rotation": rot, "isMirror": False, "attrs": {}})
        d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Symbol", sym, kv=None, vv=None, rot=None, fs=10,
                                            align="LEFT_BOTTOM"))
        na = geo["name_attr"]
        tx, ty = tf(na["x"], na["y"], rot)
        align = na["align"]
        if rot == 180:
            align = {"RIGHT_MIDDLE": "LEFT_MIDDLE", "LEFT_MIDDLE": "RIGHT_MIDDLE"}.get(align, align)
        if dev_key == "GND":
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Device", DEV["GND"]))
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Name", net))
        else:
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Name", net, kv=None, vv=name_visible, x=x + tx,
                                                y=y + ty, rot=None, fs=10, align=align))
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Device", pr.dev_uuid(dev_key)))
        d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, "Relevance", "[]", x=x, y=y, align="RIGHT_TOP"))
        self.comps.append({"ref": None, "dev": dev_key, "x": x, "y": y, "rot": rot, "part": geo["parts"][0],
                           "pins": {"1": (x, y)}, "net": net, "label": (x + tx, y + ty, align, net)})

    def gnd(self, x, y, rot=0):
        """Ground flag; rot 0 hangs down, 90 points right, 270 points left."""
        self._flag("GND", x, y, rot, "GND", True)

    def port(self, x, y, net, kind, side):
        """Net port at (x, y) with its flag on `side` ('left' / 'right')."""
        rot = {("IN", "left"): 0, ("IN", "right"): 180, ("OUT", "right"): 0, ("OUT", "left"): 180}[(kind, side)]
        self._flag(kind, x, y, rot, net, True)

    # -- wires
    def wire(self, pts, net, label=None):
        """Polyline through pts; label=(x, y, align) shows the net name there."""
        d = self.doc
        wid = d.nid()
        d.add("WIRE", wid, {"groupId": "", "locked": False, "zIndex": d.zi()})
        segs = list(zip(pts, pts[1:])) or [(pts[0], pts[0])]
        for (x1, y1), (x2, y2) in segs:
            d.add("LINE", uuid.uuid4().hex[:16], {"lineGroup": wid, "startX": x1, "startY": y1, "endX": x2,
                                                  "endY": y2, "strokeColor": None, "strokeStyle": None,
                                                  "fillColor": None, "strokeWidth": None, "fillStyle": None})
        lx, ly, al = label or (pts[0][0], pts[0][1], None)
        d.add("ATTR", d.nid(), attr_payload(d.zi(), wid, "NET", net, vv=bool(label), x=lx, y=ly, align=al))
        d.add("ATTR", d.nid(), attr_payload(d.zi(), wid, "Relevance", "[]"))
        self.wires.append((net, segs, label))

    def stub_port(self, pin, net, kind, side, length=20):
        x, y = pin
        x2 = x - length if side == "left" else x + length
        self.wire([(x, y), (x2, y)], net)
        self.port(x2, y, net, kind, side)

    def stub_gnd(self, pin, direction="down", length=10):
        x, y = pin
        end = {"down": (x, y + length), "right": (x + length, y), "left": (x - length, y), "up": (x, y - length)}
        x2, y2 = end[direction]
        self.wire([(x, y), (x2, y2)], "GND")
        self.gnd(x2, y2, {"down": 0, "right": 90, "left": 270, "up": 180}[direction])

    def text(self, x, y, s, size=None):
        d = self.doc
        d.add("TEXT", d.nid(), {"groupId": "", "locked": False, "zIndex": d.zi(), "x": x, "y": y, "rotation": 0,
                                "value": s, "color": None, "fillColor": None, "fontFamily": None, "fontSize": size,
                                "strikeout": None, "underline": None, "italic": None, "fontWeight": None,
                                "align": "LEFT_BOTTOM", "version": "2.0"})
        self.texts.append((x, y, s, size))

    def lines(self, sch_uuid):
        return self.doc.lines({"title": self.title, "schematic": sch_uuid, "zIndex": self.number})


# ---------------------------------------------------------------- project
R_NEW = {"470": ("LR1F470R", "470Ω"), "12k": ("LR1F12K", "12kΩ"), "13k": ("LR1F13K", "13kΩ"),
         "15k": ("LR1F15K", "15kΩ"), "33k": ("LR1F33K", "33kΩ"), "100k": ("LR1F100K", "100kΩ")}
C_NEW = {"1n": ("FG28C0G1H102JNT00", "1nF"), "100p": ("FG28C0G1H101JNT00", "100pF")}


class Project:
    def __init__(self):
        self.lib = load_library()
        self.symgeo = {u: symbol_geometry(d) for u, d in self.lib.items() if d["docType"] == "SYMBOL"}
        self.devices = {k: (u, meta(self.lib[u])) for k, u in DEV.items()}
        self.new_docs = []      # extra SYMBOL / DEVICE docs (lines)
        self.uids, self.next_uid = {}, 2
        self._new_devices()

    def device_attrs(self, key):
        return self.devices[key][1]["attributes"]

    def dev_uuid(self, key):
        return self.devices[key][0]

    def sym_of(self, key):
        return self.device_attrs(key)["Symbol"]

    def unique_id(self, ref):
        if ref not in self.uids:
            self.uids[ref] = f"gge{self.next_uid}"
            self.next_uid += 1
        return self.uids[ref]

    def _device(self, key, title, attrs, tags=()):
        d = Doc("DEVICE")
        m = {"title": title, "tags": list(tags), "source": f"{new_uuid()}|{USER['uuid']}", "images": [],
             "attributes": attrs}
        self.new_docs.append(("DEVICE", d.lines(m)))
        self.devices[key] = (d.uuid, m)

    def _symbol(self, sym):
        lines = sym.build()
        self.new_docs.insert(0, ("SYMBOL", lines))
        self.lib_symbol(sym.doc.uuid, lines)
        return sym.doc.uuid

    def lib_symbol(self, uid, lines):
        self.symgeo[uid] = symbol_geometry(parse(lines)[uid])

    def _new_devices(self):
        r1k = meta(self.lib[DEV["R1k"]])["attributes"]
        for val, (mpn, value) in R_NEW.items():
            a = dict(r1k)
            a.update({"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                      "LCSC Part Name": f"Metal film resistor {value} ±1% 600mW",
                      "Description": f"Metal film resistor {value} ±1% 600mW (TE LR1F series)"})
            self._device("R" + val, mpn, a, ["Resistors", "Through Hole Resistors"])
        c100n = meta(self.lib[DEV["C100n"]])["attributes"]
        for val, (mpn, value) in C_NEW.items():
            a = dict(c100n)
            a.update({"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                      "Tolerance": "±5%", "Temperature Coefficient": "C0G",
                      "LCSC Part Name": f"{value} ±5% 50V C0G",
                      "Description": f"Capacitance:{value} Tolerance:±5% Voltage Rating:50V Temperature Coefficient:C0G"})
            self._device("C" + val, mpn, a, ["Capacitors", "Multilayer Ceramic Capacitors MLCC - Leaded"])
        d4148 = meta(self.lib[SRC["1N4148"]])["attributes"]
        a = dict(d4148)
        a.update({"Symbol": meta(self.lib[SRC["1N5819"]])["attributes"]["Symbol"], "Manufacturer Part": "BAT85",
                  "LCSC Part Name": "BAT85", "Supplier Part": "", "Manufacturer": "", "Datasheet": "",
                  "Description": "Schottky diode 30 V 200 mA, DO-35"})
        self._device("BAT85", "BAT85", a, ["Diodes", "Schottky Diodes"])
        dip16 = meta(self.lib[SRC["74HC595N"]])["attributes"]["Footprint"]
        for key, sym, title, desig, fp, desc in (
                ("SEED", seed_symbol(), "Daisy Seed + seed_power_opamps", "U?", "",
                 "Daisy Seed plugged into Rob Heel's seed_power_opamps breakout (socket strips on the main board)"),
                ("MUX", mux_symbol(), "74HC4051", "U?", dip16, "8-channel analog multiplexer, DIP-16"),
                ("LED", led_symbol(), "LED 3mm bicolour R/G CC", "D?", "",
                 "3 mm bicolour LED, red/green, common cathode (middle lead)"),
                ("SW", button_symbol(), "Push button", "SW?", "", "Momentary push button, 6x6 mm tactile")):
            su = self._symbol(sym)
            attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": title, "Designator": desig,
                     "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": fp,
                     "3D Model": "", "3D Model Title": "", "3D Model Transform": "", "Description": desc}
            self._device(key, title, attrs)

    def write(self, pages, path):
        board, sch = Doc("BOARD", new_uuid()[:16]), Doc("SCH")
        used = {u for u, m in self.devices.values()}
        refs = {m["attributes"].get(k) for u, m in self.devices.values() for k in ("Symbol", "Footprint")}
        keep = {"FOOTPRINT": refs, "SYMBOL": refs, "DEVICE": used}
        lines = []
        for typ in ("FOOTPRINT", "SYMBOL", "DEVICE"):
            for u, d in self.lib.items():
                if d["docType"] == typ and u in keep[typ]:
                    lines += d["lines"]
            lines += [l for t, ls in self.new_docs if t == typ for l in ls]
        lines += board.lines({"title": "Plaitsy", "zIndex": 1})
        lines += sch.lines({"title": "Plaitsy Schema", "board": board.uuid, "zIndex": None})
        for pg in pages:
            lines += pg.lines(sch.uuid)
        lines += Doc("CONFIG", "CONFIG").lines({"defaultSheet": ""})
        lines += [l for u, d in self.lib.items() if d["docType"] == "BLOB" for l in d["lines"]]
        project = {"title": "Plaitsy", "cbb_project": False, "editorVersion": EDIT, "introduction": "",
                   "description": "Mutable Instruments Plaits clone on stripboard: Daisy Seed, TL074 CV inputs, "
                                  "74HC4051 pot mux.", "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr("Plaitsy.epru", "\n".join(lines) + "\n")
        return lines


# ---------------------------------------------------------------- layout
POWER = {"3V3A", "+12V", "-12V"}
# Nets that cross between the boards, and their direction seen from the main board
TO_FACEPLATE = {"OUT", "AUX", "MUX_S0", "MUX_S1", "MUX_S2", "PROBE", "LED8_R_IO", *LED_ORDER[:15]}
FROM_FACEPLATE = {"BTN_A", "BTN_B", "MUX_OUT", *[f"CV_{c[0]}" for c in CHANNELS]}


def r_dev(value):
    return {"1k": "R1k", "10k": "R10k"}.get(value, "R" + value)


def c_dev(value):
    return {"100n": "C100n", "1u": "C1u"}.get(value, "C" + value)


def two_pin(pg, part, x, y, rot, dev, des=None, value_at=None):
    return pg.place(part.ref, dev, x, y, rot, des=des, value_at=value_at)


H_TXT = ((-20, -7, "LEFT_BOTTOM"), (2, -7, "LEFT_BOTTOM"))     # designator, value above a horizontal part
V_TXT = ((8, -2, "LEFT_BOTTOM"), (8, 8, "LEFT_BOTTOM"))        # beside a vertical part


def main_page(pr, parts):
    P = {p.ref: p for p in parts}
    pg = Page(pr, "Main board", 1)

    # Seed on the breakout: every used pin gets a net port
    pg.text(150, Y(55), "Daisy Seed on seed_power_opamps breakout", 12)
    sx, sy = 260, Y(240)
    u2 = pg.place("U2", "SEED", sx, sy, des=(-80, SEED_TOP - 14, "LEFT_BOTTOM"), name=False)
    for pid, (row, num, name) in SEED_PINS.items():
        net = P["U2"].nets.get(pid)
        if not net:
            continue
        side = "left" if pid[0] == "L" else "right"
        if net == "GND" or net in POWER:
            kind = "IN"
        elif net in TO_FACEPLATE or net.startswith("D"):
            kind = "OUT"
        else:
            kind = "IN"    # ADC inputs, buttons, mux out
        pg.stub_port(u2[num], net, kind, side)

    # LED resistors: Seed GPIO -> LED anode line on the faceplate
    pg.text(70, Y(560), "LED resistors (LEDs are on the faceplate)", 12)
    for i in range(15):
        ref = f"R{60 + i}"
        col, row = divmod(i, 8)
        x, y = 140 + col * 260, Y(600 + row * 30)
        r = two_pin(pg, P[ref], x, y, 0, r_dev(P[ref].value), *H_TXT)
        pg.stub_port(r["1"], f"D{i}", "IN", "left")
        pg.stub_port(r["2"], LED_ORDER[i], "OUT", "right")

    # CV input channels
    pg.text(560, Y(32), "CV inputs: TL074 inverting stages, biased from 3V3A, 1k into the Seed ADC", 12)
    n = 21
    for i, (name, rf, cf, bias, u, sec) in enumerate(CHANNELS):
        col, row = divmod(i, 4)
        ox, oy = 730 + col * 490, Y(155 + row * 170)
        rin, rfb, rs = (P[f"R{n + 3 * i + k}"] for k in range(3))
        cfb = P[f"C{21 + i}"]
        amp = pg.place(u, "TL074", ox, oy, unit=sec, des=(12, 22, "LEFT_BOTTOM"), value_at=(12, 32, "LEFT_BOTTOM"))
        a_in = pg.place(rin.ref, r_dev(rin.value), ox - 90, oy - 10, des=H_TXT[0], value_at=H_TXT[1])
        a_rf = pg.place(rfb.ref, r_dev(rfb.value), ox, oy - 60, des=H_TXT[0], value_at=H_TXT[1])
        a_cf = pg.place(cfb.ref, c_dev(cfb.value), ox, oy - 90, des=(-20, -10, "LEFT_BOTTOM"),
                        value_at=(2, -10, "LEFT_BOTTOM"))
        a_rs = pg.place(rs.ref, r_dev(rs.value), ox + 100, oy, des=H_TXT[0], value_at=H_TXT[1])
        out, inm, inp = SECTION[sec]
        nin, nout = f"IN_{name}", f"OA_{name}"
        jx, jy = ox - 55, oy - 10          # summing node
        kx = ox + 60                       # output node column
        pg.wire([a_in["2"], (jx, jy)], nin)
        pg.wire([(jx, jy), amp[inm]], nin)
        pg.wire([(jx, jy), (jx, oy - 60)], nin)
        pg.wire([(jx, oy - 60), a_rf["1"]], nin)
        pg.wire([(jx, oy - 60), (jx, oy - 90), a_cf["1"]], nin)
        pg.wire([amp[out], (kx, oy)], nout)
        pg.wire([(kx, oy), a_rs["1"]], nout)
        pg.wire([(kx, oy), (kx, oy - 60)], nout)
        pg.wire([(kx, oy - 60), a_rf["2"]], nout)
        pg.wire([(kx, oy - 60), (kx, oy - 90), a_cf["2"]], nout)
        pg.stub_port(a_in["1"], f"CV_{name}", "IN", "left")
        pg.stub_port(amp[inp], bias, "IN", "left", length=30)
        pg.stub_port(a_rs["2"], f"ADC_{name}", "OUT", "right")
        if sec == 1:   # this unit carries the supply pins
            vcc, vee = amp["4"], amp["11"]
            pg.wire([vcc, vcc], "+12V", label=(vcc[0] + 3, vcc[1] - 2, "LEFT_BOTTOM"))
            pg.wire([vee, vee], "-12V", label=(vee[0] + 3, vee[1] + 8, "LEFT_BOTTOM"))

    # Bias dividers
    pg.text(530, Y(750), "Bias", 12)
    for k, (rt, rb, cb, net) in enumerate((("R45", "R46", "C29", "BIAS_A"), ("R47", "R48", "C30", "BIAS_V"))):
        x, top = 620 + k * 180, Y(800)
        a = pg.place(rt, r_dev(P[rt].value), x, top + 20, 270, *V_TXT)
        b = pg.place(rb, r_dev(P[rb].value), x, top + 80, 270, *V_TXT)
        c = pg.place(cb, c_dev(P[cb].value), x + 40, top + 80, 270, des=(8, -2, "LEFT_BOTTOM"),
                     value_at=(8, 8, "LEFT_BOTTOM"))
        node = (x, top + 50)
        pg.wire([a["2"], node], net)
        pg.wire([node, b["1"]], net)
        pg.wire([node, (x + 40, top + 50), c["1"]], net)
        pg.wire([node, (x - 20, top + 50)], net)
        pg.port(x - 20, top + 50, net, "OUT", "left")
        pg.wire([a["1"], (x, top - 10), (x - 20, top - 10)], "3V3A")
        pg.port(x - 20, top - 10, "3V3A", "IN", "left")
        pg.stub_gnd(b["2"])
        pg.stub_gnd(c["2"])

    # V/OCT clamp diodes
    pg.text(890, Y(750), "V/OCT clamp", 12)
    x, top = 980, Y(800)
    d21 = pg.place("D21", "BAT85", x, top + 20, 270, *V_TXT)
    d22 = pg.place("D22", "BAT85", x, top + 80, 270, *V_TXT)
    node = (x, top + 50)
    pg.wire([d21["2"], node], "ADC_VOCT")         # anode (pin 2) down to the node
    pg.wire([node, d22["1"]], "ADC_VOCT")         # cathode (pin 1) up to the node
    pg.wire([node, (x - 20, top + 50)], "ADC_VOCT")
    pg.port(x - 20, top + 50, "ADC_VOCT", "IN", "left")
    pg.wire([d21["1"], (x, top - 10), (x - 20, top - 10)], "3V3A")
    pg.port(x - 20, top - 10, "3V3A", "IN", "left")
    pg.stub_gnd(d22["2"])

    # Supply decoupling, one pair per TL074
    pg.text(1030, Y(750), "Supply decoupling U3, U4", 12)
    for k, (cp, cn) in enumerate((("C31", "C32"), ("C33", "C34"))):
        x, top = 1120 + k * 140, Y(790)
        a = pg.place(cp, c_dev(P[cp].value), x, top + 20, 270, *V_TXT)
        b = pg.place(cn, c_dev(P[cn].value), x, top + 80, 270, *V_TXT)
        node = (x, top + 50)
        pg.wire([a["2"], node], "GND")
        pg.wire([node, b["1"]], "GND")
        pg.wire([node, (x - 15, top + 50)], "GND")
        pg.gnd(x - 15, top + 50, 270)
        pg.wire([a["1"], (x, top - 10), (x - 20, top - 10)], "+12V")
        pg.port(x - 20, top - 10, "+12V", "IN", "left")
        pg.wire([b["2"], (x, top + 120), (x - 20, top + 120)], "-12V")
        pg.port(x - 20, top + 120, "-12V", "IN", "left")

    pg.text(40, Y(1090), "Net ports with the same name connect. Ports for nets that cross to the faceplate are the "
                        "board-to-board pins (see docs/design.md).", 10)
    pg.text(40, Y(1110), "Ground: AGND (Seed pin 20) and DGND (pin 40) meet on the breakout; take the bias "
                        "dividers to AGND, the LED returns to DGND.", 10)
    return pg


def faceplate_page(pr, parts):
    P = {p.ref: p for p in parts}
    pg = Page(pr, "Faceplate", 2)
    label_of = {j[0]: j[1] for j in JACKS}
    probe_r = {p.nets["1"]: p for p in parts if p.ref in ("R9", "R10", "R11", "R12", "R13")}

    # Jacks: sleeve and grounded switch lugs to GND, tips to the main board
    pg.text(70, Y(45), "Jacks (Thonkiconn) and the normalization probe", 12)
    for i, (ref, label, tip, tn) in enumerate(JACKS):
        col, row = divmod(i, 5)
        jx, jy = 130 + col * 360, Y(125 + row * 95)
        j = pg.place(ref, "JACK", jx, jy, des=(-25, -22, "LEFT_BOTTOM"), name=False)
        pg.text(jx - 25, jy + 30, label, 10)
        s = j["1"]
        pg.wire([s, (s[0], s[1] - 20), (s[0] + 20, s[1] - 20)], "GND")
        pg.gnd(s[0] + 20, s[1] - 20, 90)
        if tn == "GND":
            pg.stub_gnd(j["2"], "right", 20)
        elif tn:
            r = probe_r[tn]
            rp = pg.place(r.ref, r_dev(r.value), j["2"][0] + 40, j["2"][1], des=H_TXT[0], value_at=H_TXT[1])
            pg.wire([j["2"], rp["1"]], tn)
            pg.stub_port(rp["2"], "PROBE", "IN", "right")
        x, y = j["3"]
        if tip.startswith("CV_"):
            pg.wire([(x, y), (x + 120, y)], tip)
            pg.port(x + 120, y, tip, "OUT", "right")
        else:
            pg.wire([(x, y), (x + 120, y)], tip)
            pg.port(x + 120, y, tip, "IN", "right")

    # Pots into the mux
    pg.text(820, Y(45), "Pots, read through the 74HC4051", 12)
    for i, (ref, label, wiper, mpin) in enumerate(POTS):
        col, row = divmod(i, 4)
        px, py = 930 + col * 230, Y(130 + row * 95)
        p = pg.place(ref, "POT", px, py, des=(8, -22, "LEFT_BOTTOM"), value_at=(8, -12, "LEFT_BOTTOM"))
        pg.text(px - 40, py + 32, label, 10)
        pg.stub_port(p["3"], "3V3A", "IN", "left")
        pg.stub_gnd(p["1"], "right", 15)
        w = p["2"]
        pg.wire([w, (w[0], w[1] - 15), (w[0] - 20, w[1] - 15)], wiper)
        pg.port(w[0] - 20, w[1] - 15, wiper, "OUT", "left")

    ux, uy = 1460, Y(170)
    mux = pg.place("U1", "MUX", ux, uy, des=(-50, -52, "LEFT_BOTTOM"), value_at=(-50, 58, "LEFT_BOTTOM"))
    nets = P["U1"].nets
    for row, num, name in MUX_LEFT:
        net = nets[num]
        if net == "GND":
            pg.stub_gnd(mux[num], "left", 15)
        else:
            pg.stub_port(mux[num], net, "IN", "left")
    gnd_pins = []
    for row, num, name in MUX_RIGHT:
        net = nets[num]
        if net == "GND":
            gnd_pins.append(mux[num])
        elif net == "3V3A":
            pg.stub_port(mux[num], net, "IN", "right")
        elif net == "MUX_OUT":
            pg.stub_port(mux[num], net, "OUT", "right")
        else:
            pg.stub_port(mux[num], net, "IN", "right")
    bx = gnd_pins[0][0] + 15
    for gp in gnd_pins:
        pg.wire([gp, (bx, gp[1])], "GND")
    for a, b in zip(gnd_pins, gnd_pins[1:]):
        pg.wire([(bx, a[1]), (bx, b[1])], "GND")
    pg.wire([(bx, gnd_pins[-1][1]), (bx, gnd_pins[-1][1] + 10)], "GND")
    pg.gnd(bx, gnd_pins[-1][1] + 10)
    c8 = pg.place("C8", c_dev(P["C8"].value), 1460, Y(300), 270, *V_TXT)
    pg.wire([c8["1"], (1460, Y(270)), (1440, Y(270))], "3V3A")
    pg.port(1440, Y(270), "3V3A", "IN", "left")
    pg.stub_gnd(c8["2"])
    pg.text(1395, Y(345), "C8 at U1 pin 16", 8)

    # LEDs and buttons
    pg.text(70, Y(620), "Model LEDs (3-lead bicolour, common cathode) and buttons", 12)
    for k in range(8):
        col, row = divmod(k, 4)
        lx, ly = 300 + col * 330, Y(680 + row * 70)
        ref = f"D{k + 1}"
        led = pg.place(ref, "LED", lx, ly, des=(-15, -24, "LEFT_BOTTOM"), name=False)
        x2, y2 = led["2"]
        pg.wire([(x2, y2), (x2 + 15, y2)], "GND")
        pg.gnd(x2 + 15, y2)
        pg.stub_port(led["3"], f"LED{k + 1}_G", "IN", "left")
        if k == 7:   # LED8 red has its resistor on this board
            r1 = pg.place("R1", r_dev(P["R1"].value), lx - 70, ly - 10, 180, des=(-20, -7, "LEFT_BOTTOM"),
                          value_at=(2, -7, "LEFT_BOTTOM"))
            pg.wire([led["1"], r1["1"]], "LED8_R")
            pg.stub_port(r1["2"], "LED8_R_IO", "IN", "left")
        else:
            pg.stub_port(led["1"], f"LED{k + 1}_R", "IN", "left")
    for k, (ref, sig_pin, gnd_pin, net, mirror, label) in enumerate((
            ("SW1", "2", "1", "BTN_A", False, "left button"), ("SW2", "1", "2", "BTN_B", True, "right button"))):
        bx_, by_ = 860, Y(690 + k * 80)
        sw = pg.place(ref, "SW", bx_, by_, des=(-12, -20, "LEFT_BOTTOM"), name=False, mirror=mirror)
        pg.text(bx_ - 30, by_ + 22, label, 10)
        pg.stub_port(sw[sig_pin], net, "OUT", "right")
        pg.stub_gnd(sw[gnd_pin], "left", 15)
    return pg


# ---------------------------------------------------------------- checks
def check(pg, parts, pin_map):
    """Connectivity from the drawing (points, wires, port names) against circuit.py."""
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    def key(p):
        return (round(p[0], 2), round(p[1], 2))

    names = collections.defaultdict(set)
    pin_at = {}
    for c in pg.comps:
        for num, pos in c["pins"].items():
            if c["ref"]:
                pin_at[(c["ref"], num)] = key(pos)
            else:
                names[key(pos)].add(c["net"])
            find(key(pos))
    segs = []
    for net, ss, _ in pg.wires:
        for a, b in ss:
            union(key(a), key(b))
            names[key(a)].add(net)
            segs.append((key(a), key(b)))
    # T-junctions and pins sitting on the middle of a wire are not allowed here
    points = set(parent)
    problems = []
    for a, b in segs:
        for p in points:
            if p in (a, b):
                continue
            if (min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]) and
                    (b[0] - a[0]) * (p[1] - a[1]) == (b[1] - a[1]) * (p[0] - a[0])):
                problems.append(f"point {p} lies inside wire {a}-{b}")
    # merge by name (ports and wire names are global)
    by_name = {}
    for p, ns in names.items():
        for n in ns:
            if n in by_name:
                union(p, by_name[n])
            else:
                by_name[n] = p
    groups = collections.defaultdict(set)
    for (ref, num), p in pin_at.items():
        groups[find(p)].add((ref, num))
    group_names = collections.defaultdict(set)
    for p, ns in names.items():
        group_names[find(p)] |= ns
    want = collections.defaultdict(set)
    for part in parts:
        for pid, net in part.nets.items():
            if net.startswith("NC_"):
                continue
            num = pin_map(part, pid)
            if (part.ref, num) not in pin_at:
                problems.append(f"{part.ref}.{pid} ({num}) not drawn on {pg.title}")
                continue
            want[net].add((part.ref, num))
    for net, members in want.items():
        gs = {find(pin_at[m]) for m in members}
        if len(gs) != 1:
            problems.append(f"net {net} split into {len(gs)} groups")
        for g in gs:
            other = {n for n in group_names[g] if n != net}
            if other:
                problems.append(f"net {net} touches {sorted(other)}")
    # pins drawn but not wired to anything in the netlist (allowed only if the netlist leaves them open)
    wired = {m for ms in want.values() for m in ms}
    for (ref, num), p in pin_at.items():
        if (ref, num) not in wired and len(groups[find(p)]) > 1:
            problems.append(f"{ref}.{num} is connected but should be open")
    return problems


def pin_map(part, pid):
    ref = part.ref
    if ref == "U2":
        return SEED_PINS[pid][1]
    if ref in ("D21", "D22"):
        return {"1": "2", "2": "1"}[pid]       # library Schottky symbol: pin 2 = anode
    return pid


# ---------------------------------------------------------------- preview
def render(pr, pg, path, scale=1.0):
    from PIL import Image, ImageDraw, ImageFont
    k = 1.6 * scale
    img = Image.new("RGB", (int(W * k) + 20, int(H * k) + 20), "white")
    dr = ImageDraw.Draw(img)

    def P(x, y):
        return 10 + x * k, 10 + (y + H) * k

    try:
        font = ImageFont.truetype("arial.ttf", int(9 * k * 0.75))
        small = ImageFont.truetype("arial.ttf", int(7 * k * 0.75))
    except OSError:
        font = small = ImageFont.load_default()

    def text(x, y, s, align="LEFT_BOTTOM", f=None):
        f = f or font
        tw = dr.textlength(str(s), font=f)
        X, Yp = P(x, y)
        h = f.size
        if align and align.startswith("RIGHT"):
            X -= tw
        elif align and align.startswith("CENTER"):
            X -= tw / 2
        if align and align.endswith("MIDDLE"):
            Yp -= h / 2
        elif align is None or align.endswith("BOTTOM"):
            Yp -= h
        dr.text((X, Yp), str(s), fill="#203080", font=f)

    dr.rectangle([P(0, -H), P(W, 0)], outline="#999999")
    for c in pg.comps:
        geo = pr.symgeo[pr.sym_of(c["dev"])]
        x0, y0, rot = c["x"], c["y"], c["rot"]
        m = -1 if c.get("mirror") else 1
        for t, s in geo["shapes"]:
            if s.get("partId") not in (None, c["part"]):
                continue
            if t == "POLY":
                pts = [P(x0 + tf(m * p["x"], p["y"], rot)[0], y0 + tf(m * p["x"], p["y"], rot)[1])
                       for p in s["points"]]
                if len(pts) > 1:
                    dr.line(pts, fill="#a00000", width=1)
            elif t == "RECT":
                a = tf(s["dotX1"], s["dotY1"], rot)
                b = tf(s["dotX2"], s["dotY2"], rot)
                dr.rectangle([P(x0 + min(a[0], b[0]), y0 + min(a[1], b[1])),
                              P(x0 + max(a[0], b[0]), y0 + max(a[1], b[1]))], outline="#a00000")
        for p in geo["pins"]:
            if p["part"] != c["part"]:
                continue
            ex, ey = tf(m * p["x"], p["y"], rot)
            ux, uy = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}[p["rot"] % 360]
            dx, dy = tf(m * ux, uy, rot)
            dr.line([P(x0 + ex, y0 + ey), P(x0 + ex + dx * p["len"], y0 + ey + dy * p["len"])], fill="#a00000")
        if c["ref"]:
            dx, dy, al, ref = c["des"]
            text(dx, dy, ref, al)
            if c["name"]:
                a = pr.device_attrs(c["dev"])
                nm = a.get("Value") if a.get("Name") == "={Value}" else a.get("Manufacturer Part", "")
                text(c["name"][0], c["name"][1], nm, c["name"][2], small)
        elif c["dev"] != "GND":
            lx, ly, al, net = c["label"]
            text(lx, ly, net, al, small)
    for net, segs, label in pg.wires:
        for a, b in segs:
            dr.line([P(*a), P(*b)], fill="#008000", width=2)
        if label:
            text(label[0], label[1], net, label[2], small)
    for x, y, s, size in pg.texts:
        text(x, y, s, f=font if (size or 10) >= 10 else small)
    # junction dots where three or more wire ends meet
    ends = collections.Counter()
    for net, segs, _ in pg.wires:
        for a, b in segs:
            if a != b:
                ends[a] += 1
                ends[b] += 1
    for p, cnt in ends.items():
        if cnt >= 3:
            X, Yp = P(*p)
            dr.ellipse([X - 3, Yp - 3, X + 3, Yp + 3], fill="#008000")
    img.save(path)


def main():
    pr = Project()
    mb, fp = main_board_parts(), faceplate_parts()
    pages = [main_page(pr, mb), faceplate_page(pr, fp)]
    bad = check(pages[0], mb, pin_map) + check(pages[1], fp, pin_map)
    for b in bad:
        print("PROBLEM:", b)
    pr.write(pages, OUT)
    for pg in pages:
        render(pr, pg, PREVIEW.format(pg.title.lower().replace(" ", "-")))
    n = sum(1 for pg in pages for c in pg.comps if c["ref"])
    print(f"{OUT}: {n} part units on {len(pages)} pages, {len(bad)} problems")


if __name__ == "__main__":
    main()
