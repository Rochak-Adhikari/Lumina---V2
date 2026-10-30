# Phase 05 — Verification, recovery and policy

1. **Objective:** Keep dynamic control honest under interruption, failures and uncertain effects.
2. **Why necessary:** current recipe/owned-window evidence cannot establish this phase's broader guarantee. P0 removes source/document uncertainty; subsequent phases add only unmet requirements.
3. **Prerequisites:** exact mandatory dependencies for P5.1, P5.2 are in [ROADMAP.md](../ROADMAP.md). Overall owner plan approval precedes implementation. P2 native work additionally needs D1 and named target authorization; P3.2 needs D2 and transmission/local-trial permission.
4. **Capabilities added/completed:** P5.1 fault/retry/settlement; P5.2 exact risk approvals, privacy and restart.
5. **Reuse:** Cancellation/leases/unknown inventory, task statuses and same client identity.
6. **Out of scope:** New recovery journal, automatic adoption, production R3 activation.
7. **Expected source files:** control_authority.py, computer_control.py, computer_use.py, runtime.py, server.py, providers/privacy.py and current approval UI. Paths without a directory are under lumina/ unless web/tests are specified. Inspect before editing; no wholesale replacement.
8. **Justified proposed modules:** None; reuse existing state and stores. Names are proposed, never claims of present implementation.
9. **Public function contracts:** C14,C22–C30 in [CONTRACTS.md](../CONTRACTS.md); existing API compatibility is mandatory.
10. **State/invariants:** TaskManager status remains authoritative; progress phase may describe observing/planning/admitting/executing/verifying. Source/session/target/geometry/generation cannot silently change. Stop invalidates future admissions, not already accepted OS effects. No success from a model/API return alone.
11. **Tests:** All acceptance fault rows, two clients, replay/expiry, late inspector after generation change, synthetic private canaries, failed cleanup, isolated restart. Unit/component/deterministic integration run before native/model tiers. Include relevant legacy goal/action/authority/observation regressions; do not rerun unrelated suites or unreviewed native tests.
12. **Acceptance:** No unknown effect becomes success or replay through cleanup; no late result revives state; both control approval layers revoked; sharing independent.
13. **Evidence artifacts:** assigned milestone's patch/changed-file list, initial/final Git/hash checkpoint, commands and pass/fail/error/skip counts, safe failure records, native versus simulated versus provider labels, and acceptance-row evidence links. No screenshots/private input retained by default; synthetic opt-in evidence only.
14. **Resource/compatibility/security/regression risks:** Semantic risk misclassification/auth limitations; D3 remains a separate material gate.
15. **Dependencies:** sole register rows P5.1, P5.2; no unlisted optional enhancement may become an implicit prerequisite. No concurrent shared-file editing.
16. **Phase exit:** every assigned row's explicit gate satisfied with its required tier; no escalation of supported scope beyond that evidence.
17. **Pause conditions:** unexplained safety failure, missing target/model authorization, source drift affecting reviewed code, new security/licensing/model feasibility change, or uncertainty requiring private data. Stop affected work, preserve evidence, continue unrelated permitted work only when dependencies allow. Routine implementation defects stay in the row.
18. **Effort/confidence:** per-row ROADMAP estimates are authoritative; sum phase rows. MASTER_PLAN carries contingency/calendar assumptions. Do not add another duplicate schedule or silent phase.
19. **Handoff assumptions:** P6 may assume tested ordinary scope/failure policy only.
20. **Next assignment rule:** implementation requires one exact ID and ends at its gate. P0 is already a static audit; it does not imply runtime success.

## Sub-milestones and task order

**P5.1: Fault, retry and cancellation settlement.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: All matrix faults classify no-effect versus unknown; no mutation replay on lost reply; late work retained until actual settlement.

**P5.2: Permissions, privacy and restart gate.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: Risk escalation/approvals exact; R3 production disabled; restart disarmed; logs redact synthetic sensitive canaries; sharing independent.

## Reusable Astra handoff prompt
Execute only <ID from P5.1, P5.2> after explicit owner assignment. Read this phase, ../EXECUTION_PROTOCOL.md, the exact ../ROADMAP.md row and referenced ../CONTRACTS.md IDs. Confirm current root/branch/HEAD/status and inspect control_authority.py, computer_control.py, computer_use.py, runtime.py, server.py, providers/privacy.py and current approval UI. Preserve dirty/untracked/concurrent hunks and all historical evidence. Deliver the specified implementation through existing Runtime/authority; prohibit New recovery journal, automatic adoption, production R3 activation. Test deterministic boundaries first; native/provider scope requires its own passed prerequisites and permission. Never weaken a guard or relabel simulated results as native. Record exact changes, commands/counts/tier, uncertainty and hashes. Update STATUS.md, that ROADMAP row and acceptance evidence. Stop at the exit gate; do not start another milestone or repeat the full audit.
