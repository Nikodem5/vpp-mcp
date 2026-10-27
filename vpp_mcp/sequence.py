"""Sequence (interaction) diagrams: build a whole diagram from a JSON spec.

Ported from the generator that produced SD01-SD12 for the lab project; the
format was copied from VP-authored files and the result was confirmed to open
in VP 2026 (see vpp-zasady/02_diagramy_sekwencji.md).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .notation import Obj, Lst, Raw, parse, dump, ref
from .project import Project, VppError

OPERATOR = {'alt': 65, 'loop': 71, 'opt': 73}
OP_TAB_W = {'alt': 23, 'loop': 30, 'opt': 25}
OPERATOR_NAME = {v: k for k, v in OPERATOR.items()}

# set by build_sequence_diagrams() for the duration of one build
_ED = None
AUTHOR = 'Claude'
REL_ROOT = ''


def new_id():
    return _ED.new_id()


def ts():
    return _ED.ts()


def q(s):
    """VP quoted string"""
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def hdr(i, name, typ):
    return '%s:%s:%s {\n' % (i, 'NULL' if name is None else q(name), typ)


def reflist(key, refs, ind='\t'):
    if not refs:
        return ''
    return '%s%s=(\n%s\n%s);\n' % (ind, key, ', \n'.join('%s\t<%s>' % (ind, r) for r in refs), ind)


def views(diagram, de, ind='\t'):
    return ('%s_modelViews=(\n%s\t{%s:"View":ModelView {\n%s\t\tcontainer=<%s>;\n%s\t\tview="%s";\n%s\t}}\n%s);\n'
            % (ind, ind, new_id(), ind, diagram, ind, de, ind, ind))


# ------------------------------------------------------------------ text width
def tw(s):
    w = 0.0
    for ch in s:
        if ch in 'il.,:;\'!|()[] ':
            w += 3.5
        elif ch in 'mwMW':
            w += 9
        elif ch.isupper():
            w += 7.5
        else:
            w += 6.2
    return int(w + 0.5)


# ------------------------------------------------------------------ view snippets
def color(r, g, b, a=255, ind='\t'):
    return '(\n%s\t%d, \n%s\t%d, \n%s\t%d, \n%s\t%d\n%s)' % (ind, r, ind, g, ind, b, ind, a, ind)


BLACK = color(0, 0, 0)
WHITE = color(255, 255, 255)
BLUE = color(122, 207, 245)
FONT = '(\n\t\t@name="Dialog";, \n\t\t@color=(\n\t\t\t0, \n\t\t\t0, \n\t\t\t0, \n\t\t\t255\n\t\t);, \n\t\t@size=11;, \n\t\t@style=0;\n\t)'
LINE = '(\n\t\t@cap=0;, \n\t\t@transparency=0;, \n\t\t@weight=1.0;, \n\t\t@color=(\n\t\t\t0, \n\t\t\t0, \n\t\t\t0, \n\t\t\t255\n\t\t);, \n\t\t@hasStroke=T;\n\t)'
GLINE = '(\n\t\t@cap=0;, \n\t\t@transparency=0;, \n\t\t@weight=1.0;, \n\t\t@color=(\n\t\t\t192, \n\t\t\t192, \n\t\t\t192, \n\t\t\t255\n\t\t);, \n\t\t@hasStroke=T;\n\t)'


def fill(transp, r, g, b, a):
    return ('(\n\t\t@gradientStyle=1;, \n\t\t@transparency=%d;, \n\t\t@type=1;, \n\t\t@color1=(\n\t\t\t%d, \n\t\t\t%d, \n\t\t\t%d, \n\t\t\t%d\n\t\t);\n\t)'
            % (transp, r, g, b, a))


def caption(x, y, w, h, side=1, visible=True, iw=None, ih=None):
    return ('(\n\t\t@x=%d;, \n\t\t@y=%d;, \n\t\t@width=%d;, \n\t\t@height=%d;, \n\t\t@side=%d;, \n\t\t@visible=%s;, \n\t\t@internalWidth=%d;, \n\t\t@internalHeight=%d;\n\t)'
            % (x, y, w, h, side, 'T' if visible else 'F', -2147483648 if iw is None else iw, -2147483648 if ih is None else ih))



# ------------------------------------------------------------------ class model
class Model:
    """Classes, operations (incl. inherited through generalization/realization) and actors."""

    def __init__(self, p: Project):
        self.p = p
        self.names = {i: r.name for i, r in p.me.items()}
        self.cls = {r.name: r.id for r in p.classifiers()}
        self.ops = {}
        for r in p.classifiers():
            lst = []
            for m in r.obj.children():
                if m.type != 'Operation':
                    continue
                ps = [(x.name, p.type_text(x)) for x in m.children() if x.type == 'Parameter']
                ret = None if (not m.has('returnType') and not m.has('returnType_string')) else p.type_text(m, 'returnType')
                lst.append((m.id, m.name, ps, ret))
            self.ops[r.id] = lst
        self.supers = {}
        for rel in p.relationships():
            if rel['kind'] in ('generalization', 'realization'):
                sub = p.find_class(rel['subclass'] if rel['kind'] == 'generalization' else rel['class']).id
                sup = p.find_class(rel['superclass'] if rel['kind'] == 'generalization' else rel['interface']).id
                self.supers.setdefault(sub, []).append(sup)

    def class_id(self, name):
        return self.p.find_class(name).id

    def resolve(self, cls_id, text):
        """'zmienStatus(OPLACONE)' -> (owner class id, op id, signature label). Matches by name and argument count."""
        name = text.split('(')[0].strip()
        inner = text[text.index('(') + 1:text.rindex(')')].strip() if '(' in text else ''
        nargs = len([a for a in inner.split(',') if a.strip()]) if inner else 0
        seen, frontier = set(), [cls_id]
        while frontier:
            hits = []
            for cid in frontier:
                hits += [(cid, o) for o in self.ops.get(cid, []) if o[1] == name and len(o[2]) == nargs]
            if len(hits) == 1:
                cid, (oid, on, ps, ret) = hits[0]
                sig = '%s(%s)' % (on, ', '.join('%s : %s' % p if p[1] else p[0] for p in ps))
                if ret and ret != 'void':
                    sig += ' : ' + ret
                return cid, oid, sig
            if len(hits) > 1:
                raise VppError('Operacja %s na %s jest niejednoznaczna (przeciążenie).' % (text, self.names[cls_id]))
            seen.update(frontier)
            frontier = [s for cid in frontier for s in self.supers.get(cid, []) if s not in seen]
        have = ', '.join('%s(%d arg.)' % (o[1], len(o[2])) for o in self.ops.get(cls_id, []))
        raise VppError('Klasa %s (ani jej nadklasy/interfejsy) nie ma operacji %s z %d argumentami. Dodaj ją najpierw '
                       '(vpp_edit_class_model, add_operation). Ma: %s' % (self.names[cls_id], name, nargs, have or 'brak'))


# ------------------------------------------------------------------ diagram builder
class Act:
    def __init__(self, part, ctx):
        self.part, self.ctx, self.counter = part, ctx, 0
        self.id, self.de = new_id(), new_id()
        self.ys, self.parent, self.caller = [], None, None
        part['acts'].append(self)

    def path(self, frame):
        return '%s:%s$%s' % (frame, self.part['me'], self.id)


class SD:
    def __init__(self, model, spec, frame_ids, msg_container):
        self.m, self.spec = model, spec
        self.did = new_id()
        self.frame = frame_ids[spec['name']]
        self.frame_ids = frame_ids
        self.mc = msg_container
        self.parts, self.pk = [], {}
        for p in spec['parts']:
            if p[0] == 'actor':
                d = dict(kind='actor', key=p[1], name=p[1], cls=None, created=False)
            else:
                d = dict(kind='obj', key=p[1] if p[1] else ':' + p[2], name=p[1], cls=model.class_id(p[2]), clsname=p[2], created=p[3])
            d.update(me=new_id(), de=new_id(), acts=[], from_ends=[], to_ends=[], idx=len(self.parts))
            self.parts.append(d)
            self.pk[d['key']] = d
        self.msgs, self.frags, self.occs, self.gates = [], [], [], []
        self.root = [0]
        self.stack = []
        self.cursor = 140

    # ---------------- numbering / activations
    def number(self, act):
        if act is None:
            self.root[0] += 1
            return str(self.root[0])
        act.counter += 1
        return '%s.%d' % (act.ctx, act.counter) if act.ctx else str(act.counter)

    def find(self, key):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].part['key'] == key:
                return i
        return -1

    def sender(self, key):
        p = self.pk[key]
        if p['kind'] == 'actor':
            del self.stack[:]
            return None
        i = self.find(key)
        if i >= 0:
            del self.stack[i + 1:]
            return self.stack[i]
        if 'create_seq' not in p:
            raise VppError('%s: %s sends without activation' % (self.spec['name'], key))
        a = Act(p, p['create_seq'])          # execution started by its creation
        self.stack.append(a)
        return a

    def msg(self, kind, frm, to, y, seq, **kw):
        d = dict(kind=kind, frm=frm, to=to, y=y, seq=seq, id=new_id(), de=new_id(),
                 fe=new_id(), te=new_id(), fa=None, ta=None, op=None, sig=None, name=None, ret_of=None, operand=None)
        d.update(kw)
        d['operand'] = self.cur_operand
        if self.cur_operand is not None:
            self.cur_operand['msgs'].append(d)
        if d['fa']:
            d['fa'].ys.append(y)
        if d['ta']:
            d['ta'].ys.append(y)
        self.msgs.append(d)
        return d

    # ---------------- items
    def run(self):
        self.cur_operand = None
        self.items(self.spec['items'], None, 0)
        self.bottom = self.cursor + 10

    def items(self, items, operand, depth):
        for it in items:
            k = it[0]
            if k == 'call':
                _, f, t, text = it
                fa = self.sender(f)
                seq = self.number(fa)
                tp = self.pk[t]
                if self.find(t) >= 0:
                    raise VppError('re-entrant call to %s' % t)
                ta = Act(tp, seq)
                ta.parent = fa
                self.stack.append(ta)
                owner, oid, sig = self.m.resolve(tp['cls'], text)
                d = self.msg('call', f, t, self.cursor, seq, fa=fa, ta=ta, op='%s$%s' % (owner, oid), sig=sig, text=text)
                ta.caller = d
                self.cursor += 40
            elif k == 'self':
                _, a, text = it
                fa = self.sender(a)
                seq = self.number(fa)
                owner, oid, sig = self.m.resolve(self.pk[a]['cls'], text)
                d = self.msg('self', a, a, self.cursor, seq, fa=fa, ta=fa, op='%s$%s' % (owner, oid), sig=sig, text=text)
                fa.ys.append(self.cursor + 20)
                self.cursor += 55
            elif k == 'create':
                _, f, t, text = it
                fa = self.sender(f)
                seq = self.number(fa)
                tp = self.pk[t]
                y = self.cursor + 5
                tp['create_seq'] = seq
                tp['create_y'] = y
                op = sig = None
                if text:
                    owner, oid, sig = self.m.resolve(tp['cls'], text)
                    op = '%s$%s' % (owner, oid)
                self.msg('create', f, t, y, seq, fa=fa, op=op, sig=sig, name='create', text=text)
                self.cursor = y + 45
            elif k == 'ret':
                _, f, t, label = it
                i = self.find(f)
                if i < 0:
                    raise VppError('%s: return from inactive %s' % (self.spec['name'], f))
                fa = self.stack[i]
                del self.stack[i:]
                tp = self.pk[t]
                if tp['kind'] == 'actor':
                    ta = None
                    del self.stack[:]
                else:
                    j = self.find(t)
                    if j < 0:
                        raise VppError('%s: return to inactive %s' % (self.spec['name'], t))
                    del self.stack[j + 1:]
                    ta = self.stack[j]
                seq = self.number(ta)
                d = self.msg('ret', f, t, self.cursor, seq, fa=fa, ta=ta, name=label, text=label)
                if fa.caller is not None and fa.caller['frm'] == t and fa.caller.get('ret_msg') is None:
                    fa.caller['ret_msg'] = d
                self.cursor += 40
            elif k == 'sig':
                _, f, t, text = it
                fa = self.sender(f)
                seq = self.number(fa)
                self.msg('sig', f, t, self.cursor, seq, fa=fa, name=text, text=text)
                self.cursor += 40
            elif k == 'found':
                _, t, text = it
                del self.stack[:]
                seq = self.number(None)
                tp = self.pk[t]
                ta = Act(tp, seq)
                self.stack.append(ta)
                owner, oid, sig = self.m.resolve(tp['cls'], text)
                g = dict(id=new_id(), de=new_id(), y=self.cursor, target=t, operand=operand)
                self.gates.append(g)
                d = self.msg('found', None, t, self.cursor, seq, ta=ta, op='%s$%s' % (owner, oid), sig=sig, text=text, gate=g)
                g['msg'] = d
                self.cursor += 40
            elif k in ('loop', 'opt', 'alt'):
                ops = [(it[1], it[2])] if k != 'alt' else it[1]
                fr = dict(kind=k, id=new_id(), de=new_id(), operand=operand, depth=depth, top=self.cursor - 10, ops=[],
                          name='CombinedFragment' + ('' if not self.frags else str(len(self.frags) + 1)))
                self.frags.append(fr)
                if operand is not None:
                    operand['children'].append(('cf', fr))
                self.cursor += 55
                snapshot = list(self.stack)
                for n, (guard, sub) in enumerate(ops):
                    top = fr['top'] + 18 if n == 0 else self.cursor - 15
                    if n > 0:
                        self.cursor += 45
                    od = dict(id=new_id(), de=new_id(), gid=new_id(), guard=guard, msgs=[], children=[], frag=fr, top=top)
                    fr['ops'].append(od)
                    if k == 'alt':
                        self.stack[:] = snapshot
                    prev = self.cur_operand
                    self.cur_operand = od
                    self.items(sub, od, depth + 1)
                    self.cur_operand = prev
                fr['bottom'] = self.cursor - 20
                self.cursor += 10
            elif k == 'ref':
                _, target, covered = it
                if operand is None:
                    raise VppError('ref outside operand not supported')
                oc = dict(id=new_id(), de=new_id(), target=target, covered=covered, top=self.cursor - 10, height=40, operand=operand)
                operand['children'].append(('occ', oc))
                self.occs.append(oc)
                self.cursor += 50
            else:
                raise VppError('unknown item %r' % (k,))

    # ---------------- layout
    def label(self, d):
        if d['kind'] in ('call', 'self', 'found'):
            return '%s: %s' % (d['seq'], d['sig'])
        if d['kind'] == 'create':
            return '%s: %s' % (d['seq'], d['sig'] or 'create')
        return '%s: %s' % (d['seq'], d['name'])

    def layout(self):
        P = self.parts
        for p in P:
            if p['kind'] == 'actor':
                p['cap'] = tw(p['name']) + 8
                p['w'] = max(60, p['cap'] + 6)
            else:
                p['cap'] = tw('%s : %s' % (p['name'], p['clsname'])) + 10
                p['w'] = max(100, p['cap'] + 16)
        n = len(P)
        gaps = [max(190, (P[i]['w'] + P[i + 1]['w']) // 2 + 50) for i in range(n - 1)]
        for _ in range(3):
            for d in self.msgs:
                L = min(int(tw(self.label(d)) * 1.1) + 30, 480) + 40
                if d['kind'] == 'self':
                    i = self.pk[d['frm']]['idx']
                    if i < n - 1 and gaps[i] < L + 40:
                        gaps[i] = L + 40
                    continue
                if d['kind'] == 'found':
                    continue
                i, j = sorted((self.pk[d['frm']]['idx'], self.pk[d['to']]['idx']))
                have = sum(gaps[i:j])
                if have < L:
                    add = (L - have + (j - i) - 1) // (j - i)
                    for g in range(i, j):
                        gaps[g] += add
        left = 60 + (40 if self.gates and self.pk[self.gates[0]['target']]['idx'] == 0 else 0)
        cx = left + P[0]['w'] // 2
        for i, p in enumerate(P):
            if i:
                cx += gaps[i - 1]
            p['cx'] = cx
            p['x'] = cx - p['w'] // 2
            p['y'] = p['create_y'] - 17 if 'create_y' in p else 60
            p['h'] = self.bottom - p['y']
        # activations: geometry + nesting
        acts = [a for p in P for a in p['acts']]
        for a in acts:
            a.top = min(a.ys) - 8
            a.end = max(a.ys) + 10
        for a in sorted(acts, key=lambda a: -min(a.ys)):
            if a.parent is not None:
                a.parent.end = max(a.parent.end, a.end + 5)
        for a in acts:
            a.x = a.part['cx'] - 4
            a.h = max(20, a.end - a.top)
        # fragments
        def covered(fr):
            s = set()
            for od in fr['ops']:
                for d in od['msgs']:
                    s.update(k for k in (d['frm'], d['to']) if k)
                for kind, ch in od['children']:
                    s |= covered(ch) if kind == 'cf' else set(ch['covered'])
            return s
        for fr in self.frags:
            fr['covered'] = sorted(covered(fr), key=lambda k: self.pk[k]['idx'])
            pad = 30 - 9 * fr['depth']
            cov = [self.pk[k] for k in fr['covered']]
            fr['x'] = min(p['x'] for p in cov) - pad
            fr['w'] = max(p['x'] + p['w'] for p in cov) + pad - fr['x']
            fr['h'] = fr['bottom'] - fr['top']
            for n_, od in enumerate(fr['ops']):
                od['bottom'] = fr['ops'][n_ + 1]['top'] if n_ + 1 < len(fr['ops']) else fr['bottom']
                od['x'], od['w'] = fr['x'], fr['w']
        for oc in self.occs:
            cov = [self.pk[k] for k in oc['covered']]
            pad = 30 - 9 * (oc['operand']['frag']['depth'] + 1)
            oc['x'] = min(p['x'] for p in cov) - pad
            oc['w'] = max(p['x'] + p['w'] for p in cov) + pad - oc['x']
        for g in self.gates:
            g['x'] = self.pk[g['target']]['cx'] - 120
            g['y'] = g['y'] - 10

    # ---------------- serialization
    def build(self, db):
        F, D, MC = self.frame, self.did, self.mc
        name = self.spec['name']
        lp = lambda p: '%s:%s' % (F, p['me'])
        mpath = lambda d: '%s:%s:%s' % (REL_ROOT, MC, d['id'])
        de_rows, me_rows = [], []
        sort_ids = []

        # ---- messages
        for d in self.msgs:
            t = ts()
            frm = self.pk[d['frm']] if d['frm'] else None
            to = self.pk[d['to']]
            s = hdr(d['id'], d['name'], 'Message')
            if d['ta'] is not None and d['kind'] != 'create':
                s += '\ttoActivation=<%s>;\n' % d['ta'].path(F)
            s += '\t_modelEditable=T;\n'
            if d['kind'] in ('call', 'self', 'found', 'create'):
                s += '\tactionType={%s:"Call":ActionTypeCall {\n' % new_id()
                if d['op']:
                    s += '\t\toperation=<%s>;\n' % d['op']
                s += '\t\tpmAuthor="%s";\n\t\tpmCreateDateTime="%d";\n\t\t_modelViews=NULL;\n\t\tlastModifiedTime=%d;\n\t\t_modelEditable=T;\n\t}};\n' % (AUTHOR, t, t)
            elif d['kind'] == 'ret':
                s += '\tactionType={%s:"Return":ActionTypeReturn {\n\t\tpmAuthor="%s";\n\t\tpmCreateDateTime="%d";\n\t\t_modelViews=NULL;\n\t\t_modelEditable=T;\n\t}};\n' % (new_id(), AUTHOR, t)
            if d['fa'] is not None:
                s += '\tfromActivation=<%s>;\n' % d['fa'].path(F)
            s += '\t_masterViewId="%s";\n\tpmAuthor="%s";\n\tlastModifiedTime=%d;\n\tpmCreateDateTime="%d";\n' % (d['de'], AUTHOR, t, t)
            s += views(D, d['de'])
            s += '\tsequenceNumber="%s";\n' % d['seq']
            if d['kind'] == 'create':
                s += '\ttype=2;\n'
            elif d['kind'] == 'self':
                s += '\ttype=3;\n'
            if d.get('ret_msg'):
                s += '\treturnMessage=<%s>;\n' % mpath(d['ret_msg'])
            src = '%s:%s' % (F, d['gate']['id']) if d['kind'] == 'found' else lp(frm)
            for side, eid, ref, direc in (('from', d['fe'], src, 0), ('to', d['te'], lp(to), 1)):
                s += ('\t%s={%s:NULL:MessageEnd {\n\t\tpmAuthor="%s";\n\t\tpmCreateDateTime="%d";\n\t\t_modelViews=NULL;\n\t\tDirection=%d;\n\t\t_modelEditable=T;\n\t\tEndModelElement=<%s>;\n\t}};\n'
                      % (side, eid, AUTHOR, t, direc, ref))
            s += '\tpmLastModified="%d";\n}' % t
            me_rows.append((d['id'], 'Message', MC, d['name'], s))
            if d['kind'] == 'found':
                d['gate']['from_end'] = '%s$%s' % (mpath(d), d['fe'])
            else:
                frm['from_ends'].append('%s$%s' % (mpath(d), d['fe']))
            to['to_ends'].append('%s$%s' % (mpath(d), d['te']))

        # ---- fragments (model)
        def frag_path(fr):
            if fr['operand'] is None:
                return '%s:%s' % (F, fr['id'])
            return '%s:%s' % (op_path(fr['operand']), fr['id'])

        def op_path(od):
            return '%s:%s' % (frag_path(od['frag']), od['id'])

        op_names = [0]
        for fr in self.frags:
            t = ts()
            s = hdr(fr['id'], fr['name'], 'CombinedFragment')
            s += '\t_modelEditable=T;\n\tinteractionOperator=%d;\n\t_masterViewId="%s";\n\tpmAuthor="%s";\n\tlastModifiedTime=%d;\n\tpmCreateDateTime="%d";\n' % (OPERATOR[fr['kind']], fr['de'], AUTHOR, t, t)
            s += views(D, fr['de'])
            s += reflist('coveredLifeLines', [lp(self.pk[k]) for k in fr['covered']])
            s += reflist('Child', [op_path(od) for od in fr['ops']])
            s += '\tpmLastModified="%d";\n}' % t
            parent = fr['operand']['id'] if fr['operand'] is not None else F
            me_rows.append((fr['id'], 'CombinedFragment', parent, fr['name'], s))
            for od in fr['ops']:
                t = ts()
                op_names[0] += 1
                od['name'] = 'Operand' + ('' if op_names[0] == 1 else str(op_names[0]))
                s = hdr(od['id'], od['name'], 'InteractionOperand')
                s += '\t_modelEditable=T;\n\t_masterViewId="%s";\n' % od['de']
                s += reflist('messages', [mpath(d) for d in od['msgs']])
                s += '\tpmAuthor="%s";\n\tlastModifiedTime=%d;\n\tpmCreateDateTime="%d";\n' % (AUTHOR, t, t)
                s += ('\tguard={%s:"InteractionConstraint":InteractionConstraint {\n\t\tpmAuthor="%s";\n\t\tpmCreateDateTime="%d";\n\t\t_modelViews=NULL;\n\t\tlastModifiedTime=%d;\n\t\tconstraint=%s;\n\t\t_modelEditable=T;\n\t}};\n'
                      % (od['gid'], AUTHOR, t, t, q(od['guard'])))
                s += views(D, od['de'])
                kids = [frag_path(ch) if kind == 'cf' else '%s:%s' % (op_path(od), ch['id']) for kind, ch in od['children']]
                s += reflist('Child', kids)
                s += '\tpmLastModified="%d";\n}' % t
                me_rows.append((od['id'], 'InteractionOperand', fr['id'], od['name'], s))

        # ---- interaction occurrences (ref)
        for oc in self.occs:
            t = ts()
            s = hdr(oc['id'], oc['target'], 'InteractionOccurrence')
            s += '\trefersTo=<%s>;\n' % self.frame_ids[oc['target']]
            s += reflist('coveredLifeLines', [lp(self.pk[k]) for k in oc['covered']])
            s += '\t_masterViewId="%s";\n\tpmLastModified="%d";\n\tpmAuthor="%s";\n\tpmCreateDateTime="%d";\n' % (oc['de'], t, AUTHOR, t)
            s += views(D, oc['de'])
            s += '\tlastModifiedTime=%d;\n\t_modelEditable=T;\n}' % t
            me_rows.append((oc['id'], 'InteractionOccurrence', oc['operand']['id'], oc['target'], s))

        # ---- gates
        for g in self.gates:
            t = ts()
            s = hdr(g['id'], 'Gate', 'Gate')
            s += '\t_modelEditable=T;\n\t_masterViewId="%s";\n\tpmAuthor="%s";\n' % (g['de'], AUTHOR)
            s += reflist('FromEndRelationships', [g['from_end']])
            s += '\tlastModifiedTime=%d;\n\tpmCreateDateTime="%d";\n' % (t, t)
            s += views(D, g['de'])
            s += '\tpmLastModified="%d";\n}' % t
            me_rows.append((g['id'], 'Gate', F, 'Gate', s))

        # ---- participants (model)
        for p in self.parts:
            t = ts()
            if p['kind'] == 'actor':
                s = hdr(p['me'], p['name'], 'InteractionActor')
                s += reflist('FromEndRelationships', p['from_ends'])
                s += '\t_masterViewId="%s";\n\tpmLastModified="%d";\n\tpmAuthor="%s";\n\tpmCreateDateTime="%d";\n' % (p['de'], t, AUTHOR, t)
                s += views(D, p['de'])
                s += '\tlastModifiedTime=%d;\n\t_modelEditable=T;\n' % t
                s += reflist('ToEndRelationships', p['to_ends'])
                s += '}'
                me_rows.append((p['me'], 'InteractionActor', F, p['name'], s))
            else:
                s = hdr(p['me'], p['name'], 'InteractionLifeLine')
                s += '\t_modelEditable=T;\n\t_masterViewId="%s";\n\tbaseClassifier=<%s>;\n\tpmAuthor="%s";\n' % (p['de'], p['cls'], AUTHOR)
                s += reflist('FromEndRelationships', p['from_ends'])
                s += '\tlastModifiedTime=%d;\n\tpmCreateDateTime="%d";\n' % (t, t)
                s += views(D, p['de'])
                s += reflist('ToEndRelationships', p['to_ends'])
                if p['acts']:
                    blocks = []
                    for a in p['acts']:
                        blocks.append('\t\t{%s:"Activation":Activation {\n\t\t\t_masterViewId="%s";\n\t\t\tpmAuthor="%s";\n\t\t\tpmCreateDateTime="%d";\n%s\t\t\t_modelEditable=T;\n\t\t}}'
                                      % (a.id, a.de, AUTHOR, t, views(D, a.de, '\t\t\t')))
                    s += '\tactivations=(\n%s\n\t);\n' % ', \n'.join(blocks)
                s += '\tpmLastModified="%d";\n}' % t
                me_rows.append((p['me'], 'InteractionLifeLine', F, p['name'], s))

        # ---- frame
        t = ts()
        s = hdr(F, name, 'Frame')
        if self.gates:
            s += reflist('gates', ['%s:%s' % (F, g['id']) for g in self.gates])
        kids = [lp(p) for p in self.parts] + ['%s:%s' % (F, fr['id']) for fr in self.frags if fr['operand'] is None] + ['%s:%s' % (F, g['id']) for g in self.gates]
        s += '\tpmLastModified="%d";\n\tpmAuthor="%s";\n' % (t, AUTHOR)
        s += reflist('Child', kids)
        s += '\tpmCreateDateTime="%d";\n\t_modelViews=NULL;\n\tlastModifiedTime=%d;\n\t_modelEditable=T;\n}' % (t, t)
        me_rows.append((F, 'Frame', None, name, s))

        # ---- views
        for fr in self.frags:                                   # behind everything
            par = fr['operand']
            rx, ry = (fr['x'], fr['top']) if par is None else (fr['x'] - par['x'], fr['top'] - par['top'])
            s = hdr(fr['de'], fr['name'], 'CombinedFragment')
            s += '\tparentConnectorHeaderLength=40;\n\t_fillColor=%s;\n\tbackground=%s;\n\twidth=%d;\n' % (fill(100, 122, 207, 245, 0), BLUE, fr['w'])
            s += '\t_captionUIModel=%s;\n\t_elementFont=%s;\n' % (caption(0, 0, OP_TAB_W[fr['kind']], 18, side=12), FONT)
            s += '\tmetaModelElement=<%s>;\n\tforeground=%s;\n\tconnectToPoint=T;\n\ty=%d;\n\toverrideAppearanceWithStereotypeIcon=T;\n\tx=%d;\n' % (frag_path(fr), BLACK, ry, rx)
            if par is not None:
                s += '\t_parent=<%s:%s>;\n' % (D, par['de'])
            s += '\t_lineModel=%s;\n\theight=%d;\n\tparentConnectorLineLength=10;\n}' % (LINE, fr['h'])
            de_rows.append((fr['de'], 'CombinedFragment', fr['id'], None, par['de'] if par is not None else None, s))
            sort_ids.append(fr['de'])
            for od in fr['ops']:
                h = od['bottom'] - od['top']
                s = hdr(od['de'], od['name'], 'InteractionOperand')
                s += '\tparentConnectorHeaderLength=40;\n\t_fillColor=%s;\n\tbackground=%s;\n\twidth=%d;\n' % (fill(0, 122, 207, 245, 255), BLUE, od['w'])
                s += '\t_captionUIModel=%s;\n\t_elementFont=%s;\n' % (caption(od['x'], od['top'], od['w'], h, side=7, visible=False), FONT)
                s += '\tmetaModelElement=<%s>;\n\tforeground=%s;\n\tconnectToPoint=T;\n\ty=%d;\n\toverrideAppearanceWithStereotypeIcon=T;\n\tx=%d;\n' % (op_path(od), BLACK, od['top'], od['x'])
                s += '\t_lineModel=%s;\n\theight=%d;\n\tparentConnectorLineLength=10;\n}' % (LINE, h)
                de_rows.append((od['de'], 'InteractionOperand', od['id'], None, None, s))
                sort_ids.append(od['de'])
        for oc in self.occs:
            par = oc['operand']
            s = hdr(oc['de'], oc['target'], 'InteractionOccurrence')
            s += '\tforeground=%s;\n\tcreatorDiagramType="InteractionDiagram";\n\t_durationConstraintUIInfo=NULL;\n\tconnectToPoint=T;\n\ty=%d;\n\tx=%d;\n' % (BLACK, oc['top'] - par['top'], oc['x'] - par['x'])
            s += '\tmetaModelElement=<%s:%s>;\n\toverrideAppearanceWithStereotypeIcon=T;\n\tparentConnectorHeaderLength=40;\n\tparentConnectorLineLength=10;\n\theight=%d;\n' % (op_path(par), oc['id'], oc['height'])
            s += '\t_fillColor=%s;\n\twidth=%d;\n\tbackground=%s;\n\t_parent=<%s:%s>;\n\t_elementFont=%s;\n' % (fill(100, 122, 207, 245, 0), oc['w'], BLUE, D, par['de'], FONT)
            s += '\t_captionUIModel=%s;\n\t_lineModel=%s;\n}' % (caption(0, 0, oc['w'], oc['height'], side=12), LINE)
            de_rows.append((oc['de'], 'InteractionOccurrence', oc['id'], None, par['de'], s))
            sort_ids.append(oc['de'])
        for p in self.parts:
            typ = 'InteractionActor' if p['kind'] == 'actor' else 'InteractionLifeLine'
            s = hdr(p['de'], p['name'], typ)
            s += '\tforeground=%s;\n\tcustomText="";\n\tparentFrame=<%s>;\n\tconnectToPoint=T;\n\ty=%d;\n\tx=%d;\n' % (BLACK, F, p['y'], p['x'])
            s += '\tmetaModelElement=<%s>;\n\toverrideAppearanceWithStereotypeIcon=T;\n\tparentConnectorHeaderLength=40;\n\tparentConnectorLineLength=10;\n\theight=%d;\n' % (lp(p), p['h'])
            s += '\t_fillColor=%s;\n\twidth=%d;\n\tbackground=%s;\n\t_elementFont=%s;\n' % (fill(0, 255, 255, 255, 255), p['w'], WHITE, FONT)
            if p['kind'] == 'actor':
                cap = caption((p['w'] - p['cap']) // 2, 35, p['cap'], 15)
            else:
                cap = caption(0, 8, p['w'], 15)
            s += '\t_captionUIModel=%s;\n\t_lineModel=%s;\n}' % (cap, LINE)
            de_rows.append((p['de'], typ, p['me'], None, None, s))
            sort_ids.append(p['de'])
            for a in p['acts']:
                s = hdr(a.de, 'Activation', 'Activation')
                s += '\tparentConnectorHeaderLength=40;\n\t_fillColor=%s;\n\tbackground=%s;\n\twidth=8;\n' % (fill(0, 255, 255, 255, 255), BLUE)
                s += '\t_captionUIModel=%s;\n\t_elementFont=%s;\n' % (caption(a.x, a.top, 8, a.h, side=7, visible=False), FONT)
                s += '\tmetaModelElement=<%s>;\n\tforeground=%s;\n\tconnectToPoint=T;\n\ty=%d;\n\toverrideAppearanceWithStereotypeIcon=T;\n\tx=%d;\n' % (a.path(F), BLACK, a.top, a.x)
                s += '\t_lineModel=%s;\n\theight=%d;\n\tparentConnectorLineLength=10;\n}' % (LINE, a.h)
                de_rows.append((a.de, 'Activation', None, a.path(F), None, s))
                sort_ids.append(a.de)
        for g in self.gates:
            s = hdr(g['de'], 'Gate', 'Gate')
            s += '\t_fillColor=%s;\n\tbackground=%s;\n\tconnectionPointType=1;\n\twidth=20;\n' % (fill(100, 122, 207, 245, 0), BLUE)
            s += '\t_captionUIModel=%s;\n\t_elementFont=%s;\n' % (caption(-12, 20, 44, 15), FONT)
            s += '\tmetaModelElement=<%s:%s>;\n\tforeground=%s;\n\ty=%d;\n\toverrideAppearanceWithStereotypeIcon=T;\n\tx=%d;\n' % (F, g['id'], color(192, 192, 192), g['y'], g['x'])
            s += '\t_lineModel=%s;\n\theight=20;\n}' % GLINE
            de_rows.append((g['de'], 'Gate', g['id'], None, None, s))
            sort_ids.append(g['de'])
        for d in self.msgs:
            to = self.pk[d['to']]
            y = d['y']
            if d['kind'] == 'found':
                g = d['gate']
                fshape, fx0, fy0 = g['de'], g['x'], g['y']
                fpt = (g['x'] + 10, y)
            else:
                frm = self.pk[d['frm']]
                fshape, fx0, fy0 = frm['de'], frm['x'], frm['y']
            if d['kind'] == 'self':
                ax = d['fa'].x + 8
                pts_abs = [(ax, y), (ax + 30, y), (ax + 30, y + 20), (ax, y + 20)]
            else:
                right = to['cx'] > (frm['cx'] if d['kind'] != 'found' else fpt[0])
                if d['kind'] == 'found':
                    a = fpt
                elif d['fa'] is not None:
                    a = (d['fa'].x + (8 if right else 0), y)
                else:
                    a = (frm['cx'], y)
                if d['kind'] == 'create':
                    b = (to['x'] if right else to['x'] + to['w'], y)
                elif d['ta'] is not None:
                    b = (d['ta'].x + (0 if right else 8), y)
                else:
                    b = (to['cx'], y)
                pts_abs = [a, b]
            rel = [(px - fx0, py - fy0) for px, py in pts_abs[:-1]] + [(pts_abs[-1][0] - to['x'], pts_abs[-1][1] - to['y'])]
            if d['kind'] == 'found':
                rel[0] = (10, 10)
            fr_pts = [(px - fx0, py - fy0) for px, py in pts_abs]
            xs, ys = [p[0] for p in fr_pts], [p[1] for p in fr_pts]
            lab = self.label(d)
            cw, ch = int(tw(lab) * 1.1) + 30, 15   # VP pads captions; too narrow -> label shown as '...'
            if d['kind'] == 'self':
                cx_, cy_ = 36, 2
            else:
                dx = pts_abs[1][0] - pts_abs[0][0]
                cx_, cy_ = (dx - cw) // 2, -ch - 6
            s = hdr(d['de'], d['name'], 'Message')
            s += '\tbackground=%s;\n\twidth=%d;\n\ttoPinType=1;\n\tuseToShapeCenter=T;\n' % (BLACK, max(xs) - min(xs) + 100)
            s += '\t_captionUIModel=%s;\n\t_toShape=<%s:%s>;\n\t_elementFont=%s;\n' % (caption(cx_, cy_, cw, ch), D, to['de'], FONT)
            s += '\t_points="%s";\n' % ''.join('%d,%d;' % p for p in rel)
            s += '\tmetaModelElement=<%s>;\n\tfromPinType=1;\n\tforeground=%s;\n\ty=%d;\n\t_fromShape=<%s:%s>;\n\tx=%d;\n' % (mpath(d), BLACK, min(ys) - 50, D, fshape, min(xs) - 50)
            s += '\t_lineModel=%s;\n\theight=%d;\n\tuseFromShapeCenter=T;\n}' % (LINE, max(ys) - min(ys) + 100)
            de_rows.append((d['de'], 'Message', d['id'], None, None, s))
            sort_ids.append(d['de'])

        # ---- diagram
        t = ts()
        s = hdr(D, name, 'InteractionDiagram')
        s += '\tpaintConnectorThroughLabel=1;\n\t_shapeGroups=NULL;\n\tdiagramBackground=%s;\n' % WHITE
        s += '\tconnectorLabelOrientation=0;\n\tshowMessageStereotype=T;\n\tshowPackageNameStyle=0;\n\tshowDefaultPackage=F;\n\tpointConnectorEndToCompartmentMember=T;\n\tautoFitShapesSize=F;\n\tconnectorStyle=1;\n\tdiagramPreviewData_name=NULL;\n\tshowSequenceNumbers=T;\n'
        s += '\t_interactionDiagramLayoutOptions=(\n\t\t@absoluteLifelineSpacingDistance=80;, \n\t\t@absoluteMessageSpacingDistance=30;, \n\t\t@handleLabelsWhenLayout=T;, \n\t\t@lifelineSpacing=0;, \n\t\t@messageSpacing=0;, \n\t\t@realTimeLayout=F;\n\t);\n'
        s += '\t_globalPaletteOption=T;\n\tconnectionPointStyle=0;\n\tgridWidth=10;\n\tpmCreateDateTime="%d";\n\tshowActivations=T;\n\talignToGrid=F;\n' % t
        s += '\tcustomizedSortDiagramElementIds=(\n%s\n\t);\n' % ', \n'.join('\t\t"%s"' % i for i in sort_ids)
        s += '\tdiagramPreviewData_id="%s";\n\tautoExtendActivations=T;\n\tpmLastModified="%d";\n\thiddenDiagramElementIds=NULL;\n\tgridVisible=F;\n\tcreationTime=%d;\n' % (new_id(), t, t)
        s += '\tshowMessagesOperationSignature=T;\n\tpmAuthor="%s";\n\tlastModified=%d;\n\tconnectorLineJumpsSize=0;\n\tshowStereotypes=T;\n\tshapePresentationOption=0;\n\tconnectorModelElementNameAlignment=4;\n\tvoiceIds=NULL;\n\tdisplayLifeLinesAsRobustnessAnalysisIcon=0;\n\tinitializeDiagramForCreate=T;\n\treferenceMappingReferencedElementIds=NULL;\n' % (AUTHOR, t)
        s += '\t_rootFrame=<%s>;\n' % F
        s += reflist('Child', ['%s:%s' % (D, r[0]) for r in de_rows])
        s += '\treferenceMappingElementIds=NULL;\n\tmodelElementNameAlignment=4;\n\tshowActivityStateNodeCaption=524287;\n\tconnectorLineJumps=0;\n\tgridHeight=10;\n\tgridColor=%s;\n\tshowModelElementIdModelTypes=NULL;\n}' % color(192, 192, 192)

        return me_rows, de_rows, (D, name, s), [d['id'] for d in self.msgs]


# ------------------------------------------------------------------ JSON spec -> internal tuples
def _conv_items(items, path='items'):
    out = []
    for n, it in enumerate(items or []):
        where = f'{path}[{n}]'
        if not isinstance(it, dict) or 'type' not in it:
            raise VppError(f'{where}: każdy element musi być obiektem z polem "type".')
        t = it['type']
        try:
            if t == 'call':
                out.append(('call', it['from'], it['to'], it['operation']))
            elif t == 'self':
                out.append(('self', it['on'], it['operation']))
            elif t == 'create':
                out.append(('create', it['from'], it['to'], it.get('constructor')))
            elif t == 'return':
                out.append(('ret', it['from'], it['to'], it.get('label', '')))
            elif t == 'found':
                out.append(('found', it['to'], it['operation']))
            elif t == 'signal':
                out.append(('sig', it['from'], it['to'], it['label']))
            elif t in ('loop', 'opt'):
                out.append((t, it['guard'], _conv_items(it['items'], where + '.items')))
            elif t == 'alt':
                ops = [(o['guard'], _conv_items(o['items'], f'{where}.operands[{k}].items')) for k, o in enumerate(it['operands'])]
                if len(ops) < 2:
                    raise VppError(f'{where}: alt potrzebuje co najmniej 2 operandów (np. drugi z guard "else").')
                out.append(('alt', ops))
            elif t == 'ref':
                out.append(('ref', it['diagram'], it['covers']))
            else:
                raise VppError(f'{where}: nieznany typ {t!r}. Dozwolone: call, self, create, return, found, signal, loop, opt, alt, ref.')
        except KeyError as e:
            raise VppError(f'{where} ({t}): brak pola {e}.')
    return out


def convert_spec(spec: dict) -> dict:
    if 'name' not in spec or 'participants' not in spec or 'items' not in spec:
        raise VppError('Diagram potrzebuje pól: name, participants, items.')
    parts = []
    for n, p in enumerate(spec['participants']):
        if 'actor' in p:
            parts.append(('actor', p['actor']))
        elif 'class' in p:
            parts.append(('obj', p.get('name', '') or '', p['class'], bool(p.get('created', False))))
        else:
            raise VppError(f'participants[{n}]: podaj {{"actor": "Klient"}} albo {{"name": "koszyk", "class": "Koszyk", "created": false}}.')
    keys = [p[1] if p[0] == 'actor' else (p[1] or ':' + p[2]) for p in parts]
    if len(set(keys)) != len(keys):
        raise VppError('Uczestnicy muszą mieć unikalne nazwy (aktor po nazwie, obiekt po "name" albo ":Klasa").')
    items = _conv_items(spec['items'])

    def check(its):
        for it in its:
            k = it[0]
            names = {'call': it[1:3], 'self': it[1:2], 'create': it[1:3], 'ret': it[1:3], 'found': it[1:2], 'sig': it[1:3]}.get(k, ())
            for x in names:
                if x not in keys:
                    raise VppError(f'Komunikat {k} odwołuje się do {x!r}, którego nie ma wśród uczestników: {", ".join(keys)}')
            if k in ('loop', 'opt'):
                check(it[2])
            elif k == 'alt':
                for _, sub in it[1]:
                    check(sub)
            elif k == 'ref':
                for x in it[2]:
                    if x not in keys:
                        raise VppError(f'ref obejmuje {x!r}, którego nie ma wśród uczestników.')
    check(items)
    return dict(name=spec['name'], parts=parts, items=items)


# ------------------------------------------------------------------ editor integration
def _frames_by_name(p: Project) -> Dict[str, str]:
    out = {}
    for d in p.dg.values():
        if d.model_type == 'InteractionDiagram':
            f = d.obj.get('_rootFrame')
            if isinstance(f, Raw):
                out[d.name] = f.text.strip('<>')
    return out


def _message_container(ed) -> str:
    """'relRoot:msgContainer' path, creating the Message container if needed."""
    return ed._rel_container('Message')


def build_sequence_diagrams(ed, specs: List[dict]) -> List[str]:
    global _ED, AUTHOR, REL_ROOT
    p = ed.p
    conv = [convert_spec(s) for s in specs]
    existing = {d.name for d in p.dg.values()}
    for s in conv:
        if s['name'] in existing:
            raise VppError(f'Diagram {s["name"]!r} już istnieje. Usuń go najpierw (vpp_delete_sequence_diagram) albo zmień nazwę.')
    _ED, AUTHOR = ed, ed.author
    try:
        mc_path = _message_container(ed)
        REL_ROOT, mc = mc_path.split(':')
        model = Model(p)
        frame_ids = _frames_by_name(p)
        for s in conv:
            frame_ids[s['name']] = new_id()
        report = []
        for s in conv:
            sd = SD(model, s, frame_ids, mc)
            sd.run()
            sd.layout()
            me_rows, de_rows, (did, name, dtext), msg_ids = sd.build(None)
            for i, typ, parent, nm, txt in me_rows:
                ed.add_me(parse(txt), typ, parent, nm)
            for i, typ, mid, comp, par, txt in de_rows:
                r = ed.add_de(parse(txt), typ, did, mid, par)
                r.composite = comp
            from .project import Row
            p.dg[did] = Row('DIAGRAM', did, parse(dtext), 'InteractionDiagram', None, name)
            ed.dirty_dg.add(did)
            ed.append_diagram_root(did)
            ed.append_root(frame_ids[name])
            cont = p.me[mc]
            for m in msg_ids:
                v = cont.obj.get('Child')
                if not isinstance(v, Lst):
                    cont.obj.set('Child', Lst([]), before='pmCreateDateTime')
                cont.obj.get('Child').items.append(ref(f'{REL_ROOT}:{mc}:{m}'))
            ed.touch(cont)
            report.append(f'{name}: {len(sd.parts)} uczestników, {len(sd.msgs)} komunikatów, '
                          f'{sum(len(x["acts"]) for x in sd.parts)} aktywacji, {len(sd.frags)} fragmentów, '
                          f'{len(sd.occs)} ref, {len(sd.gates)} gate')
        return report
    finally:
        _ED = None


def delete_sequence_diagram(ed, name: str) -> str:
    p = ed.p
    d = p.find_diagram(name, 'InteractionDiagram')
    frame = d.obj.get('_rootFrame').text.strip('<>')
    # every model element owned (transitively) by the frame
    owned, frontier = {frame}, [frame]
    while frontier:
        nxt = [i for i, r in p.me.items() if r.parent in frontier and i not in owned]
        owned.update(nxt)
        frontier = nxt
    # messages whose ends point into this frame
    msgs = set()
    for i, r in p.me.items():
        if r.model_type == 'Message':
            txt = dump(r.obj)
            if f'<{frame}:' in txt:
                msgs.add(i)
    # refs from other diagrams to this frame
    for i, r in p.me.items():
        if r.model_type == 'InteractionOccurrence' and i not in owned and r.obj.text('refersTo') == f'<{frame}>':
            user = next((dd.name for dd in p.dg.values() if dd.model_type == 'InteractionDiagram'
                         and _under(p, i, dd.obj.get('_rootFrame').text.strip('<>'))), '?')
            raise VppError(f'Diagram {name} jest użyty przez ref w diagramie {user}. Usuń najpierw tamten diagram albo jego ref.')
    gone = owned | msgs
    for c in p.me.values():
        if c.id in gone:
            continue
        v = c.obj.get('Child')
        if isinstance(v, Lst):
            keep = [it for it in v.items if not (isinstance(it, Raw) and it.text.strip('<>').split(':')[-1] in gone)]
            if len(keep) != len(v.items):
                v.items = keep
                ed.touch(c)
    c = p.conn
    for i in gone:
        c.execute('delete from MODEL_ELEMENT where ID=?', (i,))
        p.me.pop(i, None)
        ed.dirty_me.discard(i)
    for i in [x.id for x in p.de.values() if x.diagram == d.id]:
        c.execute('delete from DIAGRAM_ELEMENT where ID=?', (i,))
        p.de.pop(i, None)
        ed.dirty_de.discard(i)
    c.execute('delete from DIAGRAM where ID=?', (d.id,))
    p.dg.pop(d.id, None)
    ed.dirty_dg.discard(d.id)
    for lst in (p.root_list, p.diagram_list):
        v = lst.get('Child')
        v.items = [it for it in v.items if it.text.strip('<>') not in (frame, d.id)]
    ed.dirty_info = True
    return f'Usunięto diagram sekwencji {name} ({len(owned)} elementów modelu, {len(msgs)} komunikatów)'


def describe_sequence_diagram(p: Project, name: str) -> dict:
    d = p.find_diagram(name, 'InteractionDiagram')
    frame = d.obj.get('_rootFrame').text.strip('<>')
    parts = []
    for rr in d.obj.refs('Child'):
        sh = p.de.get(rr.split(':')[-1])
        if sh and sh.model_type in ('InteractionLifeLine', 'InteractionActor'):
            m = p.me.get(sh.model)
            if m:
                if m.model_type == 'InteractionActor':
                    parts.append((p.geometry(sh)[0], f'actor {m.name}'))
                else:
                    bc = m.obj.get('baseClassifier')
                    parts.append((p.geometry(sh)[0], f'{m.name or ""} : {p.name_of(bc.text) if isinstance(bc, Raw) else "?"}'))
    parts.sort()
    lname = {}
    for i, r in p.me.items():
        if r.parent == frame and r.model_type in ('InteractionLifeLine', 'InteractionActor', 'Gate'):
            if r.model_type == 'InteractionLifeLine':
                bc = r.obj.get('baseClassifier')
                lname[i] = (r.name or '') + ':' + (p.name_of(bc.text) if isinstance(bc, Raw) else '?')
            else:
                lname[i] = r.name
    msgs = []
    for i, r in p.me.items():
        if r.model_type != 'Message':
            continue
        f, t = r.obj.get('from'), r.obj.get('to')
        if not (isinstance(f, Obj) and isinstance(t, Obj)):
            continue
        fe, te = f.text('EndModelElement') or '', t.text('EndModelElement') or ''
        if not te.startswith(f'<{frame}:'):
            continue
        at = r.obj.get('actionType')
        op = at.get('operation') if isinstance(at, Obj) else None
        kind = {'2': 'create', '3': 'self'}.get(r.obj.text('type') or '', 'return' if isinstance(at, Obj) and at.type == 'ActionTypeReturn' else 'call')
        label = r.name
        if isinstance(op, Raw):
            cls_id, oid = op.text.strip('<>').split('$')
            cls = p.me.get(cls_id.split(':')[-1])
            o = next((x for x in cls.obj.children() if x.id == oid), None) if cls else None
            label = f'{o.name}()' if o else '?'
        msgs.append((r.obj.text('sequenceNumber') or '', kind, lname.get(fe.strip('<>').split(':')[-1], '?'),
                     lname.get(te.strip('<>').split(':')[-1], '?'), label))

    def key(s):
        return [int(x) for x in s[0].split('.') if x.isdigit()]
    msgs.sort(key=key)
    frags = []
    for i, r in p.me.items():
        if r.model_type == 'CombinedFragment' and _under(p, i, frame):
            ops = [p.me[x.split(':')[-1]] for x in r.obj.refs('Child') if x.split(':')[-1] in p.me]
            frags.append({'_name': _natkey(r.name or ''), 'operator': OPERATOR_NAME.get(int(r.obj.text('interactionOperator') or 0), r.obj.text('interactionOperator')),
                          'guards': [o.obj.get('guard').text('constraint') if isinstance(o.obj.get('guard'), Obj) else None for o in ops]})
    frags.sort(key=lambda f: f.pop('_name'))
    return {'diagram': d.name, 'participants': [x[1] for x in parts],
            'messages': [f'{s} [{k}] {a} -> {b}: {l}' for s, k, a, b, l in msgs], 'fragments': frags}


def _natkey(s):
    import re as _re
    return [int(x) if x.isdigit() else x for x in _re.split(r'(\d+)', s)]


def _under(p: Project, i: str, frame: str) -> bool:
    seen = set()
    while i and i not in seen:
        seen.add(i)
        if i == frame:
            return True
        r = p.me.get(i)
        i = r.parent if r else None
    return False
