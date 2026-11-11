"""PNG preview of a UML SEQUENCE diagram drawn from the geometry stored in the .vpp file.

It is NOT Visual Paradigm's own rendering, but it reads the same data (lifeline and activation boxes, message points,
combined fragments with operands/guards, references, gates) and draws it in a similar look, so a developer can judge a
generated diagram without opening VP: lifelines, activations, arrows, numbering, fragments and where they sit.

Geometry conventions (see docs/format-sequence-diagrams.md, sections 4 and 7):
- lifeline / actor shapes: x, y, width, height; the dashed line runs from the head down to y + height at x + width / 2;
- Activation shapes: absolute x, y, 8 x height;
- Message connectors: ``_points`` "x,y;x,y;": the first point is relative to the ``_fromShape`` origin, the last point to the
  ``_toShape`` origin, bend points to the from shape;
- child shapes (``_parent``): x, y relative to the parent shape. Visual Paradigm itself draws such a child at its stored
  x, y measured from the diagram origin (nested fragments land in wrong places); ``vp_like_children=True`` reproduces that.
"""
import math
import os
from typing import Dict, List, Optional, Tuple

from .notation import Obj, Raw
from .project import Project, VppError, Row
from .render import BLACK, _font
from .sequence import OPERATOR_NAME

_HEAD_H = 34           # height of a lifeline head box (a create message arrives at its middle: 17 px)
_ACTOR_LINE_Y = 54     # an actor's dashed line starts this far below its top
_TAB_H = 18
_GUARD_DX = 36         # guard text offset from the left edge of the fragment
_MAX_PIXELS = 60_000_000


# ------------------------------------------------------------------ small helpers
def _ref_id(r) -> Optional[str]:
    """'<Diagram:ShapeId>' -> 'ShapeId'."""
    if isinstance(r, Raw):
        return r.text.strip("<>").split(":")[-1].split("$")[0]
    return None


def _raw_geom(s: Row) -> Tuple[int, int, int, int]:
    o = s.obj
    return tuple(int(float(o.text(k, "0") or 0)) for k in ("x", "y", "width", "height"))  # type: ignore


def _abs_pos(p: Project, s: Row, vp_like: bool) -> Tuple[int, int]:
    """Absolute position of a shape's origin (adds the parents' positions unless vp_like)."""
    x, y, _, _ = _raw_geom(s)
    if vp_like:
        return x, y
    seen = set()
    cur = s
    while cur.parent and cur.parent in p.de and cur.parent not in seen:
        seen.add(cur.parent)
        cur = p.de[cur.parent]
        px, py, _, _ = _raw_geom(cur)
        x, y = x + px, y + py
    return x, y


def _dashed(dr, pts, width, dash=6.0, gap=4.0, fill=BLACK):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 0.5:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        t = 0.0
        while t < L:
            e = min(t + dash, L)
            dr.line([(x0 + ux * t, y0 + uy * t), (x0 + ux * e, y0 + uy * e)], fill=fill, width=width)
            t += dash + gap


def _arrowhead(dr, tip, d, s, filled, width):
    L, Wd = 10 * s, 4.5 * s
    bx, by = tip[0] - d[0] * L, tip[1] - d[1] * L
    nx, ny = -d[1], d[0]
    a, b = (bx + nx * Wd, by + ny * Wd), (bx - nx * Wd, by - ny * Wd)
    if filled:
        dr.polygon([tip, a, b], fill=BLACK, outline=BLACK)
    else:
        dr.line([a, tip, b], fill=BLACK, width=width)


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


# ------------------------------------------------------------------ model lookups
def _op_signature(p: Project, op: Raw) -> Optional[str]:
    """'<Class$opId>' -> 'name(p : T, ...) : Ret' (constructors without a return type), as VP prints it."""
    try:
        cls_id, oid = op.text.strip("<>").split("$")
    except ValueError:
        return None
    cls = p.me.get(cls_id.split(":")[-1])
    if not cls:
        return None
    for o in cls.obj.children():
        if o.id == oid and o.type == "Operation":
            ps = ", ".join(f"{x.name} : {p.type_text(x)}" for x in o.children() if x.type == "Parameter")
            ctor = not o.has("returnType") and not o.has("returnType_string") and o.name == cls.name
            return f"{o.name}({ps})" + ("" if ctor else f" : {p.type_text(o, 'returnType')}")
    return None


def _message_info(p: Project, me: Row) -> Tuple[str, str]:
    """(kind, label) of a message model element. kind: call | return | create | self | signal."""
    o = me.obj
    at = o.get("actionType")
    typ = o.text("type") or ""
    sig = None
    if isinstance(at, Obj):
        op = at.get("operation")
        if isinstance(op, Raw):
            sig = _op_signature(p, op)
    is_return = isinstance(at, Obj) and at.type == "ActionTypeReturn"
    if typ == "2":
        kind = "create"
    elif typ == "3":
        kind = "self"
    elif is_return:
        kind = "return"
    elif isinstance(at, Obj) and at.type not in ("ActionTypeCall", "ActionTypeReturn"):
        kind = "signal"
    else:
        kind = "call"
    name = (me.name or "").strip()
    if kind == "create":
        text = "create" + (" " + sig if sig else (" " + name if name and name != "create" else ""))
    elif kind == "return":
        text = name
    else:
        text = sig or name
    seq = (o.text("sequenceNumber") or "").strip()
    label = f"{seq}: {text}" if seq and text else (f"{seq}:" if seq else text)
    return kind, label


def _lifeline_caption(p: Project, me: Optional[Row]) -> str:
    if me is None:
        return ""
    if me.model_type == "InteractionActor":
        return me.name or ""
    bc = me.obj.get("baseClassifier")
    if isinstance(bc, Raw):
        cls = p.name_of(bc.text)
    elif me.obj.has("baseClassifier_string"):
        cls = me.obj.text("baseClassifier_string") or ""
    else:
        cls = ""
    nm = me.name or ""
    return f"{nm} : {cls}" if cls else nm


def _guard(me: Optional[Row]) -> str:
    if me is None:
        return ""
    g = me.obj.get("guard")
    if isinstance(g, Obj):
        return (g.text("constraint") or "").strip()
    return ""


# ------------------------------------------------------------------ main
def render_sequence_diagram(path: str, diagram: str, out_png: str, scale: float = 1.0,
                            vp_like_children: bool = False) -> str:
    """Draws one sequence diagram to ``out_png``. ``diagram`` is its name (or id). With ``vp_like_children=True`` child
    shapes (``_parent``) are drawn at their stored x, y measured from the diagram origin, the way VP 18.1 does it;
    by default the parent's position is added."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:
        raise VppError("Do podglądu potrzebna jest biblioteka Pillow: python -m pip install pillow") from e
    if scale <= 0:
        raise VppError("scale musi być dodatnie.")
    p = Project(path)
    try:
        d = p.find_diagram(diagram, "InteractionDiagram")
        if d.model_type != "InteractionDiagram":
            raise VppError(f"Diagram {d.name} nie jest diagramem sekwencji ({d.model_type}).")
        shapes = p.shapes_on(d.id)
        by_id = {s.id: s for s in shapes}
        pos = {s.id: _abs_pos(p, s, vp_like_children) for s in shapes}

        def box(s):
            x, y = pos[s.id]
            _, _, w, h = _raw_geom(s)
            return x, y, w, h

        # ---- lifelines / actors
        lifelines = []
        for s in shapes:
            if s.model_type in ("InteractionLifeLine", "InteractionActor"):
                me = p.me.get(s.model) if s.model else None
                lifelines.append((s, me, box(s)))
        if not lifelines:
            raise VppError(f"Diagram {d.name} nie ma linii życia.")
        # ---- activations
        acts = [box(s) for s in shapes if s.model_type == "Activation"]
        gates = [box(s) for s in shapes if s.model_type == "Gate"]
        # ---- messages
        msgs = []
        for s in shapes:
            if s.model_type != "Message":
                continue
            f, t = _ref_id(s.obj.get("_fromShape")), _ref_id(s.obj.get("_toShape"))
            if f not in by_id or t not in by_id:
                continue
            raw = []
            for q in s.obj.text("_points", "").strip(";").split(";"):
                if q.strip():
                    a, b = q.split(",")[:2]
                    raw.append((int(float(a)), int(float(b))))
            if len(raw) < 2:
                continue
            fx, fy = pos[f]
            tx, ty = pos[t]
            pts = [(fx + raw[0][0], fy + raw[0][1])] + [(fx + a, fy + b) for a, b in raw[1:-1]] + [(tx + raw[-1][0], ty + raw[-1][1])]
            me = p.me.get(s.model) if s.model else None
            kind, label = _message_info(p, me) if me else ("call", "")
            if kind == "call" and f == t:
                kind = "self"
            msgs.append((kind, label, pts))
        # ---- fragments
        cfs = [s for s in shapes if s.model_type == "CombinedFragment"]
        operand_shapes: Dict[str, Row] = {}
        for s in shapes:
            if s.model_type == "InteractionOperand" and s.model:
                operand_shapes[s.model] = s
        frags = []      # (shape, operator, box, [(operand box, guard)])
        used_operands = set()
        for s in cfs:
            me = p.me.get(s.model) if s.model else None
            code = me.obj.text("interactionOperator") if me else None
            try:
                opname = OPERATOR_NAME.get(int(code), f"op{code}")
            except (TypeError, ValueError):
                opname = "alt" if code is None else str(code)
            cx, cy, cw, ch = box(s)
            rx, ry, _, _ = _raw_geom(s)
            dx, dy = cx - rx, cy - ry            # how far this fragment was moved by its parent chain
            ops = []
            for rid in (me.obj.refs("Child") if me else []):
                oid = rid.split(":")[-1]
                osh = operand_shapes.get(oid)
                if osh is None:
                    continue
                used_operands.add(osh.id)
                ox, oy, ow, oh = box(osh)
                if (dx or dy) and not vp_like_children:
                    # operands stored in the coordinates of their fragment (relative) move with it; absolute ones stay
                    inside_abs = cx <= ox <= cx + cw and cy <= oy <= cy + ch
                    rel_inside = rx <= ox <= rx + cw and ry <= oy <= ry + ch
                    if not inside_abs and rel_inside:
                        ox, oy = ox + dx, oy + dy
                ops.append(((ox, oy, ow, oh), _guard(p.me.get(oid))))
            frags.append((s, opname, (cx, cy, cw, ch), ops))
        refs = []
        for s in shapes:
            if s.model_type == "InteractionOccurrence":
                me = p.me.get(s.model) if s.model else None
                name = (me.name or "") if me else ""
                rt = _ref_id(me.obj.get("refersTo")) if me else None
                if rt and rt in p.dg and (not name or name == "InteractionUse"):
                    name = p.dg[rt].name or name
                refs.append((name, box(s)))

        # ---- fonts and bounds
        fs = max(8, int(round(11 * scale)))
        f_reg, f_bold = _font("regular", fs), _font("bold", fs)
        meas = ImageDraw.Draw(Image.new("RGB", (4, 4)))

        def tw(txt, font=f_reg):
            return meas.textlength(txt, font=font) / scale

        xs, ys = [], []

        def grow(x0, y0, x1, y1):
            xs.extend((x0, x1))
            ys.extend((y0, y1))

        for s, me, (x, y, w, h) in lifelines:
            grow(x, y, x + w, y + max(h, _HEAD_H))
        for x, y, w, h in acts + gates:
            grow(x, y, x + w, y + h)
        for kind, label, pts in msgs:
            for q in pts:
                grow(q[0], q[1], q[0], q[1])
            if label:
                if kind == "self":
                    lx = max(q[0] for q in pts) + 6
                    grow(lx, pts[0][1], lx + tw(label), pts[0][1] + 14)
                else:
                    mx = (pts[0][0] + pts[-1][0]) / 2
                    my = (pts[0][1] + pts[-1][1]) / 2
                    grow(mx - tw(label) / 2, my - 18, mx + tw(label) / 2, my)
        for s, opname, (x, y, w, h), ops in frags:
            grow(x, y, x + w, y + h)
        for name, (x, y, w, h) in refs:
            grow(x, y, x + w, y + h)
        if not xs:
            raise VppError("Diagram jest pusty.")
        # frame ("sd Name") around everything
        title = f" {d.name} "
        fx0, fy0 = min(xs) - 24, min(ys) - 30
        fx1, fy1 = max(xs) + 24, max(ys) + 24
        fx1 = max(fx1, fx0 + tw("sd") + tw(title) + 40)
        grow(fx0, fy0, fx1, fy1)
        x0, y0, x1, y1 = min(xs) - 40, min(ys) - 40, max(xs) + 40, max(ys) + 40
        W, H = int((x1 - x0) * scale), int((y1 - y0) * scale)
        if W * H > _MAX_PIXELS:
            raise VppError(f"Obraz byłby za duży ({W}x{H} px); zmniejsz scale (np. {round(scale * 0.5, 2)}).")
        im = Image.new("RGB", (W, H), "white")
        dr = ImageDraw.Draw(im)
        lw = max(1, int(round(scale)))

        def T(x, y):
            return ((x - x0) * scale, (y - y0) * scale)

        def rect(x, y, w, h, fill=None, outline=BLACK):
            dr.rectangle([T(x, y), T(x + w, y + h)], fill=fill, outline=outline, width=lw)

        def text(x, y, s, font=f_reg, fill=BLACK):
            dr.text(T(x, y), s, fill=fill, font=font)

        def ctext(x, y, w, s, font=f_reg):
            text(x + (w - tw(s, font)) / 2, y, s, font)

        def tab(x, y, label, font=f_bold, min_w=0):
            w = max(min_w, tw(label, font) + 14)
            dr.polygon([T(x, y), T(x + w, y), T(x + w, y + _TAB_H - 7), T(x + w - 7, y + _TAB_H), T(x, y + _TAB_H)],
                       fill="white", outline=BLACK)
            text(x + 6, y + 2, label, font)
            return w

        # ---- frame
        rect(fx0, fy0, fx1 - fx0, fy1 - fy0)
        dr.polygon([T(fx0, fy0), T(fx0 + tw("sd", f_bold) + tw(title) + 14, fy0),
                    T(fx0 + tw("sd", f_bold) + tw(title) + 14, fy0 + _TAB_H - 7),
                    T(fx0 + tw("sd", f_bold) + tw(title) + 7, fy0 + _TAB_H), T(fx0, fy0 + _TAB_H)], fill="white", outline=BLACK)
        text(fx0 + 5, fy0 + 2, "sd", f_bold)
        text(fx0 + 5 + tw("sd", f_bold), fy0 + 2, title)

        # ---- fragment outlines (no fill: lifelines show through)
        for s, opname, (x, y, w, h), ops in frags:
            rect(x, y, w, h)
        for name, (x, y, w, h) in refs:
            rect(x, y, w, h)

        # ---- lifelines
        for s, me, (x, y, w, h) in lifelines:
            cap = _lifeline_caption(p, me)
            cx = x + w / 2
            if s.model_type == "InteractionActor":
                _stick_figure(dr, T, cx, y, scale, lw)
                ctext(x, y + 35, w, cap)
                top = y + _ACTOR_LINE_Y
            else:
                rect(x, y, w, _HEAD_H, fill="white")
                ctext(x, y + (_HEAD_H - 13) / 2, w, cap)
                top = y + _HEAD_H
            if s.model_type == "InteractionActor":
                rect(cx - 4, top, 8, max(0, y + h - top), fill="white")     # VP draws an actor's life line as a narrow box
            else:
                _dashed(dr, [T(cx, top), T(cx, y + h)], lw, 6 * scale, 4 * scale)
        # ---- activations
        for x, y, w, h in acts:
            rect(x, y, w, h, fill="white")
        for x, y, w, h in gates:
            rect(x, y, w, h, outline=(150, 150, 150))
        # ---- messages
        for kind, label, pts in msgs:
            sp = [T(*q) for q in pts]
            if kind in ("return", "create"):
                _dashed(dr, sp, lw, 6 * scale, 4 * scale)
            else:
                dr.line(sp, fill=BLACK, width=lw)
            _arrowhead(dr, sp[-1], _unit(sp[-2], sp[-1]), scale, filled=kind in ("call", "self"), width=lw)
            if label:
                if kind == "self":
                    text(max(q[0] for q in pts) + 6, pts[0][1] + (pts[-1][1] - pts[0][1]) / 2 - 7, label)
                else:
                    mx = (pts[0][0] + pts[-1][0]) / 2
                    my = (pts[0][1] + pts[-1][1]) / 2
                    text(mx - tw(label) / 2, my - 16, label)
        # ---- fragment tabs, operand separators and guards on top
        for s, opname, (x, y, w, h), ops in frags:
            tab(x, y, opname, min_w=OP_TAB_MIN.get(opname, 0))
            for i, ((ox, oy, ow, oh), guard) in enumerate(ops):
                if i > 0:
                    _dashed(dr, [T(x, oy), T(x + w, oy)], lw, 6 * scale, 4 * scale)
                if guard:
                    text(x + _GUARD_DX, (oy if i > 0 else y + _TAB_H) + 8, "[" + guard + "]")
        for name, (x, y, w, h) in refs:
            tab(x, y, "ref")
            ctext(x, y + h / 2 - 6, w, name)

        os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
        im.save(out_png)
        n_ll = len(lifelines)
        return (f"Diagram {d.name}: {n_ll} linii życia, {len(msgs)} komunikatów, {len(frags)} fragmentów, {len(refs)} ref, "
                f"obraz {W}x{H} px (skala {scale}), obszar x {int(x0)}..{int(x1)}, y {int(y0)}..{int(y1)}"
                f"{', child shapes jak w VP' if vp_like_children else ''}. Zapisano: {out_png}")
    finally:
        p.close()


OP_TAB_MIN = {"alt": 23, "loop": 30, "opt": 25}


def _stick_figure(dr, T, cx, y, scale, lw):
    """UML actor: head, body, arms, legs in the top 33 px."""
    r = 5
    hc = (cx, y + r + 1)
    dr.ellipse([T(hc[0] - r, hc[1] - r), T(hc[0] + r, hc[1] + r)], outline=BLACK, width=lw)
    dr.line([T(cx, y + 2 * r + 1), T(cx, y + 22)], fill=BLACK, width=lw)
    dr.line([T(cx - 9, y + 15), T(cx + 9, y + 15)], fill=BLACK, width=lw)
    dr.line([T(cx, y + 22), T(cx - 8, y + 32)], fill=BLACK, width=lw)
    dr.line([T(cx, y + 22), T(cx + 8, y + 32)], fill=BLACK, width=lw)
