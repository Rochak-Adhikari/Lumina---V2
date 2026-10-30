# Phase 04 — Dynamic closed-loop tasks

1. **Objective:** Execute non-hardcoded tasks from observations through existing Runtime.
2. **Why necessary:** current recipe/owned-window evidence cannot establish this phase's broader guarantee. P0 removes source/document uncertainty; subsequent phases add only unmet requirements.
3. **Prerequisites:** exact mandatory dependencies for P4.1, P4.2 are in [ROADMAP.md](../ROADMAP.md). Overall owner plan approval precedes implementation. P2 native work additionally needs D1 and named target authorization; P3.2 needs D2 and transmission/local-trial permission.
4. **Capabilities added/completed:** P4.1 dynamic loop; P4.2 budgets, explicit goal predicates and consistent progress.
5. **Reuse:** TaskManager sessions/events, review store, authority, controller and perception.
6. **Out of scope:** Second scheduler/database, generic workers or broad application mutation.
7. **Expected source files:** runtime.py, tasks.py, goals.py compatibility seam, computer_control.py, server.py, web/goals.js. Paths without a directory are under lumina/ unless web/tests are specified. Inspect before editing; no wholesale replacement.
8. **Justified proposed modules:** computer_use.py dynamic runner. Names are proposed, never claims of present implementation.
9. **Public function contracts:** C01,C03–C04,C12–C14,C23–C27 in [CONTRACTS.md](../CONTRACTS.md); existing API compatibility is mandatory.
10. **State/invariants:** TaskManager status remains authoritative; progress phase may describe observing/planning/admitting/executing/verifying. Source/session/target/geometry/generation cannot silently change. Stop invalidates future admissions, not already accepted OS effects. No success from a model/API return alone.
11. **Tests:** Real Runtime with fake model faults, then genuine model/native randomized owned UI layouts and wrong-done claims. Unit/component/deterministic integration run before native/model tiers. Include relevant legacy goal/action/authority/observation regressions; do not rerun unrelated suites or unreviewed native tests.
12. **Acceptance:** At least three randomized layouts completed with observation-driven sequences and verified goal predicates; no recipe encoded for accepted tasks.
13. **Evidence artifacts:** assigned milestone's patch/changed-file list, initial/final Git/hash checkpoint, commands and pass/fail/error/skip counts, safe failure records, native versus simulated versus provider labels, and acceptance-row evidence links. No screenshots/private input retained by default; synthetic opt-in evidence only.
14. **Resource/compatibility/security/regression risks:** State duplication, unknown outcomes accidentally cleared, busy recovery loop.
15. **Dependencies:** sole register rows P4.1, P4.2; no unlisted optional enhancement may become an implicit prerequisite. No concurrent shared-file editing.
16. **Phase exit:** every assigned row's explicit gate satisfied with its required tier; no escalation of supported scope beyond that evidence.
17. **Pause conditions:** unexplained safety failure, missing target/model authorization, source drift affecting reviewed code, new security/licensing/model feasibility change, or uncertainty requiring private data. Stop affected work, preserve evidence, continue unrelated permitted work only when dependencies allow. Routine implementation defects stay in the row.
18. **Effort/confidence:** per-row ROADMAP estimates are authoritative; sum phase rows. MASTER_PLAN carries contingency/calendar assumptions. Do not add another duplicate schedule or silent phase.
19. **Handoff assumptions:** P5 may assume functional bounded dynamic loop, not complete fault coverage.
20. **Next assignment rule:** implementation requires one exact ID and ends at its gate. P0 is already a static audit; it does not imply runtime success.

## Sub-milestones and task order

**P4.1: Dynamic observe-plan-act-verify runner.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: Actual Runtime/TaskManager completes randomized native tasks with changing action sequences; each effect verified.

**P4.2: Goal predicates, bounded state and progress.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: Budgets stop loop, model completion checked independently, last verified checkpoint and owner-scoped events agree.

## Reusable Astra handoff prompt
Execute only <ID from P4.1, P4.2> after explicit owner assignment. Read this phase, ../EXECUTION_PROTOCOL.md, the exact ../ROADMAP.md row and referenced ../CONTRACTS.md IDs. Confirm current root/branch/HEAD/status and inspect runtime.py, tasks.py, goals.py compatibility seam, computer_control.py, server.py, web/goals.js. Preserve dirty/untracked/concurrent hunks and all historical evidence. Deliver the specified implementation through existing Runtime/authority; prohibit Second scheduler/database, generic workers or broad application mutation. Test deterministic boundaries first; native/provider scope requires its own passed prerequisites and permission. Never weaken a guard or relabel simulated results as native. Record exact changes, commands/counts/tier, uncertainty and hashes. Update STATUS.md, that ROADMAP row and acceptance evidence. Stop at the exit gate; do not start another milestone or repeat the full audit.
