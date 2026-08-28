# QualiAgent — specyfikacja implementacyjna

Jesteś moim partnerem inżynierskim przy budowie tego projektu. Pracujemy razem: ja podejmuję decyzje projektowe i przeglądam kod, ty piszesz implementację i pytasz, gdy specyfikacja jest niejednoznaczna.

## Zasady współpracy

- **Nie pisz całej aplikacji naraz.** Realizujemy etap po etapie, w kolejności z sekcji „Plan realizacji". Po każdym etapie zatrzymaj się i pokaż, co powstało.
- **Gdy specyfikacja jest niejednoznaczna, zapytaj** zamiast zgadywać. Lepiej jedno pytanie niż sto linii do wyrzucenia.
- **Nie dodawaj funkcji, których tu nie ma.** Zakres jest celowo wąski.
- **Każdy moduł ma być testowalny osobno.** Logika grafu i ingestu nie może zależeć od FastAPI ani od Next.js.
- **Piszemy w Pythonie 3.14**, z type hintami i Pydantic v2. Menedżer pakietów: **uv** (nie Poetry). Formatowanie: ruff. Typowanie: mypy.
- Jeśli uznasz, że któraś decyzja projektowa poniżej jest zła — powiedz to i uzasadnij, zanim zaczniesz kodować.

---

## Kontekst — po co to jest

Narzędzie do analizy materiału z badań jakościowych.
Badacz wrzuca transkrypcje wywiadów, PDF-y, DOCX i TXT z jednego badania, podaje pytanie badawcze, dostaje rozdział raportu z cytatami zakotwiczonymi w materiale źródłowym.

Kluczowa różnica wobec zwykłego RAG-a: to nie jest odpowiadanie na pytania. Trzeba przejrzeć cały korpus pod kątem pytania badawczego, **ocenić, czy materiał w ogóle wystarcza do rzetelnej odpowiedzi**, i napisać spójny tekst, w którym każde twierdzenie oparte na cytacie da się cofnąć do konkretnej wypowiedzi respondenta.

Halucynacja cytatu dyskwalifikuje takie narzędzie całkowicie. Weryfikacja cytatów musi być deterministyczna, nie oparta na LLM-ie.

**Cytaty są wyłącznie dosłowne.** Marker wolno wstawić tylko przy fragmencie, który jest podciągiem chunka po normalizacji białych znaków i cudzysłowów. Parfraza w tekście bieżącym jest dozwolona, ale **nie dostaje markera**.

---

## Stos technologiczny

| Warstwa      | Wybór                                                         |
| ------------ | ------------------------------------------------------------- |
| Pakiety      | uv                                                            |
| ORM          | SQLAlchemy 2.x + Alembic                                      |
| Orkiestracja | LangGraph (StateGraph, checkpointer w Postgresie)             |
| LLM          | Claude Sonnet przez `anthropic` SDK                           |
| Transkrypcja | Gemini API (`google-genai`)                                   |
| Baza         | PostgreSQL 16 + pgvector                                      |
| API          | FastAPI                                                       |
| Embeddingi   | Voyage AI (`voyage-3`), wymiar 1024                           |
| Web search   | Anthropic web search tool (węzeł od Etapu 6)                  |
| UI           | Next.js (App Router) + React                                  |
| Dokumenty    | pdfminer.six, python-docx (odczyt), python-docx (zapis raportu) |

Nie ma Streamlita. UI od Etapu 3 jest w Next.js.

---

## Struktura projektu

Backend jest pakietem FastAPI. Routers żyją pod `api/`, nie na górze pakietu. Źródłem schematu SQL jest Alembic, nie ręczny DDL w `database.py`.

```
qualiagent/
├── frontend/                         # Next.js (App Router)
│   ├── app/
│   ├── components/
│   ├── lib/                          # wyłącznie klient HTTP do API
│   └── package.json
├── qualiagent/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app, montowanie routerów
│   ├── config.py                     # pydantic-settings
│   ├── database.py                   # engine, session factory
│   ├── dependencies.py               # get_db i zależności endpointów
│   ├── models.py                     # SQLAlchemy: Study, Source, Chunk, AnalysisRun, Section, Citation
│   ├── schemas.py                    # Pydantic v2: kontrakt API i grafu
│   ├── api/
│   │   └── routers/
│   │       ├── studies.py
│   │       ├── sources.py
│   │       ├── analysis.py
│   │       └── reports.py
│   ├── ingest/
│   │   ├── loaders.py                # pdf, docx, txt, audio
│   │   ├── chunking.py
│   │   └── embedding.py
│   ├── retrieval.py
│   ├── graph/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   ├── edges.py
│   │   └── build.py
│   ├── prompts/                      # prompty jako osobne pliki .md
│   ├── verify.py
│   └── report.py
├── alembic/
│   ├── env.py
│   └── versions/
├── tests/
├── k8s/
├── alembic.ini
├── Dockerfile
├── pyproject.toml
└── uv.lock
```

`frontend/lib` woła FastAPI. Żadnej logiki biznesowej, ingestu ani grafu w Next.js.

---

## Model danych

Warstwa trwała: modele SQLAlchemy w `models.py`. Warstwa kontraktu: te same byty jako Pydantic w `schemas.py`. Graf i API operują na schematach Pydantic, nie na luźnych `dict`.

Jedno badanie (`Study`) może mieć **wiele przebiegów analizy** (`AnalysisRun`). Każdy run ma własny `thread_id` LangGraph, własne sekcje i cytaty. Ponowne uruchomienie nie nadpisuje poprzedniego wyniku.

```python
class Study(BaseModel):
    id: UUID
    name: str
    research_questions: list[str]
    web_search_enabled: bool = False
    created_at: datetime


class Source(BaseModel):
    id: UUID
    study_id: UUID
    source_code: str  # stabilny kod do markerów, np. "S03"
    filename: str
    kind: Literal["audio", "video", "pdf", "docx", "txt"]
    respondent_label: str | None  # "R03", "ekspert_2"
    raw_text: str
    status: Literal["pending", "transcribing", "indexed", "failed"]
    error: str | None = None


class Chunk(BaseModel):
    id: UUID
    source_id: UUID
    text: str
    position: int  # kolejność w źródle
    speaker: str | None
    # embedding trzymany w kolumnie vector, nie w Pydantic


class AnalysisRun(BaseModel):
    id: UUID
    study_id: UUID
    thread_id: str  # klucz checkpointera LangGraph
    status: Literal[
        "pending",
        "running",
        "awaiting_approval",
        "completed",
        "failed",
    ]
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None


class Section(BaseModel):
    id: UUID
    analysis_run_id: UUID
    research_question: str
    position: int  # kolejność pytań w raporcie
    body: str
    coverage: Literal["sufficient", "thin", "absent"]
    coverage_note: str
    respondents_covered: int
    respondents_total: int
    citations: list[Citation]


class Citation(BaseModel):
    id: UUID
    section_id: UUID
    marker: str  # "[S03:c17]"
    source_id: UUID
    chunk_id: UUID
    quoted_text: str  # zawsze dosłowny fragment chunka
    verified: bool
    verification_note: str | None = None
```

`source_code` nadawany przy insercie (kolejny wolny numer w ramach badania: `S01`, `S02`, …) i **nigdy nie zmienia się** po zmianie kolejności plików. Marker odwołuje się do `source_code` i pozycji chunka, nie do kolejności uploadu.

`quoted_text` jest obowiązkowe. Nie ma cytatu-parafrazy z markerem.

### Jak liczymy respondentów

- `respondents_total` — liczba unikalnych `respondent_label` wśród źródeł badania. Źródła bez etykiety liczą się każde z osobna, identyfikowane przez `source_id`.
- `respondents_covered` — liczba unikalnych respondentów wśród **retrieved** chunków (ta sama reguła etykiety / `source_id`).

Te liczby liczy kod, nie LLM.

### Schemat SQL

Tabele: `studies`, `sources`, `chunks`, `analysis_runs`, `sections`, `citations`.

- `chunks.embedding`: `vector(1024)`, indeks HNSW (Voyage `voyage-3`).
- `chunks` albo `sources`: kolumna `tsvector` z indeksem GIN do full-textu.
- Relacje: `Source.study_id` → `Study`; `Chunk.source_id` → `Source`; `AnalysisRun.study_id` → `Study`; `Section.analysis_run_id` → `AnalysisRun`; `Citation.section_id` → `Section`, `Citation.chunk_id` → `Chunk`.
- Checkpointy LangGraph w osobnym schemacie — `langgraph.checkpoint.postgres.PostgresSaver`.

Migracje tylko przez Alembic. Nie tworzyć plików migracji ręcznie — poprosić o uruchomienie komendy.

---

## Graf

```
ingest (poza grafem, raz na źródło; badanie można uzupełniać)
   ↓
plan ──→ retrieve ──→ coverage ──┬─ sufficient ─→ write
           ↑                     ├─ thin ───────→ reformulate ──┐
           └─────────────────────┴─ absent ─────→ web_search ───┤
                                                                 ↓
                                              write ──→ verify ──┬─ ok ──→ next_question
                                                ↑                └─ failed ─┘
                                                                             ↓
                                                       (wszystkie pytania) → assemble
```

Każde uruchomienie grafu to nowy `AnalysisRun` z własnym `thread_id`.

### Węzły

`plan`
Wejście: aktualne pytanie badawcze.
Wyjście: `subqueries: list[str]` — 4 do 8 podpytań.

Podpytania mają rozbijać pytanie na wymiary, nie parafrazować. Muszą być sformułowane w języku, jakim mówią respondenci, nie w żargonie badacza. Przykład: „Jak respondenci postrzegają zmianę organizacyjną" → co mówią wprost o zmianie, jakich metafor używają, w jakich sytuacjach temat się pojawia sam, kto wypowiada się inaczej niż większość.

`retrieve`
Dla każdego podpytania: hybrydowe wyszukiwanie w pgvector (cosine) i full-text (`ts_rank`), top-k = 8 na podpytanie, fuzja RRF, deduplikacja po `chunk_id`.
Wyjście: `retrieved: dict[str, list[Chunk]]`.
Inkrementuj `retrieval_attempts`.

W stanie grafu trzymaj identyfikatory chunków plus minimalne metadane potrzebne do `coverage`/`write`. Pełne teksty dociągaj przy `write` i `verify`, żeby checkpoint nie puchł.

`coverage` — najważniejszy węzeł, dwie fazy

**Faza 1 — deterministyczna (bez LLM-a)**

Policz `respondents_covered` i `respondents_total` według reguł z modelu danych. Policz też rozkład chunków po `source_id` (czy materiał nie stoi na jednym źródle).

- 0 retrieved chunków albo `respondents_covered == 0` → werdykt `absent`, LLM-a nie wołamy.
- w pozostałych przypadkach liczby idą do fazy 2 jako fakty, których model nie może nadpisać.

**Faza 2 — LLM**

Wejście: pytanie badawcze, chunki, twarde liczby z fazy 1.
LLM zwraca strukturalny JSON:

```json
{
  "verdict": "sufficient | thin | absent",
  "reasoning": "dwa-trzy zdania",
  "missing_dimensions": ["..."]
}
```

`respondents_covered` i `respondents_total` w stanie biorą się z fazy 1, nie z JSON-a modelu.

Kryterium werdyktu **nie** jest „czy coś znaleziono", tylko czy materiał pozwala odpowiedzieć rzetelnie:

- ilu różnych respondentów wypowiada się na temat (nie ile chunków) — to już widać z liczb
- czy są głosy odmienne, czy tylko zgodne — to ocenia LLM
- czy teza nie opierałaby się na jednej osobie — LLM widzi rozkład z fazy 1

To jest przeniesienie logiki nasycenia teoretycznego do kodu. Prompt musi to wyrażać wprost.

`reformulate`
Uruchamiany przy `thin`. Przepisuje podpytania innymi słowami — szerzej albo węziej, w zależności od `missing_dimensions`. Wraca do `retrieve`. Maksymalnie 2 próby (`retrieval_attempts`), potem przechodzi do `write` z tym, co jest.

`web_search`
Pole `Study.web_search_enabled` istnieje od Etapu 1. Węzeł implementujemy w Etapie 6.

Uruchamiany przy `absent` **i tylko gdy** `web_enabled == True`. Wyniki trafiają do `web_results` i będą użyte w osobnej sekcji „kontekst zewnętrzny".

**Twarda reguła: materiał z sieci nigdy nie miesza się z materiałem badawczym.** Narzędzie nie może sugerować, że coś jest wnioskiem z badania, jeśli pochodzi z internetu. Egzekwuj to w prompcie `write` i w strukturze raportu.

`write`
Pisze sekcję rozdziału. Reguły w prompcie:

- marker `[S03:c17]` **tylko** przy dosłownym cytacie w cudzysłowie, będącym podciągiem wskazanego chunka
- parafraza i synteza mogą stać w tekście bieżącym **bez** markera
- brak materiału → napisz, że go brak; nigdy nie uzupełniaj z wiedzy własnej
- podaj, ilu respondentów popiera daną obserwację
- głosy odmienne muszą być wymienione, nie pominięte
- ustalenia z web searcha wyłącznie w oznaczonej sekcji

Wyjście: `draft: str`, `citations: list[Citation]` (parsowane z markerów; każde `quoted_text` to treść z cudzysłowu przy markerze).

`verify` — deterministyczny, bez LLM-a, bez fuzzy match

Dla każdego markera:

- marker musi dać się sparsować do istniejącego `source_code` + chunka; nieistniejący chunk → natychmiastowa porażka
- pobierz tekst chunka po `chunk_id`
- `quoted_text` musi być podciągiem tekstu chunka po normalizacji białych znaków i cudzysłowów (exact match, nie rapidfuzz)
- brak `quoted_text` albo marker przy tekście, którego nie ma w chunku → porażka

Wyjście: `verification_failures: list[str]` z opisem, co nie przeszło.
Jeśli lista niepusta i `verify_attempts < 2` → wróć do `write` z listą poprawek. Po drugiej próbie oznacz pozostałe markery jako `verified=False` i idź dalej.

Po udanym (lub wyczerpanym) `verify` zapisz `Section` i jej `Citation` do bazy, powiązane z bieżącym `AnalysisRun`.

`assemble`
Generuje DOCX: rozdziały per pytanie badawcze, tabela cytowań (marker, respondent, źródło, fragment), nota metodologiczna (liczba źródeł, liczba respondentów, które pytania miały cienkie pokrycie, ile cytatów niezweryfikowanych).

### Stan

Stan grafu jest `TypedDict`, ale wartości `retrieved`, `citations` i `sections` muszą być zgodne ze schematami Pydantic (`Chunk`, `Citation`, `Section`), nie z ad-hoc dict.

```python
class AgentState(TypedDict):
    study_id: str
    analysis_run_id: str
    research_questions: list[str]
    current_question_idx: int

    subqueries: list[str]
    retrieved: dict[str, list[Chunk]]
    coverage: Literal["sufficient", "thin", "absent"] | None
    coverage_note: str
    respondents_covered: int
    respondents_total: int
    retrieval_attempts: int

    web_enabled: bool
    web_results: list[dict]

    draft: str
    citations: list[Citation]
    verification_failures: list[str]
    verify_attempts: int

    sections: list[Section]
```

### Human-in-the-loop

`interrupt_before=["write"]`. Badacz widzi podpytania, znalezione fragmenty i ocenę pokrycia, może zatwierdzić albo poprawić podpytania. Użyj `PostgresSaver` jako checkpointera, żeby dało się wznowić po przerwie — w ramach konkretnego `AnalysisRun.thread_id`.

---

## API

FastAPI. Każdy zasób w osobnym routerze pod `qualiagent/api/routers/`. Migracje Alembic.

Minimalny zakres (szczegóły endpointów dopinamy w Etapie 2):

- badania: CRUD, lista pytań badawczych, przełącznik `web_search_enabled`
- źródła: upload wielu plików, etykieta respondenta, status indeksowania
- analiza: start nowego `AnalysisRun`, stream postępu, resume po interrupcie, lista runów badania
- raport: sekcje i cytaty konkretnego runu, pobranie DOCX

---

## UI

Next.js od Etapu 3. Cztery zakładki:

1. **Badanie** — nazwa, pytania badawcze (lista edytowalna), przełącznik web search
2. **Materiały** — upload wielu plików naraz, pole etykiety respondenta per plik, tabela statusów
3. **Analiza** — lista przebiegów, przycisk nowego runu, podgląd `graph.stream()` na żywo (aktualny węzeł, numer iteracji, werdykt pokrycia), panel zatwierdzenia przy interrupcie
4. **Raport** — wybór runu, podgląd sekcji, tabela cytowań z wyróżnieniem niezweryfikowanych, przycisk pobrania DOCX

UI jest cienkim klientem HTTP nad FastAPI. Żadnej logiki biznesowej w `frontend/`.

Zakładki Analiza i Raport w Etapie 3 mogą być makietą (start runu, puste stany). Ożywają wraz z grafem.

---

## Plan realizacji

Realizuj etapami. Po każdym zatrzymaj się i pokaż wynik.

**Etap 1 — fundament**
`models.py`, `schemas.py`, `database.py`, pierwsza migracja Alembic (wszystkie tabele, w tym `analysis_runs`, `sections`, `citations`), `ingest/loaders.py` dla PDF/DOCX/TXT (audio pomijamy), `chunking.py`, `embedding.py` (Voyage). Test: wgranie trzech plików i sprawdzenie, że chunki są w bazie z embeddingami.

**Etap 2 — podstawowe API**
FastAPI: `main.py`, `dependencies.py`, routery badań i źródeł. Test: działają endpointy (OpenAPI + testy).

**Etap 3 — podstawowe UI**
Szkielet Next.js z czterema zakładkami, podpięty do API z Etapu 2 (Badanie + Materiały działają naprawdę).

**Etap 4 — retrieval**
`retrieval.py` z hybrydowym wyszukiwaniem i RRF. Test: zapytanie zwraca sensowne fragmenty z poprawnymi metadanymi.

**Etap 5 — graf, ścieżka główna**
`state.py`, `nodes.py` (plan, retrieve, coverage w dwóch fazach, write, verify exact-match), `build.py`. Bez warunkowych pętli — najpierw prosta ścieżka. Nowy `AnalysisRun` per uruchomienie. Test: przechodzi od pytania do zweryfikowanego szkicu i zapisuje `Section` / `Citation`.

**Etap 6 — warunkowe przejścia**
`edges.py`: pętla reformulate przy `thin`, web_search przy `absent` (gdy włączone), powrót do write przy nieudanej weryfikacji, pętla po pytaniach badawczych. Liczniki prób i twarde limity.

**Etap 7 — raport**
`report.py` — DOCX z rozdziałami, tabelą cytowań i notą metodologiczną.

**Etap 8 — transkrypcja i human-in-the-loop**
Transkrypcja audio/video przez Gemini, interrupt przed `write`, streaming do UI, Dockerfile.

**Etap 9 — k8s**
Postawienie na k8s (k3s) na VM Google — we współpracy. Instancja za basic auth albo tunelem; bez kont użytkowników.

---

## Czego nie robimy

Nie ma kont użytkowników, wielu tenantów, cache'owania odpowiedzi LLM, RAGAS ani innych frameworków ewaluacyjnych, obsługi plików większych niż 100 MB, deduplikacji między badaniami, Streamlita, Poetry, fuzzy-weryfikacji parafraz.

Wyjątek od „nie ma logowania”: na deployu instancja ma być zamknięta (basic auth, tunel albo allowlist IP). To nie jest multi-user. Transkrypty wywiadów nie mogą wisieć otwarte w internecie.

Jeśli uznasz, że któraś z tych rzeczy jest niezbędna do działania — powiedz mi, zamiast dodawać po cichu.

---

Będę to chciał postawić na VM Google'a na k8s. Ale to później.
Oraz dodać SQLAdmin.
