"""sb.py - a small stripboard design kit for the Plaitsy build.

It models a board the way stripboard-editor.com does: every row of holes is
one copper strip, cuts sever a strip ("between" two holes, or a drilled
"hole"), and link wires join holes on the component side. On top of that it

  * places parts (rigid footprints with the editor's rotation rules, or
    flexible two-lead parts with free lead positions),
  * checks a layout: holes used twice, leads under another part's body, two
    nets on one strip segment (short) and nets split over several islands
    (open),
  * renders PNG previews (component side and mirrored copper side),
  * exports a project JSON that stripboard-editor.com imports
    (Import > Raw project): schematic (symbols, stub wires, net labels) and
    board (parts, cuts, link wires).

Coordinates: (row, col), row 0 at the top, col 0 at the left, seen from the
component side. One pitch is 2.54 mm.
"""
from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field

PITCH = 2.54
G = 20  # editor schematic grid


# --------------------------------------------------------------------------
# Footprints and part definitions
# --------------------------------------------------------------------------

@dataclass
class Pin:
    id: str
    name: str
    r: int
    c: int


@dataclass
class PartDef:
    """A part definition. Built-in editor parts keep the editor's id; custom
    ones are exported into the project's componentDefs."""
    id: str
    name: str
    symbol: str
    prefix: str
    pins: list  # list[Pin]; for flexible parts only order/ids/names matter
    body: list = field(default_factory=list)  # [(r, c)] cells under the body
    category: str = "generic"
    flexible: bool = False
    custom: bool = False
    has_value: bool = True
    width: int | None = None
    height: int | None = None
    # pins that are joined inside the part (pushbutton legs share an id; the
    # breakout ties its GND/+12/-12 header pins together on its own PCB)
    internal_groups: list = field(default_factory=list)

    def __post_init__(self):
        cells = [(p.r, p.c) for p in self.pins] + list(self.body)
        if self.width is None:
            self.width = max(c for _, c in cells) + 1
        if self.height is None:
            self.height = max(r for r, _ in cells) + 1

    def editor_def(self):
        d = {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "symbol": self.symbol,
            "defaultLabelPrefix": self.prefix,
            "width": self.width,
            "height": self.height,
            "pins": [{"id": p.id, "name": p.name, "offsetRow": p.r, "offsetCol": p.c} for p in self.pins],
        }
        if self.body:
            d["bodyCells"] = [{"row": r, "col": c} for r, c in self.body]
        if self.has_value:
            d["hasValue"] = True
        if self.flexible:
            d["flexible"] = True
        return d


def inline_pins(names, step=1):
    return [Pin(str(i + 1), n, i * step, 0) for i, n in enumerate(names)]


def dip_pins(names):
    n = len(names)
    half = n // 2
    pins = [Pin(str(i + 1), names[i], i, 0) for i in range(half)]
    pins += [Pin(str(half + i + 1), names[half + i], half - 1 - i, 3) for i in range(half)]
    return pins


def dip_def(def_id, name, names):
    half = len(names) // 2
    body = [(r, c) for r in range(half) for c in (1, 2)]
    return PartDef(def_id, name, f"generic-ic-{len(names)}", "U", dip_pins(names), body,
                   category="ic", has_value=False)


# ---- built-in editor parts (ids and footprints exactly as the editor has them)

RESISTOR = PartDef("def-resistor", "Resistor", "resistor", "R",
                   [Pin("1", "1", 0, 0), Pin("2", "2", 4, 0)], category="passive", flexible=True)
CAPACITOR = PartDef("def-capacitor", "Capacitor", "capacitor", "C",
                    [Pin("1", "1", 0, 0), Pin("2", "2", 1, 0)], category="passive", flexible=True)
CAP_POL = PartDef("def-cap-polarized", "Polarized Capacitor", "cap-polarized", "C",
                  [Pin("1", "+", 0, 0), Pin("2", "\u2212", 1, 0)], category="passive", flexible=True)
DIODE = PartDef("def-diode", "Diode", "diode", "D",
                [Pin("1", "A", 0, 0), Pin("2", "K", 3, 0)], category="passive", flexible=True)
PUSHBUTTON = PartDef(
    "def-pushbutton", "Push button (momentary)", "pushbutton", "SW",
    [Pin("1", "1", 0, 0), Pin("1", "1", 0, 3), Pin("2", "2", 2, 0), Pin("2", "2", 2, 3)],
    [(0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (1, 3), (2, 1), (2, 2)],
    category="passive", has_value=False)
TL074 = dip_def("def-ic-tl074", "TL074",
                ["1OUT", "1IN\u2212", "1IN+", "V+", "2IN+", "2IN\u2212", "2OUT",
                 "3OUT", "3IN\u2212", "3IN+", "V\u2212", "4IN+", "4IN\u2212", "4OUT"])
HC4051 = dip_def("def-ic-74hc4051", "74HC4051",
                 ["A4", "A6", "A", "A7", "A5", "/E", "VEE", "GND",
                  "S2", "S1", "S0", "A3", "A0", "A1", "A2", "VCC"])


def connector_def(n):
    return PartDef(f"def-connector-{n}", f"Connector ({n}-pin)", f"connector-{n}", "J",
                   inline_pins([str(i + 1) for i in range(n)]), category="connector", has_value=False)


# ---- custom parts for this build

# Thonkiconn PJ398SM. Real legs sit 0 / 3.1 / 11.4 mm apart in one line
# (sleeve, tip-normal, tip). On 0.1" stripboard they go in holes 0, 1 and 4;
# with the jack centred between them every leg bends by 0.62 mm at most.
# The threaded bushing then sits 5.86 mm from the sleeve hole.
JACK = PartDef(
    "custom-plaitsy-thonkiconn", "Jack 3.5 mm (Thonkiconn PJ398SM)", "connector-3", "J",
    [Pin("1", "S", 0, 1), Pin("2", "TN", 1, 1), Pin("3", "T", 4, 1)],
    [(1, 0), (1, 2), (2, 0), (2, 1), (2, 2), (3, 0), (3, 1), (3, 2), (4, 0), (4, 2)],
    category="connector", custom=True, has_value=False)
JACK_BUSHING_MM = 5.86  # from the sleeve hole towards the tip hole

# Alpha 9 mm vertical pot (RD901F). Legs 2.5 mm apart in one line, shaft
# 7.5 mm behind the leg line. Unrotated: legs in col 4, body to the left,
# CW end (pin 3) on top. Rotated 180: legs in col 0, body to the right,
# CCW end (pin 1) on top - which is what a real pot does when turned.
POT9 = PartDef(
    "custom-plaitsy-alpha9", "Pot, Alpha 9 mm vertical", "potentiometer", "RV",
    [Pin("1", "CCW", 2, 4), Pin("2", "W", 1, 4), Pin("3", "CW", 0, 4)],
    [(r, c) for r in range(3) for c in range(4)],
    category="passive", custom=True)
POT_SHAFT_MM = 7.5

# 3 mm bicolour LED, 3 leads, common cathode, legs bent to the holes:
# red anode (0,0), green anode (1,0), cathode (0,2). The hole between the red
# anode and the cathode, (0,1), must be drilled. The LED body sits high above
# the board (it reaches the panel), centred over (0.5, 1).
LED_BI = PartDef(
    "custom-plaitsy-led-bicolor", "LED 3 mm bicolour R/G, common cathode", "box-l1-b2-r3", "D",
    [Pin("1", "A_R", 0, 0), Pin("2", "K", 0, 2), Pin("3", "A_G", 1, 0)],
    [(0, 1), (1, 1)],
    category="passive", custom=True)


def header_def(def_id, name, n, names=None):
    names = names or [str(i + 1) for i in range(n)]
    return PartDef(def_id, name, f"connector-{n}", "J", inline_pins(names),
                   category="connector", custom=True, has_value=False)


# --------------------------------------------------------------------------
# Placement maths (identical to the editor's boardLayout.ts)
# --------------------------------------------------------------------------

def _extents(pdef):
    rows = [p.r for p in pdef.pins] + [r for r, _ in pdef.body]
    cols = [p.c for p in pdef.pins] + [c for _, c in pdef.body]
    return max(rows), max(cols)


def rotate_offset(r, c, rot, max_r, max_c):
    if rot == 90:
        return c, max_r - r
    if rot == 180:
        return max_r - r, max_c - c
    if rot == 270:
        return max_c - c, r
    return r, c


# --------------------------------------------------------------------------
# Parts on a board
# --------------------------------------------------------------------------

@dataclass
class Part:
    ref: str
    pdef: PartDef
    value: str = ""
    nets: dict = field(default_factory=dict)  # pin id -> net name
    package: str | None = None
    # rigid placement
    pos: tuple | None = None   # (row, col) of the footprint origin
    rot: int = 0
    # flexible placement (pin 1, pin 2)
    p1: tuple | None = None
    p2: tuple | None = None
    # schematic placement
    sch: tuple | None = None   # (x, y)
    sch_rot: int = 0
    sch_mirror: bool = False
    note: str = ""
    low_profile: bool = False   # may sit under the breakout board
    pin_names: dict | None = None  # per-instance pin labels (connectors)

    def pin_positions(self):
        """{pin index: (pin id, (row, col))} - index because a pushbutton
        repeats ids."""
        out = []
        if self.pdef.flexible:
            if self.p1 is None:
                return out
            out.append((self.pdef.pins[0].id, tuple(self.p1)))
            out.append((self.pdef.pins[1].id, tuple(self.p2)))
            return out
        if self.pos is None:
            return out
        mr, mc = _extents(self.pdef)
        for p in self.pdef.pins:
            rr, cc = rotate_offset(p.r, p.c, self.rot, mr, mc)
            out.append((p.id, (self.pos[0] + rr, self.pos[1] + cc)))
        return out

    def body_cells(self):
        if self.pdef.flexible or self.pos is None:
            return []
        mr, mc = _extents(self.pdef)
        return [(self.pos[0] + a, self.pos[1] + b)
                for a, b in (rotate_offset(r, c, self.rot, mr, mc) for r, c in self.pdef.body)]

    def placed(self):
        return (self.p1 is not None) if self.pdef.flexible else (self.pos is not None)

    def net(self, pin_id):
        return self.nets.get(pin_id)


@dataclass
class Wire:
    a: tuple
    b: tuple
    net_hint: str | None = None  # only for drawing


class Board:
    def __init__(self, name, rows, cols):
        self.name = name
        self.rows = rows
        self.cols = cols
        self.parts: dict[str, Part] = {}
        self.cuts: list = []    # (row, col, kind) kind in {"between", "hole"}
        self.wires: list = []   # Wire
        self.notes: list = []

    # ---- building
    def add(self, part: Part):
        assert part.ref not in self.parts, part.ref
        self.parts[part.ref] = part
        return part

    def cut(self, r, c, kind="between"):
        """kind 'between': sever between (r,c) and (r,c+1); 'hole': drill (r,c)."""
        if (r, c, kind) not in self.cuts:
            self.cuts.append((r, c, kind))

    def drill(self, r, c):
        self.cut(r, c, "hole")

    def link(self, a, b, net=None):
        self.wires.append(Wire(tuple(a), tuple(b), net))

    # ---- analysis
    def occupancy(self):
        occ = {}
        errors = []
        for p in self.parts.values():
            for pid, pos in p.pin_positions():
                if pos in occ:
                    errors.append(f"hole {pos} used by {occ[pos]} and {p.ref}.{pid}")
                occ[pos] = f"{p.ref}.{pid}"
        wire_ends = {}
        for i, w in enumerate(self.wires):
            for pos in (w.a, w.b):
                if pos in occ and not occ[pos].startswith("wire#"):
                    errors.append(f"hole {pos} used by {occ[pos]} and wire#{i}")
                wire_ends[pos] = wire_ends.get(pos, 0) + 1
                occ[pos] = f"wire#{i}"
        for pos, n in wire_ends.items():
            if n > 2:
                errors.append(f"hole {pos} holds {n} link wire ends (max 2)")
        return occ, errors

    def segments(self):
        """Map (row, col) -> segment id (None for a drilled hole)."""
        between = {(r, c) for r, c, k in self.cuts if k == "between"}
        holes = {(r, c) for r, c, k in self.cuts if k == "hole"}
        seg = {}
        sid = 0
        for r in range(self.rows):
            sid += 1
            for c in range(self.cols):
                if (r, c) in holes:
                    seg[(r, c)] = None
                    sid += 1
                    continue
                seg[(r, c)] = sid
                if (r, c) in between:
                    sid += 1
        return seg

    def check(self, expected_nets=None, verbose=True):
        """Return (errors, warnings). expected_nets: nets that must be present."""
        errors, warnings = [], []
        occ, errs = self.occupancy()
        errors += errs
        # bounds
        for pos, who in occ.items():
            if not (0 <= pos[0] < self.rows and 0 <= pos[1] < self.cols):
                errors.append(f"{who} at {pos} is off the board")
        # drilled holes must be empty
        for r, c, k in self.cuts:
            if k == "hole" and (r, c) in occ:
                errors.append(f"drilled hole {(r, c)} holds {occ[(r, c)]}")
            if k == "between" and not (0 <= c < self.cols - 1):
                errors.append(f"cut between {(r, c)} is outside the board")
        # bodies
        body_owner = {}
        for p in self.parts.values():
            for cell in p.body_cells():
                if cell in body_owner and body_owner[cell] != p.ref:
                    errors.append(f"bodies of {body_owner[cell]} and {p.ref} overlap at {cell}")
                body_owner[cell] = p.ref
        for pos, who in occ.items():
            owner = body_owner.get(pos)
            if owner and not who.startswith(owner + "."):
                errors.append(f"{who} at {pos} is under the body of {owner}")
        # connectivity
        seg = self.segments()
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for w in self.wires:
            sa, sb_ = seg.get(w.a), seg.get(w.b)
            if sa is None or sb_ is None:
                errors.append(f"wire {w.a}-{w.b} ends in a drilled/off-board hole")
                continue
            union(sa, sb_)
        net_pins = {}
        seg_nets = {}
        for p in self.parts.values():
            pos_by_idx = p.pin_positions()
            # internal joins
            by_id = {}
            for pid, pos in pos_by_idx:
                s = seg.get(pos)
                if s is None:
                    continue
                by_id.setdefault(pid, []).append(s)
            for ss in by_id.values():
                for s in ss[1:]:
                    union(ss[0], s)
            for group in p.pdef.internal_groups:
                ss = [s for pid in group for s in by_id.get(pid, [])]
                for s in ss[1:]:
                    union(ss[0], s)
            for pid, pos in pos_by_idx:
                n = p.net(pid)
                s = seg.get(pos)
                if s is None:
                    continue
                if n:
                    net_pins.setdefault(n, []).append((p.ref, pid, pos, s))
                    seg_nets.setdefault(s, set()).add(n)
        # shorts on one segment
        for s, ns in seg_nets.items():
            if len(ns) > 1:
                where = [pos for pos, ss in seg.items() if ss == s]
                errors.append(f"short on strip segment row {where[0][0]} cols {where[0][1]}-{where[-1][1]}: {sorted(ns)}")
        # shorts through wires / internal joins
        group_nets = {}
        for s, ns in seg_nets.items():
            group_nets.setdefault(find(s), set()).update(ns)
        for g, ns in group_nets.items():
            if len(ns) > 1:
                errors.append(f"short through links: {sorted(ns)}")
        # opens
        for n, pins in sorted(net_pins.items()):
            groups = {find(s) for *_, s in pins}
            if len(groups) > 1:
                parts = {}
                for ref, pid, pos, s in pins:
                    parts.setdefault(find(s), []).append(f"{ref}.{pid}@{pos}")
                errors.append(f"open net {n}: " + " | ".join(", ".join(v) for v in parts.values()))
        # unplaced parts
        for p in self.parts.values():
            if not p.placed():
                warnings.append(f"{p.ref} is not placed")
        if expected_nets:
            for n in expected_nets:
                if n not in net_pins:
                    warnings.append(f"net {n} has no pins on {self.name}")
        if verbose:
            print(f"== {self.name}: {len(self.parts)} parts, {len(self.cuts)} cuts, {len(self.wires)} links")
            for e in errors:
                print("  ERROR", e)
            for w in warnings:
                print("  warn ", w)
            if not errors:
                print("  OK: no shorts, no opens")
        return errors, warnings

    def stats(self):
        return {
            "parts": len(self.parts),
            "cuts_between": sum(1 for *_, k in self.cuts if k == "between"),
            "cuts_drilled": sum(1 for *_, k in self.cuts if k == "hole"),
            "links": len(self.wires),
        }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _font(size):
    from PIL import ImageFont
    for f in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


NET_PALETTE = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46a0b0", "#f032e6",
    "#7fa000", "#c08000", "#008080", "#9a6324", "#800000", "#008000", "#000075",
    "#a9a9a9", "#ff6f91", "#2f4f4f", "#b8860b", "#6a5acd", "#d2691e",
]


def net_color(n, fixed):
    if n in fixed:
        return fixed[n]
    h = sum(ord(ch) * (i + 7) for i, ch in enumerate(n))
    return NET_PALETTE[h % len(NET_PALETTE)]


def render(board: Board, path, copper_side=False, scale=28, title=None, highlight=None,
           fixed_colors=None, extra_marks=None):
    """Draw the board. copper_side mirrors left/right (what you see when you
    flip the board over to cut and solder)."""
    from PIL import Image, ImageDraw
    fixed_colors = fixed_colors or {}
    pad = 3 * scale
    W = board.cols * scale + 2 * pad
    H = board.rows * scale + 2 * pad + (40 if title else 0)
    top = pad + (40 if title else 0)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img, "RGBA")
    f_small = _font(int(scale * 0.38))
    f_lab = _font(int(scale * 0.5))
    f_title = _font(22)

    def X(c):
        cc = (board.cols - 1 - c) if copper_side else c
        return pad + cc * scale + scale // 2

    def Y(r):
        return top + r * scale + scale // 2

    if title:
        d.text((pad, 8), title, fill="black", font=f_title)
    # board outline
    d.rectangle([pad - 4, top - 4, pad + board.cols * scale + 4, top + board.rows * scale + 4],
                fill="#f4ecd8", outline="#a08a5a")
    seg = board.segments()
    # nets per segment (from pins)
    seg_net = {}
    for p in board.parts.values():
        for pid, pos in p.pin_positions():
            n = p.net(pid)
            s = seg.get(pos)
            if n and s is not None:
                seg_net.setdefault(s, set()).add(n)
    # propagate through wires for colouring
    for w in board.wires:
        sa, sb_ = seg.get(w.a), seg.get(w.b)
        if sa and sb_:
            na, nb = seg_net.get(sa), seg_net.get(sb_)
            if na and not nb:
                seg_net[sb_] = set(na)
            elif nb and not na:
                seg_net[sa] = set(nb)
    # strips
    sh = int(scale * 0.62)
    for r in range(board.rows):
        c = 0
        while c < board.cols:
            s = seg[(r, c)]
            if s is None:
                c += 1
                continue
            c2 = c
            while c2 + 1 < board.cols and seg[(r, c2 + 1)] == s:
                c2 += 1
            ns = seg_net.get(s)
            if ns and len(ns) > 1:
                col = "#ff2020"
            elif ns:
                col = net_color(next(iter(ns)), fixed_colors)
            else:
                col = "#d9b36c"
            xa, xb = sorted((X(c), X(c2)))
            alpha = "ff" if ns else "ff"
            d.rectangle([xa - scale // 2 + 2, Y(r) - sh // 2, xb + scale // 2 - 2, Y(r) + sh // 2],
                        fill=col + ("90" if ns else "ff"))
            c = c2 + 1
    # cuts
    for r, c, k in board.cuts:
        if k == "hole":
            d.ellipse([X(c) - scale * 0.42, Y(r) - scale * 0.42, X(c) + scale * 0.42, Y(r) + scale * 0.42],
                      fill="white", outline="#cc0000", width=3)
            d.line([X(c) - scale * 0.3, Y(r) - scale * 0.3, X(c) + scale * 0.3, Y(r) + scale * 0.3], fill="#cc0000", width=3)
        else:
            xm = (X(c) + X(c + 1)) / 2
            d.rectangle([xm - 3, Y(r) - sh // 2 - 2, xm + 3, Y(r) + sh // 2 + 2], fill="#ffffff", outline="#cc0000")
    # holes
    for r in range(board.rows):
        for c in range(board.cols):
            d.ellipse([X(c) - 3, Y(r) - 3, X(c) + 3, Y(r) + 3], fill="#5a4a2a")
    # bodies
    for p in board.parts.values():
        cells = p.body_cells()
        pins = [pos for _, pos in p.pin_positions()]
        if not pins:
            continue
        allc = cells + pins
        if p.pdef.flexible:
            (r1, c1), (r2, c2) = pins
            col = "#3a6ea5" if p.pdef is RESISTOR else ("#c97b2a" if p.pdef in (CAPACITOR, CAP_POL) else "#555555")
            d.line([X(c1), Y(r1), X(c2), Y(r2)], fill=col, width=int(scale * 0.32))
            xm, ym = (X(c1) + X(c2)) / 2, (Y(r1) + Y(r2)) / 2
            txt = p.value or p.ref
            d.text((xm + 4, ym - 8), f"{p.ref} {txt}", fill="#103060", font=f_small)
            continue
        rs = [a for a, _ in allc]
        cs = [b for _, b in allc]
        xa, xb = sorted((X(min(cs)), X(max(cs))))
        d.rectangle([xa - scale * 0.45, Y(min(rs)) - scale * 0.45, xb + scale * 0.45, Y(max(rs)) + scale * 0.45],
                    outline="#202020", width=2, fill=(40, 40, 40, 40))
        d.text((xa - scale * 0.4, Y(min(rs)) - scale * 0.42), p.ref, fill="black", font=f_lab)
    # pins
    for p in board.parts.values():
        for pid, pos in p.pin_positions():
            n = p.net(pid)
            col = net_color(n, fixed_colors) if n else "#999999"
            r, c = pos
            d.ellipse([X(c) - scale * 0.28, Y(r) - scale * 0.28, X(c) + scale * 0.28, Y(r) + scale * 0.28],
                      fill=col, outline="black")
    # wires
    for i, w in enumerate(board.wires):
        (r1, c1), (r2, c2) = w.a, w.b
        d.line([X(c1), Y(r1), X(c2), Y(r2)], fill="#1a1a1a", width=int(scale * 0.18))
        for (rr, cc) in (w.a, w.b):
            d.ellipse([X(cc) - scale * 0.2, Y(rr) - scale * 0.2, X(cc) + scale * 0.2, Y(rr) + scale * 0.2], fill="#1a1a1a")
    # extra marks (panel features etc.)
    for m in (extra_marks or []):
        kind = m[0]
        if kind == "circle":
            _, r, c, rad_mm, col = m
            rad = rad_mm / PITCH * scale
            d.ellipse([X(c) - rad, Y(r) - rad, X(c) + rad, Y(r) + rad], outline=col, width=2)
    # axis labels
    for c in range(board.cols):
        d.text((X(c) - 6, top - pad + 10), str(c), fill="#666666", font=f_small)
        d.text((X(c) - 6, top + board.rows * scale + 12), str(c), fill="#666666", font=f_small)
    for r in range(board.rows):
        d.text((pad - 2.2 * scale, Y(r) - 7), str(r), fill="#666666", font=f_small)
        d.text((pad + board.cols * scale + 0.5 * scale, Y(r) - 7), str(r), fill="#666666", font=f_small)
    img.save(path)
    return path


# --------------------------------------------------------------------------
# Schematic geometry (mirrors symbolDefs.ts / SymbolRenderer.tsx)
# --------------------------------------------------------------------------

def symbol_pins(symbol):
    """{pin id: (x, y, side)} at rotation 0."""
    if symbol in ("resistor", "capacitor", "cap-polarized", "generic-2pin", "inductor"):
        return {"1": (0, -G, "top"), "2": (0, G, "bottom")}
    if symbol in ("diode", "led", "zener"):
        return {"1": (-2 * G, 0, "left"), "2": (2 * G, 0, "right")}
    if symbol == "potentiometer":
        return {"1": (0, -2 * G, "top"), "2": (-2 * G, 0, "left"), "3": (0, 2 * G, "bottom")}
    if symbol == "pushbutton":
        return {"1": (-2 * G, 0, "left"), "2": (2 * G, 0, "right")}
    if symbol.startswith("generic-ic-"):
        n = int(symbol.rsplit("-", 1)[1])
        per = math.ceil(n / 2)
        right = n - per
        half_w = 40
        extent = (per - 1) * G
        y0 = -math.floor(extent / 2 / G) * G
        out = {}
        for i in range(per):
            out[str(i + 1)] = (-half_w - G, y0 + i * G, "left")
        for i in range(right):
            out[str(per + i + 1)] = (half_w + G, y0 + extent - i * G, "right")
        return out
    if symbol.startswith("connector-"):
        n = int(symbol.rsplit("-", 1)[1])
        extent = (n - 1) * G
        y0 = -math.floor(extent / 2 / G) * G
        return {str(i + 1): (-2 * G, y0 + i * G, "left") for i in range(n)}
    if symbol.startswith("box-"):
        sides = {"l": (-2 * G, 0, "left"), "r": (2 * G, 0, "right"), "t": (0, -2 * G, "top"), "b": (0, 2 * G, "bottom")}
        out = {}
        for tok in symbol.split("-")[1:]:
            out[tok[1:]] = sides[tok[0]]
        return out
    raise ValueError(f"unknown symbol {symbol}")


def _rot(x, y, rot, mirror=False):
    if mirror:
        x = -x
    if rot == 90:
        return -y, x
    if rot == 180:
        return -x, -y
    if rot == 270:
        return y, -x
    return x, y


SIDE_VEC = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}


def sch_pin_points(part: Part):
    """{pin id: ((x, y) absolute, (dx, dy) outward unit vector)}"""
    pins = symbol_pins(part.pdef.symbol)
    out = {}
    for pid, (x, y, side) in pins.items():
        px, py = _rot(x, y, part.sch_rot, part.sch_mirror)
        dx, dy = _rot(*SIDE_VEC[side], part.sch_rot, part.sch_mirror)
        out[pid] = ((part.sch[0] + px, part.sch[1] + py), (dx, dy))
    return out


def sch_bbox(part: Part):
    pts = [p for p, _ in sch_pin_points(part).values()] + [part.sch]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def label_rotation(kind, d):
    """Rotation that makes the flag glyph point along d (away from the pin)."""
    dx, dy = d
    if kind == "gnd":  # glyph points down at 0
        return {(0, 1): 0, (-1, 0): 90, (0, -1): 180, (1, 0): 270}[(dx, dy)]
    return {(0, -1): 0, (1, 0): 90, (0, 1): 180, (-1, 0): 270}[(dx, dy)]


# --------------------------------------------------------------------------
# Export to stripboard-editor project JSON
# --------------------------------------------------------------------------

def _uid():
    return str(uuid.uuid4())


GND_NETS = {"GND"}
POWER_NETS = {"+12V", "-12V", "3V3A", "3V3D", "+5V"}


def export_project(board: Board, path, name, description, notes, net_colors=None,
                   stub=2 * G, wiring="touch"):
    """Write an editor project with this board's parts, a label-style
    schematic and the board layout."""
    net_colors = net_colors or {}
    defs = {}
    components = []
    wires = []
    labels = []
    comp_ids = {}
    used_points = set()
    for part in board.parts.values():
        if part.pdef.custom:
            defs[part.pdef.id] = part.pdef.editor_def()
        cid = _uid()
        comp_ids[part.ref] = cid
        comp = {
            "id": cid,
            "defId": part.pdef.id,
            "label": part.ref,
            "schematicPos": {"x": part.sch[0], "y": part.sch[1]},
            "schematicRotation": part.sch_rot,
            "boardPos": None,
            "rotation": 0,
        }
        if part.sch_mirror:
            comp["schematicMirrored"] = True
        if part.value:
            comp["value"] = part.value
        if part.package:
            comp["package"] = part.package
        if part.pdef.flexible:
            if part.p1 is not None:
                comp["boardPos"] = {"row": part.p1[0], "col": part.p1[1]}
                comp["flexibleEndPos"] = {"row": part.p2[0], "col": part.p2[1]}
        else:
            if part.pos is not None:
                comp["boardPos"] = {"row": part.pos[0], "col": part.pos[1]}
                comp["rotation"] = part.rot
        if part.pin_names:
            pd = part.pdef
            comp["footprintOverride"] = {
                "width": pd.width, "height": pd.height,
                "pins": [{"id": p.id, "name": part.pin_names.get(p.id, p.name), "offsetRow": p.r, "offsetCol": p.c}
                         for p in pd.pins],
                **({"bodyCells": [{"row": r, "col": c} for r, c in pd.body]} if pd.body else {}),
            }
        components.append(comp)
        # schematic stubs and labels
        for pid, ((x, y), (dx, dy)) in sch_pin_points(part).items():
            net = part.net(pid)
            if not net:
                continue
            ex, ey = x + dx * stub, y + dy * stub
            wires.append({"id": _uid(), "start": {"x": x, "y": y}, "end": {"x": ex, "y": ey}})
            kind = "gnd" if net in GND_NETS else ("power" if net in POWER_NETS else "label")
            labels.append({"id": _uid(), "kind": kind, "name": net, "pos": {"x": ex, "y": ey},
                           "rotation": label_rotation(kind, (dx, dy))})
            for pt in ((x, y), (ex, ey)):
                used_points.add(pt)
    # nets (the editor recomputes them from the drawing on load; these match)
    nets = {}
    assignments = []
    for part in board.parts.values():
        for pid in {p.id for p in part.pdef.pins}:
            n = part.net(pid)
            if not n:
                continue
            if n not in nets:
                col = net_colors.get(n) or ("#000000" if n in GND_NETS else ("#dc2626" if n in POWER_NETS else net_color(n, {})))
                nets[n] = {"id": _uid(), "name": n, "color": col}
            assignments.append({"netId": nets[n]["id"], "componentId": comp_ids[part.ref], "pinId": pid})
    project = {
        "version": 4,
        "name": name,
        "description": description,
        "notes": notes,
        "componentDefs": list(defs.values()),
        "components": components,
        "nets": list(nets.values()),
        "netAssignments": assignments,
        "schematicWires": wires,
        "netLabels": labels,
        "wiring": wiring,
        "board": {
            "rows": board.rows,
            "cols": board.cols,
            "lockedRows": True,
            "lockedCols": True,
            "cuts": [{"row": r, "col": c, "kind": k} for r, c, k in board.cuts],
            "wires": [{"id": _uid(), "from": {"row": w.a[0], "col": w.a[1]}, "to": {"row": w.b[0], "col": w.b[1]}}
                      for w in board.wires],
        },
        "showValuesOnBoard": True,
        "drilledCutsOnly": False,
        "noWireStacking": True,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=1, ensure_ascii=False)
    return project


def check_schematic_overlaps(board: Board, stub=2 * G):
    """Labels/stubs/pins must not touch anything they should not (touch
    wiring joins whatever touches)."""
    pts = {}
    segs = []
    problems = []
    for part in board.parts.values():
        for pid, ((x, y), (dx, dy)) in sch_pin_points(part).items():
            key = (x, y)
            owner = f"{part.ref}.{pid}"
            if key in pts:
                problems.append(f"pin point {key} shared by {pts[key]} and {owner}")
            pts[key] = owner
            if part.net(pid):
                ex, ey = x + dx * stub, y + dy * stub
                segs.append(((x, y), (ex, ey), owner))
                if (ex, ey) in pts:
                    problems.append(f"label point {(ex, ey)} of {owner} hits {pts[(ex, ey)]}")
                pts[(ex, ey)] = owner + ":label"
    # any point lying on another stub's body
    for (a, b, owner) in segs:
        for key, who in pts.items():
            if who.startswith(owner):
                continue
            x, y = key
            if a[0] == b[0] == x and min(a[1], b[1]) <= y <= max(a[1], b[1]):
                problems.append(f"{who} at {key} touches stub of {owner}")
            if a[1] == b[1] == y and min(a[0], b[0]) <= x <= max(a[0], b[0]):
                problems.append(f"{who} at {key} touches stub of {owner}")
    return problems


# --------------------------------------------------------------------------
# Automatic strip cutting
# --------------------------------------------------------------------------

def _row_occupants(board: Board):
    """{row: [(col, net)]} for every pin and link end. Unconnected pins get a
    private net so they always end up isolated."""
    rows = {}
    for p in board.parts.values():
        for pid, pos in p.pin_positions():
            n = p.net(pid) or f"~nc:{p.ref}.{pid}"
            rows.setdefault(pos[0], []).append((pos[1], n))
    for i, w in enumerate(board.wires):
        n = w.net_hint or f"~wire{i}"
        for pos in (w.a, w.b):
            rows.setdefault(pos[0], []).append((pos[1], n))
    return rows


def autocut(board: Board, avoid=None, prefer=None):
    """Add the cuts needed so no strip segment carries two nets.

    Between two neighbouring occupied holes with different nets a free hole is
    drilled (the one nearest the middle, or nearest `prefer` columns); when
    the holes are adjacent a 'between' cut is made instead. `avoid` is a set
    of (row, col) holes that must not be drilled."""
    avoid = set(avoid or ())
    added = []
    occ_rows = _row_occupants(board)
    for r, items in occ_rows.items():
        items = sorted(items)
        for (c1, n1), (c2, n2) in zip(items, items[1:]):
            if n1 == n2:
                continue
            seg = board.segments()
            if seg[(r, c1)] != seg[(r, c2)]:
                continue  # already separated
            free = [c for c in range(c1 + 1, c2) if (r, c) not in avoid]
            occupied = {c for c, _ in items}
            free = [c for c in free if c not in occupied]
            if free:
                mid = (c1 + c2) / 2
                if prefer:
                    pc = [c for c in free if c in prefer]
                    if pc:
                        free = pc
                c = min(free, key=lambda x: (abs(x - mid), x))
                board.drill(r, c)
                added.append((r, c, "hole"))
            else:
                board.cut(r, c1, "between")
                added.append((r, c1, "between"))
    return added


# --------------------------------------------------------------------------
# Footprint-shaped schematic symbols ("custom-footprint-<id>")
# --------------------------------------------------------------------------

def footprint_symbol_pins(pdef):
    """Mirror of createFootprintSymbol(): pins sit at their footprint
    positions inside a box; the side is the nearest edge."""
    max_r = pdef.height - 1
    max_c = pdef.width - 1
    off_x = (max_c // 2) * G
    off_y = (max_r // 2) * G
    out = {}
    for p in pdef.pins:
        x = p.c * G - off_x
        y = p.r * G - off_y
        d_left, d_right, d_top, d_bottom = p.c, max_c - p.c, p.r, max_r - p.r
        in_col = sum(1 for q in pdef.pins if q.c == p.c)
        in_row = sum(1 for q in pdef.pins if q.r == p.r)
        h = min(d_left, d_right)
        v = min(d_top, d_bottom)
        horizontal = h < v or (h == v and in_col >= in_row)
        if horizontal:
            side = "right" if d_right <= d_left else "left"
        else:
            side = "top" if d_top <= d_bottom else "bottom"
        out[p.id] = (x, y, side)
    return out


_symbol_pins_static = symbol_pins


def symbol_pins_for(pdef):
    if pdef.symbol.startswith("custom-footprint-"):
        return footprint_symbol_pins(pdef)
    return _symbol_pins_static(pdef.symbol)


def sch_pin_points(part: Part):  # noqa: F811 - replaces the earlier version
    pins = symbol_pins_for(part.pdef)
    out = {}
    for pid, (x, y, side) in pins.items():
        px, py = _rot(x, y, part.sch_rot, part.sch_mirror)
        dx, dy = _rot(*SIDE_VEC[side], part.sch_rot, part.sch_mirror)
        out[pid] = ((part.sch[0] + px, part.sch[1] + py), (dx, dy))
    return out


def infer_schematic_nets(parts, stub=2 * G):
    """Python replica of the editor's recalculateNets() for the drawing that
    export_project() produces: wire endpoints and same-named labels join;
    pins join what sits exactly on their point. Returns {(ref, pin): net}."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    label_at = {}
    pin_pts = []
    for part in parts:
        for pid, ((x, y), (dx, dy)) in sch_pin_points(part).items():
            pin_pts.append((part.ref, pid, (x, y)))
            net = part.net(pid)
            if not net:
                continue
            e = (x + dx * stub, y + dy * stub)
            union((x, y), e)
            label_at.setdefault(net, []).append(e)
    for net, pts in label_at.items():
        for p in pts[1:]:
            union(pts[0], p)
    names = {}
    for net, pts in label_at.items():
        names.setdefault(find(pts[0]), set()).add(net)
    result = {}
    for ref, pid, pt in pin_pts:
        root = find(pt)
        ns = names.get(root)
        if ns:
            result[(ref, pid)] = "|".join(sorted(ns))
    return result


def link_nets(board: Board):
    """Net carried by every link wire (from the pins on the strip groups it joins)."""
    seg = board.segments()
    seg_net = {}
    for p in board.parts.values():
        for pid, pos in p.pin_positions():
            n = p.net(pid)
            s = seg.get(pos)
            if n and s is not None:
                seg_net.setdefault(s, set()).add(n)
    # propagate through links until stable
    changed = True
    while changed:
        changed = False
        for w in board.wires:
            sa, sb_ = seg.get(w.a), seg.get(w.b)
            na, nb = seg_net.get(sa, set()), seg_net.get(sb_, set())
            u = na | nb
            if u and (u != na or u != nb):
                seg_net[sa] = set(u)
                seg_net[sb_] = set(u)
                changed = True
    return [(w, "|".join(sorted(seg_net.get(seg.get(w.a), set())))) for w in board.wires]
