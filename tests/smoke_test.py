"""Smoke test on ANY Visual Paradigm project that has a class diagram.

    python tests/smoke_test.py path\\to\\project.vpp

The input file is only read. Checks:
  1. every DEFINITION row parses and serializes back byte-for-byte,
  2. the verifier accepts the file as VP saved it,
  3. a write through the MCP tool functions (2 classes, a realization, an attribute,
     a sequence diagram) produces a copy that passes the verifier,
  4. reading the result back gives what was written.
The edited copy is written next to the system temp dir and its path is printed:
open it in Visual Paradigm to see the result, then delete it.
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from vpp_mcp import server as S  # noqa: E402
from vpp_mcp.notation import roundtrip_ok  # noqa: E402
from vpp_mcp.verify import verify  # noqa: E402


def main(src):
    c = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    n = bad = 0
    for t in ("MODEL_ELEMENT", "DIAGRAM", "DIAGRAM_ELEMENT"):
        for (d,) in c.execute(f"select DEFINITION from {t}"):
            n += 1
            s = d.decode("utf-8") if isinstance(d, bytes) else d
            bad += not roundtrip_ok(s)
    c.close()
    print(f"1. parser round-trip: {n - bad}/{n}")
    errs = verify(src)
    print("2. verify input:", "OK" if not errs else errs[:5])
    out = os.path.join(tempfile.gettempdir(), "vpp-mcp-smoke-test.vpp")
    if os.path.exists(out):
        os.remove(out)
    r = S.vpp_edit_class_model(src, out, [
        {"op": "add_class", "name": "SmokeTestKsztalt", "kind": "interface", "operations": ["+pole() : double"]},
        {"op": "add_class", "name": "SmokeTestKolo", "kind": "class", "attributes": ["-promien : double"],
         "operations": ["+pole() : double", "+skaluj(k : double) : void"]},
        {"op": "add_relationship", "kind": "realization", "source": "SmokeTestKolo", "target": "SmokeTestKsztalt"},
    ])
    print("3a.", r.splitlines()[0], "|", r.splitlines()[1])
    r = S.vpp_add_sequence_diagrams(out, out, overwrite_output=True, diagrams=[{
        "name": "SmokeTest sekwencja",
        "participants": [{"name": "kolo", "class": "SmokeTestKolo"}],
        "items": [{"type": "found", "to": "kolo", "operation": "skaluj(k)"},
                  {"type": "self", "on": "kolo", "operation": "pole()"}]}])
    print("3b.", r.splitlines()[0], "|", r.splitlines()[1])
    print("4.", S.vpp_get_class(out, "SmokeTestKolo").replace("\n", " ")[:200])
    print("   ", S.vpp_get_sequence_diagram(out, "SmokeTest sekwencja").replace("\n", " ")[:200])
    ok = not bad and not errs and "BŁĄD" not in r
    print("\nWYNIK:", "OK" if ok else "PROBLEM", "\nKopia do obejrzenia w VP:", out)
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
