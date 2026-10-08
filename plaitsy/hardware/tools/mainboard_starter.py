"""Main-board starter project: the Seed breakout and every board-to-board
socket placed and locked where the faceplate needs them, the LED resistors in
place under the breakout, everything else unplaced for the editor's
Auto-layout (lock the board size first)."""
import json

import sb
from sb import Board, Part, PartDef, Pin
from circuit import main_board_parts, LED_ORDER
import route

SOCKET = PartDef("custom-plaitsy-ic-socket", "Board-to-board socket (MB female)", "connector-1", "S",
                 [Pin("1", "1", 0, 0)], category="connector", custom=True, has_value=False)


def build():
    b = Board("mainboard", 41, 23)
    for p in main_board_parts():
        if p.ref == "U2":
            p.pos, p.rot = (0, 1), 0
        if p.ref.startswith("R") and 60 <= int(p.ref[1:]) <= 74:
            r = 4 + int(p.ref[1:]) - 60
            p.p1, p.p2 = (r, 2), (r, 5)  # Seed GPIO side / socket side, under the breakout
        b.add(p)
    pins = json.load(open("../stripboard/faceplate-interconnect.json"))["pins"]
    for i, pin in enumerate(sorted(pins, key=lambda q: q["mb"])):
        r, c = pin["mb"]
        b.add(Part(f"S{r}_{c}", SOCKET, nets={"1": pin["net"]}, pos=(r, c),
                   sch=(3000 + 240 * (i % 4), 100 + 80 * (i // 4))))
    return b


def main():
    b = build()
    sb.autocut(b)  # isolate the locked parts from each other
    bad = route.schematic_ok(b)
    assert not bad, bad
    notes = ("Plaitsy main board starter, seen from the component side (the side the breakout plugs into).\n"
             "Locked: the breakout (columns 1 and 7, USB/audio end at row 0) and the board-to-board sockets,\n"
             "which must stay where they are: each meets a faceplate pin at faceplate hole (row, 22 - col).\n"
             "LED resistors are placed under the breakout. Run Auto-layout for the rest with the board size locked.\n"
             "Leave out the socket contacts the breakout does not use (see docs/design.md), so strips can pass.\n"
             "Build it from two pieces of 24-strip stripboard split between rows 23 and 24.")
    proj = sb.export_project(b, "../stripboard/plaitsy-main-board-starter.json", "Plaitsy - main board (starter)",
                             "Seed breakout + sockets locked; place the CV input stages with Auto-layout.", notes)
    lock = {"U2"} | {p.ref for p in b.parts.values() if p.ref.startswith("S")} | {f"R{60 + i}" for i in range(15)}
    for c in proj["components"]:
        if c["label"] in lock:
            c["locked"] = True
    json.dump(proj, open("../stripboard/plaitsy-main-board-starter.json", "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)
    print(route.editor_check(b, "mb_starter"))
    placed = sum(1 for p in b.parts.values() if p.placed())
    print(f"{len(b.parts)} parts, {placed} placed and locked, {len(b.parts) - placed} for Auto-layout")


if __name__ == "__main__":
    main()
