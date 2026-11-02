"""The mushroom mark at the foot of every panel, in place of the old maker line
(the user's pick, 2026-11-02): the "Mycelium" drawing, a cap and a stem on
branching threads, in bare ENIG gold, that is copper under a solder-mask
opening of the same shape, like the output bands. Every module's tools
folder holds an identical copy; copy it to a new module, don't import it
across modules.

polygons(panel_w) gives the mark as closed polygons in the panel frame (mm
from the top-left, y down): HEIGHT tall, GAP under the bottom rule's lower
edge, centred on the panel. On a 4HP panel the bottom screw sits at the
centre, so there the mark's left edge lines up with the title at x 12.
The polygons overlap where the threads meet the stem; draw each one as its
own fill (the SVG's nonzero rule unites them, as they share one winding).
"""
import math

HEIGHT, GAP = 4.1, 1.6           # mm: the drawing's height; its gap under the 0.3 mm rule at y 118.6
RULE_LOW = 118.75                # lower edge of that rule
TITLE_X = 12.0                   # the frame's title start, used on 4HP panels
THREAD_W = 0.55                  # units of the 10 x 10 drawing box: 0.24 mm at HEIGHT 4.1

# the drawing in a 10 x 10 unit box, y down: a start point and ("L", p) / ("C", c1, c2, p) segments
CAP = ((1.6, 4.4), [("C", (1.6, 2.1), (3.1, 0.7), (5.0, 0.7)), ("C", (6.9, 0.7), (8.4, 2.1), (8.4, 4.4)),
                    ("C", (6.6, 3.8), (3.4, 3.8), (1.6, 4.4))])
STEM = ((4.2, 4.55), [("L", (5.8, 4.55)), ("L", (5.8, 6.9)), ("C", (5.8, 7.3), (5.4, 7.5), (5.0, 7.6)),
                      ("C", (4.6, 7.5), (4.2, 7.3), (4.2, 6.9)), ("L", (4.2, 4.55))])
THREADS = [((5.0, 7.4), [("C", (4.0, 8.2), (2.4, 8.7), (0.6, 9.4))]),
           ((5.0, 7.4), [("C", (6.0, 8.2), (7.6, 8.7), (9.4, 9.4))]),
           ((5.0, 7.4), [("L", (5.0, 9.6))]),
           ((3.1, 8.45), [("C", (2.7, 8.95), (2.55, 9.3), (2.5, 9.7))]),
           ((6.9, 8.45), [("C", (7.3, 8.95), (7.45, 9.3), (7.5, 9.7))])]


def _flatten(start, segs, n=20):
    pts = [start]
    for seg in segs:
        p0 = pts[-1]
        if seg[0] == "L":
            pts.append(seg[1])
            continue
        _, c1, c2, p3 = seg
        for i in range(1, n + 1):
            t = i / n
            a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
            pts.append((a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0], a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1]))
    return pts


def _ribbon(pts, w, n=8):
    """The outline of a stroke of width w along pts, with round ends."""
    r = w / 2
    normals = []
    for i in range(len(pts)):
        (ax, ay), (bx, by) = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        d = math.hypot(bx - ax, by - ay)
        normals.append((-(by - ay) / d, (bx - ax) / d))
    left = [(x + r * nx, y + r * ny) for (x, y), (nx, ny) in zip(pts, normals)]
    right = [(x - r * nx, y - r * ny) for (x, y), (nx, ny) in zip(pts, normals)]

    def cap(p, nrm, sign):
        nx, ny = nrm
        dx, dy = ny * sign, -nx * sign            # the stroke's direction at this end, outwards
        return [(p[0] + r * (sign * nx * math.cos(a) + dx * math.sin(a)),
                 p[1] + r * (sign * ny * math.cos(a) + dy * math.sin(a)))
                for a in (math.pi * i / n for i in range(1, n))]

    return left + cap(pts[-1], normals[-1], 1) + right[::-1] + cap(pts[0], normals[0], -1)


def _area(poly):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1])) / 2


def _units():
    """The mark's polygons in drawing units, all with the same winding."""
    polys = [_flatten(*CAP)[:-1], _flatten(*STEM)[:-1]] + [_ribbon(_flatten(*t), THREAD_W) for t in THREADS]
    return [p if _area(p) > 0 else p[::-1] for p in polys]


def polygons(panel_w):
    """The mark placed on a panel panel_w mm wide: [[(x, y), ...], ...] in panel mm, y down."""
    polys = _units()
    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    k = HEIGHT / (max(ys) - min(ys))
    x0 = TITLE_X - min(xs) * k if panel_w < 25 else panel_w / 2 - (min(xs) + max(xs)) / 2 * k
    y0 = RULE_LOW + GAP - min(ys) * k
    return [[(round(x0 + x * k, 4), round(y0 + y * k, 4)) for x, y in p] for p in polys]


def svg_path(polys):
    """One SVG path for the artwork (fill it; the nonzero rule unites the overlapping pieces)."""
    return " ".join("M " + " L ".join(f"{x:.3f} {y:.3f}" for x, y in p) + " Z" for p in polys)


if __name__ == "__main__":
    for w in (20.0, 50.5):
        ps = polygons(w)
        xs, ys = [x for p in ps for x, _ in p], [y for p in ps for _, y in p]
        print(f"W {w}: x {min(xs):.2f}..{max(xs):.2f}, y {min(ys):.2f}..{max(ys):.2f}, "
              f"{len(ps)} polygons, {sum(map(len, ps))} points")
