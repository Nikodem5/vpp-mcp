import pytest
from vpp_mcp.notation import parse, dump, Lst, Raw


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
