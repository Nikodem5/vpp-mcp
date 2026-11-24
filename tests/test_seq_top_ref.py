"""A ref (Interaction Use) directly in the frame, outside any fragment. The first test needs no VPP_SAMPLE; the second
runs end to end on a scratch copy of a project that has the diagrams 'SD03 Złóż zamówienie' and 'SD04 Opłać zamówienie'
(VPP_SAMPLE=path/to/project.vpp)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import vpp_mcp.sequence as seq  # noqa: E402
from vpp_mcp.sequence import SD, convert_spec  # noqa: E402


class StubModel:
    def class_id(self, name):
        return 'c_' + name

    def resolve(self, cls_id, text):
        return cls_id, 'op', text


class StubEd:
    n = 0

    def new_id(self):
        StubEd.n += 1
        return 'id%d' % StubEd.n

    def ts(self):
        return 0


def _spec(items):
    return {"name": "T7", "participants": [{"actor": "Klient"}, {"name": "zamowienie", "class": "Zamowienie"}], "items": items}


REF = {"type": "ref", "diagram": "Inny", "covers": ["Klient", "zamowienie"]}


def test_top_level_ref_model_and_shape(monkeypatch):
    monkeypatch.setattr(seq, '_ED', StubEd())
    items = [REF, {"type": "opt", "guard": "g", "items": [REF]}, {"type": "call", "from": "Klient", "to": "zamowienie", "operation": "f()"}]
    sd = SD(StubModel(), convert_spec(_spec(items)), {"T7": "frame", "Inny": "frame2"}, "mc")
    sd.run()
    sd.layout()
    me_rows, de_rows, _, _ = sd.build(None)
    top, inner = sd.occs
    assert top['operand'] is None and inner['operand'] is not None
    assert top['top'] < sd.frags[0]['top'] < inner['top']
    assert top['w'] > inner['w']                                    # no operand padding at the top level
    me = {r[0]: r for r in me_rows}
    assert me[top['id']][2] == sd.frame and me[inner['id']][2] == inner['operand']['id']
    assert '<%s:%s>' % (sd.frame, top['id']) in me[sd.frame][4]      # listed in the frame's Child
    assert inner['id'] not in me[sd.frame][4]
    shape = next(r[5] for r in de_rows if r[0] == top['de'])
    assert 'metaModelElement=<%s:%s>;' % (sd.frame, top['id']) in shape and '_parent' not in shape


SAMPLE = os.environ.get("VPP_SAMPLE")


@pytest.mark.skipif(not SAMPLE or not os.path.exists(SAMPLE or ""), reason="VPP_SAMPLE not set")
def test_top_level_ref_end_to_end(tmp_path):
    from vpp_mcp import server
    from vpp_mcp.project import Project
    from vpp_mcp.sequence import describe_sequence_diagram
    from vpp_mcp.verify import verify
    spec = {"name": "T7 ref na starcie", "participants": [{"actor": "Klient"}, {"name": "zamowienie", "class": "Zamowienie"}],
            "items": [{"type": "ref", "diagram": "SD04 Opłać zamówienie", "covers": ["Klient", "zamowienie"]},
                      {"type": "opt", "guard": "g", "items": [{"type": "ref", "diagram": "SD03 Złóż zamówienie",
                                                              "covers": ["Klient", "zamowienie"]}]}]}
    out, out2 = str(tmp_path / "o.vpp"), str(tmp_path / "o2.vpp")
    res = server.vpp_add_sequence_diagrams(SAMPLE, out, [spec])
    assert "2 ref" in res and not res.startswith("BŁĄD")
    assert verify(out) == []
    d = describe_sequence_diagram(Project(out), spec["name"])
    assert d["refs"] == ["SD03 Złóż zamówienie (operand)", "SD04 Opłać zamówienie (frame)"]
    server.vpp_delete_sequence_diagram(out, out2, spec["name"])
    assert verify(out2) == []
