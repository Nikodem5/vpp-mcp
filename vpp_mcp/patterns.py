"""Creational design patterns as ready-made changes of the class model (tool ``vpp_apply_pattern``).

Every pattern is a function that calls the same :class:`~vpp_mcp.edit.Editor` operations a person would use
by hand (new classes, members, relationships, stereotypes). Nothing here writes to the file directly, so the
result is verified like any other edit. Role names (Budowniczy, Kierownik, ...) become class stereotypes,
which is what a design-patterns study usually has to show.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .edit import Editor, parse_operation
from .project import VppError

LABELS = {
    "pl": {
        "singleton": "Singleton",
        "builder": "Budowniczy", "concrete_builder": "Konkretny budowniczy", "director": "Kierownik",
        "product": "Produkt",
        "creator": "Wytwórca", "concrete_creator": "Wytwórca konkretny", "concrete_product": "Produkt konkretny",
        "abstract_factory": "Fabryka abstrakcyjna", "concrete_factory": "Fabryka konkretna",
        "abstract_product": "Produkt abstrakcyjny",
        "prototype": "Prototyp", "concrete_prototype": "Prototyp konkretny",
    },
    "en": {
        "singleton": "Singleton",
        "builder": "Builder", "concrete_builder": "ConcreteBuilder", "director": "Director", "product": "Product",
        "creator": "Creator", "concrete_creator": "ConcreteCreator", "concrete_product": "ConcreteProduct",
        "abstract_factory": "AbstractFactory", "concrete_factory": "ConcreteFactory",
        "abstract_product": "AbstractProduct",
        "prototype": "Prototype", "concrete_prototype": "ConcretePrototype",
    },
}

COMMON = {"diagram", "positions", "stereotypes", "language", "fragment_diagram", "fragment_context"}


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:]


def _req(a: Dict[str, Any], key: str, pattern: str):
    if a.get(key) in (None, "", []):
        raise VppError(f"Wzorzec {pattern}: brakuje parametru {key!r}.")
    return a[key]


class _Ctx:
    """State of one pattern application."""

    def __init__(self, ed: Editor, a: Dict[str, Any]):
        self.ed, self.a = ed, a
        self.diagram: Optional[str] = a.get("diagram")
        self.positions: Dict[str, List[int]] = a.get("positions") or {}
        self.lang = a.get("language", "pl")
        if self.lang not in LABELS:
            raise VppError("language: pl albo en")
        self.use_stereotypes = bool(a.get("stereotypes", True))
        self.log: List[str] = []
        self.parts: List[str] = []          # classes taking part in the pattern, in order
        self.roles: List[str] = []          # "Role: Class"

    # ------------------------------------------------------------ helpers
    def label(self, role: str) -> str:
        return LABELS[self.lang][role]

    def exists(self, name: str) -> bool:
        return any(r.name == name for r in self.ed.p.classifiers())

    def role(self, cls: str, role: str):
        self.roles.append(f"{self.label(role)}: {cls}")
        if cls not in self.parts:
            self.parts.append(cls)

    def new_class(self, name: str, kind: str, attributes=None, operations=None, role: Optional[str] = None,
                  near: Optional[str] = None, static_members=None):
        x, y = self.positions.get(name, (None, None))
        st = [self.label(role)] if (role and self.use_stereotypes) else None
        self.log.append(self.ed.add_class(name, kind, attributes, operations, None, static_members, None,
                                          self.diagram, x, y, st, near))
        if role:
            self.role(name, role)
        elif name not in self.parts:
            self.parts.append(name)

    def mark(self, cls: str, role: str):
        """Role stereotype on an EXISTING class."""
        self.role(cls, role)
        if self.use_stereotypes:
            self.log.append(self.ed.set_stereotype(cls, [self.label(role)]))

    def has_rel(self, kind: str, src: str, tgt: str, stereotype: Optional[str]) -> bool:
        for x in self.ed.p.relationships():
            k = x["kind"]
            if kind == "generalization" and k == "generalization" and (x["subclass"], x["superclass"]) == (src, tgt):
                return True
            if kind == "realization" and k == "realization" and (x["class"], x["interface"]) == (src, tgt):
                return True
            if kind == "dependency" and k == "dependency" and (x["from"], x["to"]) == (src, tgt) \
                    and (x.get("stereotype") or None) == (stereotype or None):
                return True
        return False

    def rel(self, kind: str, src: str, tgt: str, stereotype: Optional[str] = None, **kw):
        if kind in ("generalization", "realization", "dependency") and self.has_rel(kind, src, tgt, stereotype):
            return
        self.log.append(self.ed.add_relationship(kind, src, tgt, stereotype=stereotype, diagram=self.diagram, **kw))

    def fit(self, *names: str):
        for n in names:
            try:
                self.ed.fit_class(n, self.diagram)
            except VppError:
                pass            # not drawn on this diagram


# ---------------------------------------------------------------------------- Singleton
def p_singleton(c: _Ctx):
    a, ed = c.a, c.ed
    cls = _req(a, "class", "singleton")
    row = ed.p.find_class(cls)
    if ed.p.kind_of(row) != "class":
        raise VppError(f"Singleton: {cls} jest {ed.p.kind_of(row)}; wzorzec dotyczy zwykłej klasy.")
    inst, acc = a.get("instance_field", "instance"), a.get("accessor", "getInstance")
    names = {m.name for m in row.obj.children()}
    for n in (inst, acc):
        if n in names:
            raise VppError(f"Singleton: {cls} ma już składową {n!r}. Zmień instance_field / accessor.")
    c.log.append(ed.add_attribute(cls, f"-{inst} : {cls}", static=True))
    ctors = [o for o in ed.p.member_lines(row)["operations"] if o["constructor"]]
    if len(ctors) > 1:
        raise VppError(f"Singleton: {cls} ma {len(ctors)} konstruktory; zostaw jeden albo zmień ręcznie.")
    if ctors:
        c.log.append(ed.change_operation(cls, cls, "-" + ctors[0]["text"][1:]))
    else:
        c.log.append(ed.add_operation(cls, f"-{cls}()"))
    c.log.append(ed.add_operation(cls, f"+{acc}() : {cls}", static=True))
    c.role(cls, "singleton")
    if c.use_stereotypes:
        c.log.append(ed.set_stereotype(cls, [c.label("singleton")]))
    callers = []
    for x in ed.p.relationships():
        if x["kind"] == "dependency" and x["to"] == cls:
            callers.append(x["from"])
        elif x["kind"] in ("association", "directed association", "aggregation", "composition"):
            if x["to"]["class"] == cls:
                callers.append(x["from"]["class"])
    if a.get("drop_parameters"):
        for other in ed.p.classifiers():
            if other.name == cls:
                continue
            for op in ed.p.member_lines(other)["operations"]:
                po = parse_operation(op["text"])
                keep = [(n, t) for n, t in po["params"] if t != cls]
                if len(keep) != len(po["params"]):
                    text = f"{po['vis']}{po['name']}({', '.join(f'{n} : {t}' for n, t in keep)})" \
                           + (f" : {po['ret']}" if po["ret"] else "")
                    c.log.append(ed.change_operation(other.name, po["name"], text))
                    c.fit(other.name)
                    if other.name not in callers:
                        callers.append(other.name)
    for u in sorted(set(callers)):
        if u not in c.parts:
            c.parts.append(u)
    c.fit(cls)
    if callers:
        c.log.append(f"Klienci singletona (powinni brać instancję przez {cls}.{acc}()): {', '.join(sorted(set(callers)))}")


# ---------------------------------------------------------------------------- Builder
def p_builder(c: _Ctx):
    a, ed = c.a, c.ed
    product = _req(a, "product", "builder")
    ed.p.find_class(product)
    steps: List[str] = _req(a, "steps", "builder")
    b = a.get("builder", f"{product}Builder")
    cb = a.get("concrete_builder", f"Concrete{b}")
    dr = a.get("director", f"{product}Director")
    res = a.get("result_operation", f"+pobierz{product}() : {product}")
    # the director's operation takes every distinct parameter of the steps
    params: List[Tuple[str, str]] = []
    for s in steps:
        for n, t in parse_operation(s)["params"]:
            if n not in [p[0] for p in params]:
                params.append((n, t))
    dop = a.get("director_operation") or ("+konstruuj(" + ", ".join(f"{n} : {t}" for n, t in params) + ") : void")
    ctor = a.get("concrete_constructor") or []
    attrs = a.get("concrete_attributes") or [f"-{_lower_first(product)} : {product}"]
    for n in (b, cb, dr):
        if c.exists(n):
            raise VppError(f"Budowniczy: klasa {n} już istnieje. Podaj inne nazwy (builder, concrete_builder, director).")
    # changes of the product: the constructor shrinks to what is mandatory, the rest is added step by step
    if a.get("product_constructor"):
        c.log.append(ed.change_operation(product, product, a["product_constructor"]))
    for t in a.get("product_operations") or []:
        c.log.append(ed.add_operation(product, t))
    if a.get("mark_product", True):
        c.mark(product, "product")
    else:
        c.parts.append(product)
    c.new_class(b, "interface", None, list(steps) + [res], "builder", near=product)
    c.new_class(cb, "class", attrs,
                ([f"+{cb}({', '.join(ctor)})"] if ctor else []) + list(steps) + [res], "concrete_builder", near=b)
    c.new_class(dr, "class", None, [f"+{dr}({_lower_first(b)} : {b})", dop], "director", near=b)
    c.rel("realization", cb, b)
    c.rel("dependency", cb, product, "create")
    c.rel("directed", dr, b, source_multiplicity="0..*", target_multiplicity="1", target_role=_lower_first(b))
    for cl in a.get("clients") or []:
        ed.p.find_class(cl)
        c.rel("dependency", cl, dr, "create")
        c.rel("dependency", cl, cb, "create")
        if cl not in c.parts:
            c.parts.append(cl)
    c.fit(product)


# ---------------------------------------------------------------------------- Factory method
def p_factory_method(c: _Ctx):
    a, ed = c.a, c.ed
    product = _req(a, "product", "factory_method")
    prow = ed.p.find_class(product)
    concrete = _req(a, "concrete_products", "factory_method")
    if isinstance(concrete, str):
        concrete = [concrete]
    creator = a.get("creator", f"{product}Creator")
    fm = a.get("factory_method", f"utworz{product}")
    cc = a.get("concrete_creators") or [f"{p}Creator" for p in concrete]
    if len(cc) != len(concrete):
        raise VppError("factory_method: concrete_creators musi mieć tyle elementów co concrete_products.")
    fparams = a.get("factory_params") or ""
    pk = ed.p.kind_of(prow)
    c.role(product, "product")
    if c.use_stereotypes and not ed.p.user_stereotypes(prow):
        c.log.append(ed.set_stereotype(product, [c.label("product")]))
    ops = [f"+{fm}({fparams}) : {product}"] + list(a.get("creator_operations") or [])
    c.new_class(creator, "abstract class", None, ops, "creator", near=product)
    c.log.append(ed.change_operation(creator, fm, f"+{fm}({fparams}) : {product}", abstract=True))
    for cp, cr in zip(concrete, cc):
        ed.p.find_class(cp)
        c.mark(cp, "concrete_product")
        c.new_class(cr, "class", None, [f"+{fm}({fparams}) : {product}"], "concrete_creator", near=creator)
        c.rel("generalization", cr, creator)
        c.rel("dependency", cr, cp, "create")
        if not c.has_rel("realization" if pk == "interface" else "generalization", cp, product, None):
            c.rel("realization" if pk == "interface" else "generalization", cp, product)
    c.rel("dependency", creator, product, "use")
    c.fit(product)


# ---------------------------------------------------------------------------- Abstract factory
def p_abstract_factory(c: _Ctx):
    a, ed = c.a, c.ed
    factory = _req(a, "factory", "abstract_factory")
    products = _req(a, "products", "abstract_factory")        # [{"name": AbstractProduct, "method": "utworzX"}]
    families = _req(a, "families", "abstract_factory")        # [{"name": "FabrykaX", "products": {AbstractProduct: ConcreteProduct}}]
    if c.exists(factory):
        raise VppError(f"Fabryka abstrakcyjna: klasa {factory} już istnieje.")
    methods = {}
    ops = []
    for p in products:
        ed.p.find_class(p["name"])
        methods[p["name"]] = p.get("method") or f"utworz{p['name']}"
        ops.append(f"+{methods[p['name']]}() : {p['name']}")
        c.role(p["name"], "abstract_product")
        if c.use_stereotypes and not ed.p.user_stereotypes(ed.p.find_class(p["name"])):
            c.log.append(ed.set_stereotype(p["name"], [c.label("abstract_product")]))
    first = products[0]["name"]
    c.new_class(factory, "interface", None, ops, "abstract_factory", near=first)
    for fam in families:
        fn = fam["name"]
        if c.exists(fn):
            raise VppError(f"Fabryka abstrakcyjna: klasa {fn} już istnieje.")
        c.new_class(fn, "class", None, ops, "concrete_factory", near=factory)
        c.rel("realization", fn, factory)
        for ap, cp in (fam.get("products") or {}).items():
            if ap not in methods:
                raise VppError(f"Rodzina {fn}: {ap!r} nie jest na liście products.")
            if not c.exists(cp):
                kind = ed.p.kind_of(ed.p.find_class(ap))
                c.new_class(cp, "class", None, None, "concrete_product", near=ap)
                c.rel("realization" if kind == "interface" else "generalization", cp, ap)
            else:
                c.mark(cp, "concrete_product")
            c.rel("dependency", fn, cp, "create")
    for cl in a.get("clients") or []:
        ed.p.find_class(cl)
        c.rel("dependency", cl, factory, "use")
        if cl not in c.parts:
            c.parts.append(cl)


# ---------------------------------------------------------------------------- Prototype
def p_prototype(c: _Ctx):
    a, ed = c.a, c.ed
    cls = _req(a, "class", "prototype")
    row = ed.p.find_class(cls)
    iface = a.get("prototype", "Prototyp")
    method = a.get("clone_method", "klonuj")
    if any(m.name == method for m in row.obj.children()):
        raise VppError(f"Prototyp: {cls} ma już składową {method!r}.")
    if not c.exists(iface):
        c.new_class(iface, "interface", None, [f"+{method}() : {iface}"], "prototype", near=cls)
    else:
        c.role(iface, "prototype")
    c.log.append(ed.add_operation(cls, f"+{method}() : {cls}"))
    c.mark(cls, "concrete_prototype")
    c.rel("realization", cls, iface)
    for cl in a.get("clients") or []:
        ed.p.find_class(cl)
        c.rel("dependency", cl, iface, "use")
        if cl not in c.parts:
            c.parts.append(cl)
    c.fit(cls)


# ---------------------------------------------------------------------------- registry
PATTERNS: Dict[str, Tuple[Callable[[_Ctx], None], set, str]] = {
    "singleton": (p_singleton, {"class", "instance_field", "accessor", "drop_parameters"},
                  'Singleton. {"class":"DyspozytorDostaw"}: prywatny konstruktor, statyczne pole -instance i statyczna '
                  'metoda +getInstance(). Opcjonalnie: "instance_field", "accessor", "drop_parameters":true (usuwa z metod '
                  'innych klas parametry typu tej klasy, bo klienci biorą instancję przez getInstance()).'),
    "builder": (p_builder, {"product", "steps", "builder", "concrete_builder", "director", "result_operation",
                            "director_operation", "concrete_constructor", "concrete_attributes", "product_constructor",
                            "product_operations", "mark_product", "clients"},
                'Budowniczy (Builder). {"product":"Zamowienie","builder":"BudowniczyZamowienia",'
                '"concrete_builder":"BudowniczyZamowieniaKlienta","director":"KierownikZamowien",'
                '"steps":["+dodajPozycjeZKoszyka(koszyk : Koszyk) : void","+ustawUwagi(uwagi : String) : void"],'
                '"concrete_constructor":["klient : Klient","adres : Adres"],'
                '"product_constructor":"+Zamowienie(klient : Klient, adresDostawy : Adres)",'
                '"product_operations":["+dodajPozycje(pozycja : PozycjaZamowienia) : void"],"clients":["Klient"]}. '
                'Powstają: interfejs budowniczego (kroki + operacja wyniku), konkretny budowniczy (realizacja, «create» produktu), '
                'kierownik (asocjacja do budowniczego, operacja konstruująca). Opcjonalnie: result_operation, director_operation, '
                'concrete_attributes, mark_product (domyślnie true).'),
    "factory_method": (p_factory_method, {"product", "concrete_products", "creator", "factory_method", "concrete_creators",
                                          "factory_params", "creator_operations"},
                       'Metoda wytwórcza. {"product":"BramkaPlatnosci","concrete_products":["BramkaPlatnosciOnline"],'
                       '"creator":"FabrykaBramek","factory_method":"utworzBramke","concrete_creators":["FabrykaBramekOnline"]}. '
                       'Wytwórca abstrakcyjny z abstrakcyjną metodą wytwórczą i konkretni wytwórcy tworzący konkretne produkty.'),
    "abstract_factory": (p_abstract_factory, {"factory", "products", "families", "clients"},
                         'Fabryka abstrakcyjna. {"factory":"FabrykaPlatnosci","products":[{"name":"BramkaPlatnosci","method":"utworzBramke"},'
                         '{"name":"Platnosc2","method":"utworzPlatnosc"}],"families":[{"name":"FabrykaOnline",'
                         '"products":{"BramkaPlatnosci":"BramkaPlatnosciOnline","Platnosc2":"PlatnoscOnline"}}],"clients":["Zamowienie"]}. '
                         'Brakujące produkty konkretne są tworzone i podpinane do produktu abstrakcyjnego.'),
    "prototype": (p_prototype, {"class", "prototype", "clone_method", "clients"},
                  'Prototyp. {"class":"Zamowienie","prototype":"Prototyp","clone_method":"klonuj","clients":["Klient"]}: '
                  'interfejs z operacją klonowania, klasa go realizuje i dostaje +klonuj().'),
}

ALIASES = {"budowniczy": "builder", "metoda_wytworcza": "factory_method", "factory": "abstract_factory",
           "fabryka_abstrakcyjna": "abstract_factory", "prototyp": "prototype", "factory_method": "factory_method"}


def pattern_key(name: str) -> str:
    k = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    k = ALIASES.get(k, k)
    if k not in PATTERNS:
        raise VppError(f"Nieznany wzorzec {name!r}. Dostępne: {', '.join(PATTERNS)}.")
    return k


def describe_patterns() -> Dict[str, Any]:
    return {k: {"opis": v[2], "parametry": sorted(v[1] | COMMON)} for k, v in PATTERNS.items()}


def apply_pattern(ed: Editor, name: str, params: Dict[str, Any]) -> List[str]:
    key = pattern_key(name)
    fn, allowed, _doc = PATTERNS[key]
    params = dict(params or {})
    unknown = set(params) - allowed - COMMON
    if unknown:
        raise VppError(f"Wzorzec {key}: nieznane parametry {sorted(unknown)}. Dozwolone: {sorted(allowed | COMMON)}.")
    c = _Ctx(ed, params)
    fn(c)
    out = list(c.log)
    fd = params.get("fragment_diagram")
    if fd:
        classes = list(c.parts)
        for extra in params.get("fragment_context") or []:
            if extra not in classes:
                classes.append(extra)
        out.append(ed.add_class_diagram(fd))
        out.append(ed.add_to_diagram(fd, classes, True))
    out.append("Role we wzorcu: " + "; ".join(c.roles))
    return out
