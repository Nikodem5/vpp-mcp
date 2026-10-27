# Format plików .vpp

Opis formatu, na którym opiera się serwer. Powstał przy ręcznym (skryptowym) uzupełnianiu prawdziwego projektu z laboratorium i był sprawdzany na plikach otwieranych i zapisywanych przez Visual Paradigm Community Edition 18.1 (build 20260914) oraz na publicznych projektach VP z GitHuba (ten sam `DB_VERSION` 20121026).

| Plik | Zawartość |
|---|---|
| [format-class-model.md](format-class-model.md) | Kontener SQLite, składnia DEFINITION, identyfikatory, klasy, atrybuty, metody, typy, relacje, kształty i linie na diagramie klas, listy w PROJECT_INFO, lista kontrolna. |
| [format-sequence-diagrams.md](format-sequence-diagrams.md) | Diagramy sekwencji: Frame, lifeline'y, aktorzy, komunikaty i ich numeracja, aktywacje, fragmenty loop/alt/opt, ref, Gate, układ, lista kontrolna, źródła wzorów. |

Dokumenty są po angielsku i odnoszą się miejscami do jednorazowych skryptów z pierwotnej pracy (`vpp-edit/`, `vpp-sd/`). Tych skryptów nie ma w repozytorium. Ich logika jest w `vpp_mcp/` (`edit.py`, `sequence.py`, `verify.py`).

Kody, które nie zostały potwierdzone (np. widoczność `#` i `~`), są w dokumentach oznaczone jako niepewne. Serwer ich nie używa.
