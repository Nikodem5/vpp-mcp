"""New diagrams inside Model folders (Model Explorer): PARENT_MODEL_ID, parentModel, _subDiagrams.

The first group needs no sample; the second uses VPP_SAMPLE (any VP project with a class diagram) and is skipped without it.
"""
import os
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from vpp_mcp import server as S  # noqa: E402
from vpp_mcp.edit import Editor  # noqa: E402
from vpp_mcp.notation import Lst, Raw  # noqa: E402
from vpp_mcp.project import Project, Row, VppError  # noqa: E402
from vpp_mcp.notation import parse  # noqa: E402
from vpp_mcp.verify import verify  # noqa: E402

ROOT = 'rootModelElements:"rootModelElements":rootModelElements {\n\tChild=(\n\t\t<r1>\n\t);\n}'
DIAGS = 'rootDiagrams:"rootDiagrams":rootDiagrams {\n\tChild=(\n\t\t<d1>\n\t);\n}'
DG = ('d1:"CD":ClassDiagram {\n\tpmCreateDateTime="1";\n\tdiagramPreviewData_id="p1";\n\tChild=NULL;\n}')


@pytest.fixture
def ed(tmp_path):
    f = str(tmp_path / "mini.vpp")
    c = sqlite3.connect(f)
    c.executescript("""
create table MODEL_ELEMENT (ID, USER_ID, USER_ID_PARENT, MODEL_TYPE, PARENT_ID, NAME, DEFINITION, MIRROR_SOURCE, AUTHOR, CREATE_AT, LAST_MOD_AT);
create table DIAGRAM (ID, DIAGRAM_TYPE, PARENT_MODEL_ID, NAME, DEFINITION);
create table DIAGRAM_ELEMENT (ID, SHAPE_TYPE, DIAGRAM_ID, MODEL_ELEMENT_ID, COMPOSITE_MODEL_ELEMENT_ADDRESS, REF_MODEL_ELEMENT_ADDRESS, PARENT_ID, DEFINITION);
create table PROJECT_INFO (ID, NAME, DB_VERSION, PROJECT_VERSION, PROJECT_PATCH_NO, PROJECT_BUILD, TEAMWORK, DEFINITION, ROOT_MODEL_ELEMENTS_DEFINITION, DIAGRAMS_DEFINITION);""")
    c.execute("insert into MODEL_ELEMENT (ID, MODEL_TYPE, NAME, DEFINITION) values ('r1','Class','K',?)",
              ('r1:"K":Class {\n\tpmAuthor="me";\n}',))
    c.execute("insert into DIAGRAM values ('d1','ClassDiagram',NULL,'CD',?)", (DG,))
    c.execute("insert into PROJECT_INFO (DB_VERSION, PROJECT_BUILD, ROOT_MODEL_ELEMENTS_DEFINITION, DIAGRAMS_DEFINITION) values ('1','b',?,?)",
              (ROOT, DIAGS))
    c.commit()
    c.close()
    e = Editor(f, author="me", seed=1)
    yield e
    e.close()


def test_folder_created_at_top_level_and_reused(ed):
    a = ed.resolve_folder("Diagramy")
    assert a.model_type == "Model" and a.parent is None
    assert "Diagramy" not in ed.p.root_list.get("Child").items       # refs, not names
    assert any(x.text == f"<{a.id}>" for x in ed.p.root_list.get("Child").items)
    assert ed.resolve_folder("Diagramy") is a
    with pytest.raises(VppError):
        ed.resolve_folder("  ")


def test_nested_path_and_ambiguity(ed):
    leaf = ed.resolve_folder("A/B")
    top = ed.p.me[leaf.parent]
    assert top.name == "A" and top.parent is None
    assert [x.text for x in top.obj.get("Child").items] == [f"<{top.id}:{leaf.id}>"]
    assert ed.resolve_folder("B") is leaf                       # a unique name is found anywhere
    other = ed.resolve_folder("C/B")
    assert other.id != leaf.id
    with pytest.raises(VppError) as e:
        ed.resolve_folder("B")
    assert "niejednoznaczny" in str(e.value)
    assert ed.resolve_folder("C/B") is other


def test_place_diagram_and_commit(ed):
    r = ed.add_class_diagram("W folderze", folder="Moje/Diagramy")
    assert "w folderze" in r
    ed.commit()
    p = Project(ed.p.path)
    try:
        d = p.find_diagram("W folderze")
        assert d.parent and p.me[d.parent].name == "Diagramy"
        fo = p.me[d.parent]
        assert [it.text for it in fo.obj.get("_subDiagrams").items] == [f'"{d.id}"']
        assert fo.obj.entries[0][0] == "_subDiagrams"
        assert d.obj.get("parentModel").text == f"<{fo.parent}:{fo.id}>"
        assert p.find_diagram("CD").parent is None
        con = sqlite3.connect(p.path)
        assert con.execute("select PARENT_MODEL_ID from DIAGRAM where ID=?", (d.id,)).fetchone()[0] == fo.id
        con.close()
    finally:
        p.close()


def test_class_diagram_copy_does_not_inherit_folder(ed):
    ed.add_class_diagram("A", folder="F")
    ed.add_class_diagram("B", like="A")
    b = ed.p.find_diagram("B")
    assert b.parent is None and not b.obj.has("parentModel")


# ---------------------------------------------------------------- real project
SAMPLE = os.environ.get("VPP_SAMPLE")
real = pytest.mark.skipif(not SAMPLE or not os.path.exists(SAMPLE or ""), reason="VPP_SAMPLE not set")

SD = {"name": "SD folder test", "folder": "Folder testowy",
      "participants": [{"actor": "TesterFolderow"}, {"name": "a", "class": "FolderA"}],
      "items": [{"type": "call", "from": "TesterFolderow", "to": "a", "operation": "go()"},
                {"type": "return", "from": "a", "to": "TesterFolderow", "label": "ok"}]}


@real
def test_diagrams_in_folder_on_real_project(tmp_path):
    src, o1, o2, o3, o4 = (str(tmp_path / n) for n in ("src.vpp", "1.vpp", "2.vpp", "3.vpp", "4.vpp"))
    shutil.copyfile(SAMPLE, src)
    for r in (S.vpp_edit_class_model(src, o1, [
            {"op": "add_class", "name": "FolderA", "operations": ["+go() : void"]},
            {"op": "add_class", "name": "FolderS"},
            {"op": "add_class_diagram", "name": "CD folder test", "folder": "Folder testowy"},
            {"op": "add_to_diagram", "diagram": "CD folder test", "classes": ["FolderA"]}]),
              S.vpp_add_sequence_diagrams(o1, o2, [SD]),
              S.vpp_apply_pattern(o2, o3, "singleton", {"class": "FolderS", "fragment_diagram": "Singleton folder test",
                                                         "fragment_folder": "Folder testowy"})):
        assert not r.startswith("BŁĄD"), r
    assert verify(o3) == [] or verify(o3) == verify(src)
    p = Project(o3)
    try:
        folders = [m for m in p.by_type("Model") if m.name == "Folder testowy"]
        assert len(folders) == 1
        fo = folders[0]
        names = {p.dg[x.text.strip('"')].name for x in fo.obj.get("_subDiagrams").items}
        assert names == {"CD folder test", "SD folder test", "Singleton folder test"}
        assert all(p.dg[i].parent == fo.id for i in (x.text.strip('"') for x in fo.obj.get("_subDiagrams").items))
        sd = p.find_diagram("SD folder test")
        frame = p.me[sd.obj.get("_rootFrame").text.strip("<>").split(":")[-1]]
        assert frame.parent == fo.id
    finally:
        p.close()
    assert not S.vpp_get_sequence_diagram(o3, "SD folder test").startswith("BŁĄD")
    r = S.vpp_delete_sequence_diagram(o3, o4, "SD folder test")
    assert not r.startswith("BŁĄD"), r
    p = Project(o4)
    try:
        fo = [m for m in p.by_type("Model") if m.name == "Folder testowy"][0]
        assert len(fo.obj.get("_subDiagrams").items) == 2
        assert not any("SD folder test" in (d.name or "") for d in p.dg.values())
    finally:
        p.close()
