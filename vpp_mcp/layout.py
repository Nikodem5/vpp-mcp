"""Automatic placement of class boxes on a class diagram (simulated annealing).

Visual Paradigm draws a relationship as a straight line between the CENTRES of the two shapes (clipped at their borders),
so a good layout is one where those lines do not cross other classes or each other, related classes sit close together and
the whole picture is compact. Pure functions, no dependency on the project format.
"""
import math
import random
from typing import Dict, List, Optional, Sequence, Set, Tuple

Box = Tuple[float, float, float, float]          # x, y, w, h


def _center(b: Box) -> Tuple[float, float]:
    return b[0] + b[2] / 2.0, b[1] + b[3] / 2.0


def _seg_hits_box(p, q, b: Box, pad: float = 6.0) -> bool:
    """Does the segment p-q cross the rectangle b (Liang-Barsky)?"""
    x0, y0, x1, y1 = b[0] - pad, b[1] - pad, b[0] + b[2] + pad, b[1] + b[3] + pad
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pp == 0:
            if qq < 0:
                return False
        else:
            r = qq / pp
            if pp < 0:
                if r > t1:
                    return False
                t0 = max(t0, r)
            else:
                if r < t0:
                    return False
                t1 = min(t1, r)
    return t0 < t1


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def _cross(p1, p2, p3, p4) -> bool:
    return _ccw(p1, p3, p4) != _ccw(p2, p3, p4) and _ccw(p1, p2, p3) != _ccw(p1, p2, p4)


def _gap(a: Box, b: Box) -> float:
    dx = max(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]), 0)
    dy = max(b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]), 0)
    return math.hypot(dx, dy)


def cost(boxes: Sequence[Box], edges: Sequence[Tuple[int, int]], margin: float = 50.0, min_gap: float = 70.0,
         aspect: float = 1.5) -> float:
    n = len(boxes)
    c = 0.0
    for i in range(n):
        a = boxes[i]
        for j in range(i + 1, n):
            b = boxes[j]
            ox = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]) + margin
            oy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]) + margin
            if ox > 0 and oy > 0:
                c += 400 + 4 * min(ox, oy)
    cent = [_center(b) for b in boxes]
    for i, j in edges:
        for k in range(n):
            if k != i and k != j and _seg_hits_box(cent[i], cent[j], boxes[k]):
                c += 900
        g = _gap(boxes[i], boxes[j])
        if g < min_gap:
            c += (min_gap - g) * 6
        c += 0.35 * g
    for e1 in range(len(edges)):
        for e2 in range(e1 + 1, len(edges)):
            a, b = edges[e1], edges[e2]
            if len({a[0], a[1], b[0], b[1]}) < 4:
                continue
            if _cross(cent[a[0]], cent[a[1]], cent[b[0]], cent[b[1]]):
                c += 450
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    w, h = max(x1 - x0, 1), max(y1 - y0, 1)
    c += 0.06 * (w + h) + 160 * abs(math.log(w / h / aspect))
    return c


def auto_layout(boxes: Sequence[Box], edges: Sequence[Tuple[int, int]], movable: Optional[Set[int]] = None,
                steps: int = 14000, restarts: int = 6, seed: int = 7, grid: int = 10) -> List[Tuple[int, int]]:
    """New (x, y) for every box (fixed boxes keep theirs). ``edges`` are index pairs."""
    n = len(boxes)
    movable = set(range(n)) if movable is None else set(movable)
    if not movable:
        return [(int(b[0]), int(b[1])) for b in boxes]
    rng = random.Random(seed)
    total_w = sum(b[2] for b in boxes)
    total_h = sum(b[3] for b in boxes)
    span_x = max(total_w * 0.75, max(b[0] + b[2] for b in boxes))
    span_y = max(total_h * 0.75, max(b[1] + b[3] for b in boxes))

    def snap(v):
        return int(round(v / grid) * grid)

    best, best_c = None, float("inf")
    for r in range(restarts):
        cur = [list(b) for b in boxes]
        if r > 0:                                              # random start for the movable ones
            for i in movable:
                cur[i][0] = snap(rng.uniform(0, span_x))
                cur[i][1] = snap(rng.uniform(0, span_y))
        c_cur = cost([tuple(b) for b in cur], edges)
        t0, t1 = 260.0, 2.0
        for s in range(steps):
            t = t0 * (t1 / t0) ** (s / steps)
            i = rng.choice(tuple(movable))
            ox, oy = cur[i][0], cur[i][1]
            u = rng.random()
            if u < 0.55:
                cur[i][0] = snap(ox + rng.gauss(0, 60 + 200 * (1 - s / steps)))
                cur[i][1] = snap(oy + rng.gauss(0, 60 + 200 * (1 - s / steps)))
            elif u < 0.8 and len(edges):
                a, b = rng.choice(edges)
                o = b if a == i else a if b == i else rng.choice([a, b])
                ob = cur[o]
                side = rng.choice("lrtb")
                if side == "r":
                    cur[i][0], cur[i][1] = snap(ob[0] + ob[2] + 70), snap(ob[1] + rng.uniform(-100, 100))
                elif side == "l":
                    cur[i][0], cur[i][1] = snap(ob[0] - cur[i][2] - 70), snap(ob[1] + rng.uniform(-100, 100))
                elif side == "b":
                    cur[i][0], cur[i][1] = snap(ob[0] + rng.uniform(-150, 150)), snap(ob[1] + ob[3] + 70)
                else:
                    cur[i][0], cur[i][1] = snap(ob[0] + rng.uniform(-150, 150)), snap(ob[1] - cur[i][3] - 70)
            else:
                j = rng.choice(tuple(movable))
                if j == i:
                    continue
                cur[i][0], cur[i][1], cur[j][0], cur[j][1] = cur[j][0], cur[j][1], cur[i][0], cur[i][1]
                c_new = cost([tuple(b) for b in cur], edges)
                if c_new <= c_cur or rng.random() < math.exp((c_cur - c_new) / t):
                    c_cur = c_new
                else:
                    cur[i][0], cur[i][1], cur[j][0], cur[j][1] = cur[j][0], cur[j][1], cur[i][0], cur[i][1]
                continue
            c_new = cost([tuple(b) for b in cur], edges)
            if c_new <= c_cur or rng.random() < math.exp((c_cur - c_new) / t):
                c_cur = c_new
            else:
                cur[i][0], cur[i][1] = ox, oy
        if c_cur < best_c:
            best_c, best = c_cur, [tuple(b) for b in cur]
    # normalise: the top-left corner of the picture goes to (40, 40) when everything is movable
    dx = 40 - min(b[0] for b in best) if len(movable) == n else 0
    dy = 40 - min(b[1] for b in best) if len(movable) == n else 0
    return [(int(b[0] + dx), int(b[1] + dy)) for b in best]


def evaluate(boxes: Sequence[Box], edges: Sequence[Tuple[int, int]]) -> Dict[str, int]:
    """Counts of defects, for reporting: overlaps, lines through classes, crossing lines."""
    n = len(boxes)
    cent = [_center(b) for b in boxes]
    over = sum(1 for i in range(n) for j in range(i + 1, n)
               if min(boxes[i][0] + boxes[i][2], boxes[j][0] + boxes[j][2]) > max(boxes[i][0], boxes[j][0])
               and min(boxes[i][1] + boxes[i][3], boxes[j][1] + boxes[j][3]) > max(boxes[i][1], boxes[j][1]))
    through = sum(1 for i, j in edges for k in range(n) if k not in (i, j) and _seg_hits_box(cent[i], cent[j], boxes[k], 0))
    cross = 0
    for e1 in range(len(edges)):
        for e2 in range(e1 + 1, len(edges)):
            a, b = edges[e1], edges[e2]
            if len({a[0], a[1], b[0], b[1]}) == 4 and _cross(cent[a[0]], cent[a[1]], cent[b[0]], cent[b[1]]):
                cross += 1
    return {"nakładania": over, "linie_przez_klasy": through, "przecięcia_linii": cross}
