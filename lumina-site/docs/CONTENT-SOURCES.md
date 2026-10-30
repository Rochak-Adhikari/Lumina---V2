# Content sources — what the site claims and why

Every product statement on the site was checked against the Lumina project's own records in `D:\R O C H A K\LUNA 3`. Those records were **read only**; nothing in the application, its docs or its data was changed.

Evidence levels used below:

- **Recorded** — implemented and tested according to the project's retained audit documents. Not re-run for this website.
- **Design** — stated as a requirement or principle in the PRD (`Uploads/Lumina_PRD_Document_1.docx`, 2 Oct 2026).
- **Not built** — explicitly recorded as missing, blocked or future work.

## Positioning

| Site statement | Source | Level |
|---|---|---|
| Personal AI companion for Windows; private, single-user build; not publicly available | `notes/LUMINA.md`; PRD §1.3 ("The only target user… does not optimize for… public distribution") | Design |
| Voice-first, local-first | PRD §1.2, §1.5 (P0 "Local-first") | Design |
| "The model proposes; Lumina's runtime decides what is allowed" | PRD §1.5 (P0 Security: "The model proposes; runtime authorization and executors enforce"); `docs/PROJECT_HANDOFF_2026-10-18.md` §3 ("Model output cannot grant itself authority") | Design + Recorded |
| Understand → Plan → Authorize → Act → Observe → Evaluate loop; success judged by evidence | PRD §3.5 ("Success requires evidence from the environment rather than model confidence alone") | Design |
| Asks instead of guessing when unsure | PRD §2.2 ("ask instead of guessing when it is not [confident]") | Design |
| Interrupt, cancel, deny, correct | PRD §1.5 (P0 User control) | Design |

## Capability status (section 04)

| Capability | Site status | Source |
|---|---|---|
| Voice conversation (live transcription) | Working in private build | Handoff §3: Gemini Live PCM/transcription adapter, `web/voice.js`, `web/call.js` |
| Files & documents, journaled changes with undo | Working | `docs/LEGACY_FEATURE_ROADMAP.md` items 1 and 12 (all boxes checked); `LUMINA-Recovered/lumina/file_controller.py` |
| Web search with sources | Working | Roadmap item 2 (checked) |
| Reminders | Working | Roadmap item 3 (checked) |
| Supervised browser — commits/uploads/downloads blocked | Working, with limit shown | Roadmap item 4: two boxes deliberately **unchecked** (external commits, uploads/downloads). The site states the limit. |
| Screen context on request | Working | Roadmap item 5 (checked) |
| Memory & continuity (sources, corrections, forgetting, inspector, graph) | Working | Handoff §4; `docs/CONTINUITY_IMPLEMENTATION.md` |
| Supervised workers | Working | Handoff §3 (TaskManager / supervised Claude workers) |
| Proactive notices from configured events only | Working | Roadmap item 10 (checked); PRD §3.12 |
| Computer control — simulation-only | In development | `.recovery/milestone5`, `5b`, `5c`: "NO-GO for native-helper contract testing… live control"; `/api/confirm` rejects simulation proposals |
| Skills (reviewed, sandboxed) | In development | PRD §3.10; `LUMINA-Recovered/RECOVERY-INTEGRATION.md` ("Full PhaseThree/plugins require missing plugins.py") |
| "Where did we leave off?" | In development | Handoff §5–6, Gate D (proposed, not built) |
| Connected devices | Roadmap | Handoff §1: phone on another network, PC-off operation not certified |
| Cloud continuity | Roadmap | Handoff §1: bidirectional memory sync not implemented; cloud deployment not certified |
| Offline models | Roadmap | PRD §1.4 goal; no implementation evidence found |

The site's fine print says: status reflects the creator's development records as of October 2026, and "working in the private build" means implemented and tested in a single-user build — not a public release.

**Important qualification:** the handoff of 18 Oct 2026 records that the transferred workspace lost source files and could not reproduce the 10 Oct release; a recovered checkout (`LUMINA-Recovered`) has since been restored across several milestones. "Working" on the site therefore reflects recorded release evidence, not a fresh run done for this website. If the owner wants the site to reflect only re-verified capabilities, downgrade statuses in `src/content/content.ts`.

## Memory section

| Statement | Source |
|---|---|
| Memory lives in a local database on your PC | Handoff §4: canonical SQLite at `%LOCALAPPDATA%/LUMINA/memory.sqlite3` |
| Recognizable credentials are filtered out before storage | Handoff §4: `Runtime.capture_user_evidence` rejects recognizable credentials |
| Nothing shared with a cloud service without separate consent | Handoff §4.6: cloud memory requires separate cloud-storage and provider-use consent |
| Not every word is kept | PRD §3.8 ("must not treat the complete conversation history as memory") |
| Sources, confidence, corrections kept as history | Handoff §4: provenance, temporal correction, supersede history |

The four memories shown are **fictional examples**, labelled "Example memories".

## Demo

- Labelled **"Simulation · example data"** with the notice "Runs entirely in your browser. Nothing on your computer is read or changed."
- All files, vendors, prices and people are fictional.
- Permission labels follow PRD §4.1 (read-only allowed; low-risk confirmation configurable; file changes need approval). File changes requiring exact one-use approval matches `recovery_file_tools.py` as described in `RECOVERY-INTEGRATION.md`.
- The concept console is described on-site as a concept interface; the real desktop app UI differs.

## Things the site does not claim

No download, waitlist, sign-up, user numbers, testimonials, benchmarks, certifications, integrations with named third-party apps, or public availability.

## Configurable personal detail

The footer credits the creator by name (`Rochak Adhikari`, from the PRD and `notes/LUMINA.md`). It is marked `data-config="creator"` in `index.html` and can be removed or changed before publishing.
