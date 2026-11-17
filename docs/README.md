# .vpp file format

🇵🇱 [Wersja polska](README.pl.md)

A description of the format the server is built on. It was produced while manually (by script) completing a real lab project, and was checked against files opened and saved by Visual Paradigm Community Edition 18.1 (build 20260914) and against public VP projects from GitHub (the same `DB_VERSION` 20121026).

| File | Contents |
|---|---|
| [format-class-model.md](format-class-model.md) | SQLite container, DEFINITION syntax, identifiers, classes, attributes, methods, types, relationships, shapes and lines on the class diagram, lists in PROJECT_INFO, checklist. |
| [format-sequence-diagrams.md](format-sequence-diagrams.md) | Sequence diagrams: Frame, lifelines, actors, messages and their numbering, activations, loop/alt/opt fragments, ref, Gate, layout, checklist, template sources. |

The documents are in English and occasionally refer to one-off scripts from the original work (`vpp-edit/`, `vpp-sd/`). These scripts are not in the repository. Their logic lives in `vpp_mcp/` (`edit.py`, `sequence.py`, `verify.py`).

Codes that have not been confirmed (e.g. the visibility values `#` and `~`) are marked as uncertain in the documents. The server does not use them.
