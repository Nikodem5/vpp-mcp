from vpp_mcp.project import ref_id


def test_ref_id_forms():
    assert ref_id("abc") == "abc"
    assert ref_id("<abc>") == "abc"
    assert ref_id("<m:abc>") == "abc"
    assert ref_id("<d:f:abc>") == "abc"
    assert ref_id("<m:cls$op1>") == "cls"
    assert ref_id("<cls$op1>") == "cls"


def test_ref_id_quoted_string():
    assert ref_id('"abc"') == "abc"
    assert ref_id('"_9lm.x_"') == "_9lm.x_"


def test_ref_in_frame():
    from vpp_mcp.project import ref_in_frame
    assert ref_in_frame("<F:LL>", "F")
    assert ref_in_frame("<M:F:LL>", "F")
    assert not ref_in_frame("<F2:LL>", "F")
    assert not ref_in_frame("<M:F2:F>", "F")
    assert not ref_in_frame("<F>", "F")


def test_subdiagrams_roundtrip_quoted_and_empty():
    from vpp_mcp.notation import parse, dump, Lst, Raw
    from vpp_mcp.project import ref_id
    s = 'M1:"X":Model {\n\t_subDiagrams=(\n\t\t"D1", \n\t\t"D2"\n\t);\n}'
    o = parse(s)
    assert dump(o) == s
    sd = o.get("_subDiagrams")
    sd.items = [i for i in sd.items if ref_id(i.text) != "D1"]
    assert 'D1' not in dump(o) and '"D2"' in dump(o)
    sd.items = []
    assert dump(o) == 'M1:"X":Model {\n\t_subDiagrams=();\n}'
