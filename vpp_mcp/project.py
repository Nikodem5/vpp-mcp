"""Read access to a Visual Paradigm .vpp project (SQLite + VP notation)."""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional

from .notation import Obj, Lst, Raw, At, parse, dump, unquote

VIS = {None: "-", "71": "+"}
VIS_NAME = {None: "private", "71": "public"}


class VppError(Exception):
    pass


def lock_path(path: str) -> str:
    d, f = os.path.split(os.path.abspath(path))
    return os.path.join(d, "." + f + ".lck")


def is_open_in_vp(path: str) -> bool:
    """VP keeps a ``.<file>.lck`` next to a project while it is open."""
    return os.path.exists(lock_path(path))


@dataclass
class Row:
    table: str
    id: str
    obj: Obj
    model_type: Optional[str] = None   # MODEL_ELEMENT.MODEL_TYPE / DIAGRAM_ELEMENT.SHAPE_TYPE / DIAGRAM_TYPE
    parent: Optional[str] = None
    name: Optional[str] = None
    diagram: Optional[str] = None      # DIAGRAM_ELEMENT.DIAGRAM_ID
    model: Optional[str] = None        # DIAGRAM_ELEMENT.MODEL_ELEMENT_ID


class Project:
    """Loads every model element, diagram and diagram element into parsed trees."""

    def __init__(self, path: str, readonly: bool = True):
        if not os.path.exists(path):
            raise VppError(f"Nie ma pliku: {path}")
        self.path = path
        uri = f"file:{path}?mode=ro" if readonly else f"file:{path}"
        self.conn = sqlite3.connect(uri, uri=True)
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.readonly = readonly
        self.reload()

    # ------------------------------------------------------------ loading
    def reload(self):
        c = self.conn
        self.me: Dict[str, Row] = {}
        for i, mt, pid, name, d in c.execute(
                "select ID, MODEL_TYPE, PARENT_ID, NAME, DEFINITION from MODEL_ELEMENT"):
            self.me[i] = Row("MODEL_ELEMENT", i, parse(_txt(d)), mt, pid, name)
        self.dg: Dict[str, Row] = {}
        for i, dt, name, d in c.execute("select ID, DIAGRAM_TYPE, NAME, DEFINITION from DIAGRAM"):
            self.dg[i] = Row("DIAGRAM", i, parse(_txt(d)), dt, None, name)
        self.de: Dict[str, Row] = {}
        for i, st, did, mid, pid, d in c.execute(
                "select ID, SHAPE_TYPE, DIAGRAM_ID, MODEL_ELEMENT_ID, PARENT_ID, DEFINITION from DIAGRAM_ELEMENT"):
            self.de[i] = Row("DIAGRAM_ELEMENT", i, parse(_txt(d)), st, pid, None, did, mid)
        info = c.execute("select ROOT_MODEL_ELEMENTS_DEFINITION, DIAGRAMS_DEFINITION, PROJECT_BUILD, DB_VERSION from PROJECT_INFO").fetchone()
        self.root_list = parse(info[0])
        self.diagram_list = parse(info[1])
        self.build, self.db_version = info[2], info[3]

    # ------------------------------------------------------------ lookups
    def by_type(self, mtype: str) -> List[Row]:
        return [r for r in self.me.values() if r.model_type == mtype]

    def classifiers(self) -> List[Row]:
        return self.by_type("Class")

    def stereotype_names(self, o: Obj) -> List[str]:
        out = []
        for r in o.refs("stereotypes"):
            row = self.me.get(r.split(":")[-1])
            if row:
                out.append(row.name)
        return out

    def kind_of(self, row: Row) -> str:
        st = [s.lower() for s in self.stereotype_names(row.obj)]
        if "interface" in st:
            return "interface"
        if "enumeration" in st:
            return "enumeration"
        if row.obj.text("abstract") == "T":
            return "abstract class"
        return "class"

    def find_class(self, name: str) -> Row:
        hits = [r for r in self.classifiers() if r.name == name]
        if not hits:
            # tolerate missing Polish letters (Użytkownik vs Uzytkownik)
            norm = _fold(name)
            hits = [r for r in self.classifiers() if _fold(r.name or "") == norm]
        if not hits:
            raise VppError(f"Nie ma klasy/interfejsu/enumeracji o nazwie {name!r}. "
                           f"Dostępne: {', '.join(sorted(r.name for r in self.classifiers()))}")
        if len(hits) > 1:
            raise VppError(f"Nazwa {name!r} jest niejednoznaczna ({len(hits)} elementy).")
        return hits[0]

    def datatype_id(self, name: str) -> Optional[str]:
        for r in self.by_type("DataType"):
            if r.name == name:
                return r.id
        return None

    def find_diagram(self, name_or_id: str, dtype: Optional[str] = None) -> Row:
        if name_or_id in self.dg:
            return self.dg[name_or_id]
        hits = [d for d in self.dg.values() if d.name == name_or_id and (dtype is None or d.model_type == dtype)]
        if not hits:
            raise VppError(f"Nie ma diagramu {name_or_id!r}. Dostępne: " +
                           ", ".join(f"{d.name} [{d.model_type}]" for d in self.dg.values()))
        return hits[0]

    def class_diagrams(self) -> List[Row]:
        return [d for d in self.dg.values() if d.model_type == "ClassDiagram"]

    def name_of(self, ref_text: str) -> str:
        """Human name for a ``<id>``/path reference to a model element."""
        rid = ref_text.strip("<>").split("$")[0].split(":")[-1]
        r = self.me.get(rid)
        return r.name if r and r.name else rid

    # ------------------------------------------------------------ types
    def type_text(self, o: Obj, key: str = "type") -> str:
        tb = o.get("templateTypeBindInfo")
        base = None
        v = o.get(key)
        if isinstance(v, Raw) and v.text.startswith("<"):
            base = self.name_of(v.text)
        elif o.has(key + "_string"):
            base = o.text(key + "_string")
        if isinstance(tb, Obj):
            args = []
            for det in _walk_objs(tb):
                if det is tb:
                    continue
                if det.type == "TemplateTypeBindInfo":
                    t = det.get("bindedType")
                    if isinstance(t, Raw) and t.text.startswith("<"):
                        args.append(self.name_of(t.text))
                    elif det.has("bindedType_string"):
                        args.append(det.text("bindedType_string"))
            if base and args:
                return f"{base}<{', '.join(args)}>"
        return base or ("void" if key == "returnType" else "")

    # ------------------------------------------------------------ describe
    def member_lines(self, row: Row) -> Dict[str, list]:
        attrs, ops, lits = [], [], []
        for m in row.obj.children():
            static = m.text("scope") == "65"
            if m.type == "Attribute":
                mult = m.text("multiplicity")
                t = self.type_text(m)
                s = f"{VIS.get(m.text('visibility'), '?')}{m.name} : {t}" + (f" [{mult}]" if mult else "")
                attrs.append({"text": s, "static": static})
            elif m.type == "Operation":
                ps = ", ".join(f"{p.name} : {self.type_text(p)}" for p in m.children() if p.type == "Parameter")
                ctor = not m.has("returnType") and not m.has("returnType_string") and m.name == row.name
                s = f"{VIS.get(m.text('visibility'), '?')}{m.name}({ps})" + ("" if ctor else f" : {self.type_text(m, 'returnType')}")
                ops.append({"text": s, "static": static, "abstract": m.text("abstract") == "T", "constructor": ctor})
            elif m.type == "EnumerationLiteral":
                lits.append(m.name)
        return {"attributes": attrs, "operations": ops, "literals": lits}

    def relationships(self) -> List[dict]:
        out = []
        for r in self.me.values():
            o = r.obj
            if r.model_type in ("Generalization", "Realization", "Usage", "Dependency"):
                f, t = o.get("fromModel"), o.get("toModel")
                if not (isinstance(f, Raw) and isinstance(t, Raw)):
                    continue
                fn, tn = self.name_of(f.text), self.name_of(t.text)
                st = self.stereotype_names(o)
                if r.model_type == "Generalization":
                    out.append({"kind": "generalization", "id": r.id, "subclass": tn, "superclass": fn, "text": f"{tn} --|> {fn}"})
                elif r.model_type == "Realization":
                    out.append({"kind": "realization", "id": r.id, "class": tn, "interface": fn, "text": f"{tn} ..|> {fn}"})
                else:
                    out.append({"kind": "dependency", "id": r.id, "from": fn, "to": tn, "stereotype": st[0] if st else None,
                                "text": f"{fn} ..> {tn}" + (f" «{st[0]}»" if st else "")})
            elif r.model_type == "Association":
                a, b = o.get("from"), o.get("to")
                if not (isinstance(a, Obj) and isinstance(b, Obj)):
                    continue
                if not (self._end_cls(a) in self.me and self._end_cls(b) in self.me):
                    continue
                ea, eb = self._end(a), self._end(b)
                if self.me[self._end_cls(a)].model_type != "Class" or self.me[self._end_cls(b)].model_type != "Class":
                    kind = "association (use case)"
                else:
                    kind = {"67": "composition", "66": "aggregation"}.get(ea["aggregation"] or eb["aggregation"] or "", None)
                    if not kind:
                        kind = "directed association" if ea["navigable"] == "2" else "association"
                sym = {"composition": "*--", "aggregation": "o--", "directed association": "-->"}.get(kind, "--")
                txt = (f"{ea['class']} \"{ea['multiplicity'] or ''}{(' ' + ea['role']) if ea['role'] else ''}\" {sym} "
                       f"\"{eb['multiplicity'] or ''}{(' ' + eb['role']) if eb['role'] else ''}\" {eb['class']}")
                out.append({"kind": kind, "id": r.id, "from": ea, "to": eb, "text": txt})
        return out

    def _end_cls(self, end: Obj) -> str:
        v = end.get("EndModelElement") or end.get("type")
        return v.text.strip("<>").split(":")[-1] if isinstance(v, Raw) else ""

    def _end(self, end: Obj) -> dict:
        return {"class": self.name_of("<" + self._end_cls(end) + ">"), "multiplicity": end.text("multiplicity"),
                "role": end.name, "aggregation": end.text("aggregationKind"), "navigable": end.text("navigable")}

    def shapes_on(self, diagram_id: str) -> List[Row]:
        return [r for r in self.de.values() if r.diagram == diagram_id]

    def shape_of(self, model_id: str, diagram_id: str) -> Optional[Row]:
        for r in self.de.values():
            if r.diagram == diagram_id and r.model == model_id and r.parent is None:
                return r
        return None

    def geometry(self, shape: Row):
        o = shape.obj
        return tuple(int(o.text(k, "0")) for k in ("x", "y", "width", "height"))

    def summary(self) -> dict:
        kinds = {}
        for r in self.classifiers():
            kinds[self.kind_of(r)] = kinds.get(self.kind_of(r), 0) + 1
        return {
            "plik": self.path,
            "otwarty_w_VP": is_open_in_vp(self.path),
            "VP_build": self.build,
            "diagramy": [{"nazwa": d.name, "typ": d.model_type, "id": d.id} for d in self.dg.values()],
            "klasyfikatory": kinds,
            "aktorzy": [r.name for r in self.by_type("Actor")],
            "przypadki_uzycia": [r.name for r in self.by_type("UseCase")],
            "relacje_klas": len([x for x in self.relationships() if x["kind"] != "association (use case)"]),
        }

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------- helpers
def _txt(d) -> str:
    return d.decode("utf-8") if isinstance(d, (bytes, bytearray)) else d


def _walk_objs(o: Obj):
    yield o
    for _, v in o.entries:
        yield from _walk_value(v)


def _walk_value(v):
    if isinstance(v, Obj):
        yield from _walk_objs(v)
    elif isinstance(v, Lst):
        for it in v.items:
            if isinstance(it, At):
                yield from _walk_value(it.value)
            else:
                yield from _walk_value(it)


def _fold(s: str) -> str:
    tr = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return s.translate(tr).lower()
