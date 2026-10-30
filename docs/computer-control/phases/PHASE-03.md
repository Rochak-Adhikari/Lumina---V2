# Phase 03 — Replaceable model connector

1. **Objective:** Qualify an image-to-action proposer under measured cost/privacy limits.
2. **Why necessary:** current recipe/owned-window evidence cannot establish this phase's broader guarantee. P0 removes source/document uncertainty; subsequent phases add only unmet requirements.
3. **Prerequisites:** exact mandatory dependencies for P3.1, P3.2 are in [ROADMAP.md](../ROADMAP.md). Overall owner plan approval precedes implementation. P2 native work additionally needs D1 and named target authorization; P3.2 needs D2 and transmission/local-trial permission.
4. **Capabilities added/completed:** P3.1 protocol/mock transport; P3.2 zero-cost candidate qualification and real native model trial.
5. **Reuse:** Existing SDK and privacy transport where compatible; shared schema.
6. **Out of scope:** Paid fallback, credential reads in reports, unapproved large local runtime install.
7. **Expected source files:** providers/gemini.py, providers/privacy.py, proposed computer_use_model.py; mocked provider tests. Paths without a directory are under lumina/ unless web/tests are specified. Inspect before editing; no wholesale replacement.
8. **Justified proposed modules:** No additional module unless a selected transport needs one small adapter. Names are proposed, never claims of present implementation.
9. **Public function contracts:** C09–C13 in [CONTRACTS.md](../CONTRACTS.md); existing API compatibility is mandatory.
10. **State/invariants:** TaskManager status remains authoritative; progress phase may describe observing/planning/admitting/executing/verifying. Source/session/target/geometry/generation cannot silently change. Stop invalidates future admissions, not already accepted OS effects. No success from a model/API return alone.
11. **Tests:** 20 labeled synthetic screens with two layouts, held-out target labels, malformed/ambiguity/injection/timeout/rate-limit tests; separate native stage. Unit/component/deterministic integration run before native/model tiers. Include relevant legacy goal/action/authority/observation regressions; do not rerun unrelated suites or unreviewed native tests.
12. **Acceptance:** Model/version/entitlement/privacy/accuracy/latency recorded; no mocked result passes live model gate; D2 resolved.
13. **Evidence artifacts:** assigned milestone's patch/changed-file list, initial/final Git/hash checkpoint, commands and pass/fail/error/skip counts, safe failure records, native versus simulated versus provider labels, and acceptance-row evidence links. No screenshots/private input retained by default; synthetic opt-in evidence only.
14. **Resource/compatibility/security/regression risks:** Free quotas, RAM and inference delay may make action grounding unusable.
15. **Dependencies:** sole register rows P3.1, P3.2; no unlisted optional enhancement may become an implicit prerequisite. No concurrent shared-file editing.
16. **Phase exit:** every assigned row's explicit gate satisfied with its required tier; no escalation of supported scope beyond that evidence.
17. **Pause conditions:** unexplained safety failure, missing target/model authorization, source drift affecting reviewed code, new security/licensing/model feasibility change, or uncertainty requiring private data. Stop affected work, preserve evidence, continue unrelated permitted work only when dependencies allow. Routine implementation defects stay in the row.
18. **Effort/confidence:** per-row ROADMAP estimates are authoritative; sum phase rows. MASTER_PLAN carries contingency/calendar assumptions. Do not add another duplicate schedule or silent phase.
19. **Handoff assumptions:** P4 may assume one qualified proposer, not human-level understanding.
20. **Next assignment rule:** implementation requires one exact ID and ends at its gate. P0 is already a static audit; it does not imply runtime success.

## Sub-milestones and task order

**P3.1: Replaceable image-action provider and fake transport.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: One provider-neutral schema; images consent-gated; malformed/code output and late replies cannot reach adapter.

**P3.2: Zero-cost candidate and native model qualification.** Inspect relevant contracts → smallest compatible implementation → deterministic tests → authorized native/provider tier when applicable → evidence and exit check. Gate: D2 resolved; actual selected model ID/quota/privacy and held-out screen/native scores recorded; no mock substituted.

## Reusable Astra handoff prompt
Execute only <ID from P3.1, P3.2> after explicit owner assignment. Read this phase, ../EXECUTION_PROTOCOL.md, the exact ../ROADMAP.md row and referenced ../CONTRACTS.md IDs. Confirm current root/branch/HEAD/status and inspect providers/gemini.py, providers/privacy.py, proposed computer_use_model.py; mocked provider tests. Preserve dirty/untracked/concurrent hunks and all historical evidence. Deliver the specified implementation through existing Runtime/authority; prohibit Paid fallback, credential reads in reports, unapproved large local runtime install. Test deterministic boundaries first; native/provider scope requires its own passed prerequisites and permission. Never weaken a guard or relabel simulated results as native. Record exact changes, commands/counts/tier, uncertainty and hashes. Update STATUS.md, that ROADMAP row and acceptance evidence. Stop at the exit gate; do not start another milestone or repeat the full audit.
