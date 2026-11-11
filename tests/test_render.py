"""PNG preview of class diagrams. VPP_SAMPLE=project.vpp python -m pytest tests/test_render.py -q  (skipped without a sample)."""
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
pytest.importorskip("PIL")

from vpp_mcp.render import render_class_diagram  # noqa: E402

SAMPLE = os.environ.get("VPP_SAMPLE")
pytestmark = pytest.mark.skipif(not SAMPLE or not os.path.exists(SAMPLE or ""), reason="VPP_SAMPLE not set")


def test_render_main_diagram(tmp_path):
    src = tmp_path / "s.vpp"
    shutil.copyfile(SAMPLE, src)
    out = tmp_path / "d.png"
    info = render_class_diagram(str(src), None, str(out), scale=0.5)
    assert out.exists() and out.stat().st_size > 1000 and "klas" in info
