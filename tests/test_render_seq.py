"""Smoke test of the sequence diagram renderer.

    VPP_SAMPLE=path/to/project.vpp python -m pytest tests/test_render_seq.py -q

The sample must contain the diagrams 'SD03 Złóż zamówienie' and 'SD13 Wzorzec Budowniczy - składanie zamówienia'.
Without VPP_SAMPLE the tests are skipped. The file is only read.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from vpp_mcp.project import VppError  # noqa: E402
from vpp_mcp.render_seq import render_sequence_diagram  # noqa: E402

SAMPLE = os.environ.get("VPP_SAMPLE")
pytestmark = pytest.mark.skipif(not SAMPLE or not os.path.exists(SAMPLE or ""), reason="VPP_SAMPLE not set")

DIAGRAMS = ["SD03 Złóż zamówienie", "SD13 Wzorzec Budowniczy - składanie zamówienia"]


@pytest.mark.parametrize("name", DIAGRAMS)
def test_render_sequence_png(name, tmp_path):
    from PIL import Image
    out = str(tmp_path / "sd.png")
    info = render_sequence_diagram(SAMPLE, name, out, scale=0.6)
    assert os.path.exists(out) and os.path.getsize(out) > 1000
    assert name in info
    with Image.open(out) as im:
        assert im.width > 200 and im.height > 200


def test_vp_like_children_and_errors(tmp_path):
    out = str(tmp_path / "sd.png")
    render_sequence_diagram(SAMPLE, DIAGRAMS[0], out, scale=0.5, vp_like_children=True)
    assert os.path.exists(out)
    with pytest.raises(VppError):
        render_sequence_diagram(SAMPLE, DIAGRAMS[0], out, scale=5000)
    with pytest.raises(VppError):
        render_sequence_diagram(SAMPLE, "nie ma takiego diagramu", out)
