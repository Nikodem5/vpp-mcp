"""MCP server for Visual Paradigm projects (.vpp).

Runs locally (stdio). Reads projects and writes edited COPIES: the original
file is never changed, every write goes to a temporary file that must pass
the structural verifier before it replaces the output path.
"""
from __future__ import annotations

import json
import os
import shutil
import traceback
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .edit import Editor
from .patterns import PATTERNS, apply_pattern, describe_patterns
from .project import Project, VppError, is_open_in_vp, lock_path
from .sequence import build_sequence_diagrams, delete_sequence_diagram, describe_sequence_diagram
from .verify import verify

INSTRUCTIONS = """Narzędzia do czytania i edycji projektów Visual Paradigm (.vpp) bez otwierania programu.

Zasady pracy:
1. Najpierw czytaj: vpp_project_info, vpp_list_classes, vpp_get_class, vpp_list_relationships, vpp_get_sequence_diagram.
2. Zmiany zapisuj ZAWSZE do nowego pliku (output_path), np. 'projekt-v2.vpp' obok oryginału. Oryginał zostaje nietknięty.
3. Plik wynikowy nie może być otwarty w Visual Paradigm (VP trzyma wtedy plik .<nazwa>.vpp.lck). Źródło może być otwarte,
   ale wtedy do kopii trafia tylko to, co użytkownik ZAPISAŁ w VP.
4. Kolejne zmiany rób na pliku wynikowym poprzedniej (source_path = poprzedni output_path, nowy output_path),
   albo ten sam plik z overwrite_output=true.
5. Po zmianach poproś użytkownika, żeby otworzył plik w VP i od razu go zapisał (Ctrl+S) — VP przepisze go po swojemu.
   Układ linii relacji jest przybliżony; użytkownik porządkuje je ręcznie.
6. Komunikaty w diagramach sekwencji muszą wskazywać istniejące metody klas (dopasowanie po nazwie i liczbie argumentów,
   z dziedziczeniem). Brakujące metody dodaj najpierw przez vpp_edit_class_model.
"""

mcp = FastMCP("visual-paradigm", instructions=INSTRUCTIONS)


# ------------------------------------------------------------------ helpers
def _abs(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p))


def _check_source(path: str) -> str:
    path = _abs(path)
    if not path.lower().endswith(".vpp"):
        raise VppError("Plik musi mieć rozszerzenie .vpp")
    if not os.path.exists(path):
        raise VppError(f"Nie ma pliku {path}")
    return path


def _write(source_path: str, output_path: str, overwrite_output: bool, work) -> str:
    """Copy source -> tmp, run work(editor) -> list of log lines, verify, move tmp -> output."""
    src = _check_source(source_path)
    out = _abs(output_path)
    if not out.lower().endswith(".vpp"):
        raise VppError("output_path musi kończyć się na .vpp")
    if os.path.exists(out) and not overwrite_output:
        raise VppError(f"Plik {out} już istnieje. Podaj inną nazwę albo overwrite_output=true.")
    if is_open_in_vp(out):
        raise VppError(f"Plik {out} jest otwarty w Visual Paradigm ({os.path.basename(lock_path(out))}). "
                       "Zamknij go w VP albo zapisz wynik pod inną nazwą.")
    notes = []
    if is_open_in_vp(src):
        notes.append("Uwaga: plik źródłowy jest otwarty w VP. Kopia zawiera tylko to, co było zapisane w VP.")
    tmp = out + ".mcp-tmp"
    shutil.copyfile(src, tmp)
    ed = None
    try:
        ed = Editor(tmp)
        log = work(ed)
        ed.commit()
        ed.close()
        ed = None
        errs = verify(tmp)
        if errs:
            raise VppError("Weryfikacja nie przeszła, nic nie zapisano:\n- " + "\n- ".join(errs[:15]))
        os.replace(tmp, out)
    except Exception:
        if ed is not None:
            try:
                ed.close()
            except Exception:
                pass
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    lines = notes + [f"Zapisano: {out}", "Weryfikacja struktury: OK"] + [f"- {x}" for x in log]
    lines.append("Następny krok: otwórz plik w Visual Paradigm i od razu zapisz (Ctrl+S).")
    return "\n".join(lines)


def _err(e: Exception) -> str:
    if isinstance(e, VppError):
        return f"BŁĄD: {e}"
    return f"BŁĄD (nieoczekiwany): {e}\n{traceback.format_exc(limit=3)}"


def _json(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ read tools
@mcp.tool()
def vpp_project_info(path: str) -> str:
    """Podsumowanie projektu .vpp: diagramy (nazwa, typ), liczba klas/interfejsów/enumeracji, aktorzy,
    przypadki użycia, liczba relacji, czy plik jest otwarty w VP."""
    try:
        p = Project(_check_source(path))
        try:
            return _json(p.summary())
        finally:
            p.close()
    except Exception as e:
        return _err(e)


@mcp.tool()
def vpp_list_classes(path: str, with_members: bool = False) -> str:
    """Lista klas, klas abstrakcyjnych, interfejsów i enumeracji. with_members=true dodaje atrybuty, metody i wartości enumeracji
    w notacji UML (np. '-email : String', '+zaloguj(email : String, haslo : String) : boolean')."""
    try:
        p = Project(_check_source(path))
        try:
            out = []
            for r in sorted(p.classifiers(), key=lambda r: (p.kind_of(r), r.name)):
                item = {"name": r.name, "kind": p.kind_of(r)}
                if p.user_stereotypes(r):
                    item["stereotypes"] = p.user_stereotypes(r)
                if with_members:
                    m = p.member_lines(r)
                    item["attributes"] = [a["text"] + (" {static}" if a["static"] else "") for a in m["attributes"]]
                    item["operations"] = [o["text"] + (" {static}" if o["static"] else "") + (" {abstract}" if o["abstract"] else "")
                                          for o in m["operations"]]
                    if m["literals"]:
                        item["literals"] = m["literals"]
                out.append(item)
            return _json(out)
        finally:
            p.close()
    except Exception as e:
        return _err(e)


@mcp.tool()
def vpp_get_class(path: str, name: str) -> str:
    """Szczegóły jednej klasy: rodzaj, składowe, wszystkie relacje, w których uczestniczy, i położenie na diagramach klas."""
    try:
        p = Project(_check_source(path))
        try:
            r = p.find_class(name)
            m = p.member_lines(r)
            rels = [x["text"] for x in p.relationships() if r.name in x["text"].replace('"', " ").split()]
            shapes = []
            for d in p.class_diagrams():
                sh = p.shape_of(r.id, d.id)
                if sh:
                    x, y, w, h = p.geometry(sh)
                    shapes.append({"diagram": d.name, "x": x, "y": y, "width": w, "height": h})
            return _json({"name": r.name, "kind": p.kind_of(r), "stereotypes": p.user_stereotypes(r), **m,
                          "relationships": rels, "shapes": shapes})
        finally:
            p.close()
    except Exception as e:
        return _err(e)


@mcp.tool()
def vpp_list_relationships(path: str, class_name: Optional[str] = None) -> str:
    """Relacje w notacji PlantUML-podobnej: generalizacje (--|>), realizacje (..|>), zależności (..> «stereotyp»),
    asocjacje z licznościami i rolami (--, -->, o--, *--). Każda ma id (potrzebne do usuwania).
    class_name zawęża do relacji danej klasy."""
    try:
        p = Project(_check_source(path))
        try:
            rels = [x for x in p.relationships() if x["kind"] != "association (use case)"]
            if class_name:
                n = p.find_class(class_name).name
                rels = [x for x in rels if n in x["text"].replace('"', " ").split()]
            return _json([{"id": x["id"], "kind": x["kind"], "text": x["text"]} for x in rels])
        finally:
            p.close()
    except Exception as e:
        return _err(e)


@mcp.tool()
def vpp_get_sequence_diagram(path: str, name: str) -> str:
    """Opis diagramu sekwencji: uczestnicy od lewej, komunikaty z numerami VP (1, 1.1, ...), rodzaj, nadawca, odbiorca,
    operacja; fragmenty (loop/alt/opt) z warunkami."""
    try:
        p = Project(_check_source(path))
        try:
            return _json(describe_sequence_diagram(p, name))
        finally:
            p.close()
    except Exception as e:
        return _err(e)


@mcp.tool()
def vpp_export_plantuml(path: str, classes: Optional[List[str]] = None, with_members: bool = True,
                        diagram: Optional[str] = None) -> str:
    """Eksport (fragmentu) diagramu klas do PlantUML, np. do studium wzorca: fragment 'przed' i 'po' zmianie.
    classes = lista nazw klas (domyślnie wszystkie); relacje tylko między wybranymi klasami.
    diagram = nazwa diagramu klas: eksportuje klasy z tego diagramu (np. z diagramu-fragmentu wzorca)."""
    try:
        p = Project(_check_source(path))
        try:
            if diagram:
                d = p.find_diagram(diagram, "ClassDiagram")
                rows = [p.me[s.model] for s in p.shapes_on(d.id) if s.model_type == "Class" and s.parent is None]
            else:
                rows = [p.find_class(c) for c in classes] if classes else p.classifiers()
            names = {r.name for r in rows}
            L = ["@startuml", "skinparam style strictuml", "skinparam classAttributeIconSize 0", "hide empty members"]
            for r in rows:
                k = p.kind_of(r)
                head = {"interface": "interface", "enumeration": "enum", "abstract class": "abstract class"}.get(k, "class")
                st = "".join(f" <<{s}>>" for s in p.user_stereotypes(r))
                L.append(f'{head} "{r.name}" as {_puml_id(r.name)}{st} {{')
                if with_members:
                    m = p.member_lines(r)
                    for a in m["attributes"]:
                        L.append("  " + ("{static} " if a["static"] else "") + a["text"])
                    for o in m["operations"]:
                        L.append("  " + ("{static} " if o["static"] else "") + ("{abstract} " if o["abstract"] else "") + o["text"])
                    for lit in m["literals"]:
                        L.append("  " + lit)
                L.append("}")
            for x in p.relationships():
                k = x["kind"]
                if k == "generalization" and {x["subclass"], x["superclass"]} <= names:
                    L.append(f'{_puml_id(x["superclass"])} <|-- {_puml_id(x["subclass"])}')
                elif k == "realization" and {x["class"], x["interface"]} <= names:
                    L.append(f'{_puml_id(x["interface"])} <|.. {_puml_id(x["class"])}')
                elif k == "dependency" and {x["from"], x["to"]} <= names:
                    L.append(f'{_puml_id(x["from"])} ..> {_puml_id(x["to"])}' + (f' : <<{x["stereotype"]}>>' if x["stereotype"] else ""))
                elif k in ("association", "directed association", "aggregation", "composition"):
                    a, b = x["from"], x["to"]
                    if {a["class"], b["class"]} <= names:
                        sym = {"composition": "*--", "aggregation": "o--", "directed association": "-->"}.get(k, "--")
                        la = " ".join(v for v in (a["role"], a["multiplicity"]) if v)
                        lb = " ".join(v for v in (b["role"], b["multiplicity"]) if v)
                        L.append(f'{_puml_id(a["class"])} "{la}" {sym} "{lb}" {_puml_id(b["class"])}'.replace('"" ', "").replace(' ""', ""))
            L.append("@enduml")
            return "\n".join(L)
        finally:
            p.close()
    except Exception as e:
        return _err(e)


def _puml_id(n: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    return "".join(ch if ch.isalnum() else "_" for ch in s) or "X"


@mcp.tool()
def vpp_verify(path: str) -> str:
    """Strukturalna kontrola pliku .vpp (odwołania, ID, powiązania model–widok, listy). Pliki zapisane przez VP przechodzą ją zawsze."""
    try:
        errs = verify(_check_source(path))
        return "OK" if not errs else "Problemy:\n- " + "\n- ".join(errs)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ write tools
CHANGE_DOC = """Lista zmian wykonywanych po kolei, wszystkie albo żadna. Każda zmiana to obiekt z polem "op":
- {"op":"add_class","name":"FabrykaZamowien","kind":"class|abstract class|interface|enumeration",
   "attributes":["-licznik : int"], "operations":["+utworz(klient : Klient) : Zamowienie"], "literals":["A","B"],
   "static_members":["licznik"], "abstract_operations":["utworz"], "stereotypes":["Builder"],
   "x":100, "y":200, "near":"Zamowienie", "diagram":"<nazwa diagramu klas>"}
   (bez x, y klasa trafia obok klasy z pola near albo, gdy go nie ma, w wolne miejsce pod diagramem)
- {"op":"set_stereotype","class":"DyspozytorDostaw","stereotypes":["Singleton"]}  (pusta lista usuwa stereotypy użytkownika)
- {"op":"add_attribute","class":"Klient","text":"-email : String [0..1]","static":false}
- {"op":"add_operation","class":"Klient","text":"+zaloguj(email : String, haslo : String) : boolean","static":false,"abstract":false}
- {"op":"change_operation","class":"Menu","name":"dodajDanie","text":"+dodajDanie(nazwa : String, cena : double) : Danie"}
  (zachowuje ID metody, więc komunikaty w diagramach sekwencji dalej na nią wskazują)
- {"op":"change_attribute","class":"Danie","name":"cena","text":"-cena : double"}
- {"op":"remove_member","class":"Klient","name":"dodajAdres"}  (odmówi, jeśli metodę wywołuje komunikat)
- {"op":"add_literal","class":"StatusZamowienia","literal":"REKLAMOWANE"}
- {"op":"add_relationship","kind":"generalization|realization|dependency|association|directed|aggregation|composition",
   "source":"Klient","target":"Użytkownik", "source_multiplicity":"1","source_role":"klient",
   "target_multiplicity":"0..*","target_role":"zamowienia","stereotype":"use"}
   generalization: source=podklasa, target=nadklasa; realization: source=klasa, target=interfejs;
   dependency: source używa target (opcjonalny stereotype np. use/create);
   aggregation/composition: source=całość (romb przy source); directed: strzałka przy target.
- {"op":"remove_relationship","id":"<id z vpp_list_relationships>"}
- {"op":"move_class","class":"Koszyk","x":400,"y":120}  (przelicza linie relacji tej klasy)
- {"op":"fit_class","class":"Koszyk"}  (dopasowuje rozmiar pudełka do treści)
- {"op":"add_class_diagram","name":"Singleton: po zmianach"}  (nowy, pusty diagram klas, np. fragment do studium wzorca)
- {"op":"add_to_diagram","diagram":"Singleton: po zmianach","classes":["DyspozytorDostaw","Kurier"],
   "relationships":true,"positions":{"Kurier":[400,40]},"columns":3}
   (rysuje ISTNIEJĄCE klasy na tym diagramie jako drugi widok tego samego elementu modelu i, przy relationships=true,
   wszystkie relacje modelu między narysowanymi klasami; bez positions klasy układają się w siatkę)
Typy: int, double, boolean, void, char, long, float, byte, short, nazwy klas z projektu, dowolny tekst (String, LocalDateTime),
generyki np. List<Danie>. Widoczność: + publiczna, - prywatna.
Gdy projekt ma kilka diagramów klas, zmiany bez pola diagram trafiają na ten z największą liczbą klas (główny)."""

# op -> (required fields, optional fields). Unknown fields are an error instead of being silently ignored.
OPS = {
    "add_class": ({"name"}, {"kind", "attributes", "operations", "literals", "static_members", "abstract_operations",
                             "diagram", "x", "y", "stereotypes", "near"}),
    "set_stereotype": ({"class"}, {"stereotypes"}),
    "add_attribute": ({"class", "text"}, {"static"}),
    "add_operation": ({"class", "text"}, {"static", "abstract"}),
    "change_operation": ({"class", "name", "text"}, {"static", "abstract"}),
    "change_attribute": ({"class", "name", "text"}, {"static"}),
    "remove_member": ({"class", "name"}, set()),
    "add_literal": ({"class", "literal"}, set()),
    "add_relationship": ({"kind", "source", "target"}, {"source_multiplicity", "source_role", "target_multiplicity",
                                                        "target_role", "stereotype", "diagram"}),
    "remove_relationship": ({"id"}, set()),
    "move_class": ({"class", "x", "y"}, {"diagram"}),
    "fit_class": ({"class"}, {"diagram"}),
    "add_class_diagram": ({"name"}, {"like"}),
    "add_to_diagram": ({"diagram", "classes"}, {"relationships", "positions", "columns"}),
}


def _apply(ed: Editor, ch: Dict[str, Any]) -> str:
    op = ch.get("op")
    g = ch.get
    if op not in OPS:
        raise VppError(f"Nieznana operacja {op!r}. Dostępne: {', '.join(OPS)}.")
    req, opt = OPS[op]
    unknown = set(ch) - {"op"} - req - opt
    if unknown:
        raise VppError(f"operacja {op}: nieznane pola {sorted(unknown)}. Dozwolone: {sorted(req | opt)}.")
    missing = [k for k in req if ch.get(k) is None]
    if missing:
        raise VppError(f"operacja {op}: brakuje pól {sorted(missing)}.")
    if op == "add_class":
        return ed.add_class(g("name"), g("kind", "class"), g("attributes"), g("operations"), g("literals"),
                            g("static_members"), g("abstract_operations"), g("diagram"), g("x"), g("y"),
                            g("stereotypes"), g("near"))
    if op == "set_stereotype":
        return ed.set_stereotype(g("class"), g("stereotypes"))
    if op == "add_attribute":
        return ed.add_attribute(g("class"), g("text"), bool(g("static", False)))
    if op == "add_operation":
        return ed.add_operation(g("class"), g("text"), bool(g("static", False)), bool(g("abstract", False)))
    if op == "change_operation":
        return ed.change_operation(g("class"), g("name"), g("text"), g("static"), g("abstract"))
    if op == "change_attribute":
        return ed.change_attribute(g("class"), g("name"), g("text"), g("static"))
    if op == "remove_member":
        return ed.remove_member(g("class"), g("name"))
    if op == "add_literal":
        return ed.add_literal(g("class"), g("literal"))
    if op == "add_relationship":
        return ed.add_relationship(g("kind"), g("source"), g("target"), g("source_multiplicity"), g("source_role"),
                                   g("target_multiplicity"), g("target_role"), g("stereotype"), g("diagram"))
    if op == "remove_relationship":
        return ed.remove_relationship(g("id"))
    if op == "move_class":
        return ed.move_class(g("class"), int(g("x")), int(g("y")), g("diagram"))
    if op == "fit_class":
        return ed.fit_class(g("class"), g("diagram"))
    if op == "add_class_diagram":
        return ed.add_class_diagram(g("name"), g("like"))
    if op == "add_to_diagram":
        return ed.add_to_diagram(g("diagram"), g("classes"), bool(g("relationships", True)), g("positions"), g("columns"))
    raise VppError(f"Nieznana operacja {op!r}.")


@mcp.tool(description="Zmiany w modelu klas i na diagramie klas; wynik do NOWEGO pliku (oryginał bez zmian).\n" + CHANGE_DOC)
def vpp_edit_class_model(source_path: str, output_path: str, changes: List[Dict[str, Any]], overwrite_output: bool = False) -> str:
    try:
        def work(ed):
            out = []
            for n, ch in enumerate(changes):
                try:
                    out.append(_apply(ed, ch))
                except VppError as e:
                    raise VppError(f"zmiana nr {n + 1} ({ch.get('op')}): {e}")
                ed.commit()   # keep in-memory state consistent for the next change; tmp file is discarded on error
            return out
        return _write(source_path, output_path, overwrite_output, work)
    except Exception as e:
        return _err(e)


SD_DOC = """Dodaje całe diagramy sekwencji (każdy jako osobny diagram). Każdy diagram:
{"name":"SD13 Reklamacja",
 "participants":[{"actor":"Klient"}, {"name":"klient","class":"Klient"}, {"name":"zamowienie","class":"Zamowienie"},
                 {"name":"","class":"Klient"} /* ':Klient' = wywołanie statyczne */,
                 {"name":"platnosc","class":"Platnosc","created":true} /* tworzony w trakcie */],
 "items":[
   {"type":"call","from":"Klient","to":"klient","operation":"anulujZamowienie(zamowienie)"},
   {"type":"self","on":"zamowienie","operation":"czyMoznaAnulowac()"},
   {"type":"create","from":"zamowienie","to":"platnosc","constructor":"Platnosc(...)" /* opcjonalnie */},
   {"type":"return","from":"zamowienie","to":"klient","label":"true"},
   {"type":"found","to":"dyspozytor","operation":"przydzielKuriera(dostawa)"},
   {"type":"signal","from":"bramka","to":"System płatności","label":"żądanie autoryzacji"},
   {"type":"loop","guard":"dla każdej pozycji","items":[...]},
   {"type":"opt","guard":"status == W_DOSTAWIE","items":[...]},
   {"type":"alt","operands":[{"guard":"można anulować","items":[...]},{"guard":"else","items":[...]}]},
   {"type":"ref","diagram":"SD04 Opłać zamówienie","covers":["Klient","zamowienie"]}  /* tylko wewnątrz loop/opt/alt */
 ]}
Uczestników wskazuje się nazwą aktora albo nazwą obiektu (':Klasa' gdy name puste). Operacja: nazwa(arg1, arg2) — argumenty
to tylko etykiety, liczy się nazwa i liczba argumentów; metoda musi istnieć w klasie odbiorcy lub jej nadklasie/interfejsie.
Zwroty (return) muszą wracać do obiektu, który jest aktywny (wywołał). replace_existing=true najpierw usuwa diagramy o tych nazwach."""


@mcp.tool(description="Dodaje diagramy sekwencji do kopii projektu.\n" + SD_DOC)
def vpp_add_sequence_diagrams(source_path: str, output_path: str, diagrams: List[Dict[str, Any]],
                              replace_existing: bool = False, overwrite_output: bool = False) -> str:
    try:
        def work(ed):
            out = []
            if replace_existing:
                names = {d.name for d in ed.p.dg.values()}
                for spec in diagrams:
                    if spec.get("name") in names:
                        out.append(delete_sequence_diagram(ed, spec["name"]))
                ed.commit()
            out += build_sequence_diagrams(ed, diagrams)
            return out
        return _write(source_path, output_path, overwrite_output, work)
    except Exception as e:
        return _err(e)


@mcp.tool()
def vpp_delete_sequence_diagram(source_path: str, output_path: str, name: str, overwrite_output: bool = False) -> str:
    """Usuwa diagram sekwencji (diagram, jego ramkę, uczestników, komunikaty, fragmenty) w kopii projektu.
    Odmówi, jeśli inny diagram odwołuje się do niego przez ref."""
    try:
        return _write(source_path, output_path, overwrite_output, lambda ed: [delete_sequence_diagram(ed, name)])
    except Exception as e:
        return _err(e)


PATTERN_DOC = "Wzorce kreacyjne jako gotowe zmiany modelu klas (wynik do NOWEGO pliku, oryginał bez zmian).\n" + "\n".join(
    f"- {k}: {v[2]}" for k, v in PATTERNS.items()) + """
Wspólne parametry (params): "diagram" (na którym diagramie rysować nowe klasy; domyślnie główny), "positions" ({"Klasa":[x,y]}),
"stereotypes" (true: role wzorca jako stereotypy klas, domyślnie true), "language" ("pl"/"en", nazwy ról),
"fragment_diagram" (nazwa nowego diagramu klas z samym wzorcem, do studium) i "fragment_context" (dodatkowe klasy na tym diagramie).
Wynik zawiera listę zmian i mapę ról. Żeby pokazać stan 'przed', zrób fragment_diagram w KOPII pliku sprzed wzorca
(diagram jest widokiem modelu, więc w jednym pliku nie da się zachować 'przed' obok 'po')."""


@mcp.tool()
def vpp_list_patterns() -> str:
    """Wzorce, które potrafi zastosować vpp_apply_pattern, z opisem i parametrami."""
    return _json(describe_patterns())


@mcp.tool(description=PATTERN_DOC)
def vpp_apply_pattern(source_path: str, output_path: str, pattern: str, params: Dict[str, Any],
                      overwrite_output: bool = False) -> str:
    try:
        return _write(source_path, output_path, overwrite_output, lambda ed: apply_pattern(ed, pattern, params))
    except Exception as e:
        return _err(e)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
