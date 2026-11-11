"""PNG preview of a class diagram drawn from the geometry stored in the .vpp file.

It is NOT Visual Paradigm's own rendering, but it uses the same data (shape boxes, connector points, member lines,
multiplicities, roles, stereotypes) and a similar look, so it is good enough to judge a layout: overlaps, lines running
through classes, crossings, distances, crowded places.
"""
import math
import os
from typing import List, Optional, Tuple


from .notation import Raw
from .project import Project, VppError

BLUE = (122, 207, 245)
BLACK = (0, 0, 0)
GREY = (90, 90, 90)

_FONT_FILES = {
    "regular": ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"],
    "bold": ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"],
}


def _font(kind: str, size: int):
    from PIL import ImageFont
    for f in _FONT_FILES[kind]:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _points(shape, shapes_by_id, p: Project):
    f, t = shape.obj.get("_fromShape"), shape.obj.get("_toShape")
    if not (isinstance(f, Raw) and isinstance(t, Raw)):
        return None
    fid, tid = f.text.strip("<>").split(":")[-1], t.text.strip("<>").split(":")[-1]
    if fid not in shapes_by_id or tid not in shapes_by_id:
        return None
    raw = [tuple(int(v) for v in q.split(",")) for q in shape.obj.text("_points").strip(";").split(";") if q]
    if len(raw) < 2:
        return None
    fg, tg = p.geometry(shapes_by_id[fid]), p.geometry(shapes_by_id[tid])
    pts = [(fg[0] + raw[0][0], fg[1] + raw[0][1])]
    pts += [(fg[0] + x, fg[1] + y) for x, y in raw[1:-1]]          # bend points are relative to the from shape
    pts.append((tg[0] + raw[-1][0], tg[1] + raw[-1][1]))
    return fid, tid, pts


def render_class_diagram(path: str, diagram: Optional[str], out_png: str, scale: float = 1.0,
                         crop: Optional[Tuple[int, int, int, int]] = None) -> str:
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:
        raise VppError("Do podglądu potrzebna jest biblioteka Pillow: python -m pip install pillow") from e
    p = Project(path)
    try:
        d = p.find_diagram(diagram, "ClassDiagram") if diagram else None
        if d is None:
            ds = [x for x in p.dg.values() if x.model_type == "ClassDiagram"]
            if not ds:
                raise VppError("Brak diagramu klas.")
            d = max(ds, key=lambda x: len([s for s in p.shapes_on(x.id) if s.model_type == "Class"]))
        shapes = [s for s in p.shapes_on(d.id) if s.parent is None]
        classes = {s.id: s for s in shapes if s.model_type == "Class"}
        if not classes:
            raise VppError(f"Diagram {d.name} nie ma klas.")
        boxes = {i: p.geometry(s) for i, s in classes.items()}
        conns = []
        for s in shapes:
            if s.model_type == "Class":
                continue
            r = _points(s, classes, p)
            if r:
                conns.append((s, r))
        allx = [b[0] for b in boxes.values()] + [b[0] + b[2] for b in boxes.values()]
        ally = [b[1] for b in boxes.values()] + [b[1] + b[3] for b in boxes.values()]
        for _, (_, _, pts) in conns:
            allx += [q[0] for q in pts]
            ally += [q[1] for q in pts]
        x0, y0, x1, y1 = crop or (min(allx) - 40, min(ally) - 40, max(allx) + 40, max(ally) + 40)
        W, H = int((x1 - x0) * scale), int((y1 - y0) * scale)
        if W * H > 60_000_000:
            raise VppError(f"Obraz byłby za duży ({W}x{H}); zmniejsz scale albo podaj crop.")
        im = Image.new("RGB", (W, H), "white")
        dr = ImageDraw.Draw(im)
        fs = max(8, int(round(11 * scale)))
        f_reg, f_bold = _font("regular", fs), _font("bold", fs)

        def T(x, y):
            return ((x - x0) * scale, (y - y0) * scale)

        def text(x, y, s, font=None, fill=BLACK):
            dr.text(T(x, y), s, fill=fill, font=font or f_reg)

        # ---- connectors first (under the boxes)
        notes = []
        for s, (fid, tid, pts) in conns:
            r = p.me.get(s.model) if s.model else None
            kind = s.model_type
            dashed = kind in ("Usage", "Dependency", "Realization")
            col = BLACK
            _line(dr, [T(*q) for q in pts], col, dashed, max(1, int(scale)))
            f_end, t_end = pts[0], pts[-1]
            f_dir, t_dir = _dir(pts[1], pts[0]), _dir(pts[-2], pts[-1])
            if kind in ("Generalization", "Realization"):
                _tri(dr, T(*f_end), f_dir, scale)                      # arrow head at the super type / interface (from end)
            elif kind in ("Usage", "Dependency"):
                _arrow(dr, T(*t_end), t_dir, scale)
            elif kind == "Association" and r is not None:
                a, b = r.obj.get("from"), r.obj.get("to")
                ea, eb = p._end(a), p._end(b)
                if ea["aggregation"] in ("66", "67"):
                    _diamond(dr, T(*f_end), f_dir, scale, filled=ea["aggregation"] == "67")
                if eb["aggregation"] in ("66", "67"):
                    _diamond(dr, T(*t_end), t_dir, scale, filled=eb["aggregation"] == "67")
                if ea["navigable"] == "2":
                    _arrow(dr, T(*t_end), t_dir, scale)
                if eb["navigable"] == "2":
                    _arrow(dr, T(*f_end), f_dir, scale)
                for tag, end, pt, dirv in (("A", ea, f_end, f_dir), ("B", eb, t_end, t_dir)):
                    for kind, val in (("multiplicity", end["multiplicity"]), ("role", end["role"])):
                        if not val:
                            continue
                        rect = _rect(s.obj.get(f"{kind}{tag}Rectangle"))
                        if rect is not None and s.obj.text(f"has{kind.capitalize()}{tag}Shape") == "T":
                            notes.append((val, (pt[0] + rect[0] + rect[2] / 2, pt[1] + rect[1] + rect[3] / 2), "centre"))
                        else:
                            notes.append((val, pt, (dirv, 0 if kind == "multiplicity" else 1)))
            if r is not None:
                st = p.stereotype_names(r.obj)
                if st:
                    mid = pts[len(pts) // 2] if len(pts) % 2 else ((pts[len(pts) // 2 - 1][0] + pts[len(pts) // 2][0]) / 2,
                                                               (pts[len(pts) // 2 - 1][1] + pts[len(pts) // 2][1]) / 2)
                    notes.append(("<<" + st[0] + ">>", mid, None))
        # ---- classes
        for sid, s in classes.items():
            x, y, w, h = boxes[sid]
            m = p.me[s.model]
            dr.rectangle([T(x, y), T(x + w, y + h)], fill=BLUE, outline=BLACK)
            sts = ([("Interface")] if p.kind_of(m) == "interface" else []) + p.user_stereotypes(m)
            if p.kind_of(m) == "enumeration":
                sts = ["enumeration"] + sts
            yy = y + 4
            for n in sts:
                _ctext(dr, T, x, w, yy, "<<" + n + ">>", f_reg, scale)
                yy += 15
            _ctext(dr, T, x, w, yy + 2, m.name or "", f_bold, scale)
            yy += 21
            ml = p.member_lines(m)
            if ml["attributes"] or ml["operations"] or ml["literals"]:
                dr.line([T(x, yy - 2), T(x + w, yy - 2)], fill=BLACK, width=1)
            for lit in ml["literals"]:
                text(x + 4, yy, lit)
                yy += 15
            for a_ in ml["attributes"]:
                _member(dr, T, x + 4, yy, a_, f_reg, scale)
                yy += 15
            if ml["attributes"] and ml["operations"]:
                dr.line([T(x, yy + 1), T(x + w, yy + 1)], fill=BLACK, width=1)
                yy += 6
            for o in ml["operations"]:
                _member(dr, T, x + 4, yy, o, f_reg, scale)
                yy += 15
        # ---- end labels on top
        for lab, pt, dirv in notes:
            lw = dr.textlength(lab, font=f_reg) / scale
            if dirv is None:                                       # stereotype caption
                text(pt[0] - lw / 2, pt[1] - 17, lab, fill=GREY)
            elif dirv == "centre":                                 # label rectangle stored in the file (centre of the text)
                text(pt[0] - lw / 2, pt[1] - 7, lab, fill=(20, 20, 120))
            else:                                                  # no rectangle: VP-like default guess
                (dx, dy), slot = dirv
                nx, ny = -dy, dx
                cx = pt[0] - dx * (lw / 2 + 14) + (nx * 10 if slot else -nx * 10)
                cy = pt[1] - dy * 14 + (ny * 10 if slot else -ny * 10)
                text(cx - lw / 2, cy - 7, lab, fill=(20, 20, 120))
        os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
        im.save(out_png)
        return f"Diagram {d.name}: {len(classes)} klas, {len(conns)} linii, obraz {W}x{H} px (skala {scale}), obszar x {x0}..{x1}, y {y0}..{y1}. Zapisano: {out_png}"
    finally:
        p.close()


def _rect(v):
    """``( x, y, w, h )`` list from the file -> tuple of ints or None."""
    try:
        q = [int(i.text) for i in v.items]
        return tuple(q) if len(q) == 4 else None
    except Exception:
        return None


def _dir(a, b):
    """Unit vector pointing from a towards b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def _line(dr, pts, col, dashed, width):
    if not dashed:
        dr.line(pts, fill=col, width=width)
        return
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L // 8))
        for i in range(n):
            a, b = i / n, (i + 0.55) / n
            dr.line([(x0 + (x1 - x0) * a, y0 + (y1 - y0) * a), (x0 + (x1 - x0) * b, y0 + (y1 - y0) * b)], fill=col, width=width)


def _tri(dr, pt, d, s):
    """Hollow triangle whose tip is at pt; d points from the line towards the tip."""
    L, Wd = 13 * s, 6.5 * s
    bx, by = pt[0] - d[0] * L, pt[1] - d[1] * L
    nx, ny = -d[1], d[0]
    dr.polygon([pt, (bx + nx * Wd, by + ny * Wd), (bx - nx * Wd, by - ny * Wd)], fill="white", outline=BLACK)


def _arrow(dr, pt, d, s):
    L, Wd = 11 * s, 5 * s
    bx, by = pt[0] - d[0] * L, pt[1] - d[1] * L
    nx, ny = -d[1], d[0]
    dr.line([(bx + nx * Wd, by + ny * Wd), pt, (bx - nx * Wd, by - ny * Wd)], fill=BLACK, width=max(1, int(s)))


def _diamond(dr, pt, d, s, filled):
    L, Wd = 18 * s, 5.5 * s
    mx, my = pt[0] - d[0] * L / 2, pt[1] - d[1] * L / 2
    nx, ny = -d[1], d[0]
    tail = (pt[0] - d[0] * L, pt[1] - d[1] * L)
    dr.polygon([pt, (mx + nx * Wd, my + ny * Wd), tail, (mx - nx * Wd, my - ny * Wd)], fill=BLACK if filled else "white", outline=BLACK)


def _ctext(dr, T, x, w, y, s, font, scale):
    tw = dr.textlength(s, font=font) / scale
    dr.text(T(x + (w - tw) / 2, y), s, fill=BLACK, font=font)


def _member(dr, T, x, y, m, font, scale):
    dr.text(T(x, y), m["text"], fill=BLACK, font=font)
    if m.get("static"):
        tw = dr.textlength(m["text"], font=font) / scale
        a, b = T(x, y + 13), T(x + tw, y + 13)
        dr.line([a, b], fill=BLACK, width=1)

