# Phase 02 — Native Windows substrate

1. **Objective:** Implement bounded native input on explicitly authorized disposable targets.
2. **Why necessary:** current recipe/owned-window evidence cannot establish this phase's broader guarantee. P0 removes source/document uncertainty; subsequent phases add only unmet requirements.
3. **Prerequisites:** exact mandatory dependencies for P2.1, P2.2, P2.3 are in [ROADMAP.md](../ROADMAP.md). Overall owner plan approval precedes implementation. P2 native work additionally needs D1 and named target authorization; P3.2 needs D2 and transmission/local-trial permission.
4. **Capabilities added/completed:** P2.1 no-effect facade; P2.2 focus/pointer/key/text/chord/scroll; P2.3 bounded drag and display matrix.
5. **Reuse:** Same authority/controller, owned native fixture, shared capture and UIA inspection.
6. **Out of scope:** Arbitrary shell/Run input, protected/elevated surfaces, production R3, general Toggle.
7. **Expected source files:** control_authority.py, computer_control.py, computer_action.py, computer_windows.py, owned_windows.py fixture; proposed test_windows_input.py. Paths without a directory are under lumina/ unless web/tests are specified. Inspect before editing; no wholesale replacement.
8. **Justified proposed modules:** windows_input.py explicitly registered adapter. Names are proposed, never claims of present implementation.
9. **Public function contracts:** C05–C08,C14–C22 in [CONTRACTS.md](../CONTRACTS.md); existing API compatibility is mandatory.
10. **State/invariants:** TaskManager status remains authoritative; progress phase may describe observing/planning/admitting/executing/verifying. Source/session/target/geometry/generation cannot silently change. Stop invalidates future admissions, not already accepted OS effects. No success from a model/API return alone.
11. **Tests:** Fake stop/admission races then real authorized primitives, partial SendInput, physical modifiers, focus drift, release failures, negative/mixed-DPI geometry. Unit/component/deterministic integration run before native/model tiers. Include relevant legacy goal/action/authority/observation regressions; do not rerun unrelated suites or unreviewed native tests.
12. **Acceptance:** Native readback/postframes verify each primitive; no admission after Stop; held-input uncertainty blocks rearm; D1 accepted before native expansion.
13. **Evidence artifacts:** assigned milestone's patch/changed-file list, initial/final Git/hash checkpoint, commands and pass/fail/error/skip counts, safe failure records, native versus simulated versus provider labels, and acceptance-row evidence links. No screenshots/private input retained by default; synthetic opt-in evidence only.
14. **Resource/compatibility/security/regression risks:** Global focus TOCTOU, blocking native calls, key-release failure; no atomic HWND targeting promise.
15. **Dependencies:** sole register rows P2.1, P2.2, P2.3; no unlisted optional enhancement may become an implicit prerequisite. No concurrent shared-file editing.
16. **Phase exit:** every assigned row's explicit gate satisfied with its required tier; no escalation of supported scope beyond that evidence.
17. **Pause conditions:** unexplained safety failure, missing target/model authorization, source drift affecting reviewed code, new security/licensing/model feasibility change, or uncertainty requiring private data. Stop affected work, preserve evidence, continue unrelated permitted work only when dependencies allow. Routine implementation defects stay in the row.
18. **Effort/confidence:** per-row ROADMAP estimates are authoritative; sum phase rows. MASTER_PLAN carries contingency/calendar assumptions. Do not add another duplicate schedule or silent phase.
19. **Handoff assumptions:** P3/P4 may assume only primitives and display configurations actually native-tested.
20. **Next assignment rule:** implementation requires one exact ID and ends at its gate. P0 is already a static audit; it does not imply runtime success.

## Sub-milestones and task order

**P2.1: Native executor facade and no-effect gate.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: Explicit adapter admission only; race fakes prove no admission after stop; no SendInput activated.

**P2.2: Owned native focus, pointer, keys and cleanup.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: D1 approved; authorized owned fixture verifies focus/move/click/type/chord/scroll and partial-input cleanup; uncertainty retained.

**P2.3: Drag, display transitions and measured primitive gate.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: Bounded drag release, display/DPI invalidation, fresh captured postconditions; hardware gaps explicitly block broad-display claim.

## Reusable Astra handoff prompt
Execute only <ID from P2.1, P2.2, P2.3> after explicit owner assignment. Read this phase, ../EXECUTION_PROTOCOL.md, the exact ../ROADMAP.md row and referenced ../CONTRACTS.md IDs. Confirm current root/branch/HEAD/status and inspect control_authority.py, computer_control.py, computer_action.py, computer_windows.py, owned_windows.py fixture; proposed test_windows_input.py. Preserve dirty/untracked/concurrent hunks and all historical evidence. Deliver the specified implementation through existing Runtime/authority; prohibit Arbitrary shell/Run input, protected/elevated surfaces, production R3, general Toggle. Test deterministic boundaries first; native/provider scope requires its own passed prerequisites and permission. Never weaken a guard or relabel simulated results as native. Record exact changes, commands/counts/tier, uncertainty and hashes. Update STATUS.md, that ROADMAP row and acceptance evidence. Stop at the exit gate; do not start another milestone or repeat the full audit.
