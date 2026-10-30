# Phase 01 — Action and observation contracts

1. **Objective:** Define one typed dynamic action path and fresh target/geometry proofs.
2. **Why necessary:** current recipe/owned-window evidence cannot establish this phase's broader guarantee. P0 removes source/document uncertainty; subsequent phases add only unmet requirements.
3. **Prerequisites:** exact mandatory dependencies for P1.1, P1.2 are in [ROADMAP.md](../ROADMAP.md). Overall owner plan approval precedes implementation. P2 native work additionally needs D1 and named target authorization; P3.2 needs D2 and transmission/local-trial permission.
4. **Capabilities added/completed:** P1.1 strict single-action schema and fake runner seam; P1.2 geometry/identity and delayed-inference re-grounding.
5. **Reuse:** ObservationStream, action dataclasses, TaskManager and existing controller.
6. **Out of scope:** Native input, real model calls, parallel capture.
7. **Expected source files:** computer_action.py, computer_control.py, observations.py, runtime.py, tasks.py, computer_windows.py; focused tests. Paths without a directory are under lumina/ unless web/tests are specified. Inspect before editing; no wholesale replacement.
8. **Justified proposed modules:** computer_geometry.py pure transforms; computer_use_model.py parser/protocol only. Names are proposed, never claims of present implementation.
9. **Public function contracts:** C01–C08,C12–C14 in [CONTRACTS.md](../CONTRACTS.md); existing API compatibility is mandatory.
10. **State/invariants:** TaskManager status remains authoritative; progress phase may describe observing/planning/admitting/executing/verifying. Source/session/target/geometry/generation cannot silently change. Stop invalidates future admissions, not already accepted OS effects. No success from a model/API return alone.
11. **Tests:** Parser/property tests, source/DPI/HWND/PID reuse, fake completion rejection, legacy controller/goals regressions. Unit/component/deterministic integration run before native/model tiers. Include relevant legacy goal/action/authority/observation regressions; do not rerun unrelated suites or unreviewed native tests.
12. **Acceptance:** Malformed actions have zero effects; fresh frame does not silently rebind stale coordinates; control Stop preserves sharing.
13. **Evidence artifacts:** assigned milestone's patch/changed-file list, initial/final Git/hash checkpoint, commands and pass/fail/error/skip counts, safe failure records, native versus simulated versus provider labels, and acceptance-row evidence links. No screenshots/private input retained by default; synthetic opt-in evidence only.
14. **Resource/compatibility/security/regression risks:** Compatibility, source clock semantics and private values.
15. **Dependencies:** sole register rows P1.1, P1.2; no unlisted optional enhancement may become an implicit prerequisite. No concurrent shared-file editing.
16. **Phase exit:** every assigned row's explicit gate satisfied with its required tier; no escalation of supported scope beyond that evidence.
17. **Pause conditions:** unexplained safety failure, missing target/model authorization, source drift affecting reviewed code, new security/licensing/model feasibility change, or uncertainty requiring private data. Stop affected work, preserve evidence, continue unrelated permitted work only when dependencies allow. Routine implementation defects stay in the row.
18. **Effort/confidence:** per-row ROADMAP estimates are authoritative; sum phase rows. MASTER_PLAN carries contingency/calendar assumptions. Do not add another duplicate schedule or silent phase.
19. **Handoff assumptions:** P2 may assume validated contracts/geometry only.
20. **Next assignment rule:** implementation requires one exact ID and ends at its gate. P0 is already a static audit; it does not imply runtime success.

## Sub-milestones and task order

**P1.1: Typed dynamic-action and admission contract.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: Strict one-action parser; new runner fake-only; model done cannot bypass verifier; legacy recipes unchanged.

**P1.2: Fresh target, geometry and delayed-inference binding.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: Transforms and source/session/geometry invalidation pass; new frame cannot silently rebind stale coordinates.

## Reusable Astra handoff prompt
Execute only <ID from P1.1, P1.2> after explicit owner assignment. Read this phase, ../EXECUTION_PROTOCOL.md, the exact ../ROADMAP.md row and referenced ../CONTRACTS.md IDs. Confirm current root/branch/HEAD/status and inspect computer_action.py, computer_control.py, observations.py, runtime.py, tasks.py, computer_windows.py; focused tests. Preserve dirty/untracked/concurrent hunks and all historical evidence. Deliver the specified implementation through existing Runtime/authority; prohibit Native input, real model calls, parallel capture. Test deterministic boundaries first; native/provider scope requires its own passed prerequisites and permission. Never weaken a guard or relabel simulated results as native. Record exact changes, commands/counts/tier, uncertainty and hashes. Update STATUS.md, that ROADMAP row and acceptance evidence. Stop at the exit gate; do not start another milestone or repeat the full audit.
