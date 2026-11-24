"""Generalization between actors (not classifiers) must not break Model setup (no VPP_SAMPLE needed)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from vpp_mcp.project import Project  # noqa: E402
from vpp_mcp.sequence import Model  # noqa: E402


class _Obj:
    def children(self):
        return []


class _Row:
    def __init__(self, i, name):
        self.id, self.name, self.obj = i, name, _Obj()


class _Proj:
    def __init__(self, rows, rels):
        self._rows, self._rels = rows, rels
        self.me = {r.id: r for r in rows}

    def classifiers(self):
        return self._rows

    def relationships(self):
        return self._rels

    find_class = Project.find_class


def test_actor_generalization_is_skipped_class_generalization_kept():
    rows = [_Row('1', 'Base'), _Row('2', 'Derived'), _Row('3', 'Iface')]
    rels = [{'kind': 'generalization', 'subclass': 'Actor3', 'superclass': 'Actor2'},
            {'kind': 'generalization', 'subclass': 'Derived', 'superclass': 'Actor2'},
            {'kind': 'generalization', 'subclass': 'Derived', 'superclass': 'Base'},
            {'kind': 'realization', 'class': 'Derived', 'interface': 'Iface'}]
    m = Model(_Proj(rows, rels))
    assert m.supers == {'2': ['1', '3']}
