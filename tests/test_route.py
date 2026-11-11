"""Unit tests of the orthogonal router (pure geometry, no project file needed)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from vpp_mcp.layout import route_edges  # noqa: E402


def _inside(p, b, pad=0):
    return b[0] + pad < p[0] < b[0] + b[2] - pad and b[1] + pad < p[1] < b[1] + b[3] - pad


def test_routes_are_orthogonal_and_avoid_boxes():
    boxes = [(40, 40, 300, 160), (40, 400, 300, 160), (500, 40, 300, 160), (500, 220, 300, 160), (500, 400, 300, 160)]
    edges = [(0, 1), (0, 2), (1, 4), (2, 3), (0, 4), (3, 4)]
    for rt, (i, j) in zip(route_edges(boxes, edges), edges):
        pts = rt["points"]
        assert not rt.get("straight")
        for a, b in zip(pts, pts[1:]):
            assert a[0] == b[0] or a[1] == b[1], (a, b)
            for k, bx in enumerate(boxes):                  # sample points along every segment
                for t in range(0, 11):
                    q = (a[0] + (b[0] - a[0]) * t / 10, a[1] + (b[1] - a[1]) * t / 10)
                    assert not _inside(q, bx), (i, j, k, q)


def test_end_segments_are_perpendicular_and_long_enough():
    boxes = [(40, 40, 300, 160), (500, 300, 300, 160)]
    (rt,) = route_edges(boxes, [(0, 1)])
    pts, n0, n1 = rt["points"], rt["n0"], rt["n1"]
    d0 = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
    d1 = (pts[-2][0] - pts[-1][0], pts[-2][1] - pts[-1][1])
    assert (d0[0] * n0[0] + d0[1] * n0[1]) >= 20 and (d1[0] * n1[0] + d1[1] * n1[1]) >= 20


def test_parallel_edges_get_different_anchors():
    boxes = [(40, 40, 300, 160), (500, 40, 300, 160)]
    r = route_edges(boxes, [(0, 1), (0, 1)])
    assert r[0]["points"][0] != r[1]["points"][0]
