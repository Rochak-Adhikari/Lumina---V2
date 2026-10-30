# Continuity engine implementation audit

## Repository baseline — 9 October 2026

The actual server entry point is `python -m lumina`: `lumina/__main__.py` loads Config, creates the aiohttp application, and serves the local runtime. The desktop launcher starts this same Python application. Runtime constructs MemoryStore and passes it into ToolRegistry. The original readers/writers are runtime remember/recall commands, the search_memory tool, and GET/POST /api/memory. Server cleanup closes the store. Providers previously received no durable continuity context.

The original memory database is SQLite at `%LOCALAPPDATA%/LUMINA/memory.sqlite3` unless `memory_path` is configured. Its sole table is `memories`, with integer IDs, category, text, creation/update times and soft deletion. There is no migration framework. Journal entries are excluded by default. Deletion uses an exact, expiring confirmation. The existing database passed a read-only integrity check before changes; no private contents were printed.

TaskManager has explicit lifecycle callbacks and UUID task IDs. Persistent worker adapters already restore task/session metadata. DesktopServices owns the active workspace and current file selection. KnowledgeGraph reads the separate notes graph; it is not the canonical memory database and will remain unchanged. PhaseTwo owns its own bounded automation scheduler. The memory implementation will use these existing boundaries rather than replace them.

Baseline: `python -m pytest tests -q` with `LUMINA_PHASE2_UI_TEST=1` completed in 190.39 seconds: 531 passed, one failed. The existing native Windows control fixture refused invocation with `user_takeover` while real input occurred. This is a pre-existing safety refusal, not a memory regression. Startup/API checks passed within the suite. No separate lint/type-check configuration was found. The repository's pytest.ini and documentation have been moved by the user; these changes are preserved.

## Migration and ownership plan

Keep the existing MemoryStore import and integer-ID interface as a compatibility facade. Add the normalized engine under lumina/continuity to avoid introducing a conflicting memory.py/memory package. Expand the existing database through explicit versioned, transactional migrations; back it up with SQLite's backup API before upgrading. Import legacy notes as attributed, unparsed notes rather than inventing semantic triples. Keep original rows and deletion markers. The rollback path is to stop all runtimes and restore the pre-migration SQLite backup together with the old application version; do not run destructive down migrations.

Runtime owns event authority. Model proposals are untrusted candidates and cannot self-confirm or execute SQL. MemoryService owns admission, lifecycle and context APIs; Repository owns serialized transactions and the outbox. User confirmation remains local, exact and short-lived. Canonical state and its provenance commit together. No cloud service, embedding provider, or new model dependency is introduced.

## Implementation complete — local phase

The local continuity phase is implemented in the main application and the existing Phase 2 portable distribution. This does not mean cloud synchronization, Android handoff, semantic embeddings, or learned personal prediction are implemented. Those remain outside this release.

### Architecture implemented

`lumina.continuity` owns the canonical model. `MemoryService` supplies domain operations; `MemoryAdmissionService` mediates proposals; `Repository` owns SQLite transactions, migrations and legacy mapping. Retrieval and state projections are separate modules. `lumina/memory.py` preserves the old `MemoryStore` import, integer note IDs, remember/search/deletion interfaces and categories. No provider SDK, vector database, cloud service or additional dependency was introduced.

Canonical records cover entities, immutable source events, temporal facts, evidence, episodes, decisions, goals, commitments, open loops, typed relationships, admission candidates, predictions and behavioral observations. Confidence, stability, importance and freshness remain separate quantities. Explicit stable keys identify entities; matching names alone do not merge people or projects. A local device UUID persists across restarts.

Admission creates, rejects, deduplicates, reinforces, disputes or supersedes records deterministically. Repeating the same source does not increase confidence or duplicate evidence. Independent source identities can reinforce a belief. A conflicting model proposal cannot silently replace a confirmed user fact. Corrections close the old validity interval and create a replacement, preserving historical retrieval. Changing a tracked assumption marks the associated decision as needing review. Decisions retain the chosen option, rejected alternatives, reasoning, constraints, assumptions and expected outcome.

Model proposals must cite an actual runtime-captured user statement; callers cannot supply confirmation authority or fabricated source fields through the tool schema. Canonical model-proposed writes require the existing one-use, 60-second local confirmation. Record versions and related deletion scope are rechecked at execution. A plain “continue” retrieves context and cannot approve another pending action.

Retrieval uses SQLite FTS5 plus structured project/entity/time/privacy filters. It ranks content overlap, confidence, authority, stability, freshness and importance. Query text is escaped rather than treated as FTS syntax. Scope and temporal restrictions apply before the per-table candidate cap. The default context budget is 12,000 serialized characters, with a hard range of 512–48,000; the public model tool has a smaller upper bound. Returned records carry source evidence and explicit uncertainty. Unsupported queries return no claimed answer. This is lexical and structured retrieval, not embedding similarity.

### Database and migrations

Migration `001_initial.sql` creates the normalized tables plus `meta`, `schema_migrations`, `legacy_memory_map`, `episode_events`, `current_state`, `memory_fts` and `sync_outbox`. UUID identities, revision numbers, UTC timestamps, privacy classes and synchronization policy are stored with canonical records. SQLite runs with foreign keys, WAL, a bounded busy timeout and serialized transactions. Nested writes use savepoints. Canonical admission, provenance and outbox changes commit together.

Before upgrading an existing database, the SQLite backup API writes a sibling named `memory.sqlite3.before-continuity-<unique-id>.backup`. Migrations run transactionally and reject newer unsupported schema versions. Backup handles close explicitly on Windows. A corrupt database is not silently reset or overwritten; memory becomes unavailable while the rest of the runtime can start.

Legacy rows retain their original values and IDs. An idempotent map links them to canonical, attributed, unparsed notes; migration does not pretend old free text is verified semantic knowledge. Journal entries remain sensitive and excluded from normal recall. Secret-like legacy notes remain in the untouched legacy database but are excluded from canonical import and normal search. Migration is preservation, not retroactive credential scrubbing.

The outbox records local mutation identity/version metadata. Nothing sends it to a server. It is a foundation for a future synchronization protocol, not a working sync system.

### Runtime integration

Runtime records selected meaningful user text/transcripts, actual workspace changes, observed task transitions and safe tool outcome metadata. Greetings and recognizable credentials are rejected. Tool arguments, file contents, screenshots, provider prose and raw worker output are not copied wholesale into continuity events. Assistant claims do not become evidence that an operation succeeded.

The existing task callback feeds durable open loops; completion or cancellation resolves them. A task that was running before shutdown is described as last observed, not asserted to still be running. `PersonalState` is rebuilt from canonical records and events; its stored projection is disposable. `ContinuationContext` selects the current project, workspace, unfinished task, open loops, blockers, goals, decisions, constraints, recent episode and observed files. It never spawns or resumes a worker by itself.

Bounded consolidation groups source events by session, project and privacy. Episodes contain deterministic observed-event summaries, not invented narrative outcomes. Consolidation uses the existing runtime scheduler at most once every five minutes and at orderly session close, with no extra daemon. Background work is awaited before SQLite closes.

Behavioral observations require at least three distinct sessions and remain hypotheses. The initial prediction rule suggests that evidenced unfinished work may be revisited, with 0.55 confidence and a seven-day horizon. The service accepts explicit outcome feedback and reports accuracy only when feedback exists. It does not claim psychological understanding or infer sensitive attributes.

Registered tools include recall, propose, explain, continuation, timeline, status, patterns, predictions, related records, correction, forgetting and resolution. The private local `/api/continuity` endpoint requires the session token even for reads. Online tool output excludes sensitive, device-local and cloud-blocked records; the local inspector can explain explicitly selected private records. Existing origin and permission checks remain in force.

### Current capabilities and inspector

The sidebar now has Memory. It shows real availability/counts, current unfinished work, searchable records and an evidence view. The evidence view separates the belief, status, privacy, confidence, stability, freshness, source observations and history; complete structured evidence is expandable. Correction, completion, invalidation and hard deletion all use the existing confirmation dialog. Refresh clears stale selection so a previously displayed belief is not presented as current after correction.

Invalidation removes a fact from current retrieval while retaining history. Hard deletion removes the approved record, linked source evidence, dependent memories, legacy mappings and affected cached state from the active database. Its preview warns that sharing evidence can widen the deletion. Scope changes invalidate confirmation. Interactive hard deletion stops for oversized archives/scopes and requires offline review instead of making an unbounded scan or partial deletion. Offline backups and old session logs are independent copies and are not erased; no forensic secure-erasure claim is made.

### Testing and live evidence

The final full regression run passed 957 tests, with one opt-in physical-input test skipped, in 104.52 seconds. There are 426 new continuity cases, including the 400-case benchmark. Tests include existing filesystem, messaging, voice, camera, browser, task, worker, settings, graph, server and UI suites. The native physical-input fixture is opt-in; the baseline run demonstrated its existing `user_takeover` refusal, so final unattended regression leaves that single test skipped rather than weakening the safeguard.

New tests exercise admission, independent evidence, contradictions, supersession, correction, historical/current queries, decision assumptions, goals, commitments, open-loop resolution, episodes, projection rebuilds, continuation after restart, entity/project isolation, privacy, credentials, budgets, transactional rollback, event immutability, concurrent deduplication, schema compatibility, real confirmation expiry/replay/staleness, dependent-deletion scope, migration handle cleanup, unavailable storage and the inspector's correction flow. A browser test uses the real application and confirmation UI at 1366×768 and reports no page errors.

The permanent benchmark contains 400 deterministic cases: eight scenario families with 50 domain/variant combinations each. All 400 passed, comprising 3,400 assertions. Measured precision and recall were 1.0; false-memory, stale-result and contradiction error rates were zero on this corpus; continuity accuracy and provenance coverage were 1.0. There were 450 returned records, 250 temporal queries, 50 contradiction checks, 200 continuity slots and 500 provenance records. The latest standalone run measured 650 operations, approximately 0.95 ms mean and 1.86 ms p95; the largest returned context was 3,663 characters. No model calls, model tokens or metered costs were incurred. These synthetic fixture results are not a claim of perfect real-world memory accuracy or production latency at large scale. The benchmark initially caught an identifier-only false match; retrieval now requires content overlap.

A read-only SQLite copy of the actual installed memory database was migrated and reopened. All 58 legacy rows were unchanged, integrity and foreign-key checks passed, the pre-upgrade backup restored correctly, and the second opening did not duplicate imported records. The actual user database was not migrated or modified by this verification. It will upgrade, with backup, when the updated application is next started normally.

The portable application's own Python runtime passed a real process-level API test: ready status, save/retrieve, confirmation before correction, confirmed correction, orderly shutdown, restart, corrected current value, historical value and provenance. It used a disposable database and the local provider. No online reasoning call was required.

A relocated copy of the distribution launched its real native WebView2 window. Owned server startup and shutdown passed; a pre-existing valid server was reused and left alive; a foreign process on the selected port was rejected. The UI loaded after readiness, rendered the graph with 11 actual nodes and reported a connected runtime. WebView2 reported version 151.0.4129.101. The unchanged executable's actual signature state is `NotSigned`; this remains an unsigned local development distribution.

Evidence files under `artifacts/`: `continuity-regression.xml`, `continuity-benchmark.json`, `continuity-migration-verification.json`, `continuity-portable-verification.json`, `continuity-desktop-verification.json`, and the disposable-data screenshot `continuity-inspector.png`.

### Prepared components and known limitations

Implemented: the local canonical engine, admission, source provenance, temporal fact retrieval, causal decision records, correction/forgetting, projections, continuation, deterministic operational hypotheses, inspector, migration and evaluation.

Partially implemented by design: episode summaries are counts of meaningful observed events, not LLM-written accounts; behavior recognition currently covers repeated workspace/task activity; predictions use one conservative unfinished-work rule. Prediction feedback and explicit relationship/impact operations are service APIs, while the conversational layer exposes a smaller set of typed tools. No automatic psychological profiling or opaque learned policy exists.

Prepared only: stable IDs, revisions, privacy/sync policy and a local transactional outbox. Not implemented: cloud transport/conflict reconciliation, Android clients, device pairing/revocation, embeddings, vector indexes, PostgreSQL/pgvector, learned predictions or encrypted cloud backup. Device identity is local to this database, not authenticated cross-device identity. Copying an entire database to another device does not constitute secure device handoff.

Local SQLite is not encrypted at rest. Windows filesystem protection remains the storage boundary. Backups may contain private historical data and need user-controlled protected storage. Secret screening is conservative pattern matching, not a guarantee that every arbitrary secret can be recognized. An original legacy credential is intentionally preserved in the original rows/backup rather than silently deleting user data.

Context and candidate caps are intentional; large archives may require narrower queries. Retrieval metrics reset with the process. The benchmark does not validate provider tool-selection accuracy. Live microphone, speech playback and an authenticated online-model memory conversation were not newly certified by this memory release; existing simulated voice/provider regressions passed. No paid service or new model was configured.

One failed verifier attempt left a temporary copy at `C:\Users\ADMINI~1\AppData\Local\Temp\lumina-memory-migration-xj9012r4`. Its Windows handle leak was fixed and the verifier then passed. Automatic approval review rejected the attempted cleanup with “blocked by policy” and no further reason; the copy was not deleted through another route. It contains a test copy of the existing memory database and should be treated as private.

### Files changed

All following paths are relative to `C:\Users\Administrator\Documents\ChatGPT\LUNA 3`:

| Path | Change |
|---|---|
| `lumina/continuity/models.py` | Provider-neutral records and secret screening |
| `lumina/continuity/migrations/001_initial.sql` | Canonical schema, indexes, FTS, outbox and immutable-event guard |
| `lumina/continuity/repository.py` | Transactions, migrations, backups and idempotent legacy import |
| `lumina/continuity/policy.py` | Bounds, privacy, timestamp and value validation |
| `lumina/continuity/admission.py` | Admission service boundary |
| `lumina/continuity/service.py` | Domain lifecycle, evidence, correction, forgetting, relationships and maintenance |
| `lumina/continuity/retrieval.py` | FTS/structured ranking, temporal filtering and bounded evidence packs |
| `lumina/continuity/state.py` | Rebuildable state, continuation, episodes and conservative hypotheses |
| `lumina/continuity/__init__.py` | Public package exports |
| `lumina/memory.py` | Legacy compatibility facade and unavailable-storage behavior |
| `lumina/continuity_commands.py` | Typed tools, exact confirmations, online filtering and local commands |
| `lumina/runtime.py` | Trusted evidence capture and failure-isolated continuity integration |
| `lumina/tasks.py` | Observed task lifecycle callback |
| `lumina/tools.py` | Existing registry/confirmation integration and canonical recall |
| `lumina/server.py` | Transcript evidence, private inspector API and cleanup |
| `lumina/phase2.py` | Reuse of existing scheduler for bounded memory maintenance |
| `lumina/speech.py` | Evidence, uncertainty and continuation instruction |
| `web/continuity.js` | Local inspector and reviewed mutations |
| `web/index.html`, `web/app.js`, `web/reference.css` | Sidebar/dialog hookup and scoped styling |
| `.gitignore` | Exclude private database, WAL and migration backup files |
| `tests/test_continuity_core.py` | Core invariants, migration and Windows handle tests |
| `tests/test_continuity_state.py` | State, continuation and hypothesis tests |
| `tests/test_continuity_integration.py` | Registry/API/confirmation/failure tests |
| `tests/test_continuity_ui.py` | Real browser inspector/correction test |
| `tests/test_continuity_benchmark.py` | Permanent 400-case evaluation plus metric validation |
| `scripts/benchmark_continuity.py` | Independent fixture expectations and measured benchmark report |
| `scripts/verify_continuity_migration.py` | Read-only-copy migration verification |
| `scripts/verify_continuity_portable.py` | Portable process restart and confirmation verification |
| `docs/CONTINUITY_IMPLEMENTATION.md` | This audit, architecture, rollout and use instructions |

The portable `app/lumina` and `app/web` contain the same 21 changed/new application assets; `build-manifest.json` includes their updated hashes. The launcher binary, configuration, notes, uploads, credentials and existing Phase 1/2 behavior were preserved. The former portable application code and manifest are backed up under `artifacts/continuity-portable-backup-20261009-030450`. Existing user documentation moves and repository ignore rules were preserved. The repository already ignores tests and artifacts; the new tests remain present locally, and no commit was made.

### Migration and usage

Close the existing LUMINA window and backend before updating/starting this version. Do not run old and new application versions against the same memory database concurrently: the compatibility facade preserves old interfaces, but an old process bypasses canonical admission. Open `dist/LUMINA-Portable-Phase2/LUMINA.exe`, or start the main application with `.\.venv\Scripts\python.exe -m lumina` from the repository. Open Memory in the sidebar. First normal startup backs up and upgrades the configured database automatically; no manual schema command is necessary.

Storage remains `%LOCALAPPDATA%\LUMINA\memory.sqlite3` by default. An explicit `memory_path` in `lumina.toml` takes precedence. When that configuration is empty, an explicitly set Windows environment variable `LUMINA_MEMORY_PATH` can select another database; the fallback remains app data. No automatic copy of private memory into the portable directory was added.

Try “Memory status”, then “Remember I prefer concise explanations”, then “What do you remember about concise explanations?” Open Memory, search for that phrase, and select Evidence. Review a correction through the existing confirmation dialog, restart LUMINA and search again. The corrected value should be current and the former value should remain in its history. “Where did we leave off?” and “What are my open loops?” report recorded unfinished work; neither launches a task. “Show memory timeline” displays the evidence timeline. “What am I likely to do next?” returns only supported hypotheses and uncertainty.

To reproduce the tests, use an isolated `LUMINA_MEMORY_PATH` and run `.\.venv\Scripts\python.exe -m pytest tests -q`. Run `.\.venv\Scripts\python.exe scripts\benchmark_continuity.py --output artifacts\continuity-benchmark.json` for benchmark metrics. The migration verifier accepts a database path and tests a temporary read-only copy; it does not upgrade the source. The portable verifier accepts the distribution directory and uses a disposable database.

Rollback requires both the earlier application files and its pre-migration database backup. Stop every LUMINA process first, preserve the current database and WAL/SHM files as a separate recovery set, and restore the chosen SQLite backup through an explicit user-controlled recovery step. Do not mix current WAL files with an older database or perform a destructive down migration. No automatic rollback or deletion of later memories is attempted.

### Recommended next step

Use the inspector and recorded continuation during ordinary work, then evaluate real user-labelled retrieval and corrections before adding embeddings, broader behavior rules or synchronization. Synthetic perfection is not evidence that cross-device memory is ready.

### Architectural principle

Lumina Memory is an evidence-backed, time-aware personal state system. Events preserve what happened; knowledge represents what Lumina currently believes; episodes preserve meaningful experiences; decisions and goals preserve intent; commitments and open loops preserve unfinished responsibility; the Personal World Model represents the user's current digital and project reality; provenance explains why each belief exists; predictions remain explicitly uncertain; and the Continuity Engine turns all of this into actionable context across sessions, models, and devices. This release implements the local portion; transferring that context securely between devices remains future work.
