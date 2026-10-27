"""Generic structural checker for .vpp files (any diagram type).

Returns a list of problems; empty list = OK. The checks are the ones that
VP-authored files always satisfy (tested on files saved by VP 2026), so a
failure means our edit broke something.
"""
from __future__ import annotations

import collections
import sqlite3
from typing import Dict, List, Set

from .notation import Obj, Lst, Raw, At, parse, dump
from .project import _txt, _walk_objs


def _refs(o: Obj) -> List[str]:
    out = []

    def val(v):
        if isinstance(v, Raw):
            if v.text.startswith("<") and v.text.endswith(">"):
                out.append(v.text[1:-1])
        elif isinstance(v, Obj):
            for _, x in v.entries:
                val(x)
        elif isinstance(v, Lst):
            for it in v.items:
                val(it.value if isinstance(it, At) else it)

    for _, v in o.entries:
        val(v)
    return out


def verify(path: str, max_errors: int = 50) -> List[str]:
    errs: List[str] = []

    def E(m):
        if len(errs) < max_errors:
            errs.append(m)

    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    r = c.execute("PRAGMA integrity_check").fetchone()[0]
    if r != "ok":
        E(f"SQLite integrity_check: {r}")

    rows: Dict[str, tuple] = {}          # id -> (table, type, obj, parent, diagram, model)
    nested: Dict[str, Set[str]] = {}     # row id -> nested object ids
    all_ids = collections.Counter()
    for table, q in (("MODEL_ELEMENT", "select ID, MODEL_TYPE, DEFINITION, PARENT_ID, NULL, NULL from MODEL_ELEMENT"),
                     ("DIAGRAM", "select ID, DIAGRAM_TYPE, DEFINITION, NULL, NULL, NULL from DIAGRAM"),
                     ("DIAGRAM_ELEMENT", "select ID, SHAPE_TYPE, DEFINITION, PARENT_ID, DIAGRAM_ID, MODEL_ELEMENT_ID from DIAGRAM_ELEMENT")):
        for i, t, d, pid, did, mid in c.execute(q):
            s = _txt(d)
            try:
                o = parse(s)
            except Exception as e:  # noqa
                E(f"{table} {i}: nie da się sparsować ({e})")
                continue
            if dump(o) != s:
                E(f"{table} {i}: zapis nie jest w kanonicznym formacie VP")
            if o.id != i:
                E(f"{table} {i}: ID w nagłówku {o.id} != ID wiersza")
            if o.type != t:
                E(f"{table} {i}: typ w nagłówku {o.type} != {t}")
            rows[i] = (table, t, o, pid, did, mid)
            ids = {x.id for x in _walk_objs(o)}
            nested[i] = ids - {i}
            all_ids.update(ids)
    for i, n in all_ids.items():
        if n > 1:
            E(f"ID {i} występuje {n} razy")

    def resolves(path: str) -> bool:
        head, *members = path.split("$")
        segs = head.split(":")
        if any(sg not in rows for sg in segs):
            return False
        last = segs[-1]
        return all(m in nested.get(last, ()) for m in members)

    for i, (table, t, o, pid, did, mid) in rows.items():
        for rf in _refs(o):
            if not resolves(rf):
                E(f"{table} {i} ({t}): odwołanie <{rf}> nie istnieje")

    # model <-> view
    for i, (table, t, o, pid, did, mid) in rows.items():
        if table != "MODEL_ELEMENT":
            continue
        for x in _walk_objs(o):
            mv = x.get("_modelViews")
            if isinstance(mv, Lst):
                for v in mv.items:
                    if isinstance(v, Obj):
                        vid = v.text("view")
                        if vid not in rows or rows[vid][0] != "DIAGRAM_ELEMENT":
                            E(f"{t} {x.name or x.id}: widok {vid} nie istnieje")
    for i, (table, t, o, pid, did, mid) in rows.items():
        if table != "DIAGRAM_ELEMENT":
            continue
        if did not in rows:
            E(f"Kształt {i}: diagram {did} nie istnieje")
        if mid and mid not in rows:
            E(f"Kształt {i}: element modelu {mid} nie istnieje")
        if pid and pid not in rows:
            E(f"Kształt {i}: rodzic {pid} nie istnieje")

    # diagram child lists
    for i, (table, t, o, *_r) in rows.items():
        if table != "DIAGRAM":
            continue
        listed = set()
        for rf in o.refs("Child"):
            listed.add(rf.split(":")[-1])
            if rf.split(":")[0] != i:
                E(f"Diagram {i}: element listy Child {rf} należy do innego diagramu")
        for j, (tb, tt, oo, pid, did, mid) in rows.items():
            if tb == "DIAGRAM_ELEMENT" and did == i and pid is None and j not in listed:
                E(f"Diagram {i}: kształt {j} ({tt}) nie jest na liście Child diagramu")

    # containers
    for i, (table, t, o, pid, *_r) in rows.items():
        if t == "ModelRelationshipContainer":
            kids = {rf.split(":")[-1] for rf in o.refs("Child")}
            actual = {j for j, rr in rows.items() if rr[0] == "MODEL_ELEMENT" and rr[3] == i}
            if kids != actual:
                E(f"Kontener {o.name}: lista Child różni się od wierszy (brakuje {sorted(actual - kids)[:3]}, nadmiar {sorted(kids - actual)[:3]})")

    # project lists
    info = c.execute("select ROOT_MODEL_ELEMENTS_DEFINITION, DIAGRAMS_DEFINITION from PROJECT_INFO").fetchone()
    root = {x.split(":")[-1] for x in parse(info[0]).refs("Child")}
    actual_root = {j for j, rr in rows.items() if rr[0] == "MODEL_ELEMENT" and rr[3] is None}
    if root != actual_root:
        E(f"PROJECT_INFO rootModelElements != elementy bez rodzica (brakuje {sorted(actual_root - root)[:3]}, nadmiar {sorted(root - actual_root)[:3]})")
    dl = {x.split(":")[-1] for x in parse(info[1]).refs("Child")}
    actual_dl = {j for j, rr in rows.items() if rr[0] == "DIAGRAM"}
    if dl != actual_dl:
        E("PROJECT_INFO rootDiagrams != wiersze DIAGRAM")
    c.close()
    return errs
