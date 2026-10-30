# Phase 06 — Product and real-app integration

1. **Objective:** Verify actual dashboard workflows and hardware feasibility.
2. **Why necessary:** current recipe/owned-window evidence cannot establish this phase's broader guarantee. P0 removes source/document uncertainty; subsequent phases add only unmet requirements.
3. **Prerequisites:** exact mandatory dependencies for P6.1, P6.2 are in [ROADMAP.md](../ROADMAP.md). Overall owner plan approval precedes implementation. P2 native work additionally needs D1 and named target authorization; P3.2 needs D2 and transmission/local-trial permission.
4. **Capabilities added/completed:** P6.1 ordinary apps and full product UI; P6.2 resource/packaging gate.
5. **Reuse:** Existing frontend, APIs, task events, same native adapter.
6. **Out of scope:** Entire UI redesign, personal profiles/data, real sends/calls, installer experiments.
7. **Expected source files:** server.py, runtime.py, tools.py, web/controls.js, web/goals.js, web/control-policy.js; current package scripts/manifests only if justified. Paths without a directory are under lumina/ unless web/tests are specified. Inspect before editing; no wholesale replacement.
8. **Justified proposed modules:** None required. Names are proposed, never claims of present implementation.
9. **Public function contracts:** C23–C30 in [CONTRACTS.md](../CONTRACTS.md); existing API compatibility is mandatory.
10. **State/invariants:** TaskManager status remains authoritative; progress phase may describe observing/planning/admitting/executing/verifying. Source/session/target/geometry/generation cannot silently change. Stop invalidates future admissions, not already accepted OS effects. No success from a model/API return alone.
11. **Tests:** Notepad/Calculator, dedicated browser profile and UIA-poor fixture; cross-app synthetic text; 60-minute session; clean-package validation without installs. Unit/component/deterministic integration run before native/model tiers. Include relevant legacy goal/action/authority/observation regressions; do not rerun unrelated suites or unreviewed native tests.
12. **Acceptance:** At least three ordinary apps including visual fallback; dashboard identity/heartbeat works; laptop resource/latency limits measured and frozen.
13. **Evidence artifacts:** assigned milestone's patch/changed-file list, initial/final Git/hash checkpoint, commands and pass/fail/error/skip counts, safe failure records, native versus simulated versus provider labels, and acceptance-row evidence links. No screenshots/private input retained by default; synthetic opt-in evidence only.
14. **Resource/compatibility/security/regression risks:** Quota availability, CPU/helper overhead, untested hardware, package prerequisites.
15. **Dependencies:** sole register rows P6.1, P6.2; no unlisted optional enhancement may become an implicit prerequisite. No concurrent shared-file editing.
16. **Phase exit:** every assigned row's explicit gate satisfied with its required tier; no escalation of supported scope beyond that evidence.
17. **Pause conditions:** unexplained safety failure, missing target/model authorization, source drift affecting reviewed code, new security/licensing/model feasibility change, or uncertainty requiring private data. Stop affected work, preserve evidence, continue unrelated permitted work only when dependencies allow. Routine implementation defects stay in the row.
18. **Effort/confidence:** per-row ROADMAP estimates are authoritative; sum phase rows. MASTER_PLAN carries contingency/calendar assumptions. Do not add another duplicate schedule or silent phase.
19. **Handoff assumptions:** P7 may assume only the declared measured application/platform envelope.
20. **Next assignment rule:** implementation requires one exact ID and ends at its gate. P0 is already a static audit; it does not imply runtime success.

## Sub-milestones and task order

**P6.1: Full product UI and ordinary-app workflows.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: Authorized apps/profiles exercise actual dashboard→Runtime→adapter; at least three ordinary apps incl UIA-poor and cross-app synthetic task.

**P6.2: Laptop/PC resource and packaging gate.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: 60-minute bounded session + per-stage metrics; agreed numeric resource limits frozen; clean-package check without silent install.

## Reusable Astra handoff prompt
Execute only <ID from P6.1, P6.2> after explicit owner assignment. Read this phase, ../EXECUTION_PROTOCOL.md, the exact ../ROADMAP.md row and referenced ../CONTRACTS.md IDs. Confirm current root/branch/HEAD/status and inspect server.py, runtime.py, tools.py, web/controls.js, web/goals.js, web/control-policy.js; current package scripts/manifests only if justified. Preserve dirty/untracked/concurrent hunks and all historical evidence. Deliver the specified implementation through existing Runtime/authority; prohibit Entire UI redesign, personal profiles/data, real sends/calls, installer experiments. Test deterministic boundaries first; native/provider scope requires its own passed prerequisites and permission. Never weaken a guard or relabel simulated results as native. Record exact changes, commands/counts/tier, uncertainty and hashes. Update STATUS.md, that ROADMAP row and acceptance evidence. Stop at the exit gate; do not start another milestone or repeat the full audit.
