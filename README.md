# vpp-mcp: Claude + Visual Paradigm

Serwer [MCP](https://modelcontextprotocol.io), dzięki któremu Claude potrafi **czytać i edytować projekty Visual Paradigm (`.vpp`)**: diagram klas (klasy, interfejsy, enumeracje, atrybuty, metody, relacje) i diagramy sekwencji. Nie trzeba przy tym otwierać programu.

Powstał przy przedmiocie *Wzorce projektowe* (AGH), gdzie wszystkie diagramy robi się w Visual Paradigm Community Edition. Przydaje się przy uzupełnianiu diagramu klas, rysowaniu kilkunastu diagramów sekwencji i przy studiach wzorców, czyli zmianach w diagramie klas „przed” i „po”.

> Nieoficjalne narzędzie, niezwiązane z firmą Visual Paradigm. Format plików został odczytany z prawdziwych projektów i przetestowany na **Visual Paradigm Community Edition 18.1 (build 20260914)**. Serwer nigdy nie zmienia twojego pliku. Zawsze zapisuje zmienioną **kopię**, ale i tak trzymaj własną kopię zapasową.

*English: an unofficial MCP server that lets Claude read and edit Visual Paradigm `.vpp` projects (class model, class diagram, sequence diagrams). It always writes an edited copy and verifies it before saving. Docs are in Polish; tool descriptions mix Polish and English.*

## Co można z nim zrobić

Przykładowe polecenia dla Claude'a:

- „Pokaż, jakie klasy i relacje są w `C:\...\projekt.vpp`.”
- „Dodaj do diagramu klas wzorzec Singleton dla klasy `KatalogRestauracji` i zapisz jako `projekt-singleton.vpp`.”
- „Zrób diagram sekwencji dla przypadku użycia *Złóż zamówienie* na podstawie metod z diagramu klas.”
- „Wyeksportuj klasy `Zamowienie`, `Platnosc` i `BramkaPlatnosci` do PlantUML, potrzebuję fragmentu do studium.”

| Narzędzie | Co robi |
|---|---|
| `vpp_project_info` | Podsumowanie projektu: diagramy, liczba klas, aktorzy, przypadki użycia, czy plik jest otwarty w VP. |
| `vpp_list_classes`, `vpp_get_class` | Klasy z atrybutami i metodami w notacji UML, relacje danej klasy, położenie na diagramie. |
| `vpp_list_relationships` | Generalizacje, realizacje, zależności i asocjacje z licznościami i rolami. |
| `vpp_get_sequence_diagram` | Uczestnicy, komunikaty z numerami jak w VP (1, 1.1, …), fragmenty loop/alt/opt z warunkami. |
| `vpp_export_plantuml` | Fragment diagramu klas jako PlantUML. |
| `vpp_edit_class_model` | Partia zmian w diagramie klas: nowe klasy, interfejsy, enumeracje i klasy abstrakcyjne (z kształtem na diagramie), atrybuty i metody (także `static`, `abstract`, `List<...>`), zmiana i usuwanie składowych, wartości enumeracji, relacje każdego rodzaju, usuwanie relacji, przesuwanie i dopasowanie rozmiaru klas. |
| `vpp_add_sequence_diagrams` | Całe diagramy sekwencji z opisu: aktorzy, obiekty (także tworzone w trakcie i wywołania statyczne), call, self, create, return, found, sygnał, fragmenty loop/opt/alt, `ref`. Komunikaty są przypięte do metod z diagramu klas. |
| `vpp_delete_sequence_diagram` | Usuwa diagram sekwencji, np. żeby wygenerować go od nowa. |
| `vpp_verify` | Kontrola struktury pliku. |

## Bezpieczeństwo

- Każda zmiana trafia do nowego pliku (`output_path`). Oryginał zostaje nietknięty.
- Zmiany są wykonywane na pliku tymczasowym. Wynik powstaje tylko wtedy, gdy **wszystkie** zmiany się udały i weryfikator nie znalazł błędu.
- Serwer nie zapisze do pliku, który jest otwarty w VP. VP trzyma wtedy obok plik `.<nazwa>.vpp.lck`.
- Nie da się usunąć metody, którą wywołuje komunikat na diagramie sekwencji.
- **Po każdej zmianie otwórz plik w VP i od razu go zapisz (Ctrl+S).** VP przepisze go wtedy po swojemu.

## Instalacja

Potrzebujesz:
- Pythona 3.10 lub nowszego (na Windows z [python.org](https://www.python.org/downloads/), z zaznaczonym „Add python.exe to PATH”),
- aplikacji Claude na komputer (Claude Desktop) albo Claude Code.

### 1. Zainstaluj serwer

```
python -m pip install git+https://github.com/Nikodem5/vpp-mcp
```

Sprawdzenie: `python -c "import vpp_mcp.server"` nie powinno wypisać żadnego błędu.

### 2a. Dodaj do Claude Desktop

W aplikacji Claude otwórz **Settings → Developer → Edit Config**. Otworzy się plik `claude_desktop_config.json` (na Windows w `%APPDATA%\Claude\`). Dopisz serwer w sekcji `mcpServers`:

```json
{
  "mcpServers": {
    "visual-paradigm": {
      "command": "python",
      "args": ["-m", "vpp_mcp"]
    }
  }
}
```

Jeśli masz już inne serwery, dopisz sam wpis `"visual-paradigm": {...}` obok nich i pilnuj przecinków. Potem **zamknij i uruchom ponownie aplikację Claude**. Serwer pojawi się na liście narzędzi.

Jeśli Claude nie widzi serwera, zamiast `"python"` wpisz pełną ścieżkę do Pythona, np. `"C:\\Users\\TWOJA_NAZWA\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"`. Ścieżkę pokaże polecenie `where python`. Na macOS użyj `python3`.

### 2b. Albo dodaj do Claude Code

```
claude mcp add visual-paradigm -- python -m vpp_mcp
```

### Aktualizacja

```
python -m pip install --upgrade --force-reinstall git+https://github.com/Nikodem5/vpp-mcp
```

Potem uruchom ponownie aplikację Claude.

## Jak z tym pracować

1. Zapisz projekt w VP i najlepiej go zamknij.
2. Poproś Claude'a o zmianę i podaj pełną ścieżkę do pliku `.vpp`. Claude zapisze wynik pod nową nazwą, np. `projekt-v2.vpp`.
3. Otwórz nowy plik w VP, sprawdź i od razu zapisz (Ctrl+S).
4. Uporządkuj linie relacji i ewentualnie podpisy komunikatów. Serwer rysuje proste linie od krawędzi do krawędzi, a układ jest przybliżony.

Komunikaty na diagramach sekwencji muszą wskazywać metody, które istnieją w klasie odbiorcy, jej nadklasie albo interfejsie. Dopasowanie idzie po nazwie i liczbie argumentów. Jeśli metody brakuje, Claude dodaje ją najpierw do diagramu klas, co jest zgodne z wymaganiem spójności diagramu klas i diagramów sekwencji.

## Ograniczenia

- Obsługiwana jest widoczność `+` (publiczna) i `-` (prywatna). Kody VP dla `#` i `~` nie zostały potwierdzone.
- Aktorzy na diagramach sekwencji są osobnymi elementami o tych samych nazwach co na diagramie przypadków użycia. Tak samo wygląda to w przykładowych projektach VP.
- Brak edycji diagramów przypadków użycia, czynności i stanów. Serwer je tylko wymienia.
- Projekt z kilkoma diagramami klas wymaga podania nazwy diagramu przy dodawaniu klas i relacji.
- Testowane na projektach zapisanych przez VP Community Edition 18.1. Inne wersje mają ten sam format bazy (`DB_VERSION` 20121026), ale nie były sprawdzane w programie.

## Test na własnym projekcie

```
git clone https://github.com/Nikodem5/vpp-mcp
cd vpp-mcp
python -m pip install -e .
python tests/smoke_test.py "C:\ścieżka\do\projektu.vpp"
```

Test tylko czyta twój plik. Sprawdza parser i weryfikator, a potem tworzy w katalogu tymczasowym kopię z dwiema przykładowymi klasami i małym diagramem sekwencji. Ścieżkę do kopii wypisuje na końcu, żebyś mógł ją obejrzeć w VP.

## Budowa

| Plik | Rola |
|---|---|
| `vpp_mcp/notation.py` | Parser i serializer tekstowego formatu, w którym VP zapisuje model. Odtwarza bajt w bajt każdą definicję z plików zapisanych przez VP. |
| `vpp_mcp/project.py` | Odczyt: klasy, składowe, typy, relacje, diagramy. |
| `vpp_mcp/edit.py` | Zapis modelu klas i diagramu klas. |
| `vpp_mcp/sequence.py` | Diagramy sekwencji: generator, usuwanie, opis. |
| `vpp_mcp/verify.py` | Weryfikator struktury: odwołania, unikalność ID, powiązania model–widok, listy, kanoniczny zapis. |
| `vpp_mcp/server.py` | Serwer MCP (FastMCP, stdio). |
| `docs/` | Opis formatu `.vpp`, na którym opiera się serwer. |

Plik `.vpp` to baza SQLite, w której VP zapisuje elementy modelu i diagramów we własnej notacji tekstowej. Szczegóły są w [docs/](docs/).

## Licencja

MIT, zobacz [LICENSE](LICENSE).
