"""Netlist and pinout integrity of the stereo mixer (Mycelium).

What it checks
  A  circuit.py on its own: unique designators per board, no single-pin nets,
     every header pin pair used on both boards, faceplate nets end in _F and
     main-board nets never do, no net on both boards except through a header.
  B  circuit.py's pin maps (SECTION, NAND, FLOP, MUX, J18, jacks, pots,
     buttons) against the manufacturers' pinouts (constants block below); the
     latch and each channel's CD4053B mute switch (U11-U18: commons on the bus
     resistors' summing ends, x throws on the buses, y throws on GND, selects
     on Q, INH / VEE / VSS on GND, VDD on +12V), the mute's polarity and the
     button LED chain; the CD4053B symbol's pin names in the routed master
     and in the generated project against the datasheet.
  C  The diodes and polarised caps: cathode / + pin in the symbol AND the
     footprint actually used (pin names, silkscreen band, + mark), then
     whether D901 / D902 block a reversed cable, D903 empties C906 at
     power-off, C904 / C905 sit with + on the more positive net.
  D  The routed master (StereoMixer-routed.epro2): every pad's net on both
     PCBs against circuit.py, designators complete, no extra or missing
     parts (own parser, independent of copper_audit.py's code); the DIP-14,
     DIP-16, jack, J18, button and pot footprints the pin maps rely on. Since
     2026-11-15 the master's main board is the generated placement, unrouted.
  E  Header stacking: for H1-H9, the faceplate pin and the main-board pin that
     land at the same spot when the boards are stacked carry X and X_F. The
     pad transform is validated against the routed faceplate's track ends on
     both layers (the main board has no tracks yet).
  F  Schematic pages in the routed master and in the generated
     StereoMixer.epro2 against circuit.py (pin positions joined to wires).
  G  design.md's tables (latch with the mute switches and bus resistors,
     op-amps, headers, signal flow, what the mute switches) against circuit.py.

Run from stereo-mixer/hardware/tests:  python test_netlist.py
Only reads: imports circuit.py, opens the two exports as zip files.
"""
import collections
import json
import math
import os
import re
import zipfile

import harness

ck = harness.Checks("netlist")
circuit = harness.load("circuit")
MIL = 0.0254

# ----------------------------------------------------------------------------------------------------------
# Datasheet pinouts (pin numbers are exact facts, no min/typ/max)
# TI SLOS080 "TL07xx Low-Noise FET-Input Operational Amplifiers", pin functions, N (PDIP-14) package:
TL074_DS = {"1OUT": "1", "1IN-": "2", "1IN+": "3", "VCC+": "4", "2IN+": "5", "2IN-": "6", "2OUT": "7",
            "3OUT": "8", "3IN-": "9", "3IN+": "10", "VCC-": "11", "4IN+": "12", "4IN-": "13", "4OUT": "14"}
# TI SCHS115 "CD4093B Types, CMOS Quad 2-Input NAND Schmitt Triggers", terminal assignment:
# gate 1 inputs A 1 / B 2 -> J 3; gate 2 C 5 / D 6 -> K 4; gate 3 E 8 / F 9 -> L 10; gate 4 G 12 / H 13 -> M 11
CD4093_DS = {1: ("1", "2", "3"), 2: ("5", "6", "4"), 3: ("8", "9", "10"), 4: ("12", "13", "11"),
             "VDD": "14", "VSS": "7"}
# TI SCHS023 "CD4013B Types, CMOS Dual D-Type Flip-Flop", terminal assignment:
# Q1 1, /Q1 2, CLOCK1 3, RESET1 4, DATA1 5, SET1 6, VSS 7, SET2 8, DATA2 9, RESET2 10, CLOCK2 11, /Q2 12, Q2 13, VDD 14
CD4013_DS = {1: {"Q": "1", "QN": "2", "CLK": "3", "RESET": "4", "D": "5", "SET": "6"},
             2: {"Q": "13", "QN": "12", "CLK": "11", "RESET": "10", "D": "9", "SET": "8"}, "VDD": "14", "VSS": "7"}
# CD4013B truth table (SCHS023): data is taken on the POSITIVE clock edge; RESET and SET are active HIGH.
# TI SCHS047O "CD4051B, CD4052B, CD4053B" (rev. O, May 2026), Figure 4-3 (16-pin PDIP, top view) and Table 4-3
# "Pin Functions CD4053B": 1 BY, 2 BX, 3 CY, 4 C common ("CX OR CY OUT/IN"), 5 CX, 6 INH, 7 VEE, 8 VSS, 9 C,
# 10 B, 11 A (the channel selects), 12 AX, 13 AY, 14 A common ("AX OR AY OUT/IN"), 15 B common, 16 VDD.
CD4053B_DS = {"BY": "1", "BX": "2", "CY": "3", "C COM": "4", "CX": "5", "INH": "6", "VEE": "7", "VSS": "8",
              "C": "9", "B": "10", "A": "11", "AX": "12", "AY": "13", "A COM": "14", "B COM": "15", "VDD": "16"}
# Truth table (SCHS047O Table 7-1, CD4053B): INH 0 and select A 0 -> ax on, A 1 -> ay on (b, c the same with
# B, C); INH 1 -> every channel off.
# Doepfer A-100 "Technical details / bus" (doepfer.de/a100_man/a100t_e.htm, pinout image a100b_e.gif), 16-pin
# module header, pairs from the red stripe: 1, 2 = -12 V, 3-8 = GND, 9, 10 = +12 V, 11, 12 = +5 V, 13, 14 = CV,
# 15, 16 = Gate. (Until 2026-11-14 this table had GND on 3-10 and +12 V on 11-12, as the design did.)
EURORACK_DS = {"-12V": {"1", "2"}, "GND": {str(n) for n in range(3, 9)}, "+12V": {"9", "10"},
               "+5V": {"11", "12"}, "CV": {"13", "14"}, "GATE": {"15", "16"}}
# Thonkiconn PJ398SM / QingPu WQP518MA: KiCad Connector_Audio
# Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles.kicad_mod (gitlab.com/kicad/libraries/kicad-footprints):
# S (sleeve) at (0, 0), TN (tip switch) at (0, 3.1), T (tip) at (0, 11.4), barrel centre (0, 6.48), mm.
# The TN lug touches the tip spring with no plug in (switched, normally closed: Thonk / QingPu PJ398SM).
JACK_KICAD = {"S": 0.0, "TN": 3.1, "T": 11.4, "barrel": 6.48}
# Alpha RD902F-40 dual (KiCad Potentiometer_Alpha_RD902F-40-00D_Dual_Vertical.kicad_mod): pins 1, 2, 3 at
# (0, 0), (0, 2.5), (0, 5), pins 4, 5, 6 at (-2.5, 0 / 2.5 / 5), shaft centre (7.5, 2.5): gang 1-3 is the row
# nearer the shaft, 4-6 runs the same way. Alpha / Bourns convention for every rotary pot: seen from the shaft
# with the pins at the bottom, pins 1-2-3 run left to right and turning clockwise moves the wiper (2) to 3.
POT2_KICAD = {"1": (0, 0), "2": (0, 2.5), "3": (0, 5), "4": (-2.5, 0), "5": (-2.5, 2.5), "6": (-2.5, 5),
              "shaft": (7.5, 2.5)}
# Thonk low-profile LED button: Thonk's LowProfileButton.pdf / SW_Tact_Low_Profile_LED_ExtraHoles.kicad_mod as
# recorded in .claude/skills/module-design/references/parts.md (NOT re-confirmed in this run: Thonk's site blocks
# fetches and no public copy was found): contacts 1+2 and 3+4, LED anode 5 (L1), cathode 6 (L2).
BUTTON_DS = {"contact_a": {"1", "2"}, "contact_b": {"3", "4"}, "LED_A": "5", "LED_K": "6"}
# Diodes: 1N5819 (DO-41) and BAT85 (DO-35), the band marks the cathode (onsemi 1N5817-D, Vishay BAT85 sheets).


# ----------------------------------------------------------------------------------------------------------
# A  circuit.py on its own
MB, FB = circuit.main_board_parts(), circuit.faceplate_parts()
MBN, FBN = circuit.nets_of(MB), circuit.nets_of(FB)
PARTS = {"main": {p.ref: p for p in MB}, "face": {p.ref: p for p in FB}}

for name, parts in (("main", MB), ("face", FB)):
    dup = [r for r, n in collections.Counter(p.ref for p in parts).items() if n > 1]
    ck.check(f"A.unique_refs.{name}", not dup, f"expected no duplicate designators, got {dup}")
    nets = circuit.nets_of(parts)
    single = {n: v for n, v in nets.items() if len(v) < 2}
    ck.check(f"A.no_single_pin_nets.{name}", not single, f"expected every net on >= 2 pins, got {single}")

ck.check("A.part_counts", (len(MB), len(FB)) == (175, 59),
         f"README: main board 175 parts (2026-11-15: 159 - the 10 AQY212EH + 8 CD4053B + their 8 100 n + 10 x 10 p "
         f"on the follower inputs), faceplate 59; "
         f"got {len(MB)}, {len(FB)}")

bad_pairs = []
for ref, kind, pins in circuit.HEADERS:
    for i, (a, b) in enumerate(pins):
        expect_b = "GND_F" if a == "GND" else a + "_F"
        if b != expect_b or len(MBN[a]) < 2 or len(FBN[b]) < 2:
            bad_pairs.append((ref, i + 1, a, b, len(MBN[a]), len(FBN[b])))
ck.check("A.header_pairs_used_both_boards", not bad_pairs,
         f"expected every header pin's X on >= 2 main pins and X_F on >= 2 faceplate pins, got {bad_pairs}")

fb_bad = sorted(n for n in FBN if not n.endswith("_F"))
mb_bad = sorted(n for n in MBN if n.endswith("_F"))
ck.check("A.faceplate_nets_end_in_F", not fb_bad, f"expected all faceplate nets *_F, got {fb_bad}")
ck.check("A.main_nets_never_F", not mb_bad, f"expected no main-board net *_F, got {mb_bad}")
shared = sorted(set(MBN) & set(FBN))
ck.check("A.no_net_on_both_boards", not shared, f"expected no net name on both boards, got {shared}")
# every faceplate net that is not GND_F and every main net that leaves the board must cross through a header
hdr_mb = {a for _, _, pins in circuit.HEADERS for a, b in pins}
hdr_fb = {b for _, _, pins in circuit.HEADERS for a, b in pins}
fb_local = sorted(n for n in FBN if n not in hdr_fb)
# faceplate-only nets are allowed only when they stay between panel parts (jack tips into pots, normalling)
# verifier addition: a faceplate net X_F whose X also exists on the main board must cross through a header pin pair
# (otherwise the two halves are named as one signal but nothing joins them)
named_pairs = sorted(n[:-2] for n in FBN if n != "GND_F" and n[:-2] in MBN and n[:-2] not in hdr_mb)
ck.check("A.cross_board_names_only_via_headers", not named_pairs,
         f"X / X_F pairs on the two boards with no header pin joining them: {named_pairs}")
ck.check("A.faceplate_local_nets_are_panel_only",
         all(all(not pin.startswith("HF") for pin in FBN[n]) for n in fb_local),
         f"faceplate-only nets {fb_local}")
# both header sides have the same pin count and the same order on both boards
hdr_ok = all(len(PARTS["main"][ref].nets) == len(pins) == len(PARTS["face"][circuit.fb_ref(ref)].nets)
             and all(PARTS["main"][ref].nets[str(i + 1)] == a and
                     PARTS["face"][circuit.fb_ref(ref)].nets[str(i + 1)] == b for i, (a, b) in enumerate(pins))
             for ref, _, pins in circuit.HEADERS)
ck.check("A.header_parts_match_HEADERS", hdr_ok, "H<n> / HF<n> pin nets equal circuit.HEADERS on both boards")
gnd_pins = sum(1 for _, _, pins in circuit.HEADERS for a, _ in pins if a == "GND")
ck.check("A.header_pin_total", sum(len(p) for _, _, p in circuit.HEADERS) == 76,
         f"design.md: 76 pins in 9 headers; got {sum(len(p) for _, _, p in circuit.HEADERS)} "
         f"in {len(circuit.HEADERS)}")
every_hdr_has_gnd = [ref for ref, _, pins in circuit.HEADERS if not any(a == "GND" for a, _ in pins)]
ck.check("A.every_header_has_ground", not every_hdr_has_gnd, f"headers without a GND pin: {every_hdr_has_gnd}")

# ----------------------------------------------------------------------------------------------------------
# B  pin maps against the datasheets
sec_ds = {s: (TL074_DS[f"{s}OUT"], TL074_DS[f"{s}IN-"], TL074_DS[f"{s}IN+"]) for s in (1, 2, 3, 4)}
ck.check("B.TL074_SECTION", circuit.SECTION == sec_ds, f"expected {sec_ds}, got {circuit.SECTION}")
for u in ("U1", "U2", "U3", "U4"):
    n = PARTS["main"][u].nets
    ck.check(f"B.TL074_supply.{u}", n.get(TL074_DS["VCC+"]) == "+12V" and n.get(TL074_DS["VCC-"]) == "-12V",
             f"expected pin 4 +12V, pin 11 -12V; got 4={n.get('4')}, 11={n.get('11')}")
    ck.check(f"B.TL074_all_pins_used.{u}", set(n) == set(TL074_DS.values()), f"pins {sorted(n, key=int)}")
nand_ds = {g: CD4093_DS[g] for g in (1, 2, 3, 4)}
ck.check("B.CD4093_NAND", circuit.NAND == nand_ds, f"expected {nand_ds}, got {circuit.NAND}")
flop_ds = {h: tuple(CD4013_DS[h][k] for k in ("Q", "QN", "CLK", "RESET", "D", "SET")) for h in (1, 2)}
ck.check("B.CD4013_FLOP", circuit.FLOP == flop_ds, f"expected {flop_ds}, got {circuit.FLOP}")
for u in ("U5", "U6", "U7", "U8", "U9", "U10"):
    n = PARTS["main"][u].nets
    ck.check(f"B.CMOS_supply.{u}", n.get("14") == "+12V" and n.get("7") == "GND" and len(n) == 14,
             f"expected VDD 14 = +12V, VSS 7 = GND, all 14 pins tied; got 14={n.get('14')}, 7={n.get('7')}, "
             f"{len(n)} pins")
# the latch logic itself: CD4093 inputs tied (Schmitt inverter) from DB, output CK to the clock; D = /Q;
# SET to GND (inactive, active high); RESET = POR (active high: high at power-up -> Q low = unmuted)
logic_bad = []
for k in circuit.MONO + circuit.STEREO:
    u, g = circuit.NAND_OF[k]
    a, b, y = CD4093_DS[g]
    n = PARTS["main"][u].nets
    if not (n[a] == n[b] == f"DB{k}" and n[y] == f"CK{k}"):
        logic_bad.append((k, u, g, n[a], n[b], n[y]))
    u, h = circuit.FLOP_OF[k]
    n = PARTS["main"][u].nets
    f = CD4013_DS[h]
    if not (n[f["CLK"]] == f"CK{k}" and n[f["D"]] == n[f["QN"]] == f"QN{k}" and n[f["Q"]] == f"QK{k}"
            and n[f["SET"]] == "GND" and n[f["RESET"]] == "POR"):
        logic_bad.append((k, u, h, {kk: n[v] for kk, v in f.items()}))
ck.check("B.latch_toggle_wiring", not logic_bad, f"expected NAND(DB,DB)->CK->CLK, D=/Q, SET=GND, RESET=POR; "
                                                 f"bad: {logic_bad}")
used_gates = collections.Counter(circuit.NAND_OF.values())
used_halves = collections.Counter(circuit.FLOP_OF.values())
ck.check("B.latch_gates_unique", max(used_gates.values()) == 1 and max(used_halves.values()) == 1,
         f"each gate / flip-flop half serves one channel: {used_gates}, {used_halves}")
# The mute switch (2026-11-15): circuit.MUX's (common, x, y, select) per section against the datasheet; section a
# serves the L bus, b the R bus, c the send bus (design.md, "Mute")
SECTION_OF = {"L": "A", "R": "B", "S": "C"}
mux_ds = {bus: (CD4053B_DS[f"{s} COM"], CD4053B_DS[f"{s}X"], CD4053B_DS[f"{s}Y"], CD4053B_DS[s])
          for bus, s in SECTION_OF.items()}
ck.check("B.CD4053B_MUX", circuit.MUX == mux_ds, f"SCHS047O Table 4-3 as (common, x, y, select): expected {mux_ds}, "
                                                 f"got {circuit.MUX}")
ck.check("B.mute_switch_refs", circuit.SWITCH == {k: f"U{10 + k}" for k in circuit.MONO + circuit.STEREO}
         and all(PARTS["main"][u].kind == "CD4053" and PARTS["main"][u].value == "CD4053B"
                 for u in circuit.SWITCH.values()),
         f"one CD4053B per channel, U11-U18 (design.md); got {circuit.SWITCH}")
# every channel's switch, pin by pin: common on the bus resistor's summing end, x on the bus, y on GND, select on
# Q; INH (6) low, VEE (7) = VSS (8) = GND, VDD (16) = +12V; all 16 pins tied
for k in circuit.MONO + circuit.STEREO:
    u = circuit.SWITCH[k]
    n = PARTS["main"][u].nets
    want = {CD4053B_DS["INH"]: "GND", CD4053B_DS["VEE"]: "GND", CD4053B_DS["VSS"]: "GND", CD4053B_DS["VDD"]: "+12V"}
    for bus, s in SECTION_OF.items():
        want.update({CD4053B_DS[f"{s} COM"]: f"B{bus}{k}", CD4053B_DS[f"{s}X"]: f"SUM_{bus}",
                     CD4053B_DS[f"{s}Y"]: "GND", CD4053B_DS[s]: f"QK{k}"})
    diff = {p: (n.get(p), want.get(p)) for p in sorted(set(n) | set(want), key=int) if n.get(p) != want.get(p)}
    ck.check(f"B.mute_switch_wiring.{u}", not diff and len(n) == 16,
             f"channel {k}: pin: (circuit, datasheet-derived) differ at {diff}; {len(n)} pins tied")
# each switched net is just the bus resistor's summing end and the common: nothing else may hang on it
cold_bad = []
for k in circuit.MONO + circuit.STEREO:
    u = circuit.SWITCH[k]
    hot = ({"L": f"PL{k}", "R": f"PR{k}", "S": f"SD{k}"} if k in circuit.MONO else
           {"L": f"CH{k}L", "R": f"CH{k}R", "S": f"SD{k}"})
    for bus, s in SECTION_OF.items():
        pins = sorted(MBN[f"B{bus}{k}"])
        rs = [p.split(".")[0] for p in pins if p.split(".")[0] != u]
        ok = (len(pins) == 2 and f"{u}.{CD4053B_DS[f'{s} COM']}" in pins and len(rs) == 1
              and PARTS["main"][rs[0]].kind == "R" and set(PARTS["main"][rs[0]].nets.values()) == {hot[bus], f"B{bus}{k}"})
        if not ok:
            cold_bad.append((k, bus, pins))
ck.check("B.bus_resistor_ends_on_the_commons", not cold_bad,
         f"B<bus><k> = one bus resistor (from PL / PR / SD, or CH L / R on a stereo channel) and the switch common; "
         f"bad: {cold_bad}")
# the summing nodes: every channel reaches a bus only through its switch's x throw; the rest of each node is the
# summer (IN-, Rf, Cf) and the unswitched inputs (RETURN, DRUMS, FX IN)
sum_bad = {}
for bus, s in SECTION_OF.items():
    members = MBN[f"SUM_{bus}"]
    xs = {f"{circuit.SWITCH[k]}.{CD4053B_DS[f'{s}X']}" for k in circuit.MONO + circuit.STEREO}
    chan = [m for m in members if m not in xs and re.fullmatch(r"[RC][1-8]\d\d\.\d+", m)]
    if not xs <= set(members) or chan:
        sum_bad[bus] = {"x throws missing": sorted(xs - set(members)), "channel parts straight on the node": chan}
ck.check("B.channels_reach_the_buses_only_through_the_switch", not sum_bad,
         f"SUM_L / SUM_R / SUM_S: {sum_bad or {b: sorted(MBN[f'SUM_{b}']) for b in SECTION_OF}}")
# polarity: Q high = muted. The selects sit on Q (QK); select high puts the y throw (GND) on, so the bus resistor's
# end is grounded and the channel leaves the bus; select low (Q low, as RESET leaves it at power-up) puts x (the
# bus) on. The LED resistor on the same Q lights the button while muted.
pol_bad = []
for k in circuit.MONO + circuit.STEREO:
    u = circuit.SWITCH[k]
    n = PARTS["main"][u].nets
    fq = PARTS["main"][circuit.FLOP_OF[k][0]].nets[CD4013_DS[circuit.FLOP_OF[k][1]]["Q"]]
    for bus, s in SECTION_OF.items():
        sel = n[CD4053B_DS[s]]
        on_high, on_low = n[CD4053B_DS[f"{s}Y"]], n[CD4053B_DS[f"{s}X"]]
        if not (sel == fq and on_high == "GND" and on_low == f"SUM_{bus}"):
            pol_bad.append((u, bus, "select", sel, "flip-flop Q", fq, "on when high", on_high, "on when low", on_low))
ck.check("B.mute_polarity_Q_high_mutes", not pol_bad,
         f"select = the CD4013 Q; Q high -> y = GND (muted), Q low (power-up reset) -> x = SUM (playing); bad: {pol_bad}")
# the button LED: Q -> LED resistor -> LED<k> -> header -> button LED anode (5), cathode (6) -> GND_F, lit = muted
led_bad = []
for k in circuit.MONO + circuit.STEREO:
    rq = [p for p in MB if p.kind == "R" and set(p.nets.values()) == {f"QK{k}", f"LED{k}"}]
    if len(rq) != 1:
        led_bad.append((k, "no single QK-LED resistor", [p.ref for p in rq]))
    others = sorted(m for m in MBN[f"LED{k}"] if not (rq and m.startswith(rq[0].ref + ".")))
    if len(others) != 1 or not others[0].startswith(f"H{k}."):
        led_bad.append((k, f"LED{k} beyond the resistor", others))
    sw = PARTS["face"][f"SW{k}"].nets
    if sw[BUTTON_DS["LED_A"]] != f"LED{k}_F" or sw[BUTTON_DS["LED_K"]] != "GND_F":
        led_bad.append((f"SW{k}", "LED", sw[BUTTON_DS["LED_A"]], sw[BUTTON_DS["LED_K"]]))
ck.check("B.mute_LED_chain_polarity", not led_bad,
         f"expected Q -> LED resistor -> LED<k> -> H<k> -> button 5(A) -> 6(K) -> GND_F; bad: {led_bad}")

# J18 against the Doepfer bus
j18 = PARTS["main"]["J18"].nets
by_net = collections.defaultdict(set)
for pin, n in j18.items():
    by_net[n].add(pin)
ck.check("B.J18_minus12", by_net["N12_IN"] == EURORACK_DS["-12V"], f"expected -12V on {EURORACK_DS['-12V']}, "
                                                                    f"got N12_IN on {sorted(by_net['N12_IN'])}")
ck.check("B.J18_plus12", by_net["P12_IN"] == EURORACK_DS["+12V"], f"expected +12V on {EURORACK_DS['+12V']}, "
                                                                  f"got P12_IN on {sorted(by_net['P12_IN'])}")
ck.check("B.J18_gnd", by_net["GND"] == EURORACK_DS["GND"], f"expected GND on 3-8, got {sorted(by_net['GND'], key=int)}")
OPEN = EURORACK_DS["+5V"] | EURORACK_DS["CV"] | EURORACK_DS["GATE"]
ck.check("B.J18_5V_CV_gate_open", not (OPEN & set(j18)),
         f"+5 V / CV / Gate (11-16) left open, got {sorted(OPEN & set(j18), key=int)}")

# jacks: 1 sleeve, 2 switch lug (TN), 3 tip
jack_bad = []
for ref, label, tip, tn in circuit.JACKS:
    n = PARTS["face"][ref].nets
    if n.get("1") != "GND_F" or n.get("3") != tip or n.get("2") != tn:
        jack_bad.append((ref, n))
ck.check("B.jacks_S_TN_T", not jack_bad, f"expected 1 = sleeve GND_F, 2 = TN, 3 = tip; bad {jack_bad}")
# normalling: unpatched R inputs take L (TN of R on L's tip), unpatched mono inputs ground (TN = GND_F)
norm = {ref: tn for ref, _, _, tn in circuit.JACKS}
ck.check("B.jack_normalling", norm["J8"] == "IN7L_F" and norm["J10"] == "IN8L_F" and norm["J12"] == "RT_L_F"
         and all(norm[f"J{k}"] == "GND_F" for k in (1, 2, 3, 4, 5, 6, 7, 9, 11, 13, 14))
         and norm["J15"] is None and norm["J16"] is None and norm["J17"] is None,
         f"README: R takes L when unpatched; inputs grounded; outputs open; got {norm}")
# pots: 3 = CW end, 2 = wiper, 1 = CCW end; LEVEL / SEND / DRUMS / dual gangs: CW end on the signal, CCW on GND
pot_bad = []
for ref, label, value, (cw, w, ccw) in circuit.POTS:
    if not label.startswith("PAN") and ccw != "GND_F":
        pot_bad.append((ref, label, "CCW end not GND", ccw))
    if label.startswith("PAN") and w != "GND_F":
        pot_bad.append((ref, label, "pan wiper not GND", w))
for ref, label, value, a, b in circuit.POTS2:
    for g in (a, b):
        if g[2] != "GND_F":
            pot_bad.append((ref, label, "CCW end not GND", g))
    # gang A the L side, gang B the R side
    if not ("L" in a[0] and "R" in b[0]):
        pot_bad.append((ref, label, "gang A should be L, B R", a[0], b[0]))
ck.check("B.pots_CW_to_signal", not pot_bad, f"level pots: CW (3 / 6) = signal, CCW (1 / 4) = GND, turning "
                                             f"right raises the level; bad {pot_bad}")
pan_bad = [(ref, cw, ccw) for ref, label, v, (cw, w, ccw) in circuit.POTS if label.startswith("PAN")
           and not (cw.startswith("PL") and ccw.startswith("PR"))]
ck.check("B.pan_direction", not pan_bad, f"design.md: CW end on PL (fully CW grounds L, knob reads left to "
                                         f"right); bad {pan_bad}")
btn_bad = [(ref, PARTS["face"][ref].nets) for ref, _, k in circuit.BUTTONS
           if {PARTS["face"][ref].nets[p] for p in BUTTON_DS["contact_a"]} != {"GND_F"}
           or {PARTS["face"][ref].nets[p] for p in BUTTON_DS["contact_b"]} != {f"BTN{k}_F"}]
ck.check("B.buttons_contacts", not btn_bad, f"contacts 1+2 one side (GND_F), 3+4 the other (BTN); bad {btn_bad}")


# ----------------------------------------------------------------------------------------------------------
# Export parsing (own code: docs of records from harness.read_export, everything else here)
def _rid(h):
    i = h.get("id")
    if isinstance(i, str) and i.startswith("["):
        return json.loads(i)
    return i


def doc_meta(doc):
    return next((p for h, p in doc["recs"] if h["type"] == "META"), {})


def _path_pts(path):
    pts, i = [], 0
    while i < len(path):
        if path[i] == "L":
            i += 1
            continue
        if isinstance(path[i], str):            # ARC etc.: take the end point
            pts.append((path[i + 2] * MIL, path[i + 3] * MIL))
            i += 4
            continue
        pts.append((path[i] * MIL, path[i + 1] * MIL))
        i += 2
    return pts


class Export:
    def __init__(self, path):
        self.path = path
        self.docs = harness.read_export(path)
        self.devices = {u: doc_meta(d).get("attributes", {}) for u, d in self.docs.items()
                        if d["docType"] == "DEVICE"}
        self.boards = {u: doc_meta(d).get("title") for u, d in self.docs.items() if d["docType"] == "BOARD"}

    def of_type(self, t):
        return {u: d for u, d in self.docs.items() if d["docType"] == t}

    def pcb(self, board_title):
        for u, d in self.of_type("PCB").items():
            if self.boards.get(doc_meta(d).get("board")) == board_title:
                return d
        return None

    def footprint_pads(self, uid):
        """{num: (x mm, y mm, padType, pad id)} of a FOOTPRINT doc."""
        pads = {}
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "PAD":
                pads[p["num"]] = (p["centerX"] * MIL, p["centerY"] * MIL, p["defaultPad"]["padType"], h["id"])
        return pads

    def footprint_silk(self, uid, layers=(3,)):
        """Silk POLY segments [(x1, y1, x2, y2)] and FILL point lists on the given layers, mm."""
        segs, fills = [], []
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "POLY" and p.get("layerId") in layers:
                path = p["path"]
                if path and not isinstance(path[0], str):
                    pts = _path_pts(path)
                    segs += [(*pts[i], *pts[i + 1]) for i in range(len(pts) - 1)]
            if h["type"] == "FILL" and p.get("layerId") in layers:
                paths = [p["path"]] if p["path"] and isinstance(p["path"][0], (int, float)) else p["path"]
                for path in paths:
                    if path and not isinstance(path[0], str):
                        fills.append(_path_pts(path))
        return segs, fills

    def symbol_pins(self, uid):
        """{pin number: (name, x, y, partId)} of a SYMBOL doc."""
        pins, out = {}, {}
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "PIN":
                pins[h["id"]] = {"x": p["x"], "y": p["y"], "part": p.get("partId")}
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "ATTR" and p.get("parentId") in pins:
                pins[p["parentId"]][p["key"]] = p["value"]
        for pid, q in pins.items():
            out[q.get("Pin Number")] = (q.get("Pin Name"), q["x"], q["y"], q["part"])
        return out

    def symbol_polys(self, uid):
        return [[(pt["x"], pt["y"]) for pt in p["points"]] for h, p in self.docs[uid]["recs"]
                if h["type"] == "POLY" and "points" in p]


def pcb_components(doc):
    """{designator: {...}} with x, y (mm), angle, layer, footprint, device, nets {pad num: net}."""
    comps, attrs = {}, collections.defaultdict(dict)
    for h, p in doc["recs"]:
        if h["type"] == "COMPONENT":
            comps[h["id"]] = p
    for h, p in doc["recs"]:
        if h["type"] == "ATTR" and p.get("parentId") in comps:
            attrs[p["parentId"]][p["key"]] = p["value"]
    padnet = collections.defaultdict(dict)
    for h, p in doc["recs"]:
        if h["type"] == "PAD_NET":
            _, cid, num, padid = _rid(h)
            if p.get("padNet"):
                padnet[cid][num] = p["padNet"]
    out, dups = {}, []
    for cid, p in comps.items():
        a = attrs[cid]
        ref = a.get("Designator")
        if ref in out:
            dups.append(ref)
        out[ref] = {"id": cid, "x": p["x"] * MIL, "y": p["y"] * MIL, "angle": p["angle"] or 0,
                    "bottom": p["layerId"] == 2, "footprint": a.get("Footprint"), "device": a.get("Device"),
                    "nets": padnet[cid]}
    return out, dups


def pad_xy(comp, local):
    """Board position of a footprint-local pad (mm): bottom layer mirrors y, then rotate (easyeda-format.md)."""
    px, py = local
    if comp["bottom"]:
        py = -py
    a = math.radians(comp["angle"])
    return comp["x"] + px * math.cos(a) - py * math.sin(a), comp["y"] + px * math.sin(a) + py * math.cos(a)


def outline(doc):
    for h, p in doc["recs"]:
        if h["type"] == "POLY" and p.get("layerId") == 11 and p["path"][0] == "R":
            return tuple(round(v * MIL, 3) for v in p["path"][1:5])
    return None


ROUTED = Export(harness.ROUTED)
PCB = {"main": ROUTED.pcb("Mixer Main"), "face": ROUTED.pcb("Mixer Faceplate")}
ck.check("D.routed_has_both_pcbs", all(PCB.values()), f"PCB docs for Mixer Main / Mixer Faceplate: "
                                                      f"{[k for k, v in PCB.items() if v]}")
COMPS = {}
for b in ("main", "face"):
    COMPS[b], dups = pcb_components(PCB[b])
    ck.check(f"D.no_duplicate_designators.{b}", not dups, f"duplicates {dups}")
GEN = Export(harness.GENERATED)


# B (continued)  the CD4053B symbol's pin names against SCHS047O, in both exports: the symbol of the device the
# main PCB's U11-U18 use. The exporter names a section's common by its lower-case letter ("a"), the select by the
# upper-case one ("A") and the throws "ax" / "ay", as TI's Figure 4-3 does ("OUT/IN ax OR ay", "A", "ax").
def canon_4053(name):
    s = (name or "").strip()
    if re.fullmatch(r"[abc]", s):
        return s.upper() + " COM"
    s = re.sub(r"\s*(OUT/IN|IN/OUT)\s*", " ", s.upper()).strip()
    m = re.fullmatch(r"([ABC])X OR \1Y", s)
    return m.group(1) + " COM" if m else s


for label, ex in (("routed", ROUTED), ("generated", GEN)):
    comps, _ = pcb_components(ex.pcb("Mixer Main"))
    syms = sorted({ex.devices.get(comps[u]["device"], {}).get("Symbol") for u in circuit.SWITCH.values() if u in comps},
                  key=str)
    if len(syms) != 1 or syms[0] not in ex.docs:
        ck.check(f"B.CD4053B_symbol_pins.{label}", False, f"U11-U18 should share one CD4053B symbol; got {syms}")
        continue
    pins = ex.symbol_pins(syms[0])
    got = {num: canon_4053(v[0]) for num, v in pins.items()}
    want = {num: name for name, num in CD4053B_DS.items()}
    bad = {num: (pins[num][0] if num in pins else None, want.get(num)) for num in sorted(set(got) | set(want), key=int)
           if got.get(num) != want.get(num)}
    ck.check(f"B.CD4053B_symbol_pins.{label}", not bad and len(pins) == 16,
             f"symbol {syms[0][:8]}, {len(pins)} pins; pin: (symbol name, datasheet) differ at {bad}")


# ----------------------------------------------------------------------------------------------------------
# C  diodes and polarised caps: symbol, footprint, orientation, function
def cathode_pin_symbol(sym_uid):
    pins = ROUTED.symbol_pins(sym_uid)
    k = [num for num, (name, *_r) in pins.items() if name in ("C", "K", "Cathode", "CATHODE")]
    a = [num for num, (name, *_r) in pins.items() if name in ("A", "Anode", "ANODE")]
    return (k[0] if len(k) == 1 else None), (a[0] if len(a) == 1 else None), pins


def cathode_bar_symbol(sym_uid):
    """The pin on the side the drawn triangle points to (its apex touches the bar)."""
    pins = ROUTED.symbol_pins(sym_uid)
    for pts in ROUTED.symbol_polys(sym_uid):
        corners = sorted(set(pts))
        if len(corners) == 3:
            xs = [c[0] for c in corners]
            singles = [c for c in corners if xs.count(c[0]) == 1]
            doubles = [x for x in xs if xs.count(x) == 2]
            if len(singles) == 1 and doubles:
                side = 1 if singles[0][0] > doubles[0] else -1
                return max(pins, key=lambda n: side * pins[n][1])
    return None


def band_pad_footprint(fp_uid):
    """The pad on the band side: a silk line across the body strictly between the body's two ends."""
    pads = ROUTED.footprint_pads(fp_uid)
    segs, fills = ROUTED.footprint_silk(fp_uid, layers=(3,))
    (n1, p1), (n2, p2) = sorted(pads.items())
    across = [s for s in segs if abs(s[0] - s[2]) < 0.01 and abs(s[1] - s[3]) > 1.0]
    xs = sorted({round(s[0], 2) for s in across})
    # the body's two ends are the outermost symmetric pair (x, -x); markers outside them are ignored
    ends = [x for x in xs if x > 0 and any(abs(x + y) < 0.02 for y in xs)]
    end = max(ends) if ends else 0
    inner = [x for x in xs if abs(x) < end - 0.05 and not any(abs(x + y) < 0.02 for y in xs)]
    if abs(p2[0] - p1[0]) < 0.01 or len(inner) != 1:
        return None, xs
    x = inner[0]
    return (n1 if abs(x - p1[0]) < abs(x - p2[0]) else n2), xs


def plus_pin(uid, sym=False):
    """The symbol pin (or footprint pad) next to the '+' mark."""
    if sym:
        pins = ROUTED.symbol_pins(uid)
        polys = [p for p in ROUTED.symbol_polys(uid) if len(p) == 2]
        hs = [p for p in polys if p[0][1] == p[1][1] and abs(p[0][0] - p[1][0]) <= 5]
        vs = [p for p in polys if p[0][0] == p[1][0] and abs(p[0][1] - p[1][1]) <= 5]
        for h in hs:
            for v in vs:
                cx, cy = v[0][0], h[0][1]
                if min(h[0][0], h[1][0]) <= cx <= max(h[0][0], h[1][0]) and \
                        min(v[0][1], v[1][1]) <= cy <= max(v[0][1], v[1][1]):
                    return min(pins, key=lambda n: math.hypot(pins[n][1] - cx, pins[n][2] - cy))
        return None
    pads = ROUTED.footprint_pads(uid)
    segs, fills = ROUTED.footprint_silk(uid, layers=(3,))
    if len(fills) >= 2:                      # the library caps draw '+' as two filled bars
        pts = [q for f in fills for q in f]
        cx, cy = sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts)
        return min(pads, key=lambda n: math.hypot(pads[n][0] - cx, pads[n][1] - cy))
    return None


for ref in ("D901", "D902", "D903", "D904"):
    c = COMPS["main"][ref]
    dev = ROUTED.devices.get(c["device"], {})
    sym, fp = dev.get("Symbol"), c["footprint"]
    k_sym, a_sym, pins = cathode_pin_symbol(sym)
    bar = cathode_bar_symbol(sym)
    band, xs = band_pad_footprint(fp)
    ck.check(f"C.{ref}.symbol_cathode_pin", k_sym == "1" and a_sym == "2" and bar == "1",
             f"{dev.get('Manufacturer Part')} symbol {sym[:8]}: pin named C = {k_sym}, A = {a_sym}, bar side pin "
             f"= {bar} (expected cathode 1, anode 2 as circuit.py assumes)")
    ck.check(f"C.{ref}.footprint_band_pad", band == "1",
             f"footprint {fp[:8]}: band (silk across the body, x {xs} mm) next to pad {band}, expected pad 1")
    ck.check(f"C.{ref}.pcb_pads_match_circuit", c["nets"] == PARTS["main"][ref].nets,
             f"routed pads {c['nets']}, circuit {PARTS['main'][ref].nets}")

D = {ref: (PARTS["main"][ref].nets["2"], PARTS["main"][ref].nets["1"]) for ref in ("D901", "D902", "D903", "D904")}


def conducts(ref, v):
    a, k = D[ref]
    return v[a] - v[k] > 0.3


# normal: header +12 / -12, the board's rails loaded (P12_D just under +12, N12_D just above -12)
normal = {"P12_IN": 12.0, "P12_D": 11.6, "N12_IN": -12.0, "N12_D": -11.6}
# cable reversed: the +12 pins see -12 V and the -12 pins +12 V, the board's rails still at 0 V
reverse = {"P12_IN": -12.0, "P12_D": 0.0, "N12_IN": 12.0, "N12_D": 0.0}
for ref in ("D901", "D902"):
    a, k = D[ref]
    ck.check(f"C.{ref}_passes_normal", conducts(ref, normal),
             f"anode {a} {normal[a]:+.1f} V, cathode {k} {normal[k]:+.1f} V: must be forward-biased in use")
    ck.check(f"C.{ref}_blocks_reversed", not conducts(ref, reverse),
             f"reversed cable: anode {a} {reverse[a]:+.1f} V, cathode {k} {reverse[k]:+.1f} V")
ck.check("C.design_md_minus12_cathode_on_header", D["D902"][1] == "N12_IN",
         f"design.md: '-12 V: cathode on the header'; D902 cathode on {D['D902'][1]}")
# 1N5819 VRRM 40 V (onsemi 1N5817-D, max rating) against the 24 V it can see reversed (+12 against -12)
VRRM_1N5819 = 40.0
# verifier change: the reverse voltage now comes from the model (reversed cable, plus the worst case of the board's
# rails still charged to +-12 V when it is plugged in reversed), not a constant compared with a constant
reverse_charged = {"P12_IN": -12.0, "P12_D": 11.6, "N12_IN": 12.0, "N12_D": -11.6}
vr = max(v[D[r][1]] - v[D[r][0]] for r in ("D901", "D902") for v in (reverse, reverse_charged))
ck.check("C.1N5819_VRRM", VRRM_1N5819 >= vr, f"VRRM {VRRM_1N5819} V (onsemi 1N5817-D, max rating) against the "
                                             f"largest reverse voltage in the reversed-cable cases, {vr:.1f} V")

# D903 and the power-on reset: C906 from +12V to POR, R920 POR to GND.
c906, r920 = PARTS["main"]["C906"].nets, PARTS["main"]["R920"].nets
ck.check("C.POR_topology", set(c906.values()) == {"+12V", "POR"} and set(r920.values()) == {"POR", "GND"},
         f"C906 {c906}, R920 {r920}")
# Running: +12V = 12, POR = 0, so C906 holds 12 V. Power-off: +12V falls to 0 faster than R920 (100k x 1u =
# 100 ms) can follow, so POR is pushed to about 0 - 12 = -12 V. To empty C906 the diode must conduct there.
running = {"+12V": 12.0, "POR": 0.0, "GND": 0.0}
power_up = {"+12V": 12.0, "POR": 12.0, "GND": 0.0}
power_off = {"+12V": 0.0, "POR": -12.0, "GND": 0.0}
ck.check("C.D903_off_while_running", not conducts("D903", running) and not conducts("D903", power_up),
         f"D903 anode {D['D903'][0]}, cathode {D['D903'][1]}: must not conduct while running or at power-up")
ok = conducts("D903", power_off)
ck.check("C.D903_empties_C906_at_power_off", ok,
         f"power-off: +12V -> 0 V, POR -> {power_off['POR']:+.0f} V; D903 anode {D['D903'][0]} at "
         f"{power_off[D['D903'][0]]:+.0f} V, cathode {D['D903'][1]} at {power_off[D['D903'][1]]:+.0f} V -> "
         + ("forward-biased: it clamps POR and empties C906" if ok else
            "reverse-biased, it never conducts. Wanted across R920: anode GND, cathode POR (a Schottky there keeps "
            "POR above -0.5 V)"))
# D904 (2026-11-14): with the bus +12 V missing and -12 V present the +12V net is pulled below GND; the clamp
# must conduct then and never in use
missing = {"+12V": -0.6, "GND": 0.0}
ck.check("C.D904_clamps_a_missing_plus12", D["D904"] == ("GND", "+12V") and conducts("D904", missing)
         and not conducts("D904", running), f"D904 anode {D['D904'][0]}, cathode {D['D904'][1]}")

# Until 2026-11-14 what emptied C906 at power-off was the four CD4013 RESET inputs' protection diodes to VSS: the +12 V rail
# falls with the board's load on its own caps (D901 blocks any return; with the PSU still up the rail falls slower,
# so the board's own decay is the upper bound), C906 couples that fall onto POR.
# TI SCHS023E (CD4013B, rev. Sept 2016) absolute maximum: DC input current +-10 mA any one input (max);
# input voltage -0.5 V .. VDD + 0.5 V. The CD4000B input network has a series resistor before its clamp diodes
# (SCHS023E "CMOS protection network" figure), so the four inputs share the current roughly evenly; the share is
# still taken as /4, but every other quantity is at its worst corner (verifier change: was nominal 5 mA mutes,
# nominal caps).
# TI SLOS080: TL074 supply current 1.4 mA typ / 2.5 mA max per amplifier -> 16 amplifiers at max.
# Mute LED current, fastest-fall corner: Q at VDD, button LED VF 1.6 V (not confirmed: Thonk sheet unavailable; red
# LEDs are 1.8-2.0 V typ), through circuit.py's LED resistors (Q -> R -> LED, since 2026-11-15 no PhotoMOS LED in
# the chain). The CD4053Bs' own supply current (SCHS047O quiescent current, microamps) is left out.
# Rail capacitance at its smallest: 10 uF electrolytic -20 %, every 100 nF X7R on +12V (counted from circuit.py)
# -10 %; C906 1 uF at +10 %.
I_TL074_MAX = 2.5e-3 * 16
VF_BTN = 1.6
_LED_R = {k: next(p for p in MB if p.kind == "R" and set(p.nets.values()) == {f"QK{k}", f"LED{k}"})
          for k in circuit.MONO + circuit.STEREO}
I_MUTES = sum((12.0 - VF_BTN) / harness.ohms(r.value) for k, r in _LED_R.items())
I_PULLUPS = 8 * 12.0 / 100e3
N_100N_P12 = sum(1 for p in MB if p.kind == "C" and p.value == "100n" and set(p.nets.values()) == {"+12V", "GND"})
C_RAIL = 0.8 * harness.farads("10u") + 0.9 * N_100N_P12 * harness.farads("100n")
dvdt = (I_TL074_MAX + I_MUTES + I_PULLUPS) / C_RAIL                # V/s
i_clamp = 1.1 * harness.farads("1u") * dvdt                       # through C906 into the clamps
# Since 2026-11-14 D903 (BAT85, cathode POR, anode GND) takes that current: Vishay BAT85 IF 200 mA max (abs max),
# VF <= 0.32 V at 1 mA / 0.40 V at 10 mA, under the inputs' silicon diodes, so they carry next to nothing.
BAT85_IF_MAX = 0.2
schottky = D["D903"] == ("GND", "POR") and PARTS["main"]["D903"].kind == "BAT85"
ck.check("C.POR_clamp_current_within_abs_max", (i_clamp < BAT85_IF_MAX) if schottky else (i_clamp / 4 < 10e-3),
         f"worst case: load {(I_TL074_MAX + I_MUTES + I_PULLUPS) * 1e3:.0f} mA on {C_RAIL * 1e6:.1f} uF, +12V falls at "
         f"{dvdt / 1e3:.1f} V/ms -> {i_clamp * 1e3:.1f} mA through C906 "
         + (f"into D903 (BAT85, {BAT85_IF_MAX * 1e3:.0f} mA max): POR held at about -0.3..-0.4 V, inside the CD4013B's "
            f"-0.5 V" if schottky else
            f"into 4 RESET clamps, {i_clamp / 4 * 1e3:.2f} mA each (abs max 10 mA; {i_clamp * 1e3:.1f} mA if one input "
            f"took it all); POR still sits about 0.6 V below VSS (abs max -0.5 V)"))

# polarised caps: + pin from the symbol and the footprint actually used, then + on the more positive net
VOLTS = {"+12V": 12.0, "GND": 0.0, "-12V": -12.0}
for ref in ("C904", "C905"):
    c = COMPS["main"][ref]
    dev = ROUTED.devices.get(c["device"], {})
    sp = plus_pin(dev.get("Symbol"), sym=True)
    fpp = plus_pin(c["footprint"])
    ck.check(f"C.{ref}.plus_pin_symbol_eq_footprint", sp is not None and sp == fpp,
             f"{dev.get('Manufacturer Part')}: '+' beside symbol pin {sp}, footprint pad {fpp}")
    n = PARTS["main"][ref].nets
    other = "1" if sp == "2" else "2"
    ck.check(f"C.{ref}.plus_on_positive_net", sp in n and VOLTS[n[sp]] > VOLTS[n[other]],
             f"+ pin {sp} on {n.get(sp)}, - pin {other} on {n.get(other)}")
    ck.check(f"C.{ref}.pcb_pads_match_circuit", c["nets"] == n, f"routed {c['nets']}, circuit {n}")


# ----------------------------------------------------------------------------------------------------------
# D  the routed master against circuit.py: parts, devices, every pad's net
def expected_device(part):
    """A substring the device title / Manufacturer Part must contain for this part."""
    if part.kind == "R":
        v = part.value.upper()
        if v.endswith("K") and len(v) <= 2:
            v += "0"                                  # 1k -> LR1F1K0
        return "LR1F" + v
    if part.kind == "C":
        return {"100n": "FG28X7R1H104", "22p": "FG28C0G1H220", "1u": "SR305C105", "4p7": "C315C479",
                "10p": "C315C100"}[part.value]
    return {"CP": "178MU0033", "D5819": "1N5819", "D4148": "1N4148", "BAT85": "BAT85", "TL074": "TL074", "CD4013": "CD4013B",
            "CD4093": "CD4093B", "CD4053": "CD4053B", "HDR16": "DC3-2.54-16", "HDR8": "1x8", "HDR12": "1x12",
            "JACK": "WQP518MA", "POT": f"9mm {part.value}", "POT2": "dual-gang A100k", "SWLED": "LED button"}[part.kind]


def device_name(uid):
    a = ROUTED.devices.get(uid, {})
    t = next((doc_meta(d).get("title") for u, d in ROUTED.docs.items() if u == uid), "")
    return f"{t} | {a.get('Manufacturer Part', '')}"


for b, parts in (("main", MB), ("face", FB)):
    want = {(p.ref if b == "main" or not p.ref.startswith("H") else p.ref): p for p in parts}
    got = COMPS[b]
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    ck.check(f"D.designators_complete.{b}", not missing and not extra,
             f"{len(want)} parts in circuit.py, {len(got)} on the routed PCB; missing {missing}, extra {extra}")
    pad_bad, dev_bad, fp_missing = [], [], []
    for ref, part in want.items():
        c = got.get(ref)
        if not c:
            continue
        pads = ROUTED.footprint_pads(c["footprint"]) if c["footprint"] in ROUTED.docs else {}
        if not pads:
            fp_missing.append((ref, c["footprint"]))
            continue
        no_pad = sorted(set(part.nets) - set(pads))
        if no_pad:
            pad_bad.append((ref, "circuit pins without a pad", no_pad))
        for num in pads:
            if c["nets"].get(num) != part.nets.get(num):
                pad_bad.append((ref, num, "routed", c["nets"].get(num), "circuit", part.nets.get(num)))
        name = device_name(c["device"])
        if expected_device(part).lower() not in name.lower():
            dev_bad.append((ref, part.kind, part.value, name))
    ck.check(f"D.footprints_present.{b}", not fp_missing, f"components whose footprint doc is missing: {fp_missing}")
    ck.check(f"D.every_pad_net.{b}", not pad_bad,
             f"every pad of every part against circuit.py; {len(pad_bad)} differences: {pad_bad[:20]}")
    ck.check(f"D.devices_match_values.{b}", not dev_bad, f"device against kind/value: {dev_bad[:20]}")

# every net named on the routed boards exists in circuit.py (no stray net left from routing)
for b, nets in (("main", MBN), ("face", FBN)):
    routed_nets = {n for c in COMPS[b].values() for n in c["nets"].values()}
    ck.check(f"D.no_foreign_nets.{b}", routed_nets == set(nets),
             f"routed pad nets minus circuit: {sorted(routed_nets - set(nets))}, circuit minus routed: "
             f"{sorted(set(nets) - routed_nets)}")

# footprints used: the geometry the pin maps depend on
def fp_of(board, ref):
    return ROUTED.footprint_pads(COMPS[board][ref]["footprint"])


def dip_numbering(ref, n):
    """Pin 1 bottom-left, 1..n/2 left to right along the y = -3.81 row, n/2+1..n back along y = +3.81 (pin i
    across from n+1-i), 2.54 mm apart: the JEDEC counter-clockwise order seen from the top."""
    d = fp_of("main", ref)
    h = n // 2
    if len(d) != n or set(d) != {str(i) for i in range(1, n + 1)}:
        return False, sorted(d, key=int)
    ok = all(abs(d[str(i)][1] + 3.81) < 0.01 and abs(d[str(n + 1 - i)][1] - 3.81) < 0.01 and
             abs(d[str(i)][0] - d[str(n + 1 - i)][0]) < 0.01 for i in range(1, h + 1)) and \
        all(abs(d[str(i + 1)][0] - d[str(i)][0] - 2.54) < 0.01 for i in range(1, h))
    return ok, {k: (round(v[0], 2), round(v[1], 2)) for k, v in sorted(d.items(), key=lambda kv: int(kv[0]))}


ok, pads = dip_numbering("U1", 14)
ck.check("D.DIP14_numbering", ok, f"pin 1 bottom-left, 1-7 left to right along one row, 8-14 back along the other "
                                  f"(counter-clockwise from the top, JEDEC), rows 7.62 mm apart, pitch 2.54; {pads}")
same_dip = sorted({COMPS["main"][u]["footprint"] for u in ("U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "U9", "U10")})
ck.check("D.all_ICs_on_the_DIP14", len(same_dip) == 1, f"footprints {same_dip}")
# the CD4053Bs (2026-11-15): SCHS047O Figure 4-3 numbers its 16-pin PDIP the same way (1-8 down one side, 9-16 back
# up the other, top view), so circuit.MUX's pin numbers hold on this footprint
ok, pads = dip_numbering("U11", 16)
ck.check("D.DIP16_numbering", ok, f"CD4053B DIP-16: 1-8 along one row, 9-16 back along the other, pin i across from "
                                  f"17-i, rows 7.62 mm apart, pitch 2.54; {pads}")
same16 = sorted({COMPS["main"][u]["footprint"] for u in circuit.SWITCH.values()})
ck.check("D.all_switches_on_the_DIP16", len(same16) == 1 and same16 == [COMPS["main"]["U11"]["footprint"]]
         and doc_meta(ROUTED.docs[same16[0]]).get("title") == "DIP-16-W7.62-P2.54",
         f"U11-U18 footprints {[doc_meta(ROUTED.docs[u]).get('title') for u in same16 if u in ROUTED.docs]}")
jack = fp_of("face", "J1")
d12 = math.hypot(jack["2"][0] - jack["1"][0], jack["2"][1] - jack["1"][1])
d13 = math.hypot(jack["3"][0] - jack["1"][0], jack["3"][1] - jack["1"][1])
ck.check("D.jack_pad_spacing_vs_KiCad", abs(d12 - JACK_KICAD["TN"]) < 0.05 and abs(d13 - JACK_KICAD["T"]) < 0.05,
         f"KiCad PJ398SM: S->TN {JACK_KICAD['TN']} mm, S->T {JACK_KICAD['T']} mm; footprint pad 1->2 "
         f"{d12:.2f}, 1->3 {d13:.2f} (so 1 = S, 2 = TN, 3 = T)")
j18 = fp_of("main", "J18")
ck.check("D.J18_IDC_numbering", all(abs(j18[str(2 * i - 1)][0] - j18[str(2 * i)][0]) < 0.01 and
                                    abs(j18[str(2 * i - 1)][1] - j18[str(2 * i)][1] - (-2.54)) < 0.01
                                    for i in range(1, 9)),
         "box header: odd pins one row, even the other, pin 2n beside 2n-1 (IDC ribbon numbering)")
# verifier addition: the pairs must also run in order along the header, 2.54 mm apart (1-2, 3-4, ... 15-16)
ck.check("D.J18_pairs_in_order", all(abs(j18[str(2 * i + 1)][0] - j18[str(2 * i - 1)][0] - 2.54) < 0.01
                                     for i in range(1, 8)),
         f"pair n+1 2.54 mm further along than pair n; odd-pin x "
         f"{[round(j18[str(2 * i - 1)][0], 2) for i in range(1, 9)]}")
# assembly: pin 1 marked by the only square pad on the polarised multi-pin footprints
sq_bad = []
for b, ref in (("main", "U1"), ("main", "U5"), ("main", "U7"), ("main", "U11"), ("main", "H1"), ("main", "H9"),
               ("face", "HF1"), ("face", "HF9")):
    rects = sorted(n for n, v in fp_of(b, ref).items() if v[2] == "RECT")
    if rects != ["1"]:
        sq_bad.append((ref, rects))
ck.check("D.pin1_square_pad", not sq_bad, f"DIP-14, DIP-16 and header footprints: square pad = pin 1 only; {sq_bad}")
j18c = COMPS["main"]["J18"]
y1, y15 = pad_xy(j18c, j18["1"][:2])[1], pad_xy(j18c, j18["15"][:2])[1]
ck.check("D.J18_pin1_at_bottom", y1 < y15, f"design.md: J18 pin 1 (-12 V) at the bottom; pad 1 y {y1:.2f}, "
                                          f"pad 15 y {y15:.2f}")
btn = fp_of("face", "SW1")
BUTTON_XY = {"1": (2.54, 2.54), "2": (-2.54, 2.54), "3": (2.54, -2.54), "4": (-2.54, -2.54), "5": (2.7, 0),
             "6": (-2.7, 0)}
ck.check("D.button_footprint_vs_Thonk", all(abs(btn[n][0] - x) < 0.01 and abs(btn[n][1] - y) < 0.01
                                           for n, (x, y) in BUTTON_XY.items()),
         f"Thonk SW_Tact_Low_Profile_LED (parts.md) pins {BUTTON_XY}; footprint "
         f"{ {n: (round(v[0], 2), round(v[1], 2)) for n, v in btn.items()} }")

# pots: in the front view (x_front = W - x, both PCB docs are drawn from the rear) pins below the shaft, pin 1
# left of pin 3, gang B's 4 left of 6 and further from the shaft
W = outline(PCB["face"])[2]
pot_geo_bad = []
for ref, label, value, _ in circuit.POTS:
    c = COMPS["face"][ref]
    pads = fp_of("face", ref)
    p1, p3 = pad_xy(c, pads["1"][:2]), pad_xy(c, pads["3"][:2])
    sh = pad_xy(c, (0.0, circuit.POT_SHAFT))
    if not (W - p1[0] < W - p3[0] and p1[1] < sh[1] and p3[1] < sh[1] and c["bottom"]):
        pot_geo_bad.append((ref, label, "front x1 %.2f x3 %.2f, pins y %.2f shaft y %.2f" % (W - p1[0], W - p3[0],
                                                                                           p1[1], sh[1])))
for ref, label, value, a, b in circuit.POTS2:
    c = COMPS["face"][ref]
    pads = fp_of("face", ref)
    p = {n: pad_xy(c, pads[n][:2]) for n in "123456"}
    sh = pad_xy(c, (0.0, circuit.POT_SHAFT))
    if not (W - p["1"][0] < W - p["3"][0] and W - p["4"][0] < W - p["6"][0] and
            p["4"][1] < p["1"][1] < sh[1] and c["bottom"]):
        pot_geo_bad.append((ref, label, {n: (round(W - q[0], 2), round(q[1], 2)) for n, q in p.items()}))
ck.check("D.pots_CW_front_view", not pot_geo_bad,
         f"front view: pins down, 1 left / 3 right (CW turns the wiper to 3), gang B row further down; {pot_geo_bad}")
pot_fp = fp_of("face", "RV25")
ok = (abs((4.0 - pot_fp["2"][1]) - 7.5) < 0.01 and abs(pot_fp["1"][1] - pot_fp["4"][1] - 2.5) < 0.01 and
      abs(pot_fp["3"][0] - pot_fp["1"][0] - 5.0) < 0.01 and abs(pot_fp["6"][0] - pot_fp["4"][0] - 5.0) < 0.01)
ck.check("D.dual_pot_footprint_vs_KiCad_RD902F", ok,
         "KiCad RD902F: shaft 7.5 mm from pins 1-3, pins 4-6 2.5 mm further away, both rows in the same order")

# ----------------------------------------------------------------------------------------------------------
# E  header stacking: pads at the same board position on the two PCB docs (same frame, both looking at the
# top layer) must carry X (main) and X_F (faceplate)
ck.check("E.same_outline", outline(PCB["main"]) == outline(PCB["face"]),
         f"main {outline(PCB['main'])}, faceplate {outline(PCB['face'])} (mm: x, y top, w, h)")
mpads = []
for ref, kind, pins in circuit.HEADERS:
    c = COMPS["main"][ref]
    for num, v in fp_of("main", ref).items():
        mpads.append((ref, num, pad_xy(c, v[:2]), c["nets"].get(num), c["bottom"]))
stack_bad, sides_bad, matched = [], [], 0
for ref, kind, pins in circuit.HEADERS:
    fref = circuit.fb_ref(ref)
    c = COMPS["face"][fref]
    if c["bottom"] or not COMPS["main"][ref]["bottom"]:
        sides_bad.append((ref, "main bottom", COMPS["main"][ref]["bottom"], fref, "face bottom", c["bottom"]))
    for num, v in fp_of("face", fref).items():
        xy = pad_xy(c, v[:2])
        near = [m for m in mpads if math.hypot(m[2][0] - xy[0], m[2][1] - xy[1]) < 0.05]
        fnet = c["nets"].get(num)
        if len(near) != 1:
            stack_bad.append((fref, num, fnet, "no main-board pin under it" if not near else near))
            continue
        mref, mnum, _, mnet, _ = near[0]
        want = "GND_F" if mnet == "GND" else f"{mnet}_F"
        if fnet != want:
            stack_bad.append((fref, num, fnet, "over", mref, mnum, mnet))
        else:
            matched += 1
ck.check("E.header_sides", not sides_bad, f"male headers on the faceplate's top (rear), sockets on the main "
                                          f"board's bottom (front): {sides_bad}")
ck.check("E.stacked_pins_carry_pairs", not stack_bad and matched == 76,
         f"{matched} of 76 stacked pins carry X / X_F; bad {stack_bad[:12]}")
# pin 1 at the top in the front view, as design.md says
top_bad = []
for ref, kind, pins in circuit.HEADERS:
    c = COMPS["main"][ref]
    fp = fp_of("main", ref)
    ys = {n: pad_xy(c, v[:2])[1] for n, v in fp.items()}
    if max(ys, key=ys.get) != "1":
        top_bad.append((ref, max(ys, key=ys.get)))
ck.check("E.pin1_at_top", not top_bad, f"design.md: pin 1 at the top; headers whose top pin is not 1: {top_bad}")


# test validity: the pad transform above must put pads where the routed tracks end (non-ground header pins)
def track_ends(doc):
    ends = collections.defaultdict(list)
    for h, p in doc["recs"]:
        if h["type"] == "LINE" and p.get("netName"):
            for k in ("start", "end"):
                ends[p["netName"]].append((p[k + "X"] * MIL, p[k + "Y"] * MIL))
        if h["type"] == "VIA" and p.get("netName"):
            ends[p["netName"]].append((p["centerX"] * MIL, p["centerY"] * MIL))
    return ends


# Until 2026-11-15 this used the header pads of both boards. The master's main board is now placed but not routed
# (no tracks), so the transform is checked on the routed faceplate alone, on both of its layers: the male headers
# on the top, the jacks, pots and buttons on the bottom (the mirror the main board's sockets need too).
hit, tot, miss = collections.Counter(), collections.Counter(), []
ends = track_ends(PCB["face"])
for r, c in COMPS["face"].items():
    for num, v in fp_of("face", r).items():
        net = c["nets"].get(num)
        if net in (None, "GND_F"):
            continue
        side = "bottom" if c["bottom"] else "top"
        tot[side] += 1
        xy = pad_xy(c, v[:2])
        if any(math.hypot(e[0] - xy[0], e[1] - xy[1]) < 0.3 for e in ends[net]):
            hit[side] += 1
        else:
            miss.append(f"{r}.{num} ({net})")
main_tracks = len(track_ends(PCB["main"]))
ck.check("E.transform_sanity_tracks_end_on_pads", hit == tot and tot["top"] > 0 and tot["bottom"] > 0,
         f"faceplate: {hit['top']} of {tot['top']} top-layer and {hit['bottom']} of {tot['bottom']} bottom-layer "
         f"non-ground pads have a same-net track end or via within 0.3 mm of the computed pad centre (validates the "
         f"bottom-layer mirror + rotation used for stacking); missed {miss[:10]}; main board: {main_tracks} routed nets "
         f"(not routed yet), not used")


# ----------------------------------------------------------------------------------------------------------
# F  schematic pages against circuit.py (routed master and generated project)
def _on_seg(p, a, b, tol=0.01):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    if min(x1, x2) - tol <= x <= max(x1, x2) + tol and min(y1, y2) - tol <= y <= max(y1, y2) + tol:
        return abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) <= tol * max(1, math.hypot(x2 - x1, y2 - y1))
    return False


def _xf(cand, comp, px, py):
    order, sigma, phi = cand
    m = -1 if comp["isMirror"] else 1
    a = math.radians(sigma * (comp["rotation"] or 0))
    if order == "mirror-first":
        px = m * px
    x, y = px * math.cos(a) - py * math.sin(a), px * math.sin(a) + py * math.cos(a)
    if order == "rotate-first":
        x = m * x
    return round(comp["x"] + x, 3), round(comp["y"] + phi * y, 3)


# Every pin-placing convention is tried; the score cannot tell the rotation sense apart when every part turned
# by 90 / 270 degrees is a symmetric two-pin part, so ties go to the first: rotation counter-clockwise on the
# y-down page (x' = x cos + y sin, y' = -x sin + y cos), the convention of the exporter EasyEDA imported
# (plaitsy/hardware/tools/easyeda_export.py tf()). Two-pin non-polar parts are then compared as unordered pairs.
CANDS = [(o, s, f) for o in ("mirror-first", "rotate-first") for s in (-1, 1) for f in (1, -1)]
NONPOLAR = ("R", "C")


def schematic_nets(ex):
    """{board title: ({ref: {pin: net or None}}, stats)} from the SCH_PAGE docs, by pin positions on wires."""
    sch_board = {u: ex.boards.get(doc_meta(d).get("board")) for u, d in ex.of_type("SCH").items()}
    pages = collections.defaultdict(list)
    for u, d in ex.of_type("SCH_PAGE").items():
        pages[sch_board.get(doc_meta(d).get("schematic"))].append(d)
    sympins = {}
    result = {}
    for board, docs in pages.items():
        page_data = []
        for d in docs:
            comps = {h["id"]: p for h, p in d["recs"] if h["type"] == "COMPONENT"}
            attrs = collections.defaultdict(dict)
            for h, p in d["recs"]:
                if h["type"] == "ATTR":
                    attrs[p.get("parentId")][p["key"]] = p["value"]
            wires = {}
            for h, p in d["recs"]:
                if h["type"] == "WIRE":
                    wires[h["id"]] = []
            for h, p in d["recs"]:
                if h["type"] == "LINE" and p.get("lineGroup") in wires:
                    wires[p["lineGroup"]].append(((p["startX"], p["startY"]), (p["endX"], p["endY"])))
            named = {w: attrs[w].get("NET") for w in wires if attrs[w].get("NET")}
            page_data.append((comps, attrs, wires, named))
        # pick the symbol transform that lands the most pins on named wires or flags
        best = None
        for cand in CANDS:
            score = 0
            for comps, attrs, wires, named in page_data:
                pts = [q for w in named for seg in wires[w] for q in seg]
                ptset = {(round(x, 3), round(y, 3)) for x, y in pts}
                for cid, comp in comps.items():
                    sym = attrs[cid].get("Symbol")
                    if sym not in ex.docs or "Designator" not in attrs[cid]:
                        continue
                    if sym not in sympins:
                        sympins[sym] = ex.symbol_pins(sym)
                    for num, (name, px, py, part) in sympins[sym].items():
                        if part and part != comp["partId"]:
                            continue
                        score += _xf(cand, comp, px, py) in ptset
            if best is None or score > best[0]:
                best = (score, cand)
        cand = best[1]
        pins_of = collections.defaultdict(dict)
        conflicts, unnamed = [], []
        for comps, attrs, wires, named in page_data:
            # union named wires that touch, plus flags (net ports / ground symbols with a Name)
            groups = {w: {named[w]} for w in named}
            segs = [(w, s) for w in named for s in wires[w]]
            flag_pts = []
            for cid, comp in comps.items():
                a = attrs[cid]
                sym = a.get("Symbol")
                if "Designator" in a or not a.get("Name") or sym not in ex.docs:
                    continue
                if sym not in sympins:
                    sympins[sym] = ex.symbol_pins(sym)
                for num, (name, px, py, part) in sympins[sym].items():
                    flag_pts.append((_xf(cand, comp, px, py), a["Name"]))
            for cid, comp in comps.items():
                a = attrs[cid]
                ref = a.get("Designator")
                sym = a.get("Symbol")
                if not ref or sym not in ex.docs:
                    continue
                if sym not in sympins:
                    sympins[sym] = ex.symbol_pins(sym)
                for num, (name, px, py, part) in sympins[sym].items():
                    if part and part != comp["partId"]:
                        continue
                    p = _xf(cand, comp, px, py)
                    nets = {named[w] for w, s in segs if _on_seg(p, *s)}
                    nets |= {n for q, n in flag_pts if abs(q[0] - p[0]) < 0.01 and abs(q[1] - p[1]) < 0.01}
                    if len(nets) > 1:
                        conflicts.append((ref, num, sorted(nets)))
                    prev = pins_of[ref].get(num)
                    net = next(iter(nets)) if len(nets) == 1 else None
                    if prev is not None and net is not None and prev != net:
                        conflicts.append((ref, num, prev, net))
                    if prev is None:
                        pins_of[ref][num] = net
        result[board] = (pins_of, {"transform": cand, "score": best[0], "conflicts": conflicts})
    return result


def compare_schematic(label, ex):
    res = schematic_nets(ex)
    for board, parts in (("Mixer Main", MB), ("Mixer Faceplate", FB)):
        if board not in res:
            ck.check(f"F.{label}.{board}.pages_present", False, f"no schematic pages for {board}")
            continue
        pins_of, st = res[board]
        want = {p.ref: p for p in parts}
        missing = sorted(set(want) - set(pins_of))
        extra = sorted(set(pins_of) - set(want))
        ck.check(f"F.{label}.{board}.parts", not missing and not extra,
                 f"{len(want)} parts in circuit.py, {len(pins_of)} on the pages; missing {missing}, extra {extra}")
        ck.check(f"F.{label}.{board}.no_conflicting_labels", not st["conflicts"],
                 f"pins touching two differently named nets: {st['conflicts'][:10]}")
        diffs = []
        swapped = []
        for ref, p in want.items():
            got = pins_of.get(ref, {})
            if p.kind in NONPOLAR and len(p.nets) == 2 and sorted(map(str, got.values())) ==                     sorted(p.nets.values()) and got != p.nets:
                swapped.append(ref)
                continue
            for num in sorted(set(p.nets) | {n for n, v in got.items() if v}, key=lambda s: int(s) if s.isdigit()
                              else 0):
                if got.get(num) != p.nets.get(num):
                    diffs.append((ref, num, "page", got.get(num), "circuit", p.nets.get(num)))
        ck.check(f"F.{label}.{board}.pin_nets", not diffs,
                 f"transform {st['transform']}, {st['score']} pins on named wires; {len(diffs)} pins differ from "
                 f"circuit.py: {diffs[:15]}")
        polar_rot = [r for r in swapped if want[r].kind not in NONPOLAR]
        ck.check(f"F.{label}.{board}.polar_parts_unambiguous", not polar_rot,
                 f"{len(swapped)} non-polar two-pin parts read with pins 1 / 2 the other way round under this "
                 f"convention (harmless on R / C); polar parts affected: {polar_rot}")


compare_schematic("routed", ROUTED)
GEN = Export(harness.GENERATED)
compare_schematic("generated", GEN)


# ----------------------------------------------------------------------------------------------------------
# G  design.md's tables and stated values against circuit.py
DESIGN = open(os.path.join(harness.MODULE, "docs", "design.md"), encoding="utf-8").read()
README = open(os.path.join(harness.MODULE, "README.md"), encoding="utf-8").read()


def md_table(after):
    """Rows (lists of cells) of the first markdown table after the first line containing `after`."""
    lines = DESIGN[DESIGN.index(after):].splitlines()
    rows, started = [], False
    for ln in lines[1:]:
        if ln.startswith("|"):
            started = True
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
        elif started:
            break
    return rows


ALL = {p.ref: p for p in MB + FB}

# latch table
lt = md_table("### Mute latch")
# the LED resistor's value as the Mute latch section's text writes it (2026-11-15: "Q drives the three selects of the
# channel's CD4053B and, through 1k5, the header and the button's LED to GND_F", one value on every channel)
LATCH_TEXT = DESIGN[DESIGN.index("### Mute latch"):].split("\n### ", 1)[0]
LED_WORD = {"1k5": ("1k5", "1.5 kΩ", "1k5 Ω")}
_led_doc = re.search(r"through\s+(\S+?),\s+the\s+header\s+and\s+the\s+button's\s+LED", LATCH_TEXT)
DOC_LED = _led_doc.group(1) if _led_doc else None
ck.check("G.latch_text_states_the_LED_resistor", DOC_LED is not None,
         "design.md's Mute latch text: 'through <R>, the header and the button's LED'")


def refs_in(cell):
    """'R104–R106' -> [R104, R105, R106]; 'R703, R704, R707' -> as listed."""
    m = re.fullmatch(r"R(\d+)\s*[–-]\s*R(\d+)", cell)
    if m:
        return [f"R{n}" for n in range(int(m.group(1)), int(m.group(2)) + 1)]
    return [r.strip() for r in cell.split(",")]


cols = lt[0][1:]
rows = {r[0]: r[1:] for r in lt[1:]}
want_rows = ["CD4093 gate", "CD4013 half", "Mute switch (CD4053B), its 100 n", "Bus resistors L, R, send",
             "Pull-up, debounce, LED resistor, debounce cap"]
latch_bad = [("rows", sorted(rows), "expected", want_rows)] if sorted(rows) != sorted(want_rows) else []
for i, ch in enumerate(cols):
    if sorted(rows) != sorted(want_rows):
        break
    k = int(ch)
    g = rows["CD4093 gate"][i]
    if g != "%s.%d" % circuit.NAND_OF[k]:
        latch_bad.append((k, "gate", g, circuit.NAND_OF[k]))
    h = rows["CD4013 half"][i]
    if h != "%s.%d" % circuit.FLOP_OF[k]:
        latch_bad.append((k, "half", h, circuit.FLOP_OF[k]))
    # the mute switch and its decoupling cap: U1k, a 100 n from +12V to GND labelled for that chip
    cell = rows["Mute switch (CD4053B), its 100 n"][i]
    m = re.fullmatch(r"(U\d+), (C\d+)", cell)
    u, cap = (m.group(1), ALL.get(m.group(2))) if m else (None, None)
    if not (m and u == circuit.SWITCH[k] and ALL[u].kind == "CD4053" and cap is not None and cap.value == "100n"
            and set(cap.nets.values()) == {"+12V", "GND"} and cap.label == f"{u} VDD"):
        latch_bad.append((k, "switch / 100 n", cell, circuit.SWITCH[k]))
    # the bus resistors in the order L, R, send: hot ends on the pan feeds / SEND wiper (mono) or the followers
    # (stereo), cold ends on BL / BR / BS; values 100k / 100k / 100k (mono), 200k / 200k / 100k (stereo)
    cell = rows["Bus resistors L, R, send"][i]
    brs = [ALL.get(r) for r in refs_in(cell)]
    hot = ([f"PL{k}", f"PR{k}", f"SD{k}"] if k in circuit.MONO else [f"CH{k}L", f"CH{k}R", f"SD{k}"])
    vals = ["100k"] * 3 if k in circuit.MONO else ["200k", "200k", "100k"]
    if not (len(brs) == 3 and all(brs) and all(r.kind == "R" and r.value == v and set(r.nets.values()) == {hn, f"B{b}{k}"}
                                               for r, v, hn, b in zip(brs, vals, hot, "LRS"))):
        latch_bad.append((k, "bus resistors", cell, [(r.ref, r.value, r.nets) if r else None for r in brs]))
    cell = rows["Pull-up, debounce, LED resistor, debounce cap"][i]
    m = re.match(r"R(\d+)\W+R(\d+), (C\d+)", cell)
    if not m:
        latch_bad.append((k, "R/C cell unreadable", cell))
        continue
    a, b, cap = int(m.group(1)), int(m.group(2)), m.group(3)
    trio = [ALL.get(f"R{n}") for n in range(a, b + 1)]
    c = ALL.get(cap)
    ok = len(trio) == 3 and all(trio) and c is not None
    if ok:
        pu, dbr, led = trio
        ok = (set(pu.nets.values()) == {"+12V", f"BTN{k}"} and pu.value == "100k"
              and set(dbr.nets.values()) == {f"BTN{k}", f"DB{k}"} and dbr.value == "10k"
              and set(led.nets.values()) == {f"QK{k}", f"LED{k}"}
              and DOC_LED in LED_WORD.get(led.value, (led.value,))
              and set(c.nets.values()) == {f"DB{k}", "GND"} and c.value == "100n")
    if not ok:
        latch_bad.append((k, "R/C", cell, "LED resistor in the text", DOC_LED,
                          "in circuit.py", trio[2].value if len(trio) == 3 and trio[2] else None))
ck.check("G.latch_table", not latch_bad and len(cols) == 8, f"design.md latch table against circuit.py: {latch_bad}")
# "Q high = muted: Q drives the three selects of the channel's CD4053B and, through 1k5, the header and the
# button's LED": QK<k> is the flip-flop's Q, the three selects and the LED resistor, nothing else
q_bad = []
for k in circuit.MONO + circuit.STEREO:
    u, hf = circuit.FLOP_OF[k]
    sw = circuit.SWITCH[k]
    want = {f"{u}.{CD4013_DS[hf]['Q']}"} | {f"{sw}.{CD4053B_DS[s]}" for s in "ABC"} | {f"{_LED_R[k].ref}.1",
                                                                                       f"{_LED_R[k].ref}.2"}
    got = set(MBN[f"QK{k}"])
    if not (got <= want and len(got) == 5):
        q_bad.append((k, sorted(got)))
ck.check("G.Q_drives_the_selects_and_the_LED", not q_bad,
         f"design.md: Q drives the three selects and the LED resistor; QK nets with other members: {q_bad}")

# op-amp table
ot = md_table("### Op-amps")
hdr = ot[0][1:]
op_bad = []
for s, hcell in enumerate(hdr, start=1):
    pins = tuple(re.search(r"\((\d+)/(\d+)/(\d+)\)", hcell).groups())
    if pins != circuit.SECTION[s]:
        op_bad.append(("header pins", s, pins, circuit.SECTION[s]))


def role(cell):
    m = re.match(r"follower (\d)(?: ([LR]))?$", cell)
    if m:
        return ("FOL", m.group(1) + (m.group(2) or ""))
    m = re.match(r"([LR]) summer$", cell)
    if m:
        return ("SUM", m.group(1))
    if cell == "send summer":
        return ("SUM", "S")
    if cell == "SEND output":
        return ("OUT", "S")
    m = re.match(r"OUT ([LR]) stage$", cell)
    if m:
        return ("OUT", m.group(1))
    return ("?", cell)


for r in ot[1:]:
    for s, cell in enumerate(r[1:], start=1):
        if role(cell) != circuit.OPAMPS[(r[0], s)]:
            op_bad.append((r[0], s, cell, circuit.OPAMPS[(r[0], s)]))
ck.check("G.opamp_table", not op_bad and len(ot) == 5, f"design.md op-amp table against OPAMPS / SECTION: {op_bad}")
roles = collections.Counter(v[0] for v in circuit.OPAMPS.values())
ck.check("G.architecture_opamp_counts", (roles["FOL"], roles["SUM"], roles["OUT"]) == (10, 3, 3),
         f"design.md: 10 followers, 3 summers, 3 output stages; got {roles['FOL']}, {roles['SUM']}, {roles['OUT']}")

# header table
hdrs = {ref: [a for a, b in pins] for ref, kind, pins in circuit.HEADERS}
ht = [r for r in md_table("Pin 1 at the top (front view)") if r[0] != "Header"]
ht_bad = [(r[0], [c.strip() for c in r[1].split(",")], hdrs.get(r[0])) for r in ht
          if [c.strip() for c in r[1].split(",")] != hdrs.get(r[0])]
ck.check("G.header_table", not ht_bad and len(ht) == 9, f"design.md header table against circuit.HEADERS: {ht_bad}")
m = re.search(r"(\w+) GND pins\s+join", DESIGN)
words = {"Nine": 9, "Ten": 10, "Eleven": 11, "Twelve": 12}
ck.check("G.header_ground_pin_count_text", bool(m) and words.get(m.group(1)) == gnd_pins,
         f"design.md says '{m.group(0) if m else None}'; circuit.HEADERS has {gnd_pins} GND pins "
         f"(H1-H6 one each, H7 / H8 two each, H9 one)")
m = re.search(r"(\d+) pins in (\d+) headers", DESIGN)
ck.check("G.header_pin_count_text", bool(m) and (int(m.group(1)), int(m.group(2))) ==
         (sum(len(p) for _, _, p in circuit.HEADERS), len(circuit.HEADERS)), f"design.md '{m.group(0) if m else None}'")


# signal flow and stated values
def find_parts(kind, value, nets):
    return [p for p in MB + FB if p.kind == kind and (value is None or p.value == value)
            and sorted(p.nets.values()) == sorted(nets)]


flow_bad = []
for k in circuit.MONO:
    for cl in [("R", "10k", [f"LV{k}", f"FI{k}"]), ("R", "10k", [f"CH{k}", f"PL{k}"]), ("R", "10k", [f"CH{k}", f"PR{k}"]),
               ("R", "100k", [f"PL{k}", f"BL{k}"]), ("R", "100k", [f"PR{k}", f"BR{k}"]), ("R", "100k", [f"SD{k}", f"BS{k}"])]:
        if len(find_parts(*cl)) != 1:
            flow_bad.append((k, cl))
    lv, pan, snd = (PARTS["face"][f"RV{3 * k - j}"] for j in (2, 1, 0))
    if not (lv.value == "A100k" and lv.nets["3"] == f"IN{k}_F" and lv.nets["2"] == f"LV{k}_F"):
        flow_bad.append((k, "LEVEL", lv.value, lv.nets))
    if not (pan.value == "B10k" and pan.nets["2"] == "GND_F" and {pan.nets["1"], pan.nets["3"]} == {f"PL{k}_F", f"PR{k}_F"}):
        flow_bad.append((k, "PAN", pan.value, pan.nets))
    if not (snd.value == "A100k" and snd.nets["3"] == f"CH{k}_F" and snd.nets["2"] == f"SD{k}_F"):
        flow_bad.append((k, "SEND", snd.value, snd.nets))
for c in circuit.STEREO:
    for cl in [("R", "10k", [f"LV{c}L", f"FI{c}L"]), ("R", "10k", [f"LV{c}R", f"FI{c}R"]),
               ("R", "200k", [f"CH{c}L", f"BL{c}"]), ("R", "200k", [f"CH{c}R", f"BR{c}"]),
               ("R", "10k", [f"CH{c}L", f"AV{c}"]), ("R", "10k", [f"CH{c}R", f"AV{c}"]), ("R", "100k", [f"SD{c}", f"BS{c}"])]:
        if len(find_parts(*cl)) != 1:
            flow_bad.append((c, cl))
for cl in [("R", "200k", ["RW_L", "SUM_L"]), ("R", "200k", ["RW_R", "SUM_R"]), ("R", "300k", ["DRW", "SUM_L"]),
           ("R", "300k", ["DRW", "SUM_R"]), ("R", "100k", ["FXI", "SUM_S"]),
           ("R", "100k", ["SUM_L", "MIX_L"]), ("C", "22p", ["SUM_L", "MIX_L"]), ("R", "100k", ["SUM_R", "MIX_R"]),
           ("C", "22p", ["SUM_R", "MIX_R"]), ("R", "100k", ["SUM_S", "MIX_S"]), ("C", "22p", ["SUM_S", "MIX_S"]),
           ("R", "100k", ["MST_L", "NO_L"]), ("R", "200k", ["NO_L", "OA_L"]), ("R", "1k", ["OA_L", "OUT_L"]),
           ("R", "100k", ["MST_R", "NO_R"]), ("R", "200k", ["NO_R", "OA_R"]), ("R", "1k", ["OA_R", "OUT_R"]),
           ("R", "100k", ["MIX_S", "NO_S"]), ("R", "100k", ["NO_S", "OA_S"]), ("R", "1k", ["OA_S", "SEND"]),
           ("R", "10R", ["P12_D", "+12V"]), ("R", "10R", ["N12_D", "-12V"]), ("C", "1u", ["+12V", "POR"]),
           ("R", "100k", ["POR", "GND"])]:
    if len(find_parts(*cl)) != 1:
        flow_bad.append(cl)
for ref, label, value, a, b in circuit.POTS2:
    if value != "A100k":
        flow_bad.append((ref, label, value))
mst, ret = PARTS["face"]["RV25"].nets, PARTS["face"]["RV23"].nets
if not (mst["3"] == "MIX_L_F" and mst["2"] == "MST_L_F" and mst["6"] == "MIX_R_F" and mst["5"] == "MST_R_F"):
    flow_bad.append(("MASTER", mst))
if not (ret["3"] == "RT_L_F" and ret["2"] == "RW_L_F" and ret["6"] == "RT_R_F" and ret["5"] == "RW_R_F"):
    flow_bad.append(("RETURN", ret))
drm = PARTS["face"]["RV24"]
if not (drm.value == "A100k" and drm.nets["3"] == "DRM_F" and drm.nets["2"] == "DRW_F"):
    flow_bad.append(("DRUMS", drm.nets))
ck.check("G.signal_flow_parts", not flow_bad, f"every part the signal-flow drawing names, value and nets: {flow_bad}")
# design.md, "Mute" / "Nothing on the input side" (2026-11-15): the switch works on the summing ends of the bus
# resistors only; it touches neither the LEVEL wiper (LV), the follower's input (FI) nor its output (CH)
touch = {u: sorted(n for n in PARTS["main"][u].nets.values() if re.match(r"(LV|FI|CH|IN)\d", n))
         for u in circuit.SWITCH.values()}
ck.check("G.mute_leaves_the_input_side_alone", not any(touch.values()),
         f"design.md: a mute leaves the LEVEL wiper and the follower alone; switch pins on LV / FI / CH: "
         f"{ {u: t for u, t in touch.items() if t} }")
# "Send is post-fader and post-mute": the SEND pot hangs off CH k / AV c, and its bus resistor's end is switched by
# the channel's section c like the L / R ones
send_bad = [k for k in circuit.MONO if PARTS["face"][f"RV{3 * k}"].nets["3"] != f"CH{k}_F"]
send_bad += [k for k, rv in ((7, "RV20"), (8, "RV22")) if PARTS["face"][rv].nets["3"] != f"AV{k}_F"]
send_bad += [(k, "send resistor not switched") for k in circuit.MONO + circuit.STEREO
             if not (len(find_parts("R", "100k", [f"SD{k}", f"BS{k}"])) == 1 and
                     PARTS["main"][circuit.SWITCH[k]].nets[CD4053B_DS["C COM"]] == f"BS{k}")]
ck.check("G.send_post_fader_post_mute", not send_bad,
         f"design.md: SEND pot tops on CH k (mono) / AV c (stereo), after the follower; SD k -> 100k -> BS k on the "
         f"switch's c common; bad: {send_bad}")
# design.md, Power: "100 n per TL074 per rail beside pins 4 and 11; 100 n per CMOS chip beside its VDD pin (14; 16
# on the CD4053Bs)"
n_amp = sum(1 for p in MB if p.kind == "TL074")
n_cmos = sum(1 for p in MB if p.kind in ("CD4093", "CD4013", "CD4053"))
dec_p, dec_n = find_parts("C", "100n", ["+12V", "GND"]), find_parts("C", "100n", ["GND", "-12V"])
ck.check("G.decoupling_counts", (len(dec_p), len(dec_n)) == (n_amp + n_cmos, n_amp),
         f"design.md: 100n per TL074 per rail and per CMOS chip ({n_amp} TL074, {n_cmos} CMOS): +12V caps {len(dec_p)} "
         f"(want {n_amp + n_cmos}), -12V caps {len(dec_n)} (want {n_amp})")
kinds = collections.Counter(p.kind for p in MB + FB)
ck.check("G.panel_counts", (kinds["POT"], kinds["POT2"], kinds["SWLED"], kinds["JACK"]) == (21, 4, 8, 17),
         f"README: 25 knobs (4 dual-gang), 8 LED buttons, 17 jacks; got {kinds['POT']} + {kinds['POT2']} pots, "
         f"{kinds['SWLED']} buttons, {kinds['JACK']} jacks")
ck.check("G.main_counts", (kinds["TL074"], kinds["CD4053"], kinds["CD4093"], kinds["CD4013"], kinds["PHOTOMOS"])
         == (4, 8, 2, 4, 0),
         f"design.md: 4 TL074, 8 CD4053B mute switches, 2 CD4093, 4 CD4013, no PhotoMOS left; got {kinds['TL074']}, "
         f"{kinds['CD4053']}, {kinds['CD4093']}, {kinds['CD4013']}, {kinds['PHOTOMOS']}")
fb_other = [p.ref for p in FB if p.kind not in ("JACK", "POT", "POT2", "SWLED", "HDR8", "HDR12")]
ck.check("G.faceplate_only_panel_parts", not fb_other, f"design.md: faceplate holds panel parts and headers only; "
                                                       f"others: {fb_other}")

ck.done()
