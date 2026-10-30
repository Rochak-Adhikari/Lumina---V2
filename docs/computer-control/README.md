# Windows computer-control engineering set
Start with [MASTER_PLAN.md](MASTER_PLAN.md), then [STATUS.md](STATUS.md). This is a planning-only package; production implementation is not authorized by these documents.

Authority order: current source and reproducible evidence → owner-approved scope decisions → ROADMAP.md milestone register → phase specs and CONTRACTS.md → historical reports/original supplied plans. A conflict stops only affected work; record it before changing the plan.

| Document | Owns |
|---|---|
| CURRENT_STATE_AUDIT.md | Current source map, historical evidence, limitations |
| SOURCE_PLAN_RECONCILIATION.md | Original DOCX/Markdown comparison and requirement dispositions |
| ARCHITECTURE.md | Component boundaries, lifecycle and safety semantics |
| CONTRACTS.md | Typed implementation/function contracts |
| MASTER_PLAN.md | Completion definition, scope, phase dependency logic and effort |
| ROADMAP.md | Sole milestone register: IDs, dependencies, gates, estimates, status |
| ACCEPTANCE_TEST_MATRIX.md | Requirements, tests, faults and measurement procedures |
| EXECUTION_PROTOCOL.md | Single-milestone implementation and evidence rules |
| DECISION_LOG.md | Choices, alternatives, risks and owner decisions |
| MODEL_AND_PLATFORM_RESEARCH.md | Dated official references, pricing/privacy/license feasibility |
| STATUS.md | Current checkpoint, blockers, exact next eligible assignment |
| phases/PHASE-00.md … PHASE-07.md | Eight specifications and bounded Astra handoff prompts |
| PLANNING_PRESERVATION.json | Initial/final source and original-plan hashes, full Git status |
| PLAN_VALIDATION.json; validate_planning.py | Machine-checkable planning consistency and preservation checks |

No control feature is complete merely because these files exist. No application tests, desktop actions, model calls, installs or production startup were performed in this planning assignment. Inspection used existing Git/Python tooling only.

## Individual phase files
| File | Purpose |
|---|---|
| [phases/PHASE-00.md](phases/PHASE-00.md) | Static source baseline and preservation |
| [phases/PHASE-01.md](phases/PHASE-01.md) | Typed actions, observations, target/geometry contracts |
| [phases/PHASE-02.md](phases/PHASE-02.md) | Authorized bounded native Windows input |
| [phases/PHASE-03.md](phases/PHASE-03.md) | Replaceable image/action provider and cost qualification |
| [phases/PHASE-04.md](phases/PHASE-04.md) | Dynamic TaskManager control loop and goal predicates |
| [phases/PHASE-05.md](phases/PHASE-05.md) | Fault recovery, permissions, privacy and restart |
| [phases/PHASE-06.md](phases/PHASE-06.md) | Full UI, real apps, laptop resource and packaging gates |
| [phases/PHASE-07.md](phases/PHASE-07.md) | Blind acceptance, defect closure and release verdict |

Every phase owns its bounded implementation prompt, contracts, tests, risks, exit criteria and handoff assumptions. No separate repeated prompt files are needed. In total: twelve root Markdown documents, eight phase Markdown specifications, two preservation/validation JSON files and one validation script. The two original engineering-plan documents are inputs, not created files.
