import os
import pytest
from vpp_mcp import server
from vpp_mcp.project import VppError


class _Ed:
    def __init__(self, path):
        pass

    def commit(self):
        pass

    def close(self):
        pass


def _run(tmp_path, monkeypatch, src_errs, tmp_errs):
    src = tmp_path / "a.vpp"
    src.write_bytes(b"x")
    out = tmp_path / "b.vpp"
    monkeypatch.setattr(server, "Editor", _Ed)
    monkeypatch.setattr(server, "is_open_in_vp", lambda p: False)
    monkeypatch.setattr(server, "verify",
                        lambda p, max_errors=50: list(tmp_errs if p.endswith(".mcp-tmp") else src_errs))
    res = server._write(str(src), str(out), False, lambda ed: ["ok"])
    return res, out


def test_preexisting_problems_ignored(tmp_path, monkeypatch):
    res, out = _run(tmp_path, monkeypatch, ["A"], ["A"])
    assert out.exists() and "1 problem" in res


def test_new_problem_blocks(tmp_path, monkeypatch):
    with pytest.raises(VppError) as e:
        _run(tmp_path, monkeypatch, ["A"], ["A", "B"])
    assert "B" in str(e.value) and "- A" not in str(e.value)
    assert not (tmp_path / "b.vpp").exists()
    assert not os.path.exists(str(tmp_path / "b.vpp.mcp-tmp"))


def test_duplicate_message_is_new_problem(tmp_path, monkeypatch):
    with pytest.raises(VppError):
        _run(tmp_path, monkeypatch, ["A"], ["A", "A"])
