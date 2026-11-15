"""Put the generated main board into the routed master, keeping the routed
faceplate and panel.

The 2026-11-15 mute redesign (CD4053B switches at the buses' summing ends
instead of the AQY212EH PhotoMOS) changed the main board's netlist and
placement; the faceplate and the panel did not change. This takes

  the routed master  ../easyeda/StereoMixer-routed.epro2: every doc except the
                     "Mixer Main" board's (its BOARD, SCH, schematic pages and
                     PCB) and the library docs only those used
  the generated one  ../easyeda/StereoMixer.epro2 (easyeda_export.py): the
                     "Mixer Main" board's docs and the library docs they use

and writes the routed master again: the faceplate and panel exactly as routed
(tracks, pours, value labels), the main board placed and unrouted, to be
routed in EasyEDA. The generated library docs carry a fresh uuid and source
on every export, so a re-import takes them as they are (memory:
reference-easyeda-import-keeps-library-ids).

Run from stereo-mixer/hardware/tools:  python swap_main_board.py
(after python easyeda_export.py). Check with python copper_audit.py.
"""
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
EASYEDA = os.path.join(HERE, "..", "easyeda")
ROUTED = os.path.join(EASYEDA, "StereoMixer-routed.epro2")
GENERATED = os.path.join(EASYEDA, "StereoMixer.epro2")
BOARD_TITLE = "Mixer Main"
LIBRARY = ("FOOTPRINT", "SYMBOL", "DEVICE")
UUID = re.compile(r"[0-9a-f]{32}|[0-9a-f]{16}")


def read(path):
    """(zip member name of the .epru, other zip members {name: bytes}, docs [(DOCHEAD payload, lines)])."""
    with zipfile.ZipFile(path) as z:
        epru = next(n for n in z.namelist() if n.endswith(".epru"))
        other = {n: z.read(n) for n in z.namelist() if n != epru}
        lines = z.read(epru).decode("utf-8").split("\n")
    docs = []
    for line in lines:
        if not line:
            continue
        h, _, p = line.partition("||")
        if json.loads(h)["type"] == "DOCHEAD":
            docs.append([json.loads(p[:-1] if p.endswith("|") else p), []])
        docs[-1][1].append(line)
    return epru, other, docs


def meta(lines):
    for line in lines:
        h, _, p = line.partition("||")
        if json.loads(h)["type"] == "META":
            return json.loads(p[:-1] if p.endswith("|") else p)
    return {}


def same_doc(lines):
    """A doc's lines with the DOCHEAD's "client" (the editor session that wrote it) left out."""
    h, _, p = lines[0].partition("||")
    head = json.loads(p[:-1] if p.endswith("|") else p)
    head.pop("client", None)
    return [h, head] + lines[1:]


def main_board_docs(docs):
    """The uuids of the main board's BOARD, SCH, schematic pages and PCB."""
    board = next(d["uuid"] for d, ls in docs if d["docType"] == "BOARD" and meta(ls).get("title") == BOARD_TITLE)
    sch = next(d["uuid"] for d, ls in docs if d["docType"] == "SCH" and meta(ls).get("board") == board)
    pages = {d["uuid"] for d, ls in docs if d["docType"] == "SCH_PAGE" and meta(ls).get("schematic") == sch}
    pcb = next(d["uuid"] for d, ls in docs if d["docType"] == "PCB" and meta(ls).get("board") == board)
    return {board, sch, pcb} | pages, pcb


def library_closure(seed_docs, library):
    """The library docs the seed docs use, directly or through a device's symbol / footprint."""
    used, todo = set(), [ls for d, ls in seed_docs]
    while todo:
        text = "\n".join(todo.pop())
        for u in set(UUID.findall(text)) & set(library) - used:
            used.add(u)
            todo.append(library[u])
    return used


def main():
    epru, other, routed = read(ROUTED)
    _, _, gen = read(GENERATED)
    old_main, old_pcb = main_board_docs(routed)
    new_main, new_pcb = main_board_docs(gen)

    tracks = sum(1 for d, ls in routed if d["uuid"] == old_pcb for line in ls if line.startswith('{"type":"LINE"'))
    if tracks and "--force" not in sys.argv:
        sys.exit(f"the master's main board has {tracks} tracks: it has been routed since, and this would throw "
                 "them away. Run with --force if that is what you want.")
    keep = [(d, ls) for d, ls in routed if d["docType"] not in LIBRARY and d["uuid"] not in old_main]
    take = [(d, ls) for d, ls in gen if d["uuid"] in new_main]
    lib_r = {d["uuid"]: ls for d, ls in routed if d["docType"] in LIBRARY}
    lib_g = {d["uuid"]: ls for d, ls in gen if d["docType"] in LIBRARY}
    use_r = library_closure(keep, lib_r)
    use_g = library_closure(take, lib_g)
    # the library caches' net ports, ground flag and sheet frame are in both, differing only in the DOCHEAD's
    # editor "client" id: the routed copy is kept
    clash = sorted(u for u in use_r & use_g if same_doc(lib_r[u]) != same_doc(lib_g[u]))
    if clash:
        sys.exit(f"library docs with the same uuid but different content in both projects: {clash}")

    out, written = [], set()
    for typ in LIBRARY:                                   # library first, as EasyEDA writes it
        for lib, use in ((lib_r, use_r), (lib_g, use_g)):
            for u, ls in lib.items():
                if u in use and u not in written and next(d for d, l in routed + gen if d["uuid"] == u)["docType"] == typ:
                    out += ls
                    written.add(u)
    boards = [x for x in take if x[0]["docType"] == "BOARD"] + [x for x in keep if x[0]["docType"] == "BOARD"]
    rest_take = [x for x in take if x[0]["docType"] != "BOARD"]
    rest_keep = [x for x in keep if x[0]["docType"] != "BOARD"]
    order = ("SCH", "SCH_PAGE", "PCB", "CONFIG", "BLOB")
    for d, ls in boards:
        out += ls
    for typ in order:
        for d, ls in rest_take + rest_keep:
            if d["docType"] == typ:
                out += ls
    others = [x for x in rest_keep if x[0]["docType"] not in order]
    if others:
        sys.exit(f"unexpected doc types in the routed master: {sorted({d['docType'] for d, _ in others})}")

    dropped_lib = sorted(meta(lib_r[u]).get("title", u) for u in set(lib_r) - use_r)
    images = {n: b for n, b in other.items() if not (n.startswith("IMAGE/") and old_pcb in n)}
    with zipfile.ZipFile(ROUTED, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in images.items():
            z.writestr(n, b)
        z.writestr(epru, "\n".join(out) + "\n")
    print(f"{os.path.normpath(ROUTED)}: main board from {os.path.basename(GENERATED)} ({len(take)} docs, "
          f"{len(use_g)} library docs), faceplate and panel as routed ({len(keep)} docs, {len(use_r)} library docs); "
          f"dropped {len(dropped_lib)} library docs only the old main board used: {', '.join(dropped_lib)}")


if __name__ == "__main__":
    main()
