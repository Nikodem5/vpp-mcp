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
    return max(dx, dy)          # orthogonal lines need room in one direction, not a diagonal distance


def cost(boxes: Sequence[Box], edges: Sequence[Tuple[int, int]], margin: float = 50.0, min_gap: float = 110.0,
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
    c += 5000 * sum(1 for b in boxes if b[0] < 20 or b[1] < 20)     # keep everything on the visible canvas
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


# ====================================================================== orthogonal routing
import heapq

G = 10                                  # routing grid (px)
_N = {"t": (0, -1), "b": (0, 1), "l": (-1, 0), "r": (1, 0)}


def _anchor(b: Box, side: str, frac: float) -> Tuple[int, int]:
    x, y, w, h = b
    if side == "t":
        return int(round((x + w * frac) / G) * G), int(y)
    if side == "b":
        return int(round((x + w * frac) / G) * G), int(y + h)
    if side == "l":
        return int(x), int(round((y + h * frac) / G) * G)
    return int(x + w), int(round((y + h * frac) / G) * G)


def route_edges(boxes: Sequence[Box], edges: Sequence[Tuple[int, int]], margin: int = 14,
                max_nodes: int = 60000) -> List[dict]:
    """Orthogonal polylines between box borders for every edge (i, j). Returns, per edge, a dict with ``points`` (absolute
    integer points from the border of box i to the border of box j; both end segments are >= 20 px and perpendicular to the
    border) and ``n0``/``n1`` (outward unit normals at the two ends). Edges are routed shortest first; bends, crossings
    and overlaps with earlier routes are penalised, so lines get separated and run around other classes."""
    n = len(boxes)
    minx = int(min(b[0] for b in boxes)) - 220
    miny = int(min(b[1] for b in boxes)) - 220
    maxx = int(max(b[0] + b[2] for b in boxes)) + 220
    maxy = int(max(b[1] + b[3] for b in boxes)) + 220
    minx, miny = max(minx, 0) // G * G, max(miny, 0) // G * G
    blocked = set()
    for b in boxes:
        for cx in range((int(b[0]) - margin) // G, (int(b[0] + b[2]) + margin) // G + 1):
            for cy in range((int(b[1]) - margin) // G, (int(b[1] + b[3]) + margin) // G + 1):
                blocked.add((cx, cy))
    used_h: Dict[Tuple[int, int], int] = {}
    used_v: Dict[Tuple[int, int], int] = {}
    anchors: Dict[Tuple[int, str], List[Tuple[int, int]]] = {}
    DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]

    def side_order(a: Box, tgt: Box) -> List[str]:
        ca, ct = _center(a), _center(tgt)
        dx, dy = ct[0] - ca[0], ct[1] - ca[1]
        sc = {"r": dx, "l": -dx, "b": dy, "t": -dy}
        return sorted("tblr", key=lambda s: -sc[s])

    def pick_anchor(i: int, side: str, other: Box) -> Optional[Tuple[int, int]]:
        b = boxes[i]
        used = anchors.get((i, side), [])
        co = _center(other)
        pref = ((co[0] - b[0]) / max(b[2], 1)) if side in "tb" else ((co[1] - b[1]) / max(b[3], 1))
        pref = min(0.85, max(0.15, pref))
        cands = sorted([0.15, 0.25, 0.35, 0.5, 0.65, 0.75, 0.85, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8], key=lambda f: abs(f - pref))
        for f in cands:
            a = _anchor(b, side, f)
            if all(abs(a[0] - u[0]) + abs(a[1] - u[1]) >= 24 for u in used):
                return a
        return None

    def endpoint_cell(i: int, side: str, a: Tuple[int, int]) -> Tuple[int, int]:
        b = boxes[i]
        if side == "r":
            return int(-(-(b[0] + b[2] + 20) // G)), a[1] // G
        if side == "l":
            return int((b[0] - 20) // G), a[1] // G
        if side == "b":
            return a[0] // G, int(-(-(b[1] + b[3] + 20) // G))
        return a[0] // G, int((b[1] - 20) // G)

    def astar(c0, c1, d0):
        """Orthogonal A*; state (cell, direction). Returns (cost, [cells]) or None."""
        if c0 == c1:
            return 0.0, [c0]
        lox, loy, hix, hiy = minx // G, miny // G, maxx // G, maxy // G
        start = (c0, d0)
        best = {start: 0.0}
        prev = {}
        heap = [(abs(c0[0] - c1[0]) * G + abs(c0[1] - c1[1]) * G, 0.0, c0, d0)]
        nodes = 0
        while heap:
            f, g, c, d = heapq.heappop(heap)
            if best.get((c, d), 1e18) < g:
                continue
            if c == c1:
                path = [c]
                s = (c, d)
                while s in prev:
                    s = prev[s]
                    path.append(s[0])
                return g, path[::-1]
            nodes += 1
            if nodes > max_nodes:
                return None
            for nd, (dx, dy) in enumerate(DIRS):
                if d is not None and DIRS[d] == (-dx, -dy):
                    continue
                nc = (c[0] + dx, c[1] + dy)
                if not (lox <= nc[0] <= hix and loy <= nc[1] <= hiy):
                    continue
                if nc in blocked and nc != c1 and nc != c0:
                    continue
                cost = G
                if d is not None and nd != d:
                    cost += 45
                if dy == 0:                                   # horizontal step
                    cost += 70 * used_h.get(nc, 0) + 55 * used_v.get(nc, 0)
                else:
                    cost += 70 * used_v.get(nc, 0) + 55 * used_h.get(nc, 0)
                ng = g + cost
                if ng < best.get((nc, nd), 1e18):
                    best[(nc, nd)] = ng
                    prev[(nc, nd)] = (c, d)
                    heapq.heappush(heap, (ng + (abs(nc[0] - c1[0]) + abs(nc[1] - c1[1])) * G, ng, nc, nd))
        return None

    order = sorted(range(len(edges)), key=lambda k: math.hypot(*[a - b for a, b in zip(_center(boxes[edges[k][0]]), _center(boxes[edges[k][1]]))]))
    result: List[Optional[dict]] = [None] * len(edges)
    for k in order:
        i, j = edges[k]
        bi, bj = boxes[i], boxes[j]
        best = None
        for si in side_order(bi, bj)[:2]:
            for sj in side_order(bj, bi)[:2]:
                a0, a1 = pick_anchor(i, si, bj), pick_anchor(j, sj, bi)
                if a0 is None or a1 is None:
                    continue
                c0, c1 = endpoint_cell(i, si, a0), endpoint_cell(j, sj, a1)
                d0 = DIRS.index(_N[si])
                r = astar(c0, c1, d0)
                if r is None:
                    continue
                cost = r[0] + 2 * (abs(a0[0] - a1[0]) + abs(a0[1] - a1[1])) * 0.0
                if best is None or cost < best[0]:
                    best = (cost, si, sj, a0, a1, r[1])
        if best is None:                                       # fallback: straight line between the borders
            ci, cj = _center(bi), _center(bj)
            result[k] = {"points": [(int(ci[0]), int(ci[1])), (int(cj[0]), int(cj[1]))], "n0": (0, 0), "n1": (0, 0), "straight": True}
            continue
        _, si, sj, a0, a1, cells = best
        anchors.setdefault((i, si), []).append(a0)
        anchors.setdefault((j, sj), []).append(a1)
        pts = [a0] + [(c[0] * G, c[1] * G) for c in cells] + [a1]
        # the first/last cell points must be on the normal through the anchor
        pts[1] = (pts[1][0] if si in "lr" else a0[0], pts[1][1] if si in "tb" else a0[1]) if len(pts) > 2 else pts[1]
        out = [pts[0]]
        for q in pts[1:]:
            if q != out[-1]:
                out.append(q)
        simp = [out[0]]                                        # drop collinear middle points
        for a, b, c in zip(out, out[1:], out[2:]):
            if (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1]):
                continue
            simp.append(b)
        simp.append(out[-1])
        for a, b in zip(simp, simp[1:]):
            if a[1] == b[1]:
                for cx in range(min(a[0], b[0]) // G, max(a[0], b[0]) // G + 1):
                    used_h[(cx, a[1] // G)] = used_h.get((cx, a[1] // G), 0) + 1
            elif a[0] == b[0]:
                for cy in range(min(a[1], b[1]) // G, max(a[1], b[1]) // G + 1):
                    used_v[(a[0] // G, cy)] = used_v.get((a[0] // G, cy), 0) + 1
        result[k] = {"points": simp, "n0": _N[si], "n1": _N[sj]}
    return result
