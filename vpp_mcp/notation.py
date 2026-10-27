"""Parser and serializer for Visual Paradigm's DEFINITION text notation.

A definition looks like::

    ID:"name":Type {
    \tkey=value;
    \tlist=(
    \t\t<ref>,
    \t\t{ID:NULL:Nested {
    \t\t\tkey=value;
    \t\t}}
    \t);
    }

Design goal: ``dump(parse(s)) == s`` for every definition VP writes, so a
row can be parsed, edited as a tree and written back without disturbing
anything the edit did not touch. ``roundtrip_ok`` checks this per row; callers
must refuse to edit a row that does not round-trip.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union

__all__ = ["Obj", "Lst", "At", "Raw", "parse", "dump", "roundtrip_ok",
           "ref", "string", "unquote", "NotationError"]


class NotationError(ValueError):
    pass


@dataclass
class Raw:
    """Atomic value kept verbatim: T, F, NULL, numbers, "strings", <refs>."""
    text: str

    def __repr__(self):
        return f"Raw({self.text!r})"


@dataclass
class At:
    """An ``@key=value;`` item inside a UI-model list."""
    key: str
    value: "Value"


@dataclass
class Lst:
    items: List[Union["Value", At]] = field(default_factory=list)


@dataclass
class Obj:
    id: str
    name: Optional[str]          # raw header name: None for NULL, else unquoted text
    type: str
    entries: List[Tuple[str, "Value"]] = field(default_factory=list)
    name_raw: Optional[str] = None   # exact header text when not plain

    # ---- convenience -------------------------------------------------
    def get(self, key, default=None):
        for k, v in self.entries:
            if k == key:
                return v
        return default

    def has(self, key):
        return any(k == key for k, _ in self.entries)

    def set(self, key, value, before: Optional[str] = None):
        """Replace the value of ``key`` or append it (optionally before another key)."""
        for i, (k, _) in enumerate(self.entries):
            if k == key:
                self.entries[i] = (key, value)
                return
        if before is not None:
            for i, (k, _) in enumerate(self.entries):
                if k == before:
                    self.entries.insert(i, (key, value))
                    return
        self.entries.append((key, value))

    def remove(self, key):
        self.entries = [(k, v) for k, v in self.entries if k != key]

    def text(self, key, default=None):
        v = self.get(key)
        if isinstance(v, Raw):
            return unquote(v.text) if v.text.startswith('"') else v.text
        return default

    def children(self) -> List["Obj"]:
        v = self.get("Child")
        if isinstance(v, Lst):
            return [i for i in v.items if isinstance(i, Obj)]
        return []

    def refs(self, key) -> List[str]:
        v = self.get(key)
        if isinstance(v, Lst):
            return [i.text[1:-1] for i in v.items if isinstance(i, Raw) and i.text.startswith("<")]
        if isinstance(v, Raw) and v.text.startswith("<"):
            return [v.text[1:-1]]
        return []


Value = Union[Raw, Lst, Obj]


# ---------------------------------------------------------------- helpers
def ref(target: str) -> Raw:
    return Raw("<" + target + ">")


def string(s: str) -> Raw:
    return Raw('"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"')


def unquote(t: str) -> str:
    if not (t.startswith('"') and t.endswith('"')):
        return t
    out, i, body = [], 0, t[1:-1]
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            out.append(body[i + 1])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- parser
class _P:
    def __init__(self, s: str):
        self.s = s
        self.i = 0

    def err(self, msg):
        ctx = self.s[max(0, self.i - 40):self.i + 40].replace("\n", "\\n").replace("\t", "\\t")
        raise NotationError(f"{msg} at {self.i}: ...{ctx}...")

    def peek(self, n=1):
        return self.s[self.i:self.i + n]

    def expect(self, lit):
        if not self.s.startswith(lit, self.i):
            self.err(f"expected {lit!r}")
        self.i += len(lit)

    def skip_ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n":
            self.i += 1

    def quoted(self) -> str:
        j = self.i
        assert self.s[j] == '"'
        j += 1
        while j < len(self.s):
            c = self.s[j]
            if c == "\\":
                j += 2
                continue
            if c == '"':
                j += 1
                t = self.s[self.i:j]
                self.i = j
                return t
            j += 1
        self.err("unterminated string")

    def header(self) -> Tuple[str, Optional[str], str, Optional[str]]:
        j = self.s.index(":", self.i)
        oid = self.s[self.i:j]
        self.i = j + 1
        if self.peek() == '"':
            raw = self.quoted()
            name = unquote(raw)
            name_raw = raw
        else:
            j = self.s.index(":", self.i)
            raw = self.s[self.i:j]
            self.i = j
            name = None if raw == "NULL" else raw
            name_raw = raw
        self.expect(":")
        j = self.s.index(" {", self.i)
        typ = self.s[self.i:j]
        self.i = j
        self.expect(" {\n")
        return oid, name, typ, name_raw

    def entries(self, closing: str) -> List[Tuple[str, Value]]:
        out = []
        while True:
            self.skip_tabs()
            if self.s.startswith(closing, self.i):
                self.i += len(closing)
                return out
            j = self.s.index("=", self.i)
            key = self.s[self.i:j]
            self.i = j + 1
            val = self.value()
            self.expect(";\n")
            out.append((key, val))

    def skip_tabs(self):
        while self.peek() == "\t":
            self.i += 1

    def value(self) -> Value:
        c = self.peek()
        if c == "(":
            return self.lst()
        if c == "{":
            self.i += 1
            oid, name, typ, nraw = self.header()
            ents = self.entries("}}")
            return Obj(oid, name, typ, ents, nraw)
        if c == '"':
            return Raw(self.quoted())
        if c == "<":
            j = self.s.index(">", self.i)
            t = self.s[self.i:j + 1]
            self.i = j + 1
            return Raw(t)
        j = self.i
        while j < len(self.s) and self.s[j] not in ";,\n)":
            j += 1
        t = self.s[self.i:j]
        self.i = j
        if not t:
            self.err("empty value")
        return Raw(t)

    def lst(self) -> Lst:
        self.expect("(")
        items: List[Union[Value, At]] = []
        if self.peek() == ")":
            self.i += 1
            return Lst(items)
        self.expect("\n")
        while True:
            self.skip_tabs()
            if self.peek() == "@":
                j = self.s.index("=", self.i)
                key = self.s[self.i + 1:j]
                self.i = j + 1
                v = self.value()
                self.expect(";")
                items.append(At(key, v))
            else:
                items.append(self.value())
            if self.s.startswith(", \n", self.i):
                self.i += 3
                continue
            self.expect("\n")
            self.skip_tabs()
            self.expect(")")
            return Lst(items)


def parse(s: str) -> Obj:
    p = _P(s)
    oid, name, typ, nraw = p.header()
    ents = p.entries("}")
    if p.i != len(s):
        p.err("trailing data")
    return Obj(oid, name, typ, ents, nraw)


# ---------------------------------------------------------------- serializer
def _hdr(o: Obj) -> str:
    if o.name_raw is not None:
        n = o.name_raw
    else:
        n = "NULL" if o.name is None else string(o.name).text
    return f"{o.id}:{n}:{o.type} {{\n"


def _val(v, d: int) -> str:
    if isinstance(v, Raw):
        return v.text
    if isinstance(v, Obj):
        return "{" + _hdr(v) + "".join(_entry(k, x, d + 1) for k, x in v.entries) + "\t" * d + "}}"
    if isinstance(v, Lst):
        if not v.items:
            return "()"
        parts = []
        for it in v.items:
            if isinstance(it, At):
                parts.append("\t" * (d + 1) + "@" + it.key + "=" + _val(it.value, d + 1) + ";")
            else:
                parts.append("\t" * (d + 1) + _val(it, d + 1))
        return "(\n" + ", \n".join(parts) + "\n" + "\t" * d + ")"
    raise TypeError(type(v))


def _entry(k, v, d: int) -> str:
    return "\t" * d + k + "=" + _val(v, d) + ";\n"


def dump(o: Obj) -> str:
    return _hdr(o) + "".join(_entry(k, v, 1) for k, v in o.entries) + "}"


def roundtrip_ok(s: str) -> bool:
    try:
        return dump(parse(s)) == s
    except (NotationError, ValueError):
        return False
