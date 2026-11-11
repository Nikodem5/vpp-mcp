"""Tests of stereotypes, class diagrams and design patterns on a real project.

    VPP_SAMPLE=path/to/project.vpp python -m pytest tests/test_patterns.py -q

The sample must be a project saved by Visual Paradigm with a class diagram that has classes named like the
student project 'zamawianie jedzenia' (Zamowienie, Klient, Koszyk, Adres, DyspozytorDostaw, PracownikRestauracji,
BramkaPlatnosci, BramkaPlatnosciOnline, Platnosc, PozycjaZamowienia, Dostawa). Without VPP_SAMPLE the tests are skipped.
The file is only read; results go to pytest's tmp_path.
"""
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from vpp_mcp import server as S  # noqa: E402
from vpp_mcp.project import Project  # noqa: E402
from vpp_mcp.verify import verify  # noqa: E402

SAMPLE = os.environ.get("VPP_SAMPLE")
pytestmark = pytest.mark.skipif(not SAMPLE or not os.path.exists(SAMPLE or ""), reason="VPP_SAMPLE not set")


@pytest.fixture
def src(tmp_path):
    p = tmp_path / "src.vpp"
    shutil.copyfile(SAMPLE, p)
    assert verify(str(p)) == []
    return str(p)


def out_of(tmp_path, name="out.vpp"):
    return str(tmp_path / name)


def ok(result: str, out: str):
    assert not result.startswith("BŁĄD"), result
    assert verify(out) == [], verify(out)


def test_unknown_field_is_an_error(src, tmp_path):
    r = S.vpp_edit_class_model(src, out_of(tmp_path), [{"op": "add_class", "name": "X", "stereotyp": "A"}])
    assert r.startswith("BŁĄD") and "nieznane pola" in r


def test_stereotypes_and_fragment_diagram(src, tmp_path):
    out = out_of(tmp_path)
    r = S.vpp_edit_class_model(src, out, [
        {"op": "add_class", "name": "TestA", "kind": "interface", "stereotypes": ["Rola"], "operations": ["+f() : void"], "near": "Zamowienie"},
        {"op": "set_stereotype", "class": "Zamowienie", "stereotypes": ["Produkt"]},
        {"op": "add_class_diagram", "name": "Fragment"},
        {"op": "add_to_diagram", "diagram": "Fragment", "classes": ["Zamowienie", "Klient", "PozycjaZamowienia", "TestA"]},
    ])
    ok(r, out)
    p = Project(out)
    try:
        assert p.user_stereotypes(p.find_class("Zamowienie")) == ["Produkt"]
        assert p.user_stereotypes(p.find_class("TestA")) == ["Rola"]
        frag = p.find_diagram("Fragment")
        names = {p.me[s.model].name for s in p.shapes_on(frag.id) if s.model_type == "Class"}
        assert names == {"Zamowienie", "Klient", "PozycjaZamowienia", "TestA"}
        assert any(s.model_type == "Association" for s in p.shapes_on(frag.id))     # Klient -- Zamowienie
        # the main diagram is still the default one for later edits
        assert S.vpp_edit_class_model(out, out, [{"op": "add_class", "name": "TestB"}], overwrite_output=True).startswith("Zapisano")
    finally:
        p.close()
    # clearing
    r = S.vpp_edit_class_model(out, out, [{"op": "set_stereotype", "class": "Zamowienie", "stereotypes": []}], overwrite_output=True)
    ok(r, out)


def test_singleton(src, tmp_path):
    out = out_of(tmp_path)
    r = S.vpp_apply_pattern(src, out, "singleton", {"class": "DyspozytorDostaw", "drop_parameters": True,
                                                    "fragment_diagram": "Singleton: po", "fragment_context": ["Kurier"]})
    ok(r, out)
    c = json.loads(S.vpp_get_class(out, "DyspozytorDostaw"))
    assert c["stereotypes"] == ["Singleton"]
    assert "-instance : DyspozytorDostaw" in [a["text"] for a in c["attributes"]]
    ops = {o["text"]: o for o in c["operations"]}
    assert "-DyspozytorDostaw()" in ops and ops["+getInstance() : DyspozytorDostaw"]["static"]
    pr = json.loads(S.vpp_get_class(out, "PracownikRestauracji"))
    assert not any("DyspozytorDostaw" in o["text"] and "oznaczJakoGotowe" in o["text"] for o in pr["operations"])
    assert S.vpp_edit_class_model(out, out, [], overwrite_output=True).startswith("Zapisano")


def test_builder(src, tmp_path):
    out = out_of(tmp_path)
    r = S.vpp_apply_pattern(src, out, "builder", {
        "product": "Zamowienie", "builder": "BudowniczyZamowienia", "concrete_builder": "BudowniczyZamowieniaKlienta",
        "director": "KierownikZamowien",
        "steps": ["+dodajPozycjeZKoszyka(koszyk : Koszyk) : void", "+ustawUwagi(uwagi : String) : void"],
        "concrete_constructor": ["klient : Klient", "adres : Adres"],
        "product_constructor": "+Zamowienie(klient : Klient, adresDostawy : Adres)",
        "product_operations": ["+dodajPozycje(pozycja : PozycjaZamowienia) : void"],
        "clients": ["Klient"], "fragment_diagram": "Budowniczy: po", "fragment_context": ["Koszyk", "PozycjaZamowienia", "Adres"]})
    ok(r, out)
    p = Project(out)
    try:
        rel = {x["text"] for x in p.relationships()}
        assert "BudowniczyZamowieniaKlienta ..|> BudowniczyZamowienia" in rel
        assert "BudowniczyZamowieniaKlienta ..> Zamowienie «create»" in rel
        assert "Klient ..> KierownikZamowien «create»" in rel
        assert p.user_stereotypes(p.find_class("KierownikZamowien")) == ["Kierownik"]
        z = p.member_lines(p.find_class("Zamowienie"))["operations"]
        assert any(o["text"] == "+Zamowienie(klient : Klient, adresDostawy : Adres)" and o["constructor"] for o in z)
    finally:
        p.close()


@pytest.mark.parametrize("pattern,params", [
    ("factory_method", {"product": "BramkaPlatnosci", "concrete_products": ["BramkaPlatnosciOnline"],
                        "creator": "FabrykaBramek", "factory_method": "utworzBramke",
                        "concrete_creators": ["FabrykaBramekOnline"]}),
    ("abstract_factory", {"factory": "FabrykaPlatnosci",
                          "products": [{"name": "BramkaPlatnosci", "method": "utworzBramke"}],
                          "families": [{"name": "FabrykaOnline", "products": {"BramkaPlatnosci": "BramkaPlatnosciOnline"}},
                                       {"name": "FabrykaGotowka", "products": {"BramkaPlatnosci": "BramkaGotowka"}}],
                          "clients": ["Zamowienie"]}),
    ("prototype", {"class": "Zamowienie", "clients": ["Klient"]}),
])
def test_other_patterns(src, tmp_path, pattern, params):
    out = out_of(tmp_path)
    r = S.vpp_apply_pattern(src, out, pattern, params)
    ok(r, out)
    assert "Role we wzorcu" in r


def test_pattern_errors(src, tmp_path):
    out = out_of(tmp_path)
    assert "nieznane parametry" in S.vpp_apply_pattern(src, out, "singleton", {"class": "Klient", "zly": 1})
    assert "Nieznany wzorzec" in S.vpp_apply_pattern(src, out, "most", {})
    assert not os.path.exists(out)          # nothing is written on error
    assert "Singleton" in S.vpp_list_patterns()


def test_auto_layout_fragment(src, tmp_path):
    out = out_of(tmp_path)
    r = S.vpp_edit_class_model(src, out, [
        {"op": "add_class_diagram", "name": "Fragment"},
        {"op": "add_to_diagram", "diagram": "Fragment", "classes": ["Klient", "Koszyk", "Zamowienie", "PozycjaZamowienia"]},
        {"op": "auto_layout", "diagram": "Fragment"}])
    ok(r, out)
    assert "Po: nakładania 0, linie_przez_klasy 0, przecięcia_linii 0" in r


def test_auto_route_writes_bends_and_label_rectangles(src, tmp_path):
    out = out_of(tmp_path)
    r = S.vpp_edit_class_model(src, out, [
        {"op": "add_class_diagram", "name": "Fragment"},
        {"op": "add_to_diagram", "diagram": "Fragment", "classes": ["Klient", "Koszyk", "Zamowienie", "PozycjaZamowienia"]},
        {"op": "auto_layout", "diagram": "Fragment", "route": False},
        {"op": "auto_route", "diagram": "Fragment"}])
    ok(r, out)
    assert "ortogonalnie" in r
    p = Project(out)
    try:
        d = p.find_diagram("Fragment", "ClassDiagram")
        conns = [s for s in p.shapes_on(d.id) if s.model_type == "Association"]
        assert conns
        for s in conns:
            assert s.obj.text("connectorStyle") == "0"
            pts = [tuple(int(v) for v in q.split(",")) for q in s.obj.text("_points").strip('"').split(";") if q]
            assert len(pts) >= 2
            assert s.obj.get("multiplicityBRectangle") is not None
    finally:
        p.close()
