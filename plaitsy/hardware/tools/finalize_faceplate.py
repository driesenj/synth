"""Route the faceplate board, verify it with the editor's own checker, and
write the importable project plus build previews."""
import json
import math

import sb
import faceplate
import route

OUT = "../stripboard/plaitsy-faceplate-board.json"


def mb_hole(r, c):
    return r, 22 - c


def main():
    b = faceplate.build()
    route.route(b, "fb", opts={"strictWires": True})
    errors, _ = b.check()
    assert not errors, errors
    pins = sorted((p.pos, p.net("1")) for p in b.parts.values() if p.ref.startswith("P"))
    lines = ["Plaitsy faceplate board (FB). Seen from the front (component side to the panel).",
             "Build it from two pieces of stripboard, strips running ACROSS the module:",
             f"  upper piece rows 0-{faceplate.SPLIT} ({faceplate.SPLIT + 1} strips), lower piece rows "
             f"{faceplate.SPLIT + 1}-40 ({40 - faceplate.SPLIT} strips), both 23 holes wide.",
             "Link wires that cross the split are short flying wires between the pieces.",
             "Long and diagonal links: use insulated wire and route it around parts.",
             "",
             "Board-to-board pins (male, sticking out of the copper side). Each meets the main",
             "board socket at main-board hole (row, 22 - col):"]
    for (r, c), net in pins:
        lines.append(f"  FB ({r:2d},{c:2d}) -> MB ({r:2d},{22 - c:2d})  {net}")
    notes = "\n".join(lines)
    sb.export_project(b, OUT, "Plaitsy - faceplate board",
                      "Plaits clone: jacks, pots, LEDs, buttons, pot mux. 23 x 41, two pieces.", notes)
    print(route.editor_check(b, "fb_final"))
    sb.render(b, "../stripboard/plaitsy-faceplate-board-front.png",
              title="Plaitsy faceplate board - component side (front view)")
    sb.render(b, "../stripboard/plaitsy-faceplate-board-copper.png", copper_side=True,
              title="Plaitsy faceplate board - COPPER side (mirrored): cuts + solder")
    json.dump({"pins": [{"fb": [r, c], "mb": list(mb_hole(r, c)), "net": n} for (r, c), n in pins],
               "split_after_row": faceplate.SPLIT},
              open("../stripboard/faceplate-interconnect.json", "w"), indent=1)
    print(b.stats())


if __name__ == "__main__":
    main()
