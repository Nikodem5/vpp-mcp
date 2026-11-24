import pytest
from vpp_mcp.notation import parse, dump, Lst, Raw, roundtrip_ok


@pytest.mark.parametrize("s", [
    'X:"a":Class {\n\tF=();\n}',
    'X:"a":Class {\n\tF=(\n\t);\n}',
    'X:"a":Class {\n\tF=(\n\t\t{Y:"b":Class {\n\t\t\tG=(\n\t\t\t);\n\t\t\tH=();\n\t\t}}\n\t);\n}',
    'X:"a":Class {\n\tF=(\n\t\t1, \n\t\t2\n\t);\n}',
])
def test_roundtrip(s):
    assert dump(parse(s)) == s


def test_nl_empty_with_items_dumps_normally():
    o = parse('X:"a":Class {\n\tF=(\n\t);\n}')
    lst = o.entries[0][1]
    assert isinstance(lst, Lst) and lst.nl_empty
    lst.items.append(Raw("1"))
    assert dump(o) == 'X:"a":Class {\n\tF=(\n\t\t1\n\t);\n}'


CRLF_CASES = [
    'X:"a":Class {\r\n\tF=();\r\n}',
    'X:"a":Class {\r\n\tF=(\r\n\t);\r\n}',
    'X:"a":Class {\r\n\tF=(\r\n\t\t{Y:"b":Class {\r\n\t\t\tG=(\r\n\t\t\t);\r\n\t\t}}, \r\n\t\t2\r\n\t);\r\n}',
    'X:"a":Class {\r\n\tdoc="line1\r\nline2";\r\n}',
]


@pytest.mark.parametrize("s", CRLF_CASES)
def test_crlf_roundtrip(s):
    o = parse(s)
    assert o.crlf and dump(o) == s and roundtrip_ok(s)


def test_crlf_parses_same_tree_as_lf():
    s = CRLF_CASES[2]
    assert parse(s).entries == parse(s.replace("\r\n", "\n")).entries


def test_crlf_edit_keeps_convention():
    o = parse(CRLF_CASES[0])
    o.set("G", Raw("1"))
    assert dump(o) == 'X:"a":Class {\r\n\tF=();\r\n\tG=1;\r\n}'


def test_lf_stays_lf_and_mixed_not_roundtrip():
    assert not parse(CRLF_CASES[0].replace("\r\n", "\n")).crlf
    assert not roundtrip_ok('X:"a":Class {\r\n\tF=();\n}')
