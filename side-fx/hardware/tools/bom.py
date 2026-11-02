"""Bill of materials for Side FXy (panel name Moss), generated from circuit.py
(both boards) plus what the netlist does not hold: knobs, the PCBs, standoffs,
the breakout's sockets, the power cable. The Thonk parts get their own table
and file, so they can be ordered in one go.

Every netlist part is owned by exactly one line, and the refs per board are
checked against the routed master's components; a mismatch stops the run.

Writes docs/bom.md and hardware/bom/side-fx-bom.csv (every line, with its
source) and hardware/bom/side-fx-bom-thonk.csv (the Thonk lines alone).
The same file sits in marbles/, plaits/, stereo-mixer/: the code below the
catalogue line is identical, MODULE, BUTTONS, knobs(), EXTRA and NOTES are
the module's own. Copy it, don't import it across modules.
Run from side-fx/hardware/tools:  python bom.py
"""
import collections
import csv
import importlib.util
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.dont_write_bytecode = True


def _load(name):
    spec = importlib.util.spec_from_file_location("bom_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("circuit")
panel = _load("panel")
pcb = _load("pcb")

MODULE = {"project": "Side FXy", "file": "side-fx", "routed": "SideFXy-routed.epro2", "holes": len(circuit.HOLES_FRONT)}
BUTTONS = {"SWLED": "red"}


def knobs():
    """[(source, part, count, note)]: the four encoders' knobs."""
    n = sum(1 for p in circuit.faceplate_parts() if p.kind == "ENC")
    return [("Tayda", f"Knob for a 6 mm D-shaft encoder, about {2 * panel.ART['knob']:.0f} mm across", n,
             "match the encoders' shaft length")]


EXTRA = [        # (source, group, part, qty, note)
    ("Waveshare", "Modules", "Waveshare 1.9inch LCD Module (ST7789V2, 170 × 320, SPI), with its cable", 1,
     "DS1: the glass is taped to the panel's rear, the cable plugs into CN1"),
]
NOTES = [
    "RN1 and RN2 are SIP-9 resistor networks (the 74HC165s' pull-ups), not header strips.",
    "J5 is the MIDI input, a stereo (TRS) Thonkiconn.",
    "Check the EC11's datasheet and height against the panel gap before ordering.",
    "C4 must be a ceramic: an electrolytic is too tall for the gap between the boards.",
]

# ---------------------------------------------------------------- catalogue (the same in every copy)
# Sources: Thonk where the repo orders from it (the module-design skill's parts.md), Tayda / Mouser for the rest.
GROUPS = ["Panel parts", "Modules", "Chips", "Semiconductors", "Resistors", "Capacitors", "Connectors",
          "Mechanical", "PCBs"]
CAPS = {"100n": "100 nF ceramic (X7R), 5.08 mm leads", "1n": "1 nF C0G ceramic or film, 5.08 mm leads",
        "100p": "100 pF C0G ceramic, 5.08 mm leads", "22p": "22 pF C0G ceramic, 5.08 mm leads",
        "1u": "1 µF ceramic (X7R), 5.08 mm leads",
        "10u": "10 µF ceramic (X5R / X7R, 16 V or more), 5.08 mm leads; an electrolytic is too tall"}
CHIPS = {"TL074": ("Thonk", "TL074 quad op-amp (DIP-14) + DIP-14 socket"),
         "MCP4922": ("Mouser", "MCP4922-E/P dual 12-bit DAC (DIP-14) + DIP-14 socket"),
         "MUX": ("Tayda", "74HC4051 8-channel mux (DIP-16) + DIP-16 socket; CD4051B also works"),
         "HC595": ("Tayda", "74HC595 shift register (DIP-16) + DIP-16 socket"),
         "HC165": ("Tayda", "74HC165 shift register (DIP-16) + DIP-16 socket"),
         "H11L1": ("Tayda", "H11L1 opto-isolator (DIP-6) + DIP-6 socket"),
         "CD4013": ("Tayda", "CD4013BE dual D flip-flop (DIP-14) + DIP-14 socket"),
         "CD4093": ("Tayda", "CD4093BE quad Schmitt NAND (DIP-14) + DIP-14 socket"),
         "PHOTOMOS": ("Mouser", "Panasonic AQY212EH PhotoMOS relay (DIP-4)")}
SEMIS = {"NPN": ("Tayda", "Semiconductors", "2N3904 NPN transistor (TO-92)"),
         "BAT85": ("Tayda", "Semiconductors", "BAT85 Schottky diode (DO-35)"),
         "1N4148": ("Tayda", "Semiconductors", "1N4148 diode (DO-35)"),
         "D4148": ("Tayda", "Semiconductors", "1N4148 diode (DO-35)"),
         "D5819": ("Tayda", "Semiconductors", "1N5819 Schottky diode (DO-41)"),
         "LM4040": ("Mouser", "Semiconductors", "LM4040CIZ-2.5/NOPB 2.5 V shunt reference (TO-92); the BIZ grade works too, the AIZ is not needed (the output calibration takes out the error)"),
         "LED_G": ("Thonk", "Panel parts", "3 mm LED, green, 2 leads"),
         "LED_RG": ("Tayda", "Panel parts", "3 mm bicolour LED, red/green, common cathode, 3 leads (Thonk has no 3-lead ones)")}


def ohms(v):
    """circuit.py's resistor values (100k, 1k5, 23k2, 470, 10R) as shop text."""
    if v.endswith("R"):
        return v[:-1] + " Ω"
    if v.isdigit():
        return v + " Ω"
    m = re.fullmatch(r"(\d+)([kM])(\d*)", v)
    return f"{m.group(1)}.{m.group(3)}{m.group(2)}" if m.group(3) else v


def describe(p):
    """(source, group, part) for one netlist part; None for parts build() handles (headers, the Seed)."""
    k, v = p.kind, p.value
    if k == "JACK":
        return "Thonk", "Panel parts", "Thonkiconn PJ398SM mono jack, with nut"
    if k == "JACK_TRS":
        return "Thonk", "Panel parts", "Thonkiconn PJ366ST stereo jack, with nut"
    if k == "POT":
        return "Thonk", "Panel parts", f"Alpha 9 mm vertical pot {v.upper()}, T18 shaft"
    if k == "POT2":
        return "Thonk", "Panel parts", f"Alpha 9 mm vertical dual-gang pot {v.upper()} (RD902F), T18 shaft"
    if k in BUTTONS:
        return "Thonk", "Panel parts", f"Thonk low-profile LED button, {BUTTONS[k]}"
    if k == "ENC":
        return "Tayda", "Panel parts", ("EC11 encoder with push switch, vertical, M7 bushing, D shaft "
                                        "(Bourns PEC11R-4215F-S0024 or Tayda's EC11)")
    if k in CHIPS:
        return CHIPS[k][0], "Chips", CHIPS[k][1]
    if k in SEMIS:
        return SEMIS[k]
    if k == "R":
        return "Tayda", "Resistors", f"Resistor {ohms(v)}, metal film 1 %, 1/4 W"
    if k == "RN9":
        return "Tayda", "Resistors", "10k × 8 bussed resistor network, SIP-9 (Bourns 4609X-101-103LF, Tayda A103J)"
    if k == "C":
        return "Tayda", "Capacitors", "Capacitor " + CAPS[v]
    if k == "CP":
        return "Tayda", "Capacitors", f"Capacitor {v.replace('u', ' µF')} electrolytic, 35 V, 5 mm across, 2.5 mm leads"
    if k == "HDR16":
        return "Thonk", "Connectors", "2×8 shrouded box header, 2.54 mm (Eurorack power)"
    if k == "HDR8RA":
        return "Tayda", "Connectors", "1×8 right-angle male header, 2.54 mm (the display cable's plug lies flat on it)"
    if k.startswith("HDR") or k == "SEED":
        return None
    raise SystemExit(f"bom.py: no catalogue entry for {p.ref} ({k} {v})")


def magnitude(v):
    """A value's size, for sorting: 100k -> 1e5, 1k5 -> 1500, 470 -> 470, 10R -> 10, 100n -> 1e-7."""
    m = re.fullmatch(r"(\d+)([RkMpnu]?)(\d*)", v or "")
    if not m:
        return 0.0
    mult = {"": 1, "R": 1, "k": 1e3, "M": 1e6, "p": 1e-12, "n": 1e-9, "u": 1e-6}[m.group(2)]
    return float(f"{m.group(1)}.{m.group(3) or 0}") * mult


def natural(ref):
    m = re.match(r"([A-Z]+)(\d*)", ref)
    return m.group(1), int(m.group(2) or 0), ref


def build():
    """lines {(source, group, part): {"qty", "refs" [(board, ref)], "note"}} and owned {(board, ref): n}."""
    lines = collections.OrderedDict()
    owned = collections.Counter()

    def add(source, group, part, qty=1, refs=(), note="", owns=True, size=0.0):
        line = lines.setdefault((source, group, part), {"qty": 0, "refs": [], "note": note, "size": size})
        line["refs"] += list(refs)
        line["qty"] += qty
        if owns:
            owned.update(refs)

    headers = collections.Counter()               # (gender, pins) -> count
    header_refs = collections.defaultdict(list)
    for board, parts in (("Main", circuit.main_board_parts()), ("Faceplate", circuit.faceplate_parts())):
        for p in parts:
            d = describe(p)
            if d:
                add(*d, refs=[(board, p.ref)], size=magnitude(p.value) if p.kind in ("R", "C", "CP") else 0.0)
            elif p.kind.startswith("HDR"):
                gender = "male" if board == "Faceplate" else "female"
                headers[(gender, int(p.kind[3:]))] += 1
                header_refs[gender].append((board, p.ref))
                owned[(board, p.ref)] += 1
            elif p.kind == "SEED":
                add("Thonk", "Modules", "Electrosmith Daisy Seed", refs=[(board, p.ref)])
                add("OSHWLab / JLCPCB", "Modules", "Rob Heel's seed_power_opamps breakout, built: its own PCB and parts",
                    refs=[(board, p.ref)], owns=False, note="carries the Seed, the Eurorack power header and the audio stages")
                add("Tayda", "Connectors", "Female header 2.54 mm, 8.5 mm tall, for the breakout's two rows on the main "
                    "board: 2 × 1×24 (audio header + Seed pins) and 2 × 1×4 (power header, after one empty position)",
                    qty=4, refs=[(board, p.ref)], owns=False, note="cut from 1×40 strips; male pins under the breakout")
                add("Thonk", "Connectors", "Eurorack power cable for the breakout's power header",
                    note="check the header's pin count (10 or 16)")
    for gender in ("male", "female"):
        sizes = sorted(((pins, n) for (g, pins), n in headers.items() if g == gender), reverse=True)
        if sizes:
            kind = "Male pin header, 2.54 mm" if gender == "male" else "Female header, 2.54 mm, 8.5 mm tall"
            add("Thonk", "Connectors", f"{kind}: " + ", ".join(f"{n} × 1×{pins}" for pins, n in sizes),
                qty=sum(n for _, n in sizes), refs=header_refs[gender], owns=False,
                note=("faceplate side" if gender == "male" else "main board side")
                + "; Thonk's Male + Female Header Bag or cut from 40-pin strips")
    for source, part, n, note in knobs():
        if n:
            add(source, "Mechanical", part, qty=n, note=note)
    for source, group, part, qty, note in EXTRA:
        add(source, group, part, qty=qty, note=note)
    add("Tayda", "Mechanical", "M3 standoff, female-female, the mated headers' height (about 8.5 mm), + 2 M3 screws",
        qty=MODULE["holes"], note="one per mounting hole between the boards; measure the mated headers first")
    (w, h), _ = routed()["Main"]
    add("JLCPCB", "PCBs", f"Main board + faceplate board, {w:.1f} × {h:.1f} mm each, 2 layers, 1.6 mm", qty=1,
        note=f"from {MODULE['routed']}")
    add("JLCPCB", "PCBs", f"Panel {panel.PANEL_W:.1f} × {panel.PANEL_H} mm, 1.6 mm FR4: black mask, white silk, ENIG",
        qty=1, note=f"the panel board in {MODULE['routed']}; ENIG makes the bands and the mushroom gold")
    return lines, owned


def routed():
    """{"Main" / "Faceplate": ((width, height) mm, set of designators)} from the routed master's PCB documents."""
    with zipfile.ZipFile(os.path.join(ROOT, "hardware", "easyeda", MODULE["routed"])) as z:
        raw = z.read(next(n for n in z.namelist() if n.endswith(".epru"))).decode("utf-8")
    cur, titles, refs, size = None, {}, collections.defaultdict(set), {}
    for line in raw.split("\n"):
        if not line:
            continue
        head, _, body = line.partition("||")
        h = json.loads(head)
        body = body[:-1] if body.endswith("|") else body
        p = json.loads(body) if body else None
        if h["type"] == "DOCHEAD":
            cur = p["uuid"] if p["docType"] == "PCB" else None
        elif cur and h["type"] == "META":
            titles[cur] = p["title"]
        elif cur and h["type"] == "ATTR" and p.get("key") == "Designator" and p.get("value"):
            refs[cur].add(p["value"])
        elif cur and h["type"] == "POLY" and p.get("polyType") == "BOARD_OUTLINE" and p["path"][0] == "R":
            size[cur] = (p["path"][3] * 0.0254, p["path"][4] * 0.0254)       # "R", x, y, width, height in mil
    return {word: (size[u], refs[u]) for u, t in titles.items() for word in ("Main", "Faceplate") if word in t.split()}


def check(owned):
    problems = []
    mine = {"Main": {p.ref for p in circuit.main_board_parts()}, "Faceplate": {p.ref for p in circuit.faceplate_parts()}}
    for board, refs in mine.items():
        for ref in sorted(refs, key=natural):
            if owned[(board, ref)] != 1:
                problems.append(f"{board} {ref} is owned by {owned[(board, ref)]} lines")
    boards = routed()
    for board, refs in mine.items():
        got = boards.get(board, (None, set()))[1]
        if got != refs:
            problems.append(f"{board} board: only in {MODULE['routed']} {sorted(got - refs, key=natural)}, "
                            f"only in circuit.py {sorted(refs - got, key=natural)}")
    return problems


def write(lines):
    rows = []
    for (source, group, part), line in lines.items():
        refs = sorted(set(line["refs"]), key=lambda br: (br[0], natural(br[1])))
        boards = sorted({b for b, _ in refs})
        if len(boards) > 1:          # say which ref is on which board
            text = "; ".join(f"{b}: " + ", ".join(r for bb, r in refs if bb == b) for b in boards)
        else:
            text = ", ".join(r for _, r in refs)
        rows.append({"Source": source, "Group": group, "Qty": line["qty"], "Part": part, "Refs": text,
                     "Board": " + ".join(boards) or "—", "Note": line["note"], "_size": line["size"]})
    rows.sort(key=lambda r: (r["Source"] != "Thonk", r["Source"], GROUPS.index(r["Group"]), r["_size"], r["Part"]))
    os.makedirs(os.path.join(ROOT, "hardware", "bom"), exist_ok=True)
    fields = ["Source", "Group", "Qty", "Part", "Refs", "Board", "Note"]
    for suffix, keep in (("", lambda r: True), ("-thonk", lambda r: r["Source"] == "Thonk")):
        with open(os.path.join(ROOT, "hardware", "bom", f"{MODULE['file']}-bom{suffix}.csv"), "w",
                  newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(r for r in rows if keep(r))

    def table(sel):
        return ["| Qty | Part | Refs | Board | Note |", "|---|---|---|---|---|"] + [
            f"| {r['Qty']} | {r['Part']} | {r['Refs']} | {r['Board']} | {r['Note']} |" for r in sel]

    A = panel.ART
    hp = round((panel.PANEL_W + 0.3) / 5.08)
    md = [f"# {MODULE['project']} BOM: {A['title']}, {A['subtitle'].lower()}, {hp}HP", "",
          "Generated by `hardware/tools/bom.py` from `circuit.py`: don't edit it by hand. Quantities are for",
          f"one module. The netlist's refs are checked against `{MODULE['routed']}`, board by board.",
          f"CSV: `hardware/bom/{MODULE['file']}-bom.csv` (everything) and `hardware/bom/{MODULE['file']}-bom-thonk.csv`",
          "(the Thonk lines).", "", "## From Thonk", ""]
    md += table([r for r in rows if r["Source"] == "Thonk"])
    md += ["", "## Everything else", ""]
    for source in sorted({r["Source"] for r in rows} - {"Thonk"}):
        md += [f"### {source}", ""] + table([r for r in rows if r["Source"] == source]) + [""]
    md += ["## Notes", ""] + [f"- {n}" for n in NOTES] + [""]
    with open(os.path.join(ROOT, "docs", "bom.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return rows


def main():
    lines, owned = build()
    problems = check(owned)
    rows = write(lines)
    thonk = [r for r in rows if r["Source"] == "Thonk"]
    print(f"{MODULE['project']}: {len(rows)} lines, {len(thonk)} from Thonk ({sum(r['Qty'] for r in thonk)} items); "
          f"{len(problems)} problems")
    for p in problems:
        print("  ", p)
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
