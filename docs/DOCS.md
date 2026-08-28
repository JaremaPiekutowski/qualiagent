# QualiAgent — jak działa graf, LLM i retrieval

One-pager po kodzie: co robi LangGraph, jak wygląda run, węzły, krawędzie, language model i retrieval.

---

## Big picture

Jedno badanie (`Study`) ma źródła (wywiady) i pytania badawcze. Każde uruchomienie analizy tworzy nowy `AnalysisRun` z własnym `thread_id`. Graf LangGraph bierze bieżące pytanie, szuka fragmentów w korpusie, ocenia pokrycie, (opcjonalnie) czeka na badacza, pisze sekcję z cytatami, weryfikuje je deterministycznie, przechodzi do kolejnego pytania i na końcu składa DOCX.

Ingest (upload → chunki → embeddingi) jest **poza grafem**. Graf czyta tylko to, co już jest w Postgresie.

---

## LangGraph + checkpointer

### Co to jest w tym projekcie

Graf to `StateGraph(AgentState)` w `qualiagent/graph/build.py`. Stan (`AgentState`) to TypedDict: pytania, podpytania, retrieved chunki, coverage, draft, cytaty, sekcje, ścieżka raportu itd.

Węzły dostają zależności przez `GraphDependencies` (sesja DB, settings, embedding client, language model) — `bind_node` zamyka je w callable dla LangGraph.

### Checkpointer

Checkpointer zapisuje stan wątku pod `thread_id`, żeby dało się **wznowić** po przerwie (HITL).

| Setting | Zachowanie |
|---|---|
| `USE_POSTGRES_CHECKPOINTER=true` | `PostgresSaver` na tym samym Postgresie co aplikacja (`open_checkpointer` w `graph/checkpointer.py`) |
| `false` | wspólny `InMemorySaver` w procesie (OK lokalnie; znika po restarcie API) |

`interrupt_before=["write"]` (gdy `INTERRUPT_BEFORE_WRITE=true`) oznacza: graf dochodzi do coverage / web_search, **zatrzymuje się przed `write`**, status runu → `awaiting_approval`. Badacz widzi podpytania, chunki i coverage; potem:

- **approve** → `graph.invoke(None, config)` — kontynuacja od `write`
- **revise** → `Command(update={subqueries…}, goto="retrieve")` — ponowne wyszukiwanie z poprawionymi podpytaniami

Bez checkpointera interrupt jest niemożliwy (kompilacja rzuca błąd).

Klucz wątku: `AnalysisRun.thread_id` → `thread_config(thread_id)`.

---

## Run — jak startuje i kończy się przebieg

Główne API w `qualiagent/graph/run.py`:

1. `create_analysis_run` — wiersz w DB, status `running`, świeży `thread_id`
2. `initial_agent_state` — wypełnia `AgentState` z badania
3. `build_main_path_graph(...)` + `graph.invoke(state, config)`
4. Po wyjściu: jeśli snapshot ma `next` (interrupt) → `awaiting_approval`, inaczej → `completed`; wyjątek → `failed`

API/UI woła to samo przez routery analizy (w tym SSE `stream` z `stream_mode="updates"`). Testy zwykle wyłączają interrupt (`interrupt_before_write=False`) i nie potrzebują checkpointera.

---

## Nodes i edges

```
START → plan → retrieve → coverage
                              ├─ sufficient ──────────────→ write → verify
                              ├─ thin (attempts < 2) → reformulate → retrieve
                              └─ absent + web_enabled → web_search → write
                                                          ↑
                              verify failures & attempts < 2 ─┘
                              verify OK / limit → next_question
                                                    ├─ więcej pytań → plan
                                                    └─ koniec → assemble → END
```

### Nodes

| Węzeł | Co robi |
|---|---|
| **plan** | LLM → 4–8 podpytań w języku respondentów (`prompts/plan.md`) |
| **retrieve** | Dla każdego podpytania: hybrid search; `retrieval_attempts += 1` |
| **coverage** | Faza 1: twarde liczby respondentów (bez LLM). 0 chunków / 0 covered → `absent`. Inaczej faza 2: LLM → `sufficient` / `thin` / `absent` + `missing_dimensions`. Liczb z fazy 1 model nie nadpisuje |
| **reformulate** | Przy `thin`: LLM przepisuje podpytania (`prompts/reformulate.md`) → z powrotem do retrieve |
| **web_search** | Przy `absent` i włączonym web: Anthropic web search → `web_results` (osobno od materiału badawczego) |
| **write** | LLM pisze sekcję; markery `[S01:c0]` tylko przy dosłownych cytatach (`prompts/write.md`) |
| **verify** | Bez LLM: parse markerów, exact match cytatu w chunku (po normalizacji). Persist `Section`/`Citation` dopiero gdy sukces albo wyczerpane 2 próby |
| **next_question** | `current_question_idx += 1`, reset pól pytania |
| **assemble** | DOCX do `reports/{analysis_run_id}.docx`, `report_path` w stanie |

### Edges (routing)

W `qualiagent/graph/edges.py`:

- **po coverage:** `thin` i `retrieval_attempts < 2` → reformulate; `absent` i `web_enabled` → web_search; inaczej → write (także thin po limicie prób)
- **po verify:** są failures i `verify_attempts < 2` → write; inaczej → next_question
- **po next_question:** jeszcze są pytania → plan; inaczej → assemble

Limity: `MAX_RETRIEVAL_ATTEMPTS = 2`, `MAX_VERIFY_ATTEMPTS = 2`.

---

## Language model

Plik: `qualiagent/language_model.py`.

Interfejs `LanguageModelClient` (Protocol):

- `complete_json(system, user)` — plan, coverage, reformulate
- `complete_text(system, user)` — write
- `search_web(query)` — web_search

Produkcja: `AnthropicLanguageModelClient` (Claude, klucz `ANTHROPIC_API_KEY`, model z settings). JSON jest wyciągany z odpowiedzi tekstowej (toleruje fence \`\`\`json). Web search: tool `web_search_20250305`, wyniki parsowane do `{title, url, snippet}`.

Testy: `StubLanguageModelClient` — te same metody, bez API.

Prompty leżą w `qualiagent/prompts/*.md` i są ładowane w węzłach.

---

## Retrieval

Plik: `qualiagent/retrieval.py`. Wejście dla grafu: `search_study_chunks(session, study_id, query, ...)`.

Dla jednego zapytania:

1. **Embedding zapytania** — Voyage `embed_query` (`input_type=query`)
2. **Wektor** — cosine distance w pgvector, top-k chunków badania
3. **Full-text** — `plainto_tsquery('simple')` + `ts_rank` na `chunks.search_vector`
4. **RRF** — Reciprocal Rank Fusion obu list (`score += 1/(k + rank)`, domyślnie `k=60`)
5. **Load** — top-k po fuzji jako `RetrievedChunk` (tekst, `source_code`, respondent, position, score)

Domyślne top-k: `retrieval_top_k=8`. Zakres zawsze: źródła jednego `study_id`.

W `retrieve_node` wynik to `dict[subquery → list[RetrievedChunk]]`; coverage/write spłaszczają i deduplikują po `chunk_id`.

---

## Mapowanie plików

| Temat | Gdzie |
|---|---|
| Budowa grafu | `qualiagent/graph/build.py` |
| Routing | `qualiagent/graph/edges.py` |
| Węzły | `qualiagent/graph/nodes.py` |
| Stan | `qualiagent/graph/state.py` |
| Start / resume | `qualiagent/graph/run.py` |
| Checkpointer | `qualiagent/graph/checkpointer.py` |
| LLM | `qualiagent/language_model.py` |
| Retrieval | `qualiagent/retrieval.py` |
| Weryfikacja cytatów | `qualiagent/verify.py` |
| Raport DOCX | `qualiagent/report.py` |

---

## Minimalny happy path (jedno pytanie)

1. Run startuje → plan → retrieve → coverage=`sufficient`
2. Interrupt przed write (jeśli włączony) → approve
3. write → verify (cytaty OK) → next_question → assemble → `completed` + DOCX
