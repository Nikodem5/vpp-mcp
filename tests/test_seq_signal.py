"""An actor's signal in the middle of a call must not close open activations (no VPP_SAMPLE needed)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import vpp_mcp.sequence as seq  # noqa: E402
from vpp_mcp.sequence import SD, convert_spec  # noqa: E402


class StubModel:
    def class_id(self, name):
        return 'c_' + name

    def resolve(self, cls_id, text):
        return cls_id, 'op', text


SPEC = {"name": "T6", "participants": [{"actor": "Kierowca"}, {"name": "automat", "class": "AutomatPlatniczy"},
                                      {"name": "platnosc", "class": "PlatnoscKarta", "created": True},
                                      {"actor": "System płatności"}],
        "items": [{"type": "call", "from": "Kierowca", "to": "automat", "operation": "przyjmijOplate(bilet)"},
                  {"type": "create", "from": "automat", "to": "platnosc"},
                  {"type": "call", "from": "automat", "to": "platnosc", "operation": "zrealizuj(kwota)"},
                  {"type": "signal", "from": "platnosc", "to": "System płatności", "label": "autoryzuj(kwota)"},
                  {"type": "signal", "from": "System płatności", "to": "platnosc", "label": "potwierdzenie"},
                  {"type": "return", "from": "platnosc", "to": "automat", "label": "true"},
                  {"type": "return", "from": "automat", "to": "Kierowca", "label": "ok"}]}


class StubEd:
    n = 0

    def new_id(self):
        StubEd.n += 1
        return 'id%d' % StubEd.n

    def ts(self):
        return '0'


def test_actor_signal_keeps_activations(monkeypatch):
    monkeypatch.setattr(seq, '_ED', StubEd())
    sd = SD(StubModel(), convert_spec(SPEC), {"T6": "frame"}, "mc")
    sd.run()
    kinds = [m['kind'] for m in sd.msgs]
    assert kinds == ['call', 'create', 'call', 'sig', 'sig', 'ret', 'ret']
    assert sd.msgs[4]['fa'] is None and sd.msgs[5]['fa'] is not None
