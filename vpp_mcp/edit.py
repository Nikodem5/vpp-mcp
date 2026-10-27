"""Write access: class model and class diagram.

Every public method of :class:`Editor` changes parsed trees and writes the
changed rows back in one SQLite transaction (``commit`` / ``rollback``).
Formats follow the reference in vpp-zasady/01_model_klas.md.
"""
from __future__ import annotations

import random
import re
import time
from typing import Dict, List, Optional, Tuple

from .notation import Obj, Lst, Raw, At, parse, dump, ref, string
from .project import Project, Row, VppError, _walk_objs

ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._"
PRIMITIVES = ("boolean", "byte", "char", "double", "float", "int", "long", "short", "void")

# ------------------------------------------------------------------ text parsing
_ATTR = re.compile(r"^\s*([+\-#~])?\s*([A-Za-z_ąćęłńóśźżĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ]*)\s*:\s*(.+?)\s*(?:\[\s*([0-9*.]+)\s*\])?\s*$")
_OP = re.compile(r"^\s*([+\-#~])?\s*([\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+)\s*\((.*)\)\s*(?::\s*(.+?))?\s*$")


def parse_attribute(text: str):
    m = _ATTR.match(text)
    if not m:
        raise VppError(f"Nie rozumiem atrybutu {text!r}. Oczekuję np. '-email : String' albo '-alergeny : String [0..*]'.")
    vis, name, typ, mult = m.groups()
    return {"vis": vis or "-", "name": name, "type": typ.strip(), "mult": mult}


def _split_params(s: str) -> List[str]:
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return [p.strip() for p in out if p.strip()]


def parse_operation(text: str):
    m = _OP.match(text)
    if not m:
        raise VppError(f"Nie rozumiem metody {text!r}. Oczekuję np. '+zaloguj(email : String, haslo : String) : boolean'.")
    vis, name, params, ret = m.groups()
    ps = []
    for p in _split_params(params):
        if ":" not in p:
            raise VppError(f"Parametr {p!r} w {text!r} musi mieć typ, np. 'email : String'.")
        pn, pt = p.split(":", 1)
        ps.append((pn.strip(), pt.strip()))
    return {"vis": vis or "+", "name": name, "params": ps, "ret": ret.strip() if ret else None}


VIS_CODE = {"+": "71", "-": None}


class Editor:
    def __init__(self, path: str, author: Optional[str] = None, seed: Optional[int] = None):
        self.p = Project(path, readonly=False)
        self.rng = random.Random(seed if seed is not None else time.time_ns())
        self.used = set(self.p.me) | set(self.p.dg) | set(self.p.de)
        maxts = 0
        for rows in (self.p.me, self.p.dg, self.p.de):
            for r in rows.values():
                for o in _walk_objs(r.obj):
                    self.used.add(o.id)
                    for k in ("pmLastModified", "lastModifiedTime", "pmCreateDateTime"):
                        t = o.text(k)
                        if t and t.isdigit():
                            maxts = max(maxts, int(t))
        self._now = max(int(time.time() * 1000), maxts + 1000)
        self._stem = "".join(self.rng.choice(ALPHA) for _ in range(9))
        self._ctr = 0
        self.author = author or self._guess_author()
        self.dirty_me: set = set()
        self.dirty_de: set = set()
        self.dirty_dg: set = set()
        self.dirty_info = False
        self.log: List[str] = []

    # ------------------------------------------------------------ infra
    def _guess_author(self) -> str:
        for r in self.p.me.values():
            a = r.obj.text("pmAuthor")
            if a:
                return a
        return "Claude"

    def new_id(self) -> str:
        while True:
            self._ctr += 1
            n = self._ctr
            sfx = ALPHA[(n // 4096) % 64] + ALPHA[(n // 64) % 64] + ALPHA[n % 64]
            i = "".join(self.rng.choice(ALPHA) for _ in range(4)) + self._stem[:9] + sfx
            if i not in self.used:
                self.used.add(i)
                return i

    def ts(self) -> int:
        self._now += 3
        return self._now

    def stamp(self, o: Obj):
        t = self.ts()
        if o.has("pmLastModified"):
            o.set("pmLastModified", Raw(f'"{t}"'))
        if o.has("lastModifiedTime"):
            o.set("lastModifiedTime", Raw(str(t)))

    def bookkeeping(self, extra: Optional[List[Tuple[str, Raw]]] = None) -> List[Tuple[str, object]]:
        t = self.ts()
        e = [("pmLastModified", Raw(f'"{t}"')), ("pmAuthor", string(self.author)),
             ("pmCreateDateTime", Raw(f'"{t}"')), ("_modelViews", Raw("NULL")),
             ("lastModifiedTime", Raw(str(t))), ("_modelEditable", Raw("T"))]
        return (extra or []) + e

    def touch(self, row: Row):
        self.stamp(row.obj)
        {"MODEL_ELEMENT": self.dirty_me, "DIAGRAM_ELEMENT": self.dirty_de, "DIAGRAM": self.dirty_dg}[row.table].add(row.id)

    def commit(self):
        c = self.p.conn
        now_s = self._now // 1000
        for i in self.dirty_me:
            r = self.p.me[i]
            exists = c.execute("select 1 from MODEL_ELEMENT where ID=?", (i,)).fetchone()
            if exists:
                c.execute("update MODEL_ELEMENT set DEFINITION=?, NAME=?, LAST_MOD_AT=? where ID=?",
                          (dump(r.obj).encode("utf-8"), r.name, now_s, i))
            else:
                c.execute("insert into MODEL_ELEMENT (ID, USER_ID, USER_ID_PARENT, MODEL_TYPE, PARENT_ID, NAME, DEFINITION, MIRROR_SOURCE, AUTHOR, CREATE_AT, LAST_MOD_AT) values (?,?,?,?,?,?,?,?,?,?,?)",
                          (i, None, None, r.model_type, r.parent, r.name, dump(r.obj).encode("utf-8"), None, self.author, now_s, now_s))
        for i in self.dirty_de:
            r = self.p.de[i]
            if c.execute("select 1 from DIAGRAM_ELEMENT where ID=?", (i,)).fetchone():
                c.execute("update DIAGRAM_ELEMENT set DEFINITION=? where ID=?", (dump(r.obj).encode("utf-8"), i))
            else:
                c.execute("insert into DIAGRAM_ELEMENT (ID, SHAPE_TYPE, DIAGRAM_ID, MODEL_ELEMENT_ID, COMPOSITE_MODEL_ELEMENT_ADDRESS, REF_MODEL_ELEMENT_ADDRESS, PARENT_ID, DEFINITION) values (?,?,?,?,?,?,?,?)",
                          (i, r.model_type, r.diagram, r.model, getattr(r, "composite", None), None, r.parent, dump(r.obj).encode("utf-8")))
        for i in self.dirty_dg:
            r = self.p.dg[i]
            if c.execute("select 1 from DIAGRAM where ID=?", (i,)).fetchone():
                c.execute("update DIAGRAM set DEFINITION=?, NAME=? where ID=?", (dump(r.obj).encode("utf-8"), r.name, i))
            else:
                c.execute("insert into DIAGRAM (ID, DIAGRAM_TYPE, PARENT_MODEL_ID, NAME, DEFINITION) values (?,?,?,?,?)",
                          (i, r.model_type, None, r.name, dump(r.obj).encode("utf-8")))
        if self.dirty_info:
            c.execute("update PROJECT_INFO set ROOT_MODEL_ELEMENTS_DEFINITION=?, DIAGRAMS_DEFINITION=?",
                      (dump(self.p.root_list), dump(self.p.diagram_list)))
        c.commit()
        self.dirty_me.clear(); self.dirty_de.clear(); self.dirty_dg.clear(); self.dirty_info = False

    def rollback(self):
        self.p.conn.rollback()
        self.p.reload()
        self.dirty_me.clear(); self.dirty_de.clear(); self.dirty_dg.clear(); self.dirty_info = False

    def close(self):
        self.p.close()

    # ------------------------------------------------------------ new rows
    def add_me(self, obj: Obj, mtype: str, parent: Optional[str], name: Optional[str]) -> Row:
        r = Row("MODEL_ELEMENT", obj.id, obj, mtype, parent, name)
        self.p.me[obj.id] = r
        self.dirty_me.add(obj.id)
        return r

    def add_de(self, obj: Obj, shape_type: str, diagram: str, model: Optional[str], parent: Optional[str] = None) -> Row:
        r = Row("DIAGRAM_ELEMENT", obj.id, obj, shape_type, parent, None, diagram, model)
        self.p.de[obj.id] = r
        self.dirty_de.add(obj.id)
        return r

    def append_root(self, mid: str):
        _append_ref(self.p.root_list, "Child", mid)
        self.dirty_info = True

    def append_diagram_root(self, did: str):
        _append_ref(self.p.diagram_list, "Child", did)
        self.dirty_info = True

    def append_to_diagram(self, did: str, de_id: str, sort_list: bool = False):
        d = self.p.dg[did]
        _append_ref(d.obj, "Child", f"{did}:{de_id}")
        if sort_list:
            v = d.obj.get("customizedSortDiagramElementIds")
            if isinstance(v, Lst):
                v.items.append(Raw(f'"{de_id}"'))
        self.dirty_dg.add(did)

    def model_view(self, diagram: str, view: str) -> Obj:
        return Obj(self.new_id(), "View", "ModelView", [("container", ref(diagram)), ("view", Raw(f'"{view}"'))], '"View"')

    def link_view(self, model_row: Row, diagram: str, view: str):
        o = model_row.obj
        if not o.has("_masterViewId"):
            o.set("_masterViewId", Raw(f'"{view}"'), before="pmAuthor")
        mv = o.get("_modelViews")
        if not isinstance(mv, Lst):
            o.set("_modelViews", Lst([self.model_view(diagram, view)]))
        else:
            mv.items.append(self.model_view(diagram, view))
        self.touch(model_row)

    # ------------------------------------------------------------ types
    def type_entries(self, typ: str, key: str = "type") -> List[Tuple[str, object]]:
        """Entries for a type, e.g. ``int`` -> type=<int id>; ``List<Danie>`` -> templateTypeBindInfo."""
        typ = typ.strip()
        m = re.match(r"^([\w.]+)\s*<(.+)>$", typ)
        if m:
            base, args = m.group(1), _split_params(m.group(2))
            ent = self.type_entries(base, key)
            dets = []
            t = self.ts()
            for a in args:
                arg_ent = self.type_entries(a, "bindedType")
                arg = Obj(self.new_id(), "", "TemplateTypeBindInfo",
                          [("typeModifier", Raw("NULL"))] + arg_ent +
                          [("pmAuthor", string(self.author)), ("pmCreateDateTime", Raw(f'"{t}"')),
                           ("_modelViews", Raw("NULL")), ("lastModifiedTime", Raw(str(t))), ("_modelEditable", Raw("T"))], '""')
                dets.append(Obj(self.new_id(), "", "TemplateTypeBindDetails",
                                [("pmAuthor", string(self.author)), ("pmCreateDateTime", Raw(f'"{t}"')),
                                 ("_modelViews", Raw("NULL")), ("arguments", arg), ("lastModifiedTime", Raw(str(t))),
                                 ("_modelEditable", Raw("T"))], '""'))
            tb = Obj(self.new_id(), "", "TemplateTypeBindInfo",
                     [("bindedType_string", string(base)), ("details", Lst(dets)), ("pmAuthor", string(self.author)),
                      ("pmCreateDateTime", Raw(f'"{t}"')), ("_modelViews", Raw("NULL")),
                      ("lastModifiedTime", Raw(str(t))), ("_modelEditable", Raw("T"))], '""')
            return [(key + "_string", string(base))] + [("templateTypeBindInfo", tb)]
        if typ in PRIMITIVES:
            did = self.p.datatype_id(typ)
            if did:
                return [(key, ref(did))]
        try:
            c = self.p.find_class(typ)
            if c.name == typ:
                return [(key, ref(c.id))]
        except VppError:
            pass
        return [(key + "_string", string(typ))]

    # ------------------------------------------------------------ members
    def _attribute_obj(self, a: dict, static=False) -> Obj:
        ent: List[Tuple[str, object]] = []
        if VIS_CODE.get(a["vis"]):
            ent.append(("visibility", Raw(VIS_CODE[a["vis"]])))
        ent += self.type_entries(a["type"])
        ent += self.bookkeeping()
        if a.get("mult"):
            ent.insert(len(ent) - 1, ("multiplicity", string(a["mult"])))
        if static:
            ent.insert(len(ent) - 1, ("scope", Raw("65")))
        return Obj(self.new_id(), a["name"], "Attribute", ent)

    def _param_obj(self, name: str, typ: str) -> Obj:
        return Obj(self.new_id(), name, "Parameter", self.type_entries(typ) + self.bookkeeping())

    def _operation_obj(self, op: dict, owner: str, static=False, abstract=False, oid: Optional[str] = None) -> Obj:
        t = self.ts()
        ent: List[Tuple[str, object]] = []
        code = VIS_CODE.get(op["vis"])
        if code:
            ent.append(("visibility", Raw(code)))
        ent += [("_modelEditable", Raw("T")), ("pmAuthor", string(self.author)), ("lastModifiedTime", Raw(str(t))),
                ("pmCreateDateTime", Raw(f'"{t}"')), ("_modelViews", Raw("NULL"))]
        is_ctor = op["name"] == owner and not op["ret"]
        if not is_ctor:
            ent += self.type_entries(op["ret"] or "void", "returnType")
        if static:
            ent.append(("scope", Raw("65")))
        if abstract:
            ent.append(("abstract", Raw("T")))
        if op["params"]:
            ent.append(("Child", Lst([self._param_obj(n, ty) for n, ty in op["params"]])))
        ent.append(("pmLastModified", Raw(f'"{t}"')))
        return Obj(oid or self.new_id(), op["name"], "Operation", ent)

    def _children(self, row: Row) -> Lst:
        v = row.obj.get("Child")
        if not isinstance(v, Lst):
            v = Lst([])
            row.obj.set("Child", v, before="pmLastModified" if row.obj.has("pmLastModified") else None)
        return v

    def _member(self, cls: Row, name: str, mtype: Optional[str] = None) -> Obj:
        hits = [m for m in cls.obj.children() if m.name == name and (mtype is None or m.type == mtype)]
        if not hits:
            raise VppError(f"Klasa {cls.name} nie ma składowej {name!r}. Ma: {', '.join(m.name for m in cls.obj.children())}")
        if len(hits) > 1:
            raise VppError(f"Klasa {cls.name} ma {len(hits)} składowe o nazwie {name!r} (przeciążenie). Usuń/zmień ręcznie w VP.")
        return hits[0]

    def add_attribute(self, cls_name: str, text: str, static=False) -> str:
        cls = self.p.find_class(cls_name)
        a = parse_attribute(text)
        if any(m.name == a["name"] and m.type == "Attribute" for m in cls.obj.children()):
            raise VppError(f"{cls.name} ma już atrybut {a['name']}.")
        kids = self._children(cls)
        # attributes go before the first operation, like VP lists them
        idx = next((i for i, m in enumerate(kids.items) if isinstance(m, Obj) and m.type == "Operation"), len(kids.items))
        kids.items.insert(idx, self._attribute_obj(a, static))
        self.touch(cls)
        self._grow(cls, 1)
        return f"{cls.name}: dodano atrybut {text.strip()}" + (" {static}" if static else "")

    def add_operation(self, cls_name: str, text: str, static=False, abstract=False) -> str:
        cls = self.p.find_class(cls_name)
        op = parse_operation(text)
        self._children(cls).items.append(self._operation_obj(op, cls.name, static, abstract))
        if abstract and self.p.kind_of(cls) == "class":
            pass
        self.touch(cls)
        self._grow(cls, 1, text)
        return f"{cls.name}: dodano metodę {text.strip()}" + (" {static}" if static else "") + (" {abstract}" if abstract else "")

    def change_operation(self, cls_name: str, old_name: str, new_text: str, static: Optional[bool] = None,
                         abstract: Optional[bool] = None) -> str:
        cls = self.p.find_class(cls_name)
        old = self._member(cls, old_name, "Operation")
        op = parse_operation(new_text)
        st = old.text("scope") == "65" if static is None else static
        ab = old.text("abstract") == "T" if abstract is None else abstract
        new = self._operation_obj(op, cls.name, st, ab, oid=old.id)   # keep the id: messages stay bound
        kids = cls.obj.get("Child")
        kids.items[kids.items.index(old)] = new
        self.touch(cls)
        self._grow(cls, 0, new_text)
        return f"{cls.name}: {old_name}(...) zmienione na {new_text.strip()}"

    def change_attribute(self, cls_name: str, old_name: str, new_text: str, static: Optional[bool] = None) -> str:
        cls = self.p.find_class(cls_name)
        old = self._member(cls, old_name, "Attribute")
        a = parse_attribute(new_text)
        st = old.text("scope") == "65" if static is None else static
        new = self._attribute_obj(a, st)
        new.id = old.id
        kids = cls.obj.get("Child")
        kids.items[kids.items.index(old)] = new
        self.touch(cls)
        return f"{cls.name}: atrybut {old_name} zmieniony na {new_text.strip()}"

    def remove_member(self, cls_name: str, name: str) -> str:
        cls = self.p.find_class(cls_name)
        m = self._member(cls, name)
        users = self._references_to(f"{cls.id}${m.id}")
        if users:
            raise VppError(f"Nie usuwam {cls.name}.{name}: używają jej {len(users)} elementy (np. komunikaty na diagramach sekwencji: "
                           f"{', '.join(sorted(users)[:5])}). Najpierw zmień lub usuń te komunikaty.")
        kids = cls.obj.get("Child")
        kids.items.remove(m)
        if not kids.items:
            cls.obj.remove("Child")
        self.touch(cls)
        self._grow(cls, -1)
        return f"{cls.name}: usunięto {m.type.lower()} {name}"

    def add_literal(self, enum_name: str, literal: str) -> str:
        cls = self.p.find_class(enum_name)
        lit = Obj(self.new_id(), literal, "EnumerationLiteral",
                  self.bookkeeping()[:4] + [("classifiers", Lst([ref(cls.id)]))] + self.bookkeeping()[4:])
        self._children(cls).items.append(lit)
        self.touch(cls)
        self._grow(cls, 1)
        return f"{cls.name}: dodano wartość {literal}"

    def _references_to(self, target: str) -> List[str]:
        out = []
        needle = target.split("$")
        for r in self.p.me.values():
            s = dump(r.obj)
            if target in s and r.id != needle[0]:
                out.append(r.name or r.model_type)
        return out

    # ------------------------------------------------------------ shapes
    def _grow(self, cls: Row, lines: int, text: Optional[str] = None):
        """Classes don't auto-fit in VP projects with autoFitShapesSize=F, so resize ourselves."""
        for d in self.p.class_diagrams():
            sh = self.p.shape_of(cls.id, d.id)
            if not sh:
                continue
            x, y, w, h = self.p.geometry(sh)
            h2 = max(40, h + 15 * lines)
            w2 = max(w, _text_width(text) if text else w)
            self._set_geom(sh, w=w2, h=h2)

    def _set_geom(self, sh: Row, x=None, y=None, w=None, h=None):
        o = sh.obj
        for k, v in (("x", x), ("y", y), ("width", w), ("height", h)):
            if v is not None:
                o.set(k, Raw(str(int(v))))
        if w is not None:
            cap = o.get("_captionUIModel")
            if isinstance(cap, Lst):
                for it in cap.items:
                    if isinstance(it, At) and it.key == "width":
                        it.value = Raw(str(int(w)))
        self.dirty_de.add(sh.id)

    def _set_caption_height(self, sh: Row, h: int):
        cap = sh.obj.get("_captionUIModel")
        if isinstance(cap, Lst):
            for it in cap.items:
                if isinstance(it, At) and it.key == "height":
                    it.value = Raw(str(int(h)))
        self.dirty_de.add(sh.id)

    def _overlap_warning(self, diagram: str, shape_id: str) -> str:
        x, y, w, h = self.p.geometry(self.p.de[shape_id])
        hits = []
        for r in self.p.shapes_on(diagram):
            if r.id == shape_id or r.parent is not None or r.model_type != "Class":
                continue
            a, b, c, d = self.p.geometry(r)
            if x < a + c and a < x + w and y < b + d and b < y + h:
                hits.append(self.p.me[r.model].name if r.model in self.p.me else r.id)
        if not hits:
            return ""
        return (f" UWAGA: nachodzi na {', '.join(hits)}. Przesuń (move_class) albo podaj inne x, y; "
                f"bez x, y klasa trafia w wolne miejsce pod diagramem.")

    def fit_class(self, cls_name: str, diagram: Optional[str] = None) -> str:
        cls = self.p.find_class(cls_name)
        d = self.p.find_diagram(diagram, "ClassDiagram") if diagram else self._default_class_diagram()
        sh = self.p.shape_of(cls.id, d.id)
        if not sh:
            raise VppError(f"{cls.name} nie jest narysowana na diagramie {d.name}.")
        w, h = self._size_for(cls)
        self._set_geom(sh, w=w, h=h)
        return f"{cls.name}: rozmiar {w}x{h}"

    def _size_for(self, cls: Row) -> Tuple[int, int]:
        lines = self.p.member_lines(cls)
        texts = [x["text"] for x in lines["attributes"]] + [x["text"] for x in lines["operations"]] + lines["literals"]
        n = len(texts)
        st = 15 if self.p.stereotype_names(cls.obj) else 0
        sep = 6 if lines["attributes"] and lines["operations"] else 0
        h = 30 + st + 15 * n + sep
        w = max([_text_width(t) for t in texts] + [_text_width(cls.name or "") + 20, 97])
        return int(w), int(max(h, 40))

    def move_class(self, cls_name: str, x: int, y: int, diagram: Optional[str] = None) -> str:
        cls = self.p.find_class(cls_name)
        d = self.p.find_diagram(diagram, "ClassDiagram") if diagram else self._default_class_diagram()
        sh = self.p.shape_of(cls.id, d.id)
        if not sh:
            raise VppError(f"{cls.name} nie jest narysowana na diagramie {d.name}.")
        self._set_geom(sh, x=x, y=y)
        self._reroute(d.id, sh.id)
        return f"{cls.name}: przesunięta na ({x}, {y}). Linie relacji przeliczone." + self._overlap_warning(d.id, sh.id)

    def _default_class_diagram(self) -> Row:
        ds = self.p.class_diagrams()
        if not ds:
            raise VppError("W projekcie nie ma diagramu klas.")
        if len(ds) > 1:
            raise VppError("W projekcie jest kilka diagramów klas, podaj nazwę: " + ", ".join(d.name for d in ds))
        return ds[0]

    def _template_class_shape(self, diagram: str) -> Obj:
        for r in self.p.shapes_on(diagram):
            if r.model_type == "Class" and r.parent is None:
                return parse(dump(r.obj))
        return parse(_CLASS_SHAPE_TEMPLATE)

    def _free_spot(self, diagram: str, w: int, h: int) -> Tuple[int, int]:
        boxes = [self.p.geometry(r) for r in self.p.shapes_on(diagram) if r.parent is None and r.model_type == "Class"]
        if not boxes:
            return 40, 40
        maxy = max(b[1] + b[3] for b in boxes)
        return 40, maxy + 60

    def _stereotype(self, name: str, base: str) -> str:
        for r in self.p.by_type("Stereotype"):
            if (r.name or "").lower() == name.lower() and (r.obj.text("baseType") or "") == base:
                return r.id
        sid = self.new_id()
        o = Obj(sid, name, "Stereotype", self.bookkeeping()[:4] + [("baseType", string(base))] + self.bookkeeping()[4:])
        self.add_me(o, "Stereotype", None, name)
        self.append_root(sid)
        return sid

    def add_class(self, name: str, kind: str = "class", attributes: Optional[List[str]] = None,
                  operations: Optional[List[str]] = None, literals: Optional[List[str]] = None,
                  static_members: Optional[List[str]] = None, abstract_operations: Optional[List[str]] = None,
                  diagram: Optional[str] = None, x: Optional[int] = None, y: Optional[int] = None) -> str:
        kind = kind.lower().strip()
        if kind not in ("class", "abstract class", "abstract", "interface", "enumeration", "enum"):
            raise VppError("kind musi być jednym z: class, abstract class, interface, enumeration")
        if any(r.name == name for r in self.p.classifiers()):
            raise VppError(f"Klasa {name} już istnieje.")
        d = self.p.find_diagram(diagram, "ClassDiagram") if diagram else self._default_class_diagram()
        cid, vid = self.new_id(), self.new_id()
        ent: List[Tuple[str, object]] = []
        if kind == "interface":
            ent.append(("stereotypes", Lst([ref(self._stereotype("Interface", "Class"))])))
        if kind in ("enumeration", "enum"):
            ent.append(("stereotypes", Lst([ref(self._stereotype("enumeration", "Class"))])))
        if kind in ("abstract", "abstract class"):
            ent.append(("abstract", Raw("T")))
        t = self.ts()
        ent += [("_modelEditable", Raw("T")), ("_masterViewId", Raw(f'"{vid}"')), ("pmAuthor", string(self.author)),
                ("lastModifiedTime", Raw(str(t))), ("pmCreateDateTime", Raw(f'"{t}"')),
                ("_modelViews", Lst([self.model_view(d.id, vid)])), ("pmLastModified", Raw(f'"{t}"'))]
        row = self.add_me(Obj(cid, name, "Class", ent), "Class", None, name)
        self.append_root(cid)
        static_members = set(static_members or [])
        abstract_operations = set(abstract_operations or [])
        kids = []
        for a in attributes or []:
            pa = parse_attribute(a)
            kids.append(self._attribute_obj(pa, pa["name"] in static_members))
        for o in operations or []:
            po = parse_operation(o)
            kids.append(self._operation_obj(po, name, po["name"] in static_members,
                                            po["name"] in abstract_operations))
        for l in literals or []:
            kids.append(Obj(self.new_id(), l, "EnumerationLiteral",
                            self.bookkeeping()[:4] + [("classifiers", Lst([ref(cid)]))] + self.bookkeeping()[4:]))
        if kids:
            row.obj.set("Child", Lst(kids), before="pmLastModified")
        # shape
        w, h = self._size_for(row)
        if x is None or y is None:
            x, y = self._free_spot(d.id, w, h)
        sh = self._template_class_shape(d.id)
        sh.id = vid
        sh.name, sh.name_raw = name, None
        sh.set("metaModelElement", ref(cid))
        self.add_de(sh, "Class", d.id, cid)
        self._set_geom(self.p.de[vid], x=x, y=y, w=w, h=h)
        # header = name (15 px) + one line per stereotype; a too-short caption hides the class name in VP
        self._set_caption_height(self.p.de[vid], 30 if kind in ("interface", "enumeration", "enum") else 15)
        self.append_to_diagram(d.id, vid)
        warn = self._overlap_warning(d.id, vid)
        k = {"abstract": "abstract class", "enum": "enumeration"}.get(kind, kind)
        return f"Dodano {k} {name} na diagramie {d.name} w ({x}, {y}), rozmiar {w}x{h}, składowych: {len(kids)}" + warn

    # ------------------------------------------------------------ relationships
    def _rel_container(self, kind: str) -> str:
        root = [r for r in self.p.by_type("ModelRelationshipContainer") if r.name == "relationships" and r.parent is None]
        if not root:
            rid = self.new_id()
            self.add_me(Obj(rid, "relationships", "ModelRelationshipContainer", self.bookkeeping()), "ModelRelationshipContainer", None, "relationships")
            self.append_root(rid)
            root_id = rid
        else:
            root_id = root[0].id
        for r in self.p.by_type("ModelRelationshipContainer"):
            if r.name == kind and r.parent == root_id:
                return f"{root_id}:{r.id}"
        cid = self.new_id()
        self.add_me(Obj(cid, kind, "ModelRelationshipContainer", self.bookkeeping()), "ModelRelationshipContainer", root_id, kind)
        rr = self.p.me[root_id]
        _append_ref(rr.obj, "Child", f"{root_id}:{cid}")
        self.touch(rr)
        return f"{root_id}:{cid}"

    def _contain(self, cpath: str, rid: str):
        cid = cpath.split(":")[-1]
        c = self.p.me[cid]
        _append_ref(c.obj, "Child", f"{cpath}:{rid}")
        self.touch(c)

    def _backref(self, cls_id: str, key: str, path: str):
        r = self.p.me[cls_id]
        _append_ref(r.obj, key, path)
        self.touch(r)

    def add_relationship(self, kind: str, source: str, target: str,
                         source_multiplicity: Optional[str] = None, source_role: Optional[str] = None,
                         target_multiplicity: Optional[str] = None, target_role: Optional[str] = None,
                         stereotype: Optional[str] = None, diagram: Optional[str] = None) -> str:
        """kind: generalization (source=subclass, target=superclass), realization (source=class, target=interface),
        dependency (source uses target), association, directed (arrow at target), aggregation / composition
        (source = whole, diamond at source)."""
        kind = kind.lower().strip()
        a, b = self.p.find_class(source), self.p.find_class(target)
        d = self.p.find_diagram(diagram, "ClassDiagram") if diagram else self._default_class_diagram()
        sa, sb = self.p.shape_of(a.id, d.id), self.p.shape_of(b.id, d.id)
        if not (sa and sb):
            raise VppError(f"Obie klasy muszą być narysowane na diagramie {d.name}.")
        rid, vid = self.new_id(), self.new_id()
        if kind in ("generalization", "realization", "dependency", "usage"):
            mtype = {"generalization": "Generalization", "realization": "Realization"}.get(kind, "Usage")
            # VP stores general/interface/supplier... as: Generalization from=general to=specific,
            # Realization from=interface to=class, Usage from=client to=supplier.
            frm, to = (b, a) if mtype in ("Generalization", "Realization") else (a, b)
            ent: List[Tuple[str, object]] = []
            if stereotype:
                ent.append(("stereotypes", Lst([ref(self._stereotype(stereotype, mtype))])))
            t = self.ts()
            ent += [("_modelEditable", Raw("T")), ("toModel", ref(to.id)), ("_masterViewId", Raw(f'"{vid}"')),
                    ("pmAuthor", string(self.author)), ("lastModifiedTime", Raw(str(t))), ("pmCreateDateTime", Raw(f'"{t}"')),
                    ("_modelViews", Lst([self.model_view(d.id, vid)])), ("fromModel", ref(frm.id)), ("pmLastModified", Raw(f'"{t}"'))]
            cpath = self._rel_container(mtype)
            self.add_me(Obj(rid, None, mtype, ent, "NULL"), mtype, cpath.split(":")[-1], None)
            self._contain(cpath, rid)
            path = f"{cpath}:{rid}"
            self._backref(frm.id, "FromSimpleRelationships", path)
            self._backref(to.id, "ToSimpleRelationships", path)
            fs, ts_ = self.p.shape_of(frm.id, d.id), self.p.shape_of(to.id, d.id)
            self.add_de(parse(_simple_connector(vid, mtype, path, d.id, fs.id, ts_.id, self._cgeom(fs, ts_),
                                                (40, 14) if stereotype else (20, 0))), mtype, d.id, rid)
            self.append_to_diagram(d.id, vid)
            txt = {"Generalization": f"{a.name} --|> {b.name}", "Realization": f"{a.name} ..|> {b.name}"}.get(
                mtype, f"{a.name} ..> {b.name}" + (f" «{stereotype}»" if stereotype else ""))
            return "Dodano relację " + txt
        if kind not in ("association", "directed", "directed association", "aggregation", "composition"):
            raise VppError("kind: generalization, realization, dependency, association, directed, aggregation, composition")
        agg = {"composition": "67", "aggregation": "66"}.get(kind)
        nav_from = "2" if kind.startswith("directed") else None
        e1 = self._end("from", a.id, source_multiplicity, source_role, agg, nav_from)
        e2 = self._end("to", b.id, target_multiplicity, target_role, None, None)
        t = self.ts()
        ent = [("_modelEditable", Raw("T")), ("_masterViewId", Raw(f'"{vid}"')), ("pmAuthor", string(self.author)),
               ("lastModifiedTime", Raw(str(t))), ("pmCreateDateTime", Raw(f'"{t}"')),
               ("_modelViews", Lst([self.model_view(d.id, vid)])), ("from", e1), ("to", e2), ("pmLastModified", Raw(f'"{t}"'))]
        cpath = self._rel_container("Association")
        self.add_me(Obj(rid, None, "Association", ent, "NULL"), "Association", cpath.split(":")[-1], None)
        self._contain(cpath, rid)
        path = f"{cpath}:{rid}"
        self._backref(a.id, "FromEndRelationships", f"{path}${e1.id}")
        self._backref(b.id, "ToEndRelationships", f"{path}${e2.id}")
        self.add_de(parse(_assoc_connector(vid, path, d.id, sa.id, sb.id, self._cgeom(sa, sb))), "Association", d.id, rid)
        self.append_to_diagram(d.id, vid)
        sym = {"composition": "*--", "aggregation": "o--"}.get(kind, "-->" if nav_from else "--")
        la = " ".join(v for v in (source_multiplicity, source_role) if v)
        lb = " ".join(v for v in (target_multiplicity, target_role) if v)
        return f"Dodano {kind}: {a.name}" + (f' "{la}"' if la else "") + f" {sym}" + (f' "{lb}"' if lb else "") + f" {b.name}"

    def _end(self, side, cls_id, mult, role, aggregation, navigable) -> Obj:
        t = self.ts()
        ent: List[Tuple[str, object]] = [("visibility", Raw("65")), ("_modelEditable", Raw("T")), ("pmAuthor", string(self.author)),
                                         ("lastModifiedTime", Raw(str(t))), ("pmCreateDateTime", Raw(f'"{t}"')), ("_modelViews", Raw("NULL"))]
        if navigable is not None:
            ent.append(("navigable", Raw(navigable)))
        ent.append(("qualifier", Obj(self.new_id(), "", "Qualifier",
                                     [("pmAuthor", string(self.author)), ("pmCreateDateTime", Raw(f'"{t}"')), ("_modelViews", Raw("NULL")),
                                      ("lastModifiedTime", Raw(str(t))), ("_modelEditable", Raw("T"))], '""')))
        if aggregation:
            ent.append(("aggregationKind", Raw(aggregation)))
        ent += [("type", ref(cls_id)), ("EndModelElement", ref(cls_id))]
        if mult:
            ent.append(("multiplicity", string(mult)))
        ent.append(("Direction", Raw("0" if side == "from" else "1")))
        return Obj(self.new_id(), role, "AssociationEnd", ent, None if role else "NULL")

    def remove_relationship(self, rel_id: str) -> str:
        r = self.p.me.get(rel_id)
        if not r or r.model_type not in ("Association", "Generalization", "Realization", "Usage", "Dependency"):
            raise VppError(f"Nie ma relacji o id {rel_id}. Id znajdziesz w list_relationships.")
        # container + back-refs + connectors
        cpath_tail = r.parent
        for c in self.p.me.values():
            changed = False
            for key in ("Child", "FromSimpleRelationships", "ToSimpleRelationships", "FromEndRelationships", "ToEndRelationships"):
                v = c.obj.get(key)
                if isinstance(v, Lst):
                    keep = [it for it in v.items if not (isinstance(it, Raw) and it.text.startswith("<") and
                                                         rel_id in it.text.strip("<>").split("$")[0].split(":"))]
                    if len(keep) != len(v.items):
                        changed = True
                        if keep:
                            v.items = keep
                        else:
                            c.obj.remove(key)
            if changed:
                self.touch(c)
        for sh in [x for x in self.p.de.values() if x.model == rel_id]:
            d = self.p.dg[sh.diagram]
            v = d.obj.get("Child")
            v.items = [it for it in v.items if not (isinstance(it, Raw) and it.text == f"<{sh.diagram}:{sh.id}>")]
            self.dirty_dg.add(d.id)
            self.p.conn.execute("delete from DIAGRAM_ELEMENT where ID=?", (sh.id,))
            del self.p.de[sh.id]
            self.dirty_de.discard(sh.id)
        self.p.conn.execute("delete from MODEL_ELEMENT where ID=?", (rel_id,))
        del self.p.me[rel_id]
        self.dirty_me.discard(rel_id)
        return f"Usunięto relację {rel_id}"

    # ------------------------------------------------------------ connector geometry
    def _cgeom(self, fs: Row, ts_: Row) -> dict:
        return _connector_geometry(self.p.geometry(fs), self.p.geometry(ts_))

    def _reroute(self, diagram: str, shape_id: str):
        for r in self.p.shapes_on(diagram):
            f, t = r.obj.get("_fromShape"), r.obj.get("_toShape")
            if not (isinstance(f, Raw) and isinstance(t, Raw)):
                continue
            fid, tid = f.text.strip("<>").split(":")[-1], t.text.strip("<>").split(":")[-1]
            if shape_id not in (fid, tid) or fid not in self.p.de or tid not in self.p.de:
                continue
            g = _connector_geometry(self.p.geometry(self.p.de[fid]), self.p.geometry(self.p.de[tid]))
            o = r.obj
            o.set("_points", Raw(f'"{g["points"]}"'))
            for k, v in (("x", g["x"]), ("y", g["y"]), ("width", g["w"]), ("height", g["h"])):
                o.set(k, Raw(str(v)))
            self.dirty_de.add(r.id)


# ------------------------------------------------------------------ helpers
def _append_ref(o: Obj, key: str, target: str):
    v = o.get(key)
    if isinstance(v, Lst):
        v.items.append(ref(target))
    else:
        o.set(key, Lst([ref(target)]))


def _text_width(t: Optional[str]) -> int:
    return int(len(t or "") * 6.1 + 24)


def _border_point(g, tx, ty):
    x, y, w, h = g
    cx, cy = x + w / 2.0, y + h / 2.0
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return int(w / 2), int(h / 2)
    sx = (w / 2.0) / abs(dx) if dx else float("inf")
    sy = (h / 2.0) / abs(dy) if dy else float("inf")
    k = min(sx, sy)
    return int(round(cx + dx * k - x)), int(round(cy + dy * k - y))


def _connector_geometry(gf, gt) -> dict:
    cf = (gf[0] + gf[2] / 2.0, gf[1] + gf[3] / 2.0)
    ct = (gt[0] + gt[2] / 2.0, gt[1] + gt[3] / 2.0)
    p1 = _border_point(gf, *ct)
    p2 = _border_point(gt, *cf)
    p2f = (p2[0] + gt[0] - gf[0], p2[1] + gt[1] - gf[1])
    minx, maxx = min(p1[0], p2f[0]), max(p1[0], p2f[0])
    miny, maxy = min(p1[1], p2f[1]), max(p1[1], p2f[1])
    mid = ((p1[0] + p2f[0]) // 2, (p1[1] + p2f[1]) // 2)
    return dict(points="%d,%d;%d,%d;" % (p1 + p2), x=minx - 50, y=miny - 50, w=maxx - minx + 100,
                h=maxy - miny + 100, mid=mid)


_COLOR = "(\n\t\t0, \n\t\t0, \n\t\t0, \n\t\t255\n\t)"
_BG = "(\n\t\t122, \n\t\t207, \n\t\t245, \n\t\t255\n\t)"
_FONT = "(\n\t\t@name=\"Dialog\";, \n\t\t@color=(\n\t\t\t0, \n\t\t\t0, \n\t\t\t0, \n\t\t\t255\n\t\t);, \n\t\t@size=11;, \n\t\t@style=0;\n\t)"
_LINE = "(\n\t\t@cap=0;, \n\t\t@transparency=0;, \n\t\t@weight=1.0;, \n\t\t@color=(\n\t\t\t0, \n\t\t\t0, \n\t\t\t0, \n\t\t\t255\n\t\t);, \n\t\t@hasStroke=T;\n\t)"


def _caption(mid, w, h):
    return ("(\n\t\t@x=%d;, \n\t\t@y=%d;, \n\t\t@width=%d;, \n\t\t@height=%d;, \n\t\t@side=1;, \n\t\t@visible=T;, "
            "\n\t\t@internalWidth=-2147483648;, \n\t\t@internalHeight=-2147483648;\n\t)" % (mid[0] - w // 2, mid[1] - 8, w, h))


def _simple_connector(vid, shape_type, meta_path, diagram, fs, tsh, g, cap):
    return ("%s:NULL:%s {\n\tbackground=%s;\n\twidth=%d;\n\ttoPinType=1;\n\tuseToShapeCenter=T;\n\t_captionUIModel=%s;\n\t_toShape=<%s:%s>;\n\t_elementFont=%s;\n\t_points=\"%s\";\n\tmetaModelElement=<%s>;\n\tfromPinType=1;\n\tforeground=%s;\n\ty=%d;\n\t_fromShape=<%s:%s>;\n\tx=%d;\n\tcreatorDiagramType=\"ClassDiagram\";\n\t_lineModel=%s;\n\theight=%d;\n\tuseFromShapeCenter=T;\n}"
            % (vid, shape_type, _BG, g["w"], _caption(g["mid"], *cap), diagram, tsh, _FONT, g["points"], meta_path, _COLOR, g["y"], diagram, fs, g["x"], _LINE, g["h"]))


def _assoc_connector(vid, meta_path, diagram, fs, tsh, g):
    return ("%s:NULL:Association {\n\tforeground=%s;\n\tfromPinType=1;\n\t_points=\"%s\";\n\tshowUniqueMultiplicityConstraint=T;\n\tshowStereotypes=T;\n\ttoPinType=1;\n\tshowToRoleName=T;\n\tuseToShapeCenter=T;\n\tshowFromRoleVisibility=T;\n\tcreatorDiagramType=\"ClassDiagram\";\n\t_fromShape=<%s:%s>;\n\tshowOrderedMultiplicityConstraint=T;\n\tuseFromShapeCenter=T;\n\ty=%d;\n\tx=%d;\n\tmetaModelElement=<%s>;\n\tshowToRoleVisibility=T;\n\tshowToMultiplicity=T;\n\tshowFromRoleName=T;\n\t0SwDr=F;\n\theight=%d;\n\twidth=%d;\n\tbackground=%s;\n\t_elementFont=%s;\n\t_captionUIModel=%s;\n\t_toShape=<%s:%s>;\n\t_lineModel=%s;\n\tshowFromMultiplicity=T;\n\tshowMultiplicityConstraints=F;\n}"
            % (vid, _COLOR, g["points"], diagram, fs, g["y"], g["x"], meta_path, g["h"], g["w"], _BG, _FONT, _caption(g["mid"], 20, 0), diagram, tsh, _LINE))


# copied from a VP 2026 class shape (TypRabatu), used only when a diagram has no class shape to clone
_CLASS_SHAPE_TEMPLATE = """XXXXXXXXXXXXXXXX:"X":Class {
\tshowOperationType=1;
\tforeground=(
\t\t0,
\t\t0,
\t\t0,
\t\t255
\t);
\tshowAttributeType=1;
\tdisplayAsRobustnessAnalysisIcon=T;
\tshowReceptionType=1;
\tshowEnumerationLiteralType=1;
\tshowParameterNameInOperationSignature=T;
\tconnectToPoint=T;
\ty=40;
\tx=40;
\tmetaModelElement=<XXXXXXXXXXXXXXXX>;
\tlShCmMl=F;
\toverrideAppearanceWithStereotypeIcon=T;
\tmSwTpPts=T;
\tparentConnectorHeaderLength=40;
\tparentConnectorLineLength=10;
\theight=74;
\twpMbs=F;
\t_fillColor=(
\t\t@gradientStyle=1;,
\t\t@transparency=0;,
\t\t@type=1;,
\t\t@color1=(
\t\t\t122,
\t\t\t207,
\t\t\t245,
\t\t\t255
\t\t);
\t);
\twidth=97;
\tshowOperationSignature=T;
\tkSwCsMbSt=T;
\tvisibilityStyle=1;
\tshowInitialAttributeValue=T;
\tbackground=(
\t\t122,
\t\t207,
\t\t245,
\t\t255
\t);
\t_elementFont=(
\t\t@name="Dialog";,
\t\t@color=(
\t\t\t0,
\t\t\t0,
\t\t\t0,
\t\t\t255
\t\t);,
\t\t@size=11;,
\t\t@style=0;
\t);
\t_captionUIModel=(
\t\t@x=0;,
\t\t@y=0;,
\t\t@width=97;,
\t\t@height=30;,
\t\t@side=12;,
\t\t@visible=T;,
\t\t@internalWidth=-2147483648;,
\t\t@internalHeight=-2147483648;
\t);
\tinterfaceBall=F;
\t_lineModel=(
\t\t@cap=0;,
\t\t@transparency=0;,
\t\t@weight=1.0;,
\t\t@color=(
\t\t\t0,
\t\t\t0,
\t\t\t0,
\t\t\t255
\t\t);,
\t\t@hasStroke=T;
\t);
}"""
