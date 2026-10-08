"""Run the stripboard-editor's own completion router (cuts + link wires) on a
Board whose parts are placed, via the Node harness, and merge the result."""
import json
import os
import subprocess
import tempfile

import sb

# Where the stripboard-editor checkout and the bundled Node harness live
# (see README: "Re-running the layout tools"). Override with env vars.
_DEFAULT = os.path.join(tempfile.gettempdir(), "claude", "C--Users-joep-Code-homelab-docs",
                        "b7127489-eb19-472b-b271-9890c6b43897", "scratchpad")
SCRATCH = os.environ.get("PLAITSY_SCRATCH", _DEFAULT)
HARNESS = os.environ.get("PLAITSY_HARNESS", os.path.join(SCRATCH, "sbtest"))
FE_DIR = os.environ.get("PLAITSY_FE", os.path.join(SCRATCH, "stripboard-editor", "src", "frontend"))


def editor_check(board: sb.Board, name):
    """Run the editor's own net inference + strip checker on a board."""
    p = os.path.join(SCRATCH, f"{name}_check.json")
    sb.export_project(board, p, name, "", "")
    res = subprocess.run(["node", os.path.join(HARNESS, "check_project.js"), p], capture_output=True, text=True)
    return (res.stdout + res.stderr).strip()


def schematic_ok(board: sb.Board):
    parts = list(board.parts.values())
    bad = []
    inferred = sb.infer_schematic_nets(parts)
    for p in parts:
        for pid in {q.id for q in p.pdef.pins}:
            if p.net(pid) != inferred.get((p.ref, pid)):
                bad.append((p.ref, pid, p.net(pid), inferred.get((p.ref, pid))))
    bad += [("overlap", x) for x in sb.check_schematic_overlaps(board)]
    return bad


def route(board: sb.Board, name, opts=None, keep_existing=True):
    bad = schematic_ok(board)
    if bad:
        raise SystemExit(f"schematic drawing does not match the netlist: {bad[:5]}")
    tmp_in = os.path.join(SCRATCH, f"{name}_route_in.json")
    tmp_out = os.path.join(SCRATCH, f"{name}_route_out.json")
    sb.export_project(board, tmp_in, name, "", "")
    env = dict(os.environ, FE_DIR=FE_DIR)
    args = ["node", os.path.join(HARNESS, "complete_board.js"), tmp_in, tmp_out]
    if opts:
        args.append(json.dumps(opts))
    res = subprocess.run(args, capture_output=True, text=True, env=env)
    print(res.stdout.strip())
    if res.returncode:
        print(res.stderr[-3000:])
        raise SystemExit("router failed")
    out = json.load(open(tmp_out))
    for c in out["cuts"]:
        board.cut(c["row"], c["col"], c.get("kind", "between"))
    for w in out["wires"]:
        board.link((w["from"]["row"], w["from"]["col"]), (w["to"]["row"], w["to"]["col"]))
    return out
